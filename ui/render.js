/**
 * Safe DOM rendering utilities for RIT Assistant v3.
 * Strictly avoids innerHTML for dynamic content to ensure CSP compliance and XSS immunity.
 */

export function createEl(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [key, val] of Object.entries(attrs)) {
    if (key.startsWith("on") && typeof val === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), val);
    } else if (key === "className") {
      el.className = val;
    } else if (key === "dataset" && typeof val === "object") {
      for (const [dKey, dVal] of Object.entries(val)) {
        el.dataset[dKey] = dVal;
      }
    } else if (val !== null && val !== undefined) {
      el.setAttribute(key, String(val));
    }
  }

  for (const child of children) {
    if (typeof child === "string" || typeof child === "number") {
      el.appendChild(document.createTextNode(String(child)));
    } else if (child instanceof Node) {
      el.appendChild(child);
    }
  }
  return el;
}

/**
 * Parses text and auto-links valid http/https URLs using safe DOM text nodes and <a> elements.
 */
export function appendTextWithLinks(container, text) {
  if (!text) return;
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  let lastIndex = 0;
  let match;

  while ((match = urlRegex.exec(text)) !== null) {
    const plainText = text.substring(lastIndex, match.index);
    if (plainText) {
      container.appendChild(document.createTextNode(plainText));
    }

    const url = match[0];
    // Strip trailing punctuation like '.', ')', ','
    let cleanUrl = url;
    let trailing = "";
    while (cleanUrl.length > 0 && [".", ",", ")", ";"].includes(cleanUrl.slice(-1))) {
      trailing = cleanUrl.slice(-1) + trailing;
      cleanUrl = cleanUrl.slice(0, -1);
    }

    if (cleanUrl.startsWith("http://") || cleanUrl.startsWith("https://")) {
      const link = createEl("a", {
        href: cleanUrl,
        target: "_blank",
        rel: "noopener noreferrer"
      }, [cleanUrl]);
      container.appendChild(link);
    } else {
      container.appendChild(document.createTextNode(cleanUrl));
    }

    if (trailing) {
      container.appendChild(document.createTextNode(trailing));
    }
    lastIndex = urlRegex.lastIndex;
  }

  const remainder = text.substring(lastIndex);
  if (remainder) {
    container.appendChild(document.createTextNode(remainder));
  }
}

/**
 * Format a full URL into a clean hostname + path snippet for display.
 */
export function formatSourceSnippet(url) {
  try {
    const u = new URL(url);
    const pathParts = u.pathname.split("/").filter(Boolean);
    const file = pathParts.length > 0 ? pathParts[pathParts.length - 1] : "";
    if (file) {
      return `${u.hostname} / ${file.length > 25 ? file.slice(0, 22) + "..." : file}`;
    }
    return u.hostname;
  } catch {
    return url.length > 30 ? url.slice(0, 27) + "..." : url;
  }
}

/**
 * Renders a user message bubble.
 */
export function renderUserMessage(text) {
  return createEl("div", { className: "msg-user" }, [text]);
}

/**
 * Renders an assistant answer card.
 */
