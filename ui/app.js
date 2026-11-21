/**
 * Main application entry point for RIT Assistant v3 UI.
 */

import { fetchUIConfig, fetchUsage, submitFeedbackAPI, submitSuggestionAPI } from "./api.js";
import { currentUser, login, logout, currentToken } from "./auth.js";
import { initChat, clearHistory, askQuestion } from "./chat.js";
import { openModal, closeModal, closeAllModals } from "./dialogs.js";
import { createEl } from "./render.js";

// DOM Elements
const chatMessagesEl = document.getElementById("chat-messages");
const welcomeCardEl = document.getElementById("welcome-card");
const queryInputEl = document.getElementById("query-input");
const sendBtnEl = document.getElementById("send-btn");
const charCounterEl = document.getElementById("char-counter");
const quotaPillEl = document.getElementById("quota-pill");
const authBtnEl = document.getElementById("auth-btn");
const themeBtnEl = document.getElementById("theme-btn");
const infoBtnEl = document.getElementById("info-btn");
const clearChatBtnEl = document.getElementById("clear-chat-btn");
const chipTabsContainer = document.getElementById("chip-tabs");
const starterChipsContainer = document.getElementById("starter-chips");

let appConfig = {
  guest_limit: 5,
  max_query_chars: 500,
  institute_name: "Rajarambapu Institute of Technology",
  assistant_name: "RIT Assistant"
};

let remainingQuota = 5;

// --------------------------------------------------------------------------
// Theme Management
// --------------------------------------------------------------------------
function initTheme() {
  const saved = localStorage.getItem("rit_theme");
  const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = saved || (systemPrefersDark ? "dark" : "light");
  applyTheme(initialTheme);

  themeBtnEl.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "light";
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("rit_theme", next);
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeBtnEl.textContent = theme === "dark" ? "☀" : "☾";
  themeBtnEl.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);
}

// --------------------------------------------------------------------------
// Quota & Auth Status
// --------------------------------------------------------------------------
function updateQuotaDisplay(remaining) {
  remainingQuota = remaining;
  const user = currentUser();

  if (user) {
    quotaPillEl.textContent = "Institute member · Unlimited";
    quotaPillEl.setAttribute("data-quota", "unlimited");
    authBtnEl.textContent = `Logout (${user.masked_email})`;
    authBtnEl.setAttribute("aria-label", `Logged in as ${user.masked_email}. Click to logout.`);
    return;
  }

  authBtnEl.textContent = "Institute Login";
  authBtnEl.setAttribute("aria-label", "Log in with institute token for unlimited queries");

  if (remaining === null || remaining === undefined) {
    quotaPillEl.textContent = `${appConfig.guest_limit} free questions left`;
    quotaPillEl.setAttribute("data-quota", "good");
  } else if (remaining <= 0) {
    quotaPillEl.textContent = "0 free questions left";
    quotaPillEl.setAttribute("data-quota", "danger");
  } else if (remaining <= 2) {
    quotaPillEl.textContent = `${remaining} free question${remaining === 1 ? "" : "s"} left`;
    quotaPillEl.setAttribute("data-quota", "warn");
  } else {
    quotaPillEl.textContent = `${remaining} free questions left`;
    quotaPillEl.setAttribute("data-quota", "good");
  }
}

// --------------------------------------------------------------------------
// Starter Chips
// --------------------------------------------------------------------------
const FALLBACK_STARTER_GROUPS = [
  {
    group: "General",
    questions: [
      "What is the intake for Computer Engineering?",
      "Who is the HOD of Civil Engineering?",
      "Where is RIT located?",
      "Where can I find the academic calendar?"
    ]
  }
];

async function loadStarterChips() {
  let groups = FALLBACK_STARTER_GROUPS;
  try {
    const res = await fetch("starter_questions.json");
    if (res.ok) {
      groups = await res.json();
    }
  } catch (e) {
    console.warn("Using fallback starter questions:", e);
  }

  chipTabsContainer.replaceChildren();

  groups.forEach((grp, idx) => {
    const tabBtn = createEl("button", {
      type: "button",
      className: `chip-tab-btn ${idx === 0 ? "active" : ""}`,
      role: "tab",
      "aria-selected": idx === 0 ? "true" : "false",
      onClick: () => {
        document.querySelectorAll(".chip-tab-btn").forEach(b => {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
        });
        tabBtn.classList.add("active");
        tabBtn.setAttribute("aria-selected", "true");
        renderGroupChips(grp.questions);
      }
    }, [grp.group]);
    chipTabsContainer.appendChild(tabBtn);
  });

  if (groups.length > 0) {
    renderGroupChips(groups[0].questions);
  }
}

