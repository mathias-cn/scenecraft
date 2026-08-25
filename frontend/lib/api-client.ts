import { getApiBaseUrl } from "./config";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function joinUrl(path: string): string {
  const base = getApiBaseUrl();
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${suffix}`;
}

async function parseErrorMessage(response: Response): Promise<{ message: string; body: unknown }> {
  const text = await response.text();
  if (!text) {
    return { message: `HTTP ${response.status}`, body: null };
  }
  try {
    const json: unknown = JSON.parse(text);
    if (json && typeof json === "object" && "detail" in json) {
      const detail = (json as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return { message: detail, body: json };
      }
      if (Array.isArray(detail)) {
        const parts = detail.map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        });
        return { message: parts.join("; ") || `HTTP ${response.status}`, body: json };
      }
    }
    return { message: text, body: json };
  } catch {
    return { message: text, body: text };
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  const headers = new Headers(init.headers);
  if (!isForm && !headers.has("Content-Type") && init.body != null) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(joinUrl(path), {
    ...init,
    headers,
    cache: init.cache ?? "no-store",
  });

  if (!response.ok) {
    const { message, body } = await parseErrorMessage(response);
    throw new ApiError(response.status, message, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return (await response.text()) as T;
  }

  return (await response.json()) as T;
}

export function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  return apiFetch<T>(path, { ...init, method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  if (body instanceof FormData) {
    return apiFetch<T>(path, { ...init, method: "POST", body });
  }
  return apiFetch<T>(path, {
    ...init,
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiPatch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  return apiFetch<T>(path, {
    ...init,
    method: "PATCH",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
