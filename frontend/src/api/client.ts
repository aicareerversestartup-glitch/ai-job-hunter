// Thin fetch wrapper. Web: httpOnly session cookie. Native apps: bearer token (see platform.ts).
import { apiUrl, authHeaders, isNative, saveToken } from "./platform";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          const item = d as { loc?: unknown[]; msg?: string };
          const field = item.loc ? item.loc.filter((p) => p !== "body").join(".") : "";
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .join("; ");
    }
  }
  return fallback;
}

export async function api<T>(path: string, options: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = options;
  const init: RequestInit = {
    credentials: isNative() ? "omit" : "same-origin", ...rest,
    headers: { ...authHeaders(), ...(headers || {}) },
  };
  if (json !== undefined) {
    init.body = JSON.stringify(json);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const response = await fetch(apiUrl(path), init);
  const text = await response.text();
  const body = text ? safeJson(text) : null;
  if (!response.ok) {
    if (response.status === 401 && onUnauthorized && !path.startsWith("/api/auth/")) onUnauthorized();
    throw new ApiError(response.status, messageFrom(body, `Request failed (${response.status}).`));
  }
  if (body && typeof body === "object" && "access_token" in body) {
    await saveToken((body as { access_token: string }).access_token);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const get = <T,>(path: string) => api<T>(path);
export const post = <T,>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const put = <T,>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
export const patch = <T,>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

export async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return api<T>(path, { method: "POST", body: form });
}