function renderGroupChips(questions) {
  starterChipsContainer.replaceChildren();
  questions.forEach(q => {
    const chip = createEl("button", {
      type: "button",
      className: "starter-chip",
      onClick: () => {
        askQuestion(q, chatMessagesEl, welcomeCardEl, setPendingState);
      }
    }, [q]);
    starterChipsContainer.appendChild(chip);
  });
}

// --------------------------------------------------------------------------
// Query Input & Actions
// --------------------------------------------------------------------------
function setPendingState(isPending) {
  sendBtnEl.disabled = isPending;
  queryInputEl.disabled = isPending;
  if (!isPending) {
    queryInputEl.focus();
  }
}

function setupInputArea() {
  const updateCountAndHeight = () => {
    const len = queryInputEl.value.length;
    charCounterEl.textContent = `${len}/${appConfig.max_query_chars}`;
    sendBtnEl.disabled = (len === 0);

    queryInputEl.style.height = "auto";
    queryInputEl.style.height = Math.min(queryInputEl.scrollHeight, 140) + "px";
  };

  queryInputEl.addEventListener("input", updateCountAndHeight);

  queryInputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const val = queryInputEl.value.trim();
      if (val) {
        queryInputEl.value = "";
        updateCountAndHeight();
        askQuestion(val, chatMessagesEl, welcomeCardEl, setPendingState);
      }
    }
  });

  sendBtnEl.addEventListener("click", () => {
    const val = queryInputEl.value.trim();
    if (val) {
      queryInputEl.value = "";
      updateCountAndHeight();
      askQuestion(val, chatMessagesEl, welcomeCardEl, setPendingState);
    }
  });

  clearChatBtnEl.addEventListener("click", () => {
    if (confirm("Are you sure you want to clear the chat conversation?")) {
      clearHistory(chatMessagesEl, welcomeCardEl);
      queryInputEl.focus();
    }
  });

  // Global keyboard shortcut: "/" to focus input
  window.addEventListener("keydown", (e) => {
    if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      e.preventDefault();
      queryInputEl.focus();
    }
  });
}

