/**
 * Admin Dashboard logic for RIT Assistant IT Team.
 * Strictly keeps the admin authentication key in memory only (never in localStorage/sessionStorage).
 * Zero inline styles or innerHTML for strict CSP compliance.
 */

import { adminFetchSubmissions, adminPatchSubmissionAPI, adminFetchTopQuestions } from "./api.js";
import { createEl } from "./render.js";

let adminKey = null;

// DOM Elements
const authGate = document.getElementById("admin-auth-gate");
const authForm = document.getElementById("admin-auth-form");
const keyInput = document.getElementById("admin-key-input");
const authError = document.getElementById("admin-auth-error");
const dashboardContainer = document.getElementById("admin-dashboard-container");
const logoutAdminBtn = document.getElementById("logout-admin-btn");
const themeBtn = document.getElementById("theme-btn");

const metricsRow = document.getElementById("admin-metrics-row");
const topQuestionsContainer = document.getElementById("top-questions-container");
const filterForm = document.getElementById("admin-filter-form");
const filterKind = document.getElementById("filter-kind");
const filterStatus = document.getElementById("filter-status");
const filterQ = document.getElementById("filter-q");
const filterResetBtn = document.getElementById("filter-reset-btn");
const exportCsvBtn = document.getElementById("export-csv-btn");
const tbody = document.getElementById("submissions-tbody");
const emptyMsg = document.getElementById("table-empty-msg");

// Theme setup
const savedTheme = localStorage.getItem("rit_theme") || "light";
document.documentElement.setAttribute("data-theme", savedTheme);
themeBtn.textContent = savedTheme === "dark" ? "☀" : "☾";
themeBtn.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  themeBtn.textContent = next === "dark" ? "☀" : "☾";
  localStorage.setItem("rit_theme", next);
});

// --------------------------------------------------------------------------
// Authentication Flow (In-Memory Only)
// --------------------------------------------------------------------------
authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  authError.classList.add("sr-only");
  const key = keyInput.value.trim();

  if (!key) return;

  try {
    // Probe authentication
    await adminFetchSubmissions(key, { limit: 1 });
    adminKey = key;
    keyInput.value = "";

    // Unlock dashboard
    authGate.classList.add("sr-only");
    dashboardContainer.classList.remove("sr-only");
    logoutAdminBtn.classList.remove("hidden");

    loadDashboard();
  } catch (err) {
    authError.textContent = err.message;
    authError.classList.remove("sr-only");
  }
});

logoutAdminBtn.addEventListener("click", () => {
  adminKey = null;
  dashboardContainer.classList.add("sr-only");
  authGate.classList.remove("sr-only");
  logoutAdminBtn.classList.add("hidden");
});

// --------------------------------------------------------------------------
// Dashboard Data Loading
// --------------------------------------------------------------------------
async function loadDashboard() {
  if (!adminKey) return;
  await Promise.all([
    loadTopQuestions(),
    loadSubmissions()
  ]);
}

async function loadTopQuestions() {
  topQuestionsContainer.replaceChildren();
  try {
    const data = await adminFetchTopQuestions(adminKey);
    const questions = data.top_questions || [];

    if (questions.length === 0) {
      topQuestionsContainer.appendChild(createEl("div", {
        className: "form-help"
      }, ["No unanswered or suggested questions logged yet."]));
      return;
    }

    questions.slice(0, 5).forEach((q) => {
      const row = createEl("div", {
        className: "top-question-item"
      });

      const textWrap = createEl("div", { className: "top-question-text" }, [
        createEl("span", { className: "top-question-title" }, [q.sample_question]),
        createEl("span", { className: "form-help" }, [`Categories: ${q.kinds.join(", ")} | Status: ${q.statuses.join(", ")}`])
      ]);

      const countBadge = createEl("span", {
        className: "quota-pill",
        dataset: { quota: "warn" }
      }, [`${q.count} request${q.count === 1 ? "" : "s"}`]);

      row.appendChild(textWrap);
      row.appendChild(countBadge);
      topQuestionsContainer.appendChild(row);
    });
  } catch (err) {
    topQuestionsContainer.appendChild(createEl("div", {
      className: "form-help text-danger"
    }, [err.message]));
  }
}

async function loadSubmissions() {
  tbody.replaceChildren();
  emptyMsg.classList.add("sr-only");

  const params = {
    kind: filterKind.value || undefined,
    status: filterStatus.value || undefined,
    q: filterQ.value.trim() || undefined,
    limit: 100
  };

  try {
    const data = await adminFetchSubmissions(adminKey, params);
    renderMetrics(data.counts, data.total);

    const items = data.items || [];
    if (items.length === 0) {
      emptyMsg.classList.remove("sr-only");
      return;
    }

    items.forEach(item => {
      const mainRow = createEl("tr");

      // Date
      const dateStr = item.created_at ? item.created_at.slice(0, 10) : "";
      mainRow.appendChild(createEl("td", { className: "nowrap" }, [dateStr]));

      // Kind badge
      const kindBadge = createEl("span", {
        className: "mode-badge mode-structured capitalize"
      }, [item.kind.replace("_", " ")]);
      mainRow.appendChild(createEl("td", {}, [kindBadge]));

      // Status badge
      const statusBadge = createEl("span", {
        className: "quota-pill",
        dataset: { quota: item.status === "done" ? "good" : item.status === "in_review" ? "warn" : "normal" }
      }, [item.status]);
      mainRow.appendChild(createEl("td", {}, [statusBadge]));

      // Summary
      const summaryText = item.query || item.text || item.category || "(No text)";
      const truncated = summaryText.length > 50 ? summaryText.slice(0, 47) + "..." : summaryText;
      mainRow.appendChild(createEl("td", {}, [truncated]));

      // User Type
      mainRow.appendChild(createEl("td", { className: "capitalize" }, [item.user_type]));

      // Expand Button
      let isExpanded = false;
      let detailRow = null;

      const toggleBtn = createEl("button", {
        type: "button",
        className: "action-mini-btn",
        onClick: () => {
          isExpanded = !isExpanded;
          toggleBtn.textContent = isExpanded ? "Hide" : "Details";
          if (isExpanded) {
            detailRow = renderDetailRow(item);
            mainRow.after(detailRow);
          } else if (detailRow) {
            detailRow.remove();
            detailRow = null;
          }
        }
      }, ["Details"]);

      mainRow.appendChild(createEl("td", {}, [toggleBtn]));
      tbody.appendChild(mainRow);
    });
  } catch (err) {
    emptyMsg.textContent = err.message;
    emptyMsg.classList.remove("sr-only");
  }
}

