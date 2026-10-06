export type Stage = "parse" | "select" | "score" | "rewrite" | "finalize";

export type ProgressEvent = {
  type: "progress";
  stage: Stage | string;
  message: string;
  pct: number;
  score: number | null;
  target: number | null;
};

export type Audit = {
  interview: "Yes" | "No" | "Unknown";
  reject_reasons: string[];
  gaps: string[];
  facts_used?: string[];
  mode?: string;
  ats_score: number;
  ats_target: number;
  missing_skills: string[];
  notes: string[];
};

export type RunLogLine = { message: string; stage?: string };

export type TailorRun = {
  id: number;
  status: "running" | "done" | "error" | "stopped";
  label: string;
  company: string;
  role: string;
  stage: string;
  message: string;
  pct: number;
  score: number | null;
  target: number;
  log: RunLogLine[];
  result: TailorResult | null;
  error: string;
};

export type TailorResult = {
  status: string;
  company: string;
  role: string;
  url?: string;
  extractor?: string;
  resume_id: number | null;
  audit: Audit;
};

export type LibraryItem = {
  id: number;
  company: string;
  role: string;
  url: string;
  status: string;
  created_at: string;
  next_review_at: string;
  days_old: number;
  due: boolean;
  days_until_review: number;
  version: number;
  label: string;
  prompt: string | null;
  has_pdf: boolean;
  has_cover: boolean;
};

export type ResumeInfo = {
  uploaded: boolean;
  meta?: { source_name?: string; updated_at?: string } | null;
  summary?: {
    name?: string;
    roles?: number;
    bullets?: number;
    suggested_titles?: string[];
  };
  suggested_titles?: string[];
  warnings?: string[];
  mode?: string;
};

export type LlmChoice = { id: string; label: string };

export type Health = {
  signup?: string;
  llm?: {
    choices?: LlmChoice[];
    quota?: { limit: number | null; used: number };
  };
};

export type JobHit = {
  title?: string;
  company?: string;
  location?: string;
  url?: string;
  description?: string;
  source?: string;
};

export type TailorPayload = {
  job_description: string;
  company: string;
  target_role: string;
  url: string;
  extractor: "paste" | "jobs_api";
  llm_provider: string;
};