// --------------------------------------------------------------------------
// Dialogs: Login, Limit, Feedback, Info, Privacy
// --------------------------------------------------------------------------
function setupDialogs() {
  // 1. Auth / Login Dialog
  authBtnEl.addEventListener("click", () => {
    if (currentUser()) {
      if (confirm("Do you want to log out of your institute account?")) {
        logout();
        fetchUsage().then(u => updateQuotaDisplay(u.remaining));
      }
    } else {
      openModal("login-dialog", authBtnEl);
    }
  });

  const loginForm = document.getElementById("login-form");
  const loginTokenInput = document.getElementById("login-token-input");
  const loginErrorMsg = document.getElementById("login-error-msg");

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginErrorMsg.style.display = "none";
    loginErrorMsg.textContent = "";

    const tokenVal = loginTokenInput.value.trim();
    if (!tokenVal) return;

    const res = await login(tokenVal);
    if (res.success) {
      loginTokenInput.value = "";
      closeModal("login-dialog");
      updateQuotaDisplay(null);
    } else {
      loginErrorMsg.textContent = res.error;
      loginErrorMsg.style.display = "block";
    }
  });

  // Limit Dialog Login button
  const limitLoginBtn = document.getElementById("limit-login-btn");
  if (limitLoginBtn) {
    limitLoginBtn.addEventListener("click", () => {
      closeModal("limit-dialog");
      openModal("login-dialog");
    });
  }

  // 2. Info Dialog
  infoBtnEl.addEventListener("click", () => openModal("info-dialog", infoBtnEl));
  document.getElementById("how-link").addEventListener("click", () => openModal("info-dialog"));

  // 3. Privacy Dialog
  document.getElementById("privacy-link").addEventListener("click", () => openModal("privacy-dialog"));

  // 4. Feedback & Suggest Dialog
  const feedbackDialog = document.getElementById("feedback-dialog");
  const fbTabBtn = document.getElementById("tab-btn-feedback");
  const sgTabBtn = document.getElementById("tab-btn-suggest");
  const fbTabContent = document.getElementById("tab-content-feedback");
  const sgTabContent = document.getElementById("tab-content-suggest");

  document.getElementById("feedback-link").addEventListener("click", () => {
    openModal("feedback-dialog");
    showFeedbackTab();
  });
  document.getElementById("suggest-link").addEventListener("click", () => {
    openModal("feedback-dialog");
    showSuggestTab();
  });

  function showFeedbackTab() {
    fbTabBtn.classList.add("active");
    sgTabBtn.classList.remove("active");
    fbTabContent.style.display = "flex";
    sgTabContent.style.display = "none";
  }

  function showSuggestTab() {
    sgTabBtn.classList.add("active");
    fbTabBtn.classList.remove("active");
    sgTabContent.style.display = "flex";
    fbTabContent.style.display = "none";
  }

  fbTabBtn.addEventListener("click", showFeedbackTab);
  sgTabBtn.addEventListener("click", showSuggestTab);

  // Rating selection
  let selectedRating = null;
  document.querySelectorAll(".rating-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".rating-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      selectedRating = parseInt(btn.dataset.rating, 10);
    });
  });

  // Submit Feedback Form
  const feedbackForm = document.getElementById("feedback-form");
  const fbStatusMsg = document.getElementById("feedback-status-msg");
  feedbackForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    fbStatusMsg.style.display = "none";

    const payload = {
      kind: "general",
      rating: selectedRating,
      category: document.getElementById("feedback-category").value,
      text: document.getElementById("feedback-text").value.trim(),
      contact_email: document.getElementById("feedback-email").value.trim() || null,
      hp: document.getElementById("fb-hp").value || null
    };

    try {
      await submitFeedbackAPI(payload, currentToken());
      fbStatusMsg.textContent = "Thank you! Your feedback has been submitted.";
      fbStatusMsg.className = "form-help text-success";
      fbStatusMsg.style.display = "block";
      feedbackForm.reset();
      selectedRating = null;
      document.querySelectorAll(".rating-btn").forEach(b => b.classList.remove("active"));
      setTimeout(() => closeModal("feedback-dialog"), 2000);
    } catch (err) {
      fbStatusMsg.textContent = err.message;
      fbStatusMsg.className = "form-help text-danger";
      fbStatusMsg.style.display = "block";
    }
  });

  // Submit Suggestion Form
  const suggestForm = document.getElementById("suggest-form");
  const sgStatusMsg = document.getElementById("suggest-status-msg");
  suggestForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    sgStatusMsg.style.display = "none";

    const payload = {
      question: document.getElementById("suggest-question").value.trim(),
      details: document.getElementById("suggest-details").value.trim() || null,
      category: document.getElementById("suggest-category").value,
      contact_email: document.getElementById("suggest-email").value.trim() || null,
      kind: "suggestion",
      hp: document.getElementById("sg-hp").value || null
    };

    try {
      await submitSuggestionAPI(payload, currentToken());
      sgStatusMsg.textContent = "Thanks! The IT team reviews suggestions. New answers are added only after the data is verified.";
      sgStatusMsg.className = "form-help text-success";
      sgStatusMsg.style.display = "block";
      suggestForm.reset();
      setTimeout(() => closeModal("feedback-dialog"), 2500);
    } catch (err) {
      sgStatusMsg.textContent = err.message;
      sgStatusMsg.className = "form-help text-danger";
      sgStatusMsg.style.display = "block";
    }
  });

  // Close buttons on all modals
  document.querySelectorAll("[data-close-modal]").forEach(btn => {
    btn.addEventListener("click", () => {
      const modalId = btn.getAttribute("data-close-modal");
      closeModal(modalId);
    });
  });

  // Clicking backdrop closes modal
  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        closeModal(overlay.id);
      }
    });
  });
}

// --------------------------------------------------------------------------
// Initialization
// --------------------------------------------------------------------------
async function init() {
  initTheme();
  setupInputArea();
  setupDialogs();

  try {
    appConfig = await fetchUIConfig();
    document.querySelectorAll(".institute-name-text").forEach(el => el.textContent = appConfig.institute_name);
    document.querySelectorAll(".assistant-name-text").forEach(el => el.textContent = appConfig.assistant_name);
    if (appConfig.data_updated) {
      const duEl = document.getElementById("info-data-updated");
      if (duEl) duEl.textContent = appConfig.data_updated;
    }
  } catch (e) {
    console.warn("Could not load /ui-config:", e);
  }

  initChat(chatMessagesEl, welcomeCardEl, updateQuotaDisplay);
  await loadStarterChips();

  try {
    const usage = await fetchUsage(currentToken());
    updateQuotaDisplay(usage.remaining);
  } catch (e) {
    console.warn("Could not fetch usage quota:", e);
    updateQuotaDisplay(5);
  }
}

document.addEventListener("DOMContentLoaded", init);
