import type { TailorPayload, TailorResult } from "./types";

export const RUN_KEY = "rt_run_payload";
export const RESULT_KEY = "rt_last_result";
export const LLM_KEY = "rt_llm_provider";
const RUN_ID_KEY = "rt_run_id";
const RUN_GEN_KEY = "rt_run_gen";
const RESULT_SEEN_KEY = "rt_result_seen";

export type RunRequest = TailorPayload & { label: string };

export function saveRun(request: RunRequest) {
  sessionStorage.setItem(RUN_KEY, JSON.stringify(request));
  sessionStorage.removeItem(RUN_ID_KEY);
  const next = Number(sessionStorage.getItem(RUN_GEN_KEY) || "0") + 1;
  sessionStorage.setItem(RUN_GEN_KEY, String(next));
}

export function loadRunGen(): number {
  return Number(sessionStorage.getItem(RUN_GEN_KEY) || "0");
}

export function saveRunId(id: number) {
  const prev = sessionStorage.getItem(RUN_ID_KEY);
  sessionStorage.setItem(RUN_ID_KEY, String(id));
  sessionStorage.removeItem(RUN_GEN_KEY);
  if (prev !== String(id)) sessionStorage.removeItem(RESULT_SEEN_KEY);
}

export function markResultSeen() {
  const id = sessionStorage.getItem(RUN_ID_KEY);
  if (id) sessionStorage.setItem(RESULT_SEEN_KEY, id);
}

export function resultSeen(): boolean {
  const id = sessionStorage.getItem(RUN_ID_KEY);
  return !!id && sessionStorage.getItem(RESULT_SEEN_KEY) === id;
}

export function loadRunId(): number | null {
  const raw = sessionStorage.getItem(RUN_ID_KEY);
  const id = Number(raw);
  return raw && Number.isFinite(id) ? id : null;
}

export function loadRun(): RunRequest | null {
  const raw = sessionStorage.getItem(RUN_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as RunRequest;
  } catch {
    return null;
  }
}

export function saveResult(result: TailorResult) {
  sessionStorage.setItem(RESULT_KEY, JSON.stringify(result));
}

export function loadResult(): TailorResult | null {
  const raw = sessionStorage.getItem(RESULT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as TailorResult;
  } catch {
    return null;
  }
}

export function llmProvider() {
  return localStorage.getItem(LLM_KEY) || "auto";
}
