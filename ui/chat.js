/**
 * Chat state, message rendering, and submission flow.
 */

import { sendChatQuery, submitFeedbackAPI, submitSuggestionAPI } from "./api.js";
import { currentToken, logout } from "./auth.js";
import { renderUserMessage, renderAssistantCard, renderTypingIndicator, renderErrorCard } from "./render.js";
import { openModal } from "./dialogs.js";

const STORAGE_KEY = "rit_chat_history_v3";
const MAX_STORED_MESSAGES = 30;

let messages = []; // Array of { role: 'user'|'assistant', text, mode, sources, query }
let isPending = false;
let onQuotaUpdateCallback = null;

export function initChat(containerEl, welcomeCardEl, onQuotaUpdate) {
  onQuotaUpdateCallback = onQuotaUpdate;
  loadStoredHistory();
  renderAllMessages(containerEl, welcomeCardEl);
}

function loadStoredHistory() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      messages = JSON.parse(raw);
    }
  } catch {
    messages = [];
  }
}

function saveHistory() {
  try {
    const trimmed = messages.slice(-MAX_STORED_MESSAGES);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch (e) {
    console.warn("Could not save chat history to sessionStorage:", e);
  }
}

export function clearHistory(containerEl, welcomeCardEl) {
  messages = [];
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {}
  renderAllMessages(containerEl, welcomeCardEl);
}

export function hasMessages() {
  return messages.length > 0;
}

export function renderAllMessages(containerEl, welcomeCardEl) {
  containerEl.replaceChildren();

  if (messages.length === 0) {
    if (welcomeCardEl) welcomeCardEl.style.display = "block";
    return;
  }

  if (welcomeCardEl) welcomeCardEl.style.display = "none";

  for (const msg of messages) {
    if (msg.role === "user") {
      containerEl.appendChild(renderUserMessage(msg.text));
    } else {
      const card = renderAssistantCard({
        query: msg.query || "",
        answer: msg.text,
        mode: msg.mode,
        sources: msg.sources || []
      }, {
        onThumb: handleThumbFeedback,
        onSendToIT: handleSendUnansweredToIT
      });
      containerEl.appendChild(card);
    }
  }
  scrollToBottom(containerEl);
}

function scrollToBottom(containerEl) {
  setTimeout(() => {
    containerEl.scrollTop = containerEl.scrollHeight;
  }, 30);
}

async function handleThumbFeedback(rating, comment, data) {
  const token = currentToken();
  const payload = {
    kind: "answer",
    rating: rating,
    text: comment || null,
    query: data.query,
    answer: data.answer,
    mode: data.mode,
    sources: data.sources
  };
  try {
    await submitFeedbackAPI(payload, token);
  } catch (e) {
    console.warn("Feedback submission error:", e);
  }
}

async function handleSendUnansweredToIT(query) {
  const token = currentToken();
  const payload = {
    question: query,
    details: "Unanswered query alert from chat UI",
    kind: "unanswered"
  };
  try {
    await submitSuggestionAPI(payload, token);
    return true;
  } catch (e) {
    console.warn("Send to IT error:", e);
    return false;
  }
}

export async function askQuestion(query, containerEl, welcomeCardEl, onPendingChange) {
  const cleanQuery = query ? query.trim() : "";
  if (!cleanQuery || isPending) return;

  isPending = true;
  if (onPendingChange) onPendingChange(true);

  // 1. Add User Message
  messages.push({ role: "user", text: cleanQuery });
  saveHistory();
  if (welcomeCardEl) welcomeCardEl.style.display = "none";
  containerEl.appendChild(renderUserMessage(cleanQuery));
  scrollToBottom(containerEl);

  // 2. Add Typing Indicator
  const typingEl = renderTypingIndicator();
  containerEl.appendChild(typingEl);
  scrollToBottom(containerEl);

  try {
    const token = currentToken();
    const data = await sendChatQuery(cleanQuery, token);

    // Remove typing indicator
    typingEl.remove();

    // Add Assistant Message
    messages.push({
      role: "assistant",
      text: data.answer,
      mode: data.mode,
      sources: data.sources || [],
      query: cleanQuery
    });
    saveHistory();

    const assistantCard = renderAssistantCard({
      query: cleanQuery,
      answer: data.answer,
      mode: data.mode,
      sources: data.sources || []
    }, {
      onThumb: handleThumbFeedback,
      onSendToIT: handleSendUnansweredToIT
    });
    containerEl.appendChild(assistantCard);
    scrollToBottom(containerEl);

    // Update remaining quota
    if (onQuotaUpdateCallback) {
      onQuotaUpdateCallback(data.remaining);
    }
  } catch (err) {
    typingEl.remove();

    if (err.status === 429) {
      // Show Limit Reached Dialog
      if (onQuotaUpdateCallback) onQuotaUpdateCallback(0);
      openModal("limit-dialog");
    } else if (err.status === 401) {
      logout();
      if (onQuotaUpdateCallback) onQuotaUpdateCallback(0);
      const errEl = renderErrorCard("Your login session has expired. You have been switched back to guest access.");
      containerEl.appendChild(errEl);
    } else if (err.status === 422) {
      const errEl = renderErrorCard(err.message || "Please enter a valid question (up to 500 characters).");
      containerEl.appendChild(errEl);
    } else {
      // 5xx or network timeout
      const errEl = renderErrorCard(err.message || "Something went wrong. Please try again in a moment.", () => {
        errEl.remove();
        askQuestion(cleanQuery, containerEl, welcomeCardEl, onPendingChange);
      });
      containerEl.appendChild(errEl);
    }
    scrollToBottom(containerEl);
  } finally {
    isPending = false;
    if (onPendingChange) onPendingChange(false);
  }
}
