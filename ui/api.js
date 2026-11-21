/**
 * API client module for RIT Assistant v3.
 * Handles timeouts, network errors, and status mapping.
 */

const REQUEST_TIMEOUT_MS = 30000;

async function requestWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  options.signal = controller.signal;

  try {
    const res = await fetch(url, options);
    clearTimeout(timeoutId);
    return res;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      throw new Error("Request timed out after 30 seconds. Please try again.");
    }
    throw new Error("Network error. Could not connect to the server.");
  }
}

export async function fetchUIConfig() {
  const res = await requestWithTimeout("/ui-config");
  if (!res.ok) throw new Error("Failed to load UI configuration.");
  return res.json();
}

export async function fetchUsage(token = null) {
  const headers = {};
  if (token) {
    headers["X-Institute-Token"] = token;
  }
  const res = await requestWithTimeout("/usage", { headers });
  if (!res.ok) throw new Error("Failed to load quota usage.");
  return res.json();
}

export async function verifyTokenAPI(token) {
  const res = await requestWithTimeout("/auth/me", {
    headers: { "X-Institute-Token": token }
  });
  if (res.status === 401) {
    return { ok: false, error: "Invalid, expired, or untrusted institute token." };
  }
  if (!res.ok) {
    return { ok: false, error: `Verification failed (HTTP ${res.status}).` };
  }
  const data = await res.json();
  return { ok: true, data };
}

export async function sendChatQuery(query, token = null) {
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["X-Institute-Token"] = token;
  }

  const res = await requestWithTimeout("/chat", {
    method: "POST",
    headers,
    body: JSON.stringify({ query })
  });

  if (res.status === 429) {
    const errData = await res.json().catch(() => ({}));
    const err = new Error(errData.detail || "Guest query limit reached.");
    err.status = 429;
    throw err;
  }
  if (res.status === 401) {
    const err = new Error("Your login token has expired or is invalid.");
    err.status = 401;
    throw err;
  }
  if (res.status === 422) {
    const err = new Error("Please type a valid question (up to 500 characters).");
    err.status = 422;
    throw err;
  }
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    const err = new Error(errData.detail || "Server error occurred.");
    err.status = res.status;
    throw err;
  }

  return res.json();
}

export async function submitFeedbackAPI(payload, token = null) {
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["X-Institute-Token"] = token;
  }

  const res = await requestWithTimeout("/feedback", {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });

  if (res.status === 429) {
    throw new Error("Submission rate limit reached (5 per hour). Please try again later.");
  }
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || "Failed to submit feedback.");
  }
  return res.json();
}

export async function submitSuggestionAPI(payload, token = null) {
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["X-Institute-Token"] = token;
  }

  const res = await requestWithTimeout("/suggestions", {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });

  if (res.status === 429) {
    throw new Error("Submission rate limit reached (5 per hour). Please try again later.");
  }
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || "Failed to submit suggestion.");
  }
  return res.json();
}

// --------------------------------------------------------------------------
// Admin APIs
// --------------------------------------------------------------------------
export async function adminFetchSubmissions(adminKey, params = {}) {
  const query = new URLSearchParams();
  if (params.kind) query.set("kind", params.kind);
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  if (params.limit) query.set("limit", params.limit);
  if (params.offset) query.set("offset", params.offset);

  const res = await requestWithTimeout(`/admin/submissions?${query.toString()}`, {
    headers: { "X-Admin-Key": adminKey }
  });
  if (res.status === 401) throw new Error("Invalid admin key.");
  if (res.status === 404) throw new Error("Admin API is not enabled on this server.");
  if (!res.ok) throw new Error("Failed to retrieve submissions.");
  return res.json();
}

export async function adminPatchSubmissionAPI(adminKey, subId, patchData) {
  const res = await requestWithTimeout(`/admin/submissions/${encodeURIComponent(subId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Key": adminKey
    },
    body: JSON.stringify(patchData)
  });
  if (!res.ok) throw new Error("Failed to update submission.");
  return res.json();
}

export async function adminFetchTopQuestions(adminKey) {
  const res = await requestWithTimeout("/admin/top-questions", {
    headers: { "X-Admin-Key": adminKey }
  });
  if (!res.ok) throw new Error("Failed to fetch top questions.");
  return res.json();
}
