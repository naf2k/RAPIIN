import { useSyncExternalStore } from "react";

export type Role = "USER" | "SUPERVISOR";

export interface SessionUser {
  user_id: number;
  name: string;
  role: Role;
  email?: string;
}

const TOKEN_KEY = "beresin_token";
const USER_KEY = "beresin_user";

interface SessionState {
  token: string;
  user: SessionUser | null;
}

function loadState(): SessionState {
  try {
    const token = window.localStorage.getItem(TOKEN_KEY) ?? "";
    const raw = window.localStorage.getItem(USER_KEY);
    return { token, user: raw ? (JSON.parse(raw) as SessionUser) : null };
  } catch {
    return { token: "", user: null };
  }
}

let state: SessionState = typeof window === "undefined" ? { token: "", user: null } : loadState();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function persist(next: SessionState) {
  state = next;
  try {
    if (next.token) window.localStorage.setItem(TOKEN_KEY, next.token);
    else window.localStorage.removeItem(TOKEN_KEY);
    if (next.user) window.localStorage.setItem(USER_KEY, JSON.stringify(next.user));
    else window.localStorage.removeItem(USER_KEY);
  } catch {
    // Storage can be unavailable (private mode); the in-memory session still works.
  }
  emit();
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key !== TOKEN_KEY && event.key !== USER_KEY) return;
    state = loadState();
    emit();
  });
}

export function getToken(): string {
  return state.token;
}

export function getUser(): SessionUser | null {
  return state.user;
}

export function setSession(token: string, user: SessionUser) {
  persist({ token, user });
}

export function updateUser(user: SessionUser) {
  persist({ ...state, user });
}

export function clearSession() {
  persist({ token: "", user: null });
}

export function isLoggedIn(): boolean {
  return Boolean(state.token);
}

export function userRole(): Role | null {
  return state.user?.role ?? null;
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): SessionState {
  return state;
}

export function useSessionUser(): SessionUser | null {
  return useSyncExternalStore(subscribeSession, getSnapshot, getSnapshot).user;
}

export function useSessionToken(): string {
  return useSyncExternalStore(subscribeSession, getSnapshot, getSnapshot).token;
}
