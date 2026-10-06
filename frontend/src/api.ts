import type {
  Health,
  JobHit,
  LibraryItem,
  ResumeInfo,
  TailorPayload,
  TailorResult,
  TailorRun,
} from "./types";

const TOKEN_KEY = "rt_token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorText(detail: unknown, fallback: string): string {
  if (detail == null || detail === "") return fallback;
  if (typeof detail === "string") return detail;
  const one = (item: unknown) => {
    if (!item || typeof item !== "object") return "";
    const row = item as { msg?: string; loc?: unknown[] };
    if (typeof row.msg !== "string") return "";
    const loc = Array.isArray(row.loc)
      ? row.loc.filter((part) => part !== "body" && part !== "query").join(" ")
      : "";
    const msg = row.msg.replace(/^Value error,\s*/i, "");
    return loc ? `${loc}: ${msg}` : msg;
  };
  if (Array.isArray(detail)) {
    return detail.map(one).filter(Boolean).join(" ") || fallback;
  }
  return one(detail) || fallback;
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { ...options, headers });
  const text = await res.text();
  let data: { detail?: unknown } | null = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!res.ok) {
    throw new ApiError(res.status, errorText(data?.detail, res.statusText || "Request failed"));
  }
  return data as T;
}

export function health() {
  return api<Health>("/health");
}

export function me() {
  return api<{ user: { id: number; email: string } }>("/v1/auth/me");
}

export function login(email: string, password: string) {
  return api<{ token: string }>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function register(email: string, password: string) {
  return api<{ token: string }>("/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function changePassword(email: string, password: string) {
  return api<{ token: string }>("/v1/auth/password", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout() {
  return api("/v1/auth/logout", { method: "POST" });
}

export function getResume() {
  return api<ResumeInfo>("/v1/resume");
}

export function uploadResume(file: File) {
  const body = new FormData();
  body.append("file", file);
  return api<ResumeInfo>("/v1/resume/upload", { method: "POST", body });
}

export function deleteResume() {
  return api("/v1/resume", { method: "DELETE" });
}

export function library() {
  return api<{ resumes: LibraryItem[]; due: LibraryItem[]; review_days: number }>("/v1/library");
}

export function keepResume(id: number) {
  return api(`/v1/library/${id}/keep`, { method: "POST" });
}

export function deleteLibraryItem(id: number) {
  return api<{ linkedin_hint?: string }>(`/v1/library/${id}/delete`, { method: "POST" });
}

export function downloadUrl(id: number, kind: "resume" | "cover") {
  return `/v1/library/${id}/download?kind=${kind}`;
}

export async function downloadFile(id: number, kind: "resume" | "cover", filename: string) {
  const res = await fetch(downloadUrl(id, kind), {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const match = (res.headers.get("Content-Disposition") || "").match(/filename="?([^"]+)"?/);
  a.href = url;
  a.download = match?.[1] || filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function searchJobs(q: string, page: number) {
  const params = new URLSearchParams({ q, page: String(page), page_size: "10" });
  return api<{ jobs: JobHit[]; page: number; has_more?: boolean }>(
    `/v1/jobs/search?${params}`,
  );
}

export type StreamHandlers = {
  onRun?: (id: number) => void;
  onProgress: (event: {
    stage: string;
    message: string;
    pct: number;
    score: number | null;
    target: number | null;
  }) => void;
  onResult: (result: TailorResult) => void;
  onError: (detail: string) => void;
};

export function getRun(id: number) {
  return api<TailorRun>(`/v1/runs/${id}`);
}

export function getActiveRun() {
  return api<{ run: TailorRun | null }>("/v1/runs/active");
}

export function stopRun(id: number) {
  return api<TailorRun>(`/v1/runs/${id}/stop`, { method: "POST" });
}

export async function tailorStream(
  payload: TailorPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch("/v1/tailor/stream", {
    method: "POST",
    headers,
    body: JSON.stringify({
      ...payload,
      rewrite: payload.llm_provider !== "select",
      cover_letter: true,
    }),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    let detail = text || res.statusText;
    try {
      detail = JSON.parse(text).detail || detail;
    } catch {
      /* plain text */
    }
    throw new ApiError(res.status, detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk
        .split("\n")
        .map((part) => part.trim())
        .find((part) => part.startsWith("data:"));
      if (!line) continue;
      const event = JSON.parse(line.slice(5).trim());
      if (event.type === "run" && event.id) handlers.onRun?.(event.id);
      else if (event.type === "progress") handlers.onProgress(event);
      else if (event.type === "result") handlers.onResult(event);
      else if (event.type === "error") handlers.onError(event.detail || "Tailor failed");
    }
  }
}
