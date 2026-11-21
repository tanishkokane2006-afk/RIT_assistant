/**
 * Authentication module for RIT Assistant v3.
 * Manages signed institute tokens in sessionStorage.
 */

import { verifyTokenAPI } from "./api.js";

const TOKEN_KEY = "rit_institute_token";
const USER_KEY = "rit_institute_user";

export async function login(rawToken) {
  const token = rawToken ? rawToken.trim() : "";
  if (!token) {
    return { success: false, error: "Token cannot be empty." };
  }

  const res = await verifyTokenAPI(token);
  if (!res.ok) {
    return { success: false, error: res.error || "Token verification failed." };
  }

  try {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(res.data));
  } catch (e) {
    console.warn("Could not save to sessionStorage:", e);
  }

  return { success: true, user: res.data };
}

export function logout() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  } catch (e) {
    console.warn("Could not clear sessionStorage:", e);
  }
}

export function currentUser() {
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function currentToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function authHeader() {
  const token = currentToken();
  if (!token) return {};
  return { "X-Institute-Token": token };
}