export function renderAssistantCard(data, handlers = {}) {
  const { query, answer, mode = "doc", sources = [] } = data;
  const { onCopy, onThumb, onSendToIT } = handlers;

  const card = createEl("div", { className: "msg-assistant-card" });

  // 1. Header with Mode Badge
  let badgeLabel = "From RIT records";
  let badgeClass = "mode-structured";

  if (mode === "structured") {
    badgeLabel = "From RIT records";
    badgeClass = "mode-structured";
  } else if (mode === "semantic" || mode === "llm") {
    badgeLabel = "From RIT pages";
    badgeClass = "mode-semantic";
  } else if (mode === "link") {
    badgeLabel = "Document";
    badgeClass = "mode-link";
  } else if (mode === "no_answer" || mode === "none") {
    badgeLabel = "Not found";
    badgeClass = "mode-no_answer";
  }

  const badge = createEl("span", {
    className: `mode-badge ${badgeClass}`
  }, [badgeLabel]);

  const headerLine = createEl("div", { className: "card-header-line" }, [badge]);
  card.appendChild(headerLine);

  // 2. Answer Body
  const body = createEl("div", { className: "answer-body" });
  appendTextWithLinks(body, answer);
  card.appendChild(body);

  // 3. Document Mode Prominent Open Button
  if (mode === "link") {
    // Find first URL in sources or body
    let docUrl = (sources && sources.length > 0) ? sources[0] : "";
    if (!docUrl) {
      const match = /(https?:\/\/[^\s]+)/.exec(answer);
      if (match) docUrl = match[0];
    }
    if (docUrl && (docUrl.startsWith("http://") || docUrl.startsWith("https://"))) {
      const openBtn = createEl("a", {
        href: docUrl,
        target: "_blank",
        rel: "noopener noreferrer",
        className: "open-doc-btn"
      }, ["📄 Open Document"]);
      card.appendChild(openBtn);
    }
  }

  // 4. Sources Section
  if (sources && sources.length > 0) {
    const sourcesSec = createEl("div", { className: "sources-section" });
    const lbl = createEl("span", { className: "sources-label" }, ["Sources:"]);
    const chipsContainer = createEl("div", { className: "sources-chips-container" });

    for (const src of sources) {
      const isHttp = src.startsWith("http://") || src.startsWith("https://");
      const chipAttrs = {
        className: "source-chip",
        title: src
      };
      if (isHttp) {
        chipAttrs.href = src;
        chipAttrs.target = "_blank";
        chipAttrs.rel = "noopener noreferrer";
      }
      const chip = createEl(isHttp ? "a" : "span", chipAttrs, [formatSourceSnippet(src)]);
      chipsContainer.appendChild(chip);
    }
    sourcesSec.appendChild(lbl);
    sourcesSec.appendChild(chipsContainer);
    card.appendChild(sourcesSec);
  }

  // 5. Actions Line (Copy, Thumbs, or Send to IT)
  const actionsLine = createEl("div", { className: "card-actions-line" });
  const buttonsGroup = createEl("div", { className: "action-buttons-group" });

  // Copy Button
  const copyBtn = createEl("button", {
    type: "button",
    className: "action-mini-btn",
    title: "Copy answer to clipboard",
    "aria-label": "Copy answer to clipboard",
    onClick: async () => {
      try {
        await navigator.clipboard.writeText(answer);
        copyBtn.textContent = "✓ Copied";
        setTimeout(() => { copyBtn.textContent = "Copy"; }, 2000);
      } catch {
        if (onCopy) onCopy(answer);
      }
    }
  }, ["Copy"]);
  buttonsGroup.appendChild(copyBtn);

  // Thumbs Up
  let thumbsGiven = false;
  const thumbUpBtn = createEl("button", {
    type: "button",
    className: "action-mini-btn",
    title: "Helpful",
    "aria-label": "Helpful answer",
    onClick: () => {
      if (thumbsGiven) return;
      thumbsGiven = true;
      thumbUpBtn.setAttribute("aria-pressed", "true");
      thumbDownBtn.style.display = "none";
      if (onThumb) onThumb(5, null, data);
    }
  }, ["👍"]);

  // Thumbs Down
  const thumbDownBtn = createEl("button", {
    type: "button",
    className: "action-mini-btn",
    title: "Not helpful",
    "aria-label": "Not helpful answer",
    onClick: () => {
      if (thumbsGiven) return;
      thumbsGiven = true;
      thumbDownBtn.setAttribute("aria-pressed", "true");
      thumbUpBtn.style.display = "none";

      // Show small optional comment box
      const commentBox = createEl("div", { className: "feedback-comment-box" });
      const commentInput = createEl("input", {
        type: "text",
        className: "feedback-comment-input",
        placeholder: "Optional: What was wrong or missing? (Enter to submit)",
        maxLength: "300"
      });
      const submitComment = () => {
        const comment = commentInput.value.trim();
        if (onThumb) onThumb(1, comment || null, data);
        commentBox.replaceWith(createEl("span", {
          className: "sources-label"
        }, ["Feedback submitted. Thank you!"]));
      };
      commentInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          submitComment();
        }
      });
      commentBox.appendChild(commentInput);
      card.appendChild(commentBox);
      commentInput.focus();
    }
  }, ["👎"]);

  buttonsGroup.appendChild(thumbUpBtn);
  buttonsGroup.appendChild(thumbDownBtn);
  actionsLine.appendChild(buttonsGroup);

  // If no_answer, add "Send this question to the IT team" button
  if (mode === "no_answer" || mode === "none") {
    let sentToIT = false;
    const sendITBtn = createEl("button", {
      type: "button",
      className: "btn-send-to-it",
      onClick: async () => {
        if (sentToIT) return;
        sentToIT = true;
        sendITBtn.disabled = true;
        sendITBtn.textContent = "Sending...";
        if (onSendToIT) {
          const success = await onSendToIT(query);
          sendITBtn.textContent = success ? "✓ Sent to IT Team" : "Failed to send";
        }
      }
    }, ["Send question to IT Team"]);
    actionsLine.appendChild(sendITBtn);
  }

  card.appendChild(actionsLine);
  return card;
}

/**
 * Renders the typing indicator.
 */
export function renderTypingIndicator() {
  const container = createEl("div", {
    className: "typing-indicator",
    role: "status",
    "aria-label": "Assistant is thinking"
  }, [
    createEl("span", { className: "dot" }),
    createEl("span", { className: "dot" }),
    createEl("span", { className: "dot" }),
    createEl("span", { className: "typing-text-fallback" }, ["Thinking..."])
  ]);
  return container;
}

/**
 * Renders an error banner with a manual retry button.
 */
export function renderErrorCard(message, onRetry) {
  const card = createEl("div", { className: "error-card", role: "alert" });
  const textSpan = createEl("span", {}, [message]);
  card.appendChild(textSpan);

  if (onRetry) {
    const retryBtn = createEl("button", {
      type: "button",
      className: "btn-text",
      onClick: onRetry
    }, ["Retry"]);
    card.appendChild(retryBtn);
  }
  return card;
}