function renderMetrics(counts = {}, total = 0) {
  metricsRow.replaceChildren();

  const byKind = counts.by_kind || {};
  const byStatus = counts.by_status || {};

  const metrics = [
    { label: "Total Submissions", val: total, quota: "unlimited" },
    { label: "Unanswered Alerts", val: byKind["unanswered"] || 0, quota: "danger" },
    { label: "Suggestions", val: byKind["suggestion"] || 0, quota: "warn" },
    { label: "Answer Thumbs", val: byKind["answer_feedback"] || 0, quota: "good" },
    { label: "General Feedback", val: byKind["general_feedback"] || 0, quota: "normal" },
    { label: "Status: New", val: byStatus["new"] || 0, quota: "warn" },
    { label: "Status: Done", val: byStatus["done"] || 0, quota: "good" }
  ];

  metrics.forEach(m => {
    const pill = createEl("span", {
      className: "quota-pill",
      dataset: { quota: m.quota }
    }, [`${m.label}: ${m.val}`]);
    metricsRow.appendChild(pill);
  });
}

function renderDetailRow(item) {
  const tr = createEl("tr", { className: "detail-row" });
  const td = createEl("td", { colspan: "6" });

  const container = createEl("div", { className: "admin-detail-wrap" });

  if (item.query) {
    container.appendChild(createEl("div", {}, [
      createEl("strong", {}, ["Query: "]),
      document.createTextNode(item.query)
    ]));
  }
  if (item.answer) {
    container.appendChild(createEl("div", {}, [
      createEl("strong", {}, ["Assistant Answer: "]),
      document.createTextNode(item.answer)
    ]));
  }
  if (item.text) {
    container.appendChild(createEl("div", {}, [
      createEl("strong", {}, ["Message / Notes: "]),
      document.createTextNode(item.text)
    ]));
  }
  if (item.rating) {
    container.appendChild(createEl("div", {}, [
      createEl("strong", {}, ["Rating: "]),
      document.createTextNode(`${item.rating} / 5 stars`)
    ]));
  }
  if (item.contact_email) {
    container.appendChild(createEl("div", {}, [
      createEl("strong", {}, ["Contact Email: "]),
      document.createTextNode(item.contact_email)
    ]));
  }
  if (item.sources && item.sources.length > 0) {
    container.appendChild(createEl("div", {}, [
      createEl("strong", {}, ["Sources: "]),
      document.createTextNode(item.sources.join(", "))
    ]));
  }

  // Edit Status & Admin Note
  const editLine = createEl("div", { className: "admin-edit-line" });

  const statusSelect = createEl("select", { className: "form-select filter-status-select" });
  ["new", "in_review", "done", "declined"].forEach(st => {
    const opt = createEl("option", { value: st }, [st]);
    if (st === item.status) opt.selected = true;
    statusSelect.appendChild(opt);
  });

  const noteInput = createEl("input", {
    type: "text",
    className: "form-input admin-note-input",
    placeholder: "Add internal admin note…",
    value: item.admin_note || ""
  });

  const saveBtn = createEl("button", {
    type: "button",
    className: "btn-send",
    onClick: async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";
      try {
        await adminPatchSubmissionAPI(adminKey, item.id, {
          status: statusSelect.value,
          admin_note: noteInput.value.trim() || null
        });
        saveBtn.textContent = "✓ Saved";
        setTimeout(() => { saveBtn.textContent = "Save"; saveBtn.disabled = false; }, 1500);
      } catch (e) {
        alert("Failed to update submission: " + e.message);
        saveBtn.textContent = "Save";
        saveBtn.disabled = false;
      }
    }
  }, ["Save"]);

  editLine.appendChild(createEl("label", { className: "form-label" }, ["Status:"]));
  editLine.appendChild(statusSelect);
  editLine.appendChild(noteInput);
  editLine.appendChild(saveBtn);
  container.appendChild(editLine);

  td.appendChild(container);
  tr.appendChild(td);
  return tr;
}

// --------------------------------------------------------------------------
// Filters & Export
// --------------------------------------------------------------------------
filterForm.addEventListener("submit", (e) => {
  e.preventDefault();
  loadSubmissions();
});

filterResetBtn.addEventListener("click", () => {
  filterKind.value = "";
  filterStatus.value = "";
  filterQ.value = "";
  loadSubmissions();
});

exportCsvBtn.addEventListener("click", async () => {
  if (!adminKey) return;
  const kindVal = filterKind.value || "";
  const statusVal = filterStatus.value || "";
  const url = `/admin/export.csv?kind=${encodeURIComponent(kindVal)}&status=${encodeURIComponent(statusVal)}`;

  try {
    const res = await fetch(url, {
      headers: { "X-Admin-Key": adminKey }
    });
    if (!res.ok) throw new Error("Export failed.");
    const blob = await res.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = `rit_submissions_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);
  } catch (err) {
    alert("CSV export failed: " + err.message);
  }
});
