import { clearSession, getToken } from "@/lib/session";

const API_BASE = "/api";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function redirectToLogin() {
  if (!window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
  }
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(API_BASE + path, {
      method,
      headers,
      body: body === undefined || body === null ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Tidak dapat terhubung ke server. Periksa koneksi Anda.", 0);
  }

  if (response.status === 401) {
    if (token) {
      clearSession();
      redirectToLogin();
    }
    throw new ApiError("Sesi berakhir. Silakan masuk kembali.", 401);
  }

  const data: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      data && typeof data === "object" ? (data as { detail?: unknown }).detail : null;
    throw new ApiError(
      typeof detail === "string" ? detail : "Terjadi kesalahan. Silakan coba lagi.",
      response.status,
    );
  }

  return data as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return api<T>("GET", path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return api<T>("POST", path, body);
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return api<T>("PUT", path, body);
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return api<T>("PATCH", path, body);
}

export function apiDelete<T>(path: string): Promise<T> {
  return api<T>("DELETE", path);
}
