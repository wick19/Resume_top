import { Component, FormEvent, useEffect, useLayoutEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, getResume, health, uploadResume } from "../api";
import Grain from "../components/Grain";
import ThinkingBlob, { type ThinkingStatus } from "../components/ui/ThinkingBlob";
import { llmProvider, saveRun, LLM_KEY } from "../session";
import type { ResumeInfo } from "../types";

type Choice = {
  id: string;
  label: string;
  model?: string;
  configured?: boolean;
  remaining_tailors?: number;
};

type QuotaRow = {
  provider: string;
  label: string;
  configured: boolean;
  remaining_tailors: number;
  remaining_calls: number;
};

type LlmStatus = {
  provider?: string | null;
  choices?: Choice[];
  quotas?: QuotaRow[];
  signup?: Record<string, string>;
};

type Job = {
  company: string;
  title: string;
  location?: string;
  source?: string;
  url?: string;
  snippet?: string;
  description: string;
  matched_keywords?: string[];
  title_match?: boolean;
};

type SearchData = {
  jobs?: Job[];
  total?: number;
  page?: number;
  pages?: number;
  page_size?: number;
  keywords?: string[];
  matched_role?: string;
  title?: string;
  note?: string;
  errors?: string[];
  google_jobs_url?: string;
};

type View = "split" | "boards" | "paste";

const views: { id: View; label: string }[] = [
  { id: "split", label: "Split" },
  { id: "boards", label: "Boards" },
  { id: "paste", label: "Paste" },
];

class FieldFrame extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return null;
    return this.props.children;
  }
}

function FitField() {
  return (
    <div className="fit-field" aria-hidden="true">
      <FieldFrame>
        <Grain />
      </FieldFrame>
    </div>
  );
}

const PREVIEW = 3;
const PAGE_SIZE = 6;

function searchBlob(searching: boolean, message: string): ThinkingStatus | null {
  if (searching) return "matching";
  if (message.startsWith("Matched your ") || message.endsWith(" matches.")) return "complete";
  return null;
}

function pageMarks(current: number, total: number) {
  if (total <= 9) return Array.from({ length: total }, (_, index) => index + 1);
  const keep = new Set<number>();
  for (let number = 1; number <= Math.min(3, total); number += 1) keep.add(number);
  for (let number = Math.max(1, total - 2); number <= total; number += 1) keep.add(number);
  for (let number = current - 1; number <= current + 1; number += 1) {
    if (number >= 1 && number <= total) keep.add(number);
  }
  const numbers = [...keep].sort((a, b) => a - b);
  const marks: (number | "gap")[] = [];
  numbers.forEach((number, index) => {
    if (index > 0 && number - numbers[index - 1] > 1) marks.push("gap");
    marks.push(number);
  });
  return marks;
}

const BOARDS = [
  { name: "Remotive", note: "" },
  { name: "Remote OK", note: "" },
  { name: "Arbeitnow", note: "" },
  { name: "Jobicy", note: "" },
  { name: "Himalayas", note: "" },
  { name: "The Muse", note: "" },
  { name: "Google Jobs", note: "Opens in a tab" },
];

const SOURCE_LABEL: Record<string, string> = {
  remotive: "Remotive",
  remoteok: "Remote OK",
  arbeitnow: "Arbeitnow",
  jobicy: "Jobicy",
  himalayas: "Himalayas",
  themuse: "The Muse",
};

function plain(value: string) {
  let text = value;
  for (let pass = 0; pass < 2; pass += 1) {
    text = text
      .replace(/&nbsp;/gi, " ")
      .replace(/&amp;/gi, "&")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">")
      .replace(/&#39;/gi, "'")
      .replace(/&quot;/gi, '"');
    if (!text.includes("<")) break;
    text = text.replace(/<[^>]+>/g, " ");
  }
  return text.replace(/\s+/g, " ").trim();
}

function modelName(choice: Choice) {
  if (choice.id === "auto") return "Auto";
  if (choice.id === "select") return "Original bullets";
  return choice.label;
}

function modelDetail(choice: Choice) {
  if (choice.id === "auto") return "First model that still has rewrites";
  if (choice.id === "select") return "Keep the original bullets";
  if (choice.configured === false) return "No key";
  const parts = [];
  if (choice.model) parts.push(choice.model);
  if (typeof choice.remaining_tailors === "number") {
    parts.push(`${choice.remaining_tailors} left`);
  }
  return parts.join(" · ");
}

