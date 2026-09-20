import { storage } from "@/src/utils/storage";

const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL || "") + "/api";
export const API_ORIGIN = (process.env.EXPO_PUBLIC_BACKEND_URL || "");
export const TOKEN_KEY = "chatly_token";

/** Default request timeout. Generous because some AI/research calls are slow
 *  (the backend itself retries Sarvam/Tavily with backoff). */
const DEFAULT_TIMEOUT = 120000;

export type ErrorCategory =
  | "network"
  | "timeout"
  | "auth"
  | "server"
  | "client"
  | "unknown";

/** A user-safe error. `message` is ALWAYS safe to show to the user — it never
 *  contains tokens, stack traces or raw backend internals. */
export class ApiError extends Error {
  status?: number;
  category: ErrorCategory;
  constructor(message: string, category: ErrorCategory, status?: number) {
    super(message);
    this.name = "ApiError";
    this.category = category;
    this.status = status;
  }
}

export function wsUrl(token: string) {
  const base = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/^http/, "ws");
  return `${base}/api/ws?token=${encodeURIComponent(token)}`;
}

function isSafeDetail(detail: unknown): detail is string {
  if (typeof detail !== "string") return false;
  const d = detail.toLowerCase();
  // Never surface anything that looks like a secret / stack trace / internal path.
  const leaky = ["traceback", "sk_", "sk-", "tvly", "mongo", "bearer ", "jwt", "at /app/", ".py\", line"];
  if (leaky.some((k) => d.includes(k))) return false;
  // Keep messages short & sane.
  return detail.trim().length > 0 && detail.length <= 300;
}

function friendlyFromStatus(status: number, detail?: string): { msg: string; category: ErrorCategory } {
  const safe = detail && isSafeDetail(detail) ? detail : undefined;
  if (status === 401 || status === 403) {
    return { msg: safe || "Your session has expired. Please sign in again.", category: "auth" };
  }
  if (status === 404) {
    return { msg: safe || "We couldn't find what you were looking for.", category: "client" };
  }
  if (status === 408) {
    return { msg: safe || "The request timed out. Please try again.", category: "timeout" };
  }
  if (status === 429) {
    return { msg: safe || "You're going a bit too fast. Please wait a moment and try again.", category: "client" };
  }
  if (status === 503) {
    return { msg: safe || "The service is temporarily unavailable. Please try again shortly.", category: "server" };
  }
  if (status >= 500) {
    return { msg: safe || "Something went wrong on our end. Please try again shortly.", category: "server" };
  }
  if (status >= 400) {
    return { msg: safe || "That request couldn't be completed. Please try again.", category: "client" };
  }
  return { msg: safe || `Request failed (${status}).`, category: "unknown" };
}

async function request<T = any>(
  method: string,
  path: string,
  body?: any,
  auth = true,
  timeout = DEFAULT_TIMEOUT,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    try {
      const token = await storage.secureGet<string>(TOKEN_KEY, "");
      if (token) headers["Authorization"] = `Bearer ${token}`;
    } catch {
      /* secure storage unavailable — proceed unauthenticated; the server will 401 */
    }
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (e: any) {
    clearTimeout(timer);
    if (e?.name === "AbortError") {
      throw new ApiError(
        "The request took too long. Please check your connection and try again.",
        "timeout",
      );
    }
    throw new ApiError(
      "You appear to be offline. Please check your internet connection and try again.",
      "network",
    );
  }
  clearTimeout(timer);

  let text = "";
  try {
    text = await res.text();
  } catch {
    /* empty body */
  }
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!res.ok) {
    const detail = data?.detail ?? data?.message;
    const { msg, category } = friendlyFromStatus(res.status, detail);
    throw new ApiError(msg, category, res.status);
  }
  return data as T;
}

export const api = {
  get: <T = any>(p: string, auth = true) => request<T>("GET", p, undefined, auth),
  post: <T = any>(p: string, b?: any, auth = true) => request<T>("POST", p, b, auth),
  put: <T = any>(p: string, b?: any, auth = true) => request<T>("PUT", p, b, auth),
  patch: <T = any>(p: string, b?: any, auth = true) => request<T>("PATCH", p, b, auth),
  del: <T = any>(p: string, auth = true) => request<T>("DELETE", p, undefined, auth),
};