export default function Job() {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const viewRef = useRef<HTMLDivElement>(null);
  const [resume, setResume] = useState<ResumeInfo | null>(null);
  const [query, setQuery] = useState("");
  const [titles, setTitles] = useState<string[]>([]);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [provider, setProvider] = useState(llmProvider());
  const [search, setSearch] = useState<SearchData | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [searching, setSearching] = useState(false);
  const [message, setMessage] = useState("");
  const [jd, setJd] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [view, setView] = useState<View>("split");
  const [pill, setPill] = useState({ x: 0, y: 0, w: 0, h: 0 });
  const [uploading, setUploading] = useState(false);
  const [jump, setJump] = useState("");
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const modelRef = useRef<HTMLDivElement>(null);

  const hasResume = !!resume?.uploaded;
  const fileName = resume?.meta?.source_name || "Source resume";
  const roles = resume?.summary?.roles ?? 0;
  const bullets = resume?.summary?.bullets ?? 0;

  function readResume() {
    getResume()
      .then((data) => {
        setResume(data);
        setTitles(data.suggested_titles || data.summary?.suggested_titles || []);
      })
      .catch(() => setResume({ uploaded: false }));
  }

  useEffect(() => {
    readResume();
    health()
      .then((data) => {
        const llm = (data.llm || {}) as LlmStatus;
        const rows = llm.choices || [];
        setChoices(rows);
        const saved = llmProvider();
        const usable = rows.find((row) => row.id === saved && row.configured !== false && row.remaining_tailors !== 0);
        const next = usable ? saved : "auto";
        setProvider(next);
        localStorage.setItem(LLM_KEY, next);
      })
      .catch(() => undefined);
  }, []);

  useLayoutEffect(() => {
    const nav = viewRef.current;
    const button = nav?.querySelectorAll<HTMLButtonElement>("button")[views.findIndex((item) => item.id === view)];
    if (!nav || !button) return;
    const navBox = nav.getBoundingClientRect();
    const buttonBox = button.getBoundingClientRect();
    setPill({
      x: buttonBox.left - navBox.left,
      y: buttonBox.top - navBox.top,
      w: buttonBox.width,
      h: buttonBox.height,
    });
  }, [view]);

  useEffect(() => {
    const onResize = () => {
      const nav = viewRef.current;
      const button = nav?.querySelectorAll<HTMLButtonElement>("button")[views.findIndex((item) => item.id === view)];
      if (!nav || !button) return;
      const navBox = nav.getBoundingClientRect();
      const buttonBox = button.getBoundingClientRect();
      setPill({
        x: buttonBox.left - navBox.left,
        y: buttonBox.top - navBox.top,
        w: buttonBox.width,
        h: buttonBox.height,
      });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [view]);

  useEffect(() => {
    if (!modelOpen) return;
    function onPointer(event: PointerEvent) {
      if (!modelRef.current?.contains(event.target as Node)) setModelOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setModelOpen(false);
    }
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [modelOpen]);

  function start(payload: {
    job_description: string;
    company: string;
    target_role: string;
    url?: string;
    extractor: "paste" | "jobs_api";
    label: string;
  }) {
    if (!hasResume) {
      setMessage("Upload your source resume first. That file is what we tailor from.");
      return;
    }
    if (!payload.job_description.trim()) {
      setMessage("Paste the job description.");
      return;
    }
    saveRun({
      job_description: payload.job_description,
      company: payload.company,
      target_role: payload.target_role,
      url: payload.url || "",
      extractor: payload.extractor,
      llm_provider: provider,
      label: payload.label,
    });
    navigate("/run");
  }

  async function searchJobs(page: number, q = query) {
    const term = q.trim();
    if (!term) {
      setMessage("Type a role or pick one from your resume.");
      return;
    }
    setSearching(true);
    setMessage(page > 1 ? `Loading page ${page}…` : "Searching public boards…");
    try {
      const data = await api<SearchData>(
        `/v1/jobs/search?q=${encodeURIComponent(term)}&page=${page}&page_size=${PAGE_SIZE}`,
      );
      setSearch(data);
      setJobs(data.jobs || []);
      setJump(String(data.page || page));
      if (data.errors?.length) setMessage(`${data.note || ""} ${data.errors.join(" ")}`.trim());
      else if (!data.total) setMessage(data.note || "No matches.");
      else {
        const ctx = data.matched_role
          ? `Matched your ${data.matched_role} role`
          : data.title
            ? `Title: ${data.title}`
            : "";
        setMessage(ctx || `${data.total} matches.`);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  function onSearch(event: FormEvent) {
    event.preventDefault();
    searchJobs(1);
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setMessage("Reading the source resume…");
    try {
      await uploadResume(file);
      setMessage("");
      readResume();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  const page = search?.page || 1;
  const pages = search?.pages || 1;
  const total = search?.total || 0;
  const size = search?.page_size || PAGE_SIZE;
  const from = total ? (page - 1) * size + 1 : 0;
  const to = Math.min(page * size, total);
  const shown = view === "boards" ? jobs : jobs.slice(0, PREVIEW);
  const current = choices.find((choice) => choice.id === provider);

  return (
    <div className="fit-page">
      <FitField />
      <div className="fit-canvas">
        <div className="fit-source">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-bg text-primary" aria-hidden="true">
              <DocIcon />
            </span>
            <div>
              <p className="flex flex-wrap items-center gap-2 text-base font-medium tracking-tight">
                {hasResume ? "Source resume is on file." : "Upload a source resume."}
                {hasResume && <span className="fit-file">{fileName}</span>}
              </p>
              <p className="mt-0.5 text-[0.68rem] uppercase tracking-[0.14em] text-muted">
                {hasResume ? `${roles} roles · ${bullets} bullets` : "The tailor only rewrites what is already in it."}
              </p>
            </div>
          </div>
          <div className="fit-source-actions">
            <div className="fit-model" ref={modelRef}>
              <button
                type="button"
                className="fit-model-btn"
                aria-expanded={modelOpen}
                aria-haspopup="listbox"
                onClick={() => setModelOpen((open) => !open)}
              >
                <small>Rewrites with</small>
                {current ? modelName(current) : "Auto"}
              </button>
              {modelOpen && (
                <div className="fit-model-menu" role="listbox" aria-label="Rewrite model">
                  <p className="px-2.5 pb-1 pt-1.5 text-[0.68rem] uppercase tracking-[0.12em] text-muted">
                    Used for boards and paste
                  </p>
                  {(choices.length ? choices : [{ id: "auto", label: "Auto", configured: true }]).map((choice) => {
                    const disabled =
                      choice.configured === false ||
                      (typeof choice.remaining_tailors === "number" &&
                        choice.remaining_tailors <= 0 &&
                        choice.id !== "auto" &&
                        choice.id !== "select");
                    return (
                      <button
                        key={choice.id}
                        type="button"
                        role="option"
                        aria-selected={provider === choice.id}
                        className={`fit-model-row${provider === choice.id ? " is-on" : ""}`}
                        disabled={disabled}
                        onClick={() => {
                          setProvider(choice.id);
                          localStorage.setItem(LLM_KEY, choice.id);
                          setModelOpen(false);
                        }}
                      >
                        <span>
                          <strong>{modelName(choice)}</strong>
                          <em>{modelDetail(choice)}</em>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            <button type="button" className="btn-ghost" disabled={uploading} onClick={() => fileRef.current?.click()}>
              {hasResume ? "Switch baseline" : "Upload resume"}
            </button>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            className="hidden"
            onChange={onFile}
          />
        </div>

        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="fit-kicker">The job</p>
            <h1 className="mt-1 text-[clamp(2rem,4vw,2.6rem)] font-medium leading-none tracking-[-0.03em]">Fit a job</h1>
          </div>
          <div ref={viewRef} className="fit-views" role="tablist" aria-label="How to bring in the job">
            <span
              className="fit-view-pill"
              style={{ transform: `translate(${pill.x}px, ${pill.y}px)`, width: pill.w, height: pill.h }}
            />
            {views.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={view === item.id}
                className={`fit-view-btn${view === item.id ? " is-on" : ""}`}
                onClick={() => setView(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {(message || (total > 0 && view === "boards")) && (
          <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1">
            {message && (
              <p className="flex items-center gap-2.5 text-sm text-muted">
                {searchBlob(searching, message) && (
                  <ThinkingBlob status={searchBlob(searching, message) as ThinkingStatus} size={40} />
                )}
                <span className="transition-opacity duration-200">{message}</span>
              </p>
            )}
            {total > 0 && view === "boards" && (
              <p className="ml-auto text-sm text-muted">
                {from}–{to} of {total}
              </p>
            )}
          </div>
        )}

        <div className={`fit-grid${view === "boards" ? " is-boards" : ""}${view === "paste" ? " is-paste" : ""}`}>
          <section className={`fit-col fit-col-a${view === "paste" ? " max-lg:hidden" : ""}`} aria-hidden={view === "paste"}>
            <div className="fit-panel">
              <div className="flex items-start justify-between gap-3">
                <div
                  className="min-w-0"
                  onMouseEnter={() => setSourcesOpen(true)}
                  onMouseLeave={() => setSourcesOpen(false)}
                >
                  <p className="fit-kicker">Public boards</p>
                  <div className="fit-sources">
                    Remotive · Remote OK ·{" "}
                    <button
                      type="button"
                      className="fit-more-word"
                      aria-expanded={sourcesOpen}
                      onClick={() => setSourcesOpen((open) => !open)}
                    >
                      and more
                    </button>
                    {sourcesOpen && (
                      <span className="fit-source-card" role="tooltip">
                        <span className="grid gap-0.5 rounded-[0.9rem] bg-card p-1.5 shadow-card">
                          {BOARDS.map((board) => (
                            <span key={board.name} className="fit-source-row">
                              <span>{board.name}</span>
                              {board.note && <span>{board.note}</span>}
                            </span>
                          ))}
                        </span>
                      </span>
                    )}
                  </div>
                </div>
                {search?.google_jobs_url && (
                  <a className="fit-google" href={search.google_jobs_url} target="_blank" rel="noreferrer">
                    Google Jobs
                  </a>
                )}
              </div>
              <div className="mt-4">
                <label className="text-lg font-medium tracking-tight" htmlFor="boardSearch">
                  Search public job boards
                </label>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <form onSubmit={onSearch} className="flex min-w-0 flex-1 gap-2">
                    <div className="relative min-w-0 flex-1">
                      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true">
                        <SearchIcon />
                      </span>
                      <input
                        id="boardSearch"
                        className="fit-search"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="Role or company"
                      />
                    </div>
                    <button className="btn shrink-0" type="submit" disabled={searching}>
                      Search
                    </button>
                  </form>
                  {search && pages > 1 && (
                    <form
                      className="fit-page-jump"
                      onSubmit={(event) => {
                        event.preventDefault();
                        if (!jump.trim()) return;
                        const next = Math.trunc(Number(jump));
                        if (!Number.isFinite(next)) return;
                        const target = Math.min(pages, Math.max(1, next));
                        if (view !== "boards") setView("boards");
                        if (target !== page) searchJobs(target);
                      }}
                    >
                      <label htmlFor="pageJump">Go to</label>
                      <input
                        id="pageJump"
                        inputMode="numeric"
                        aria-label="Go to page"
                        value={jump}
                        onChange={(event) => setJump(event.target.value.replace(/[^\d]/g, ""))}
                      />
                    </form>
                  )}
                </div>
              </div>
              {titles.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted">From your resume</span>
                  {titles.map((title) => (
                    <button
                      key={title}
                      type="button"
                      className="fit-pill"
                      onClick={() => {
                        setQuery(title);
                        searchJobs(1, title);
                      }}
                    >
                      {title}
                    </button>
                  ))}
                </div>
              )}
              {!!search?.keywords?.length && (
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted">Keywords</span>
                  {search.keywords.slice(0, 8).map((word) => (
                    <span key={word} className="fit-match">
                      <i />
                      {word}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-4 flex flex-col gap-3">
                {searching && (
                  <div className="fit-skel" aria-hidden="true">
                    <span />
                    <span />
                  </div>
                )}
                {!searching &&
                  shown.map((job, index) => (
                    <article key={`${job.url}-${job.title}-${index}`} className="fit-job" style={{ animationDelay: `${index * 50}ms` }}>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h2 className="font-medium tracking-tight">{plain(job.title)}</h2>
                          <p className="mt-0.5 text-sm text-muted">
                            <span className="font-medium text-ink">{plain(job.company)}</span>
                            {" · "}
                            {plain(job.location || "Remote")}
                            {job.source ? ` · ${SOURCE_LABEL[job.source] || job.source}` : ""}
                          </p>
                        </div>
                      </div>
                      {job.snippet && <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-muted">{plain(job.snippet)}</p>}
                      {!!job.matched_keywords?.length && (
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted">Key matches</span>
                          {job.matched_keywords.map((word) => (
                            <span key={word} className="fit-match">
                              <i />
                              {word}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                        <button
                          type="button"
                          className="btn"
                          onClick={() =>
                            start({
                              job_description: job.description,
                              company: job.company,
                              target_role: job.title,
                              url: job.url,
                              extractor: "jobs_api",
                              label: `${job.company} — ${job.title}`,
                            })
                          }
                        >
                          Tailor resume
                        </button>
                        {job.url && (
                          <a className="text-sm text-primary" href={job.url} target="_blank" rel="noreferrer">
                            Open posting
                          </a>
                        )}
                      </div>
                    </article>
                  ))}
                {!searching && jobs.length === 0 && search && (
                  <p className="text-sm text-muted">Nothing on the public boards for that search. Paste the posting instead.</p>
                )}
              </div>
              {!searching && view !== "boards" && total > PREVIEW && (
                <button type="button" className="fit-see" onClick={() => setView("boards")}>
                  See all {total}
                </button>
              )}
              {!searching && view === "boards" && pages > 1 && (
                <nav className="fit-pages" aria-label="Result pages">
                  <div className="fit-page-row">
                    <button type="button" className="fit-page-arrow" aria-label="Previous page" disabled={page <= 1 || searching} onClick={() => searchJobs(page - 1)}>
                      ‹
                    </button>
                    <button type="button" className="fit-page-word" disabled={page <= 1 || searching} onClick={() => searchJobs(1)}>
                      First
                    </button>
                    {pageMarks(page, pages).map((mark, index) =>
                      mark === "gap" ? (
                        <span key={`gap-${index}`} className="fit-page-gap" aria-hidden="true">
                          …
                        </span>
                      ) : (
                        <button
                          key={mark}
                          type="button"
                          className={`fit-page-num${mark === page ? " is-on" : ""}`}
                          aria-current={mark === page ? "page" : undefined}
                          disabled={searching}
                          onClick={() => searchJobs(mark)}
                        >
                          {mark}
                        </button>
                      ),
                    )}
                    <button type="button" className="fit-page-word" disabled={page >= pages || searching} onClick={() => searchJobs(pages)}>
                      Last
                    </button>
                    <button type="button" className="fit-page-arrow" aria-label="Next page" disabled={page >= pages || searching} onClick={() => searchJobs(page + 1)}>
                      ›
                    </button>
                  </div>
                </nav>
              )}
            </div>
          </section>

          <section className={`fit-col fit-col-b${view === "boards" ? " max-lg:hidden" : ""}`} aria-hidden={view === "boards"}>
            <div className="fit-panel is-paste">
              <div className="flex items-center justify-between gap-3">
                <p className="fit-kicker is-ink">Paste</p>
                <p className="text-[0.68rem] uppercase tracking-[0.12em] text-muted">A posting you already have</p>
              </div>
              <h2 className="mt-4 text-lg font-medium tracking-tight">Paste job details</h2>
              <p className="mt-1 text-sm text-muted">Company, role, and the posting itself. We tailor only from your resume.</p>
              <form
                className="mt-4 flex flex-col gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  start({
                    job_description: jd,
                    company,
                    target_role: role,
                    extractor: "paste",
                    label: `${company || "Company"} — ${role || "Role"}`,
                  });
                }}
              >
                <label className="text-sm font-medium" htmlFor="companyField">
                  Company
                </label>
                <div className="fit-field-line">
                  <input
                    id="companyField"
                    className="fit-input"
                    placeholder="Company"
                    value={company}
                    onChange={(event) => setCompany(event.target.value)}
                  />
                </div>
                <label className="text-sm font-medium" htmlFor="roleField">
                  Role
                </label>
                <div className="fit-field-line">
                  <input
                    id="roleField"
                    className="fit-input"
                    placeholder="Role"
                    value={role}
                    onChange={(event) => setRole(event.target.value)}
                  />
                </div>
                <label className="text-sm font-medium" htmlFor="descField">
                  Job description
                </label>
                <div className="fit-field-line">
                  <textarea
                    id="descField"
                    className="fit-area"
                    placeholder="Paste the posting"
                    value={jd}
                    onChange={(event) => setJd(event.target.value)}
                  />
                </div>
                <button className="btn mt-1" type="submit">
                  Tailor this posting
                </button>
              </form>
            </div>
          </section>
        </div>

        <div className="fit-strip">
          <p className="text-sm text-muted">
            A skill the posting asks for stays off the PDF unless your source resume already shows it.
          </p>
        </div>
      </div>
    </div>
  );
}

function DocIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M7 3.5h7.2L19 8.2V20.5H7z" />
      <path d="M14 3.8V8.2h4.2" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16.5 20 20.5" />
    </svg>
  );
}
