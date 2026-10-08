import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { deleteLibraryItem, deleteResume, downloadFile, getResume, keepResume, library, uploadResume } from "../api";
import AnimatedList from "../components/AnimatedList";
import SlidingNumber from "../components/SlidingNumber";
import type { LibraryItem, ResumeInfo } from "../types";

const PAGE = 10;

function ageLabel(days: number) {
  if (days <= 0) return "Today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

function followLabel(item: LibraryItem) {
  if (item.due) return "Follow-up due";
  if (item.days_until_review <= 0) return "Follow-up due";
  if (item.days_until_review === 1) return "Follow-up tomorrow";
  return `Follow-up in ${item.days_until_review} days`;
}

function whenModified(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function pageMarks(current: number, total: number) {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const keep = new Set<number>([1, total, current - 1, current, current + 1]);
  const numbers = [...keep].filter((number) => number >= 1 && number <= total).sort((a, b) => a - b);
  const marks: (number | "gap")[] = [];
  numbers.forEach((number, index) => {
    if (index > 0 && number - numbers[index - 1] > 1) marks.push("gap");
    marks.push(number);
  });
  return marks;
}

export default function Library() {
  const [resume, setResume] = useState<ResumeInfo | null>(null);
  const [due, setDue] = useState<LibraryItem[]>([]);
  const [all, setAll] = useState<LibraryItem[]>([]);
  const [reviewDays, setReviewDays] = useState(7);
  const [openId, setOpenId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [keptId, setKeptId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<"all" | "due">("all");
  const [page, setPage] = useState(1);
  const [jump, setJump] = useState("1");
  const [tip, setTip] = useState(false);
  const [notify, setNotify] = useState<NotificationPermission | "unsupported">("unsupported");
  const fileRef = useRef<HTMLInputElement>(null);

  async function reload() {
    const [status, shelf] = await Promise.all([getResume(), library()]);
    setResume(status);
    setDue(shelf.due || []);
    setAll(shelf.resumes || []);
    setReviewDays(shelf.review_days || 7);
    notifyDue(shelf.due || []);
  }

  useEffect(() => {
    reload().catch((err) => setError(err.message));
    setNotify("Notification" in window ? Notification.permission : "unsupported");
  }, []);

  const shelf = [...all].sort((a, b) => Number(b.due) - Number(a.due) || a.days_old - b.days_old);
  const shown = filter === "due" ? shelf.filter((item) => item.due) : shelf;
  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  const safePage = Math.min(page, pages);
  const slice = shown.slice((safePage - 1) * PAGE, safePage * PAGE);
  const from = shown.length ? (safePage - 1) * PAGE + 1 : 0;
  const to = Math.min(safePage * PAGE, shown.length);

  useEffect(() => {
    const raw = window.location.hash.replace("#", "");
    if (!raw.startsWith("resume-")) return;
    const num = Number(raw.slice("resume-".length));
    const ordered = [...all].sort((a, b) => Number(b.due) - Number(a.due) || a.days_old - b.days_old);
    const index = ordered.findIndex((item) => item.id === num);
    if (index < 0) return;
    setFilter("all");
    setPage(Math.floor(index / PAGE) + 1);
    setOpenId(num);
  }, [all]);

  useEffect(() => {
    if (openId == null) return;
    const id = `resume-${openId}`;
    if (window.location.hash !== `#${id}`) return;
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [openId, safePage]);

  function openRun(id: number) {
    const next = openId === id ? null : id;
    setOpenId(next);
    setKeptId(null);
    window.history.replaceState(null, "", next == null ? "/library" : `#resume-${id}`);
    if (next != null) {
      requestAnimationFrame(() => {
        document.getElementById(`resume-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }
  }

  function choose(next: "all" | "due") {
    setFilter(next);
    setPage(1);
    setJump("1");
    setOpenId(null);
    window.history.replaceState(null, "", "/library");
  }

  function go(next: number) {
    const target = Math.min(pages, Math.max(1, next));
    setPage(target);
    setJump(String(target));
    setOpenId(null);
    window.history.replaceState(null, "", "/library");
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setMessage("Reading the source resume…");
    setError("");
    try {
      await uploadResume(file);
      setMessage("");
      await reload();
    } catch (err) {
      setMessage("");
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function removeSource() {
    if (!confirm("Remove the source resume? Tailoring stops until you upload another.")) return;
    setError("");
    try {
      await deleteResume();
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the source resume");
    }
  }

  async function onKeep(id: number) {
    setError("");
    try {
      await keepResume(id);
      setKeptId(id);
      setMessage("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the follow-up");
    }
  }

  async function onDelete(id: number) {
    if (!confirm("Delete this resume from your library? Also remove it from LinkedIn if you uploaded it.")) return;
    setError("");
    try {
      const out = await deleteLibraryItem(id);
      if (openId === id) {
        setOpenId(null);
        window.history.replaceState(null, "", "/library");
      }
      setMessage(out.linkedin_hint || "");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete that resume");
    }
  }

  function askNotifications() {
    if (!("Notification" in window)) return;
    Notification.requestPermission().then((permission) => {
      setNotify(permission);
      if (permission === "granted") notifyDue(due, true);
    });
  }

  const summary = resume?.summary || {};
  const sourceName = resume?.meta?.source_name || "Source resume";
  const modified = whenModified(resume?.meta?.updated_at);

  return (
    <div>
      <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md" className="sr-only" onChange={onFile} />

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[0.68rem] uppercase tracking-[0.14em] text-muted">
            <SlidingNumber value={shelf.length} from={0} /> tailored {shelf.length === 1 ? "resume" : "resumes"}
            {due.length > 0 && (
              <>
                {" "}
                · <SlidingNumber value={due.length} from={0} /> due
              </>
            )}
          </p>
          <h1 className="mt-1 text-[clamp(2rem,4vw,2.6rem)] font-medium tracking-[-0.03em]">Library</h1>
        </div>
      </div>

      <section className="mt-8">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="text-lg font-medium tracking-tight">Source resume</h2>
          <p className="text-[0.68rem] uppercase tracking-[0.12em] text-muted">What every tailor starts from</p>
        </div>
        <article className="fit-source">
          <div>
            <p className="flex flex-wrap items-center gap-2 font-medium">
              {resume?.uploaded ? sourceName : "No source resume yet"}
              {resume?.uploaded && (
                <span className="fit-file">
                  {summary.roles || 0} roles · {summary.bullets || 0} bullets
                </span>
              )}
            </p>
            <p className="mt-1 text-sm text-muted">
              {resume?.uploaded
                ? "This file is the fact bank. Tailoring only rewrites what is already in it."
                : "Add a PDF, DOCX, or TXT before a run."}
            </p>
            {modified && <p className="mt-2 text-[0.68rem] uppercase tracking-[0.12em] text-muted">Updated {modified}</p>}
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="btn-ghost" disabled={busy} onClick={() => fileRef.current?.click()}>
              {resume?.uploaded ? "Replace source" : "Add source"}
            </button>
            {resume?.uploaded && (
              <button type="button" className="btn-ghost" onClick={removeSource}>
                Remove
              </button>
            )}
          </div>
        </article>
        {message && <p className="mt-3 text-sm text-muted">{message}</p>}
        {error && <p className="mt-3 text-sm">{error}</p>}
      </section>

      <section className="mt-10">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-medium tracking-tight">Tailored resumes</h2>
            <div className="lib-tip" onMouseEnter={() => setTip(true)} onMouseLeave={() => setTip(false)}>
              <button
                type="button"
                className="fit-more-word text-[0.75rem]"
                aria-expanded={tip}
                onClick={() => setTip((open) => !open)}
              >
                7-day follow-up
              </button>
              {tip && (
                <div className="lib-tip-card" role="tooltip">
                  <span>
                    Each resume asks for a follow-up after {reviewDays} days. Keep moves that date forward {reviewDays}{" "}
                    days. Allow notifications and this browser tells you when one is due.
                    <span className="mt-2 block">
                      {notify === "granted" && "Notifications are on."}
                      {notify === "denied" && "Notifications are blocked in the browser settings."}
                      {notify === "default" && (
                        <button type="button" className="text-primary" onClick={askNotifications}>
                          Allow notifications
                        </button>
                      )}
                      {notify === "unsupported" && "This browser does not offer notifications."}
                    </span>
                  </span>
                </div>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={`lib-filter${filter === "all" ? " is-on" : ""}`} onClick={() => choose("all")}>
              All ({shelf.length})
            </button>
            <button type="button" className={`lib-filter${filter === "due" ? " is-on" : ""}`} onClick={() => choose("due")}>
              Due ({due.length})
            </button>
            {pages > 1 && (
              <form
                className="fit-page-jump"
                onSubmit={(event) => {
                  event.preventDefault();
                  const next = Math.trunc(Number(jump));
                  if (!Number.isFinite(next)) return;
                  go(next);
                }}
              >
                <label htmlFor="libraryJump">
                  {from}–{to} of {shown.length}
                </label>
                <input
                  id="libraryJump"
                  inputMode="numeric"
                  aria-label="Go to page"
                  value={jump}
                  onChange={(event) => setJump(event.target.value.replace(/[^\d]/g, ""))}
                />
              </form>
            )}
          </div>
        </div>

        {shown.length === 0 ? (
          <p className="text-sm text-muted">
            {filter === "due" ? "Nothing needs your attention." : "Your first tailored resume will appear here."}
          </p>
        ) : (
          <AnimatedList
            key={`${filter}-${safePage}`}
            items={slice}
            getKey={(item) => item.id}
            holdIndex={slice.findIndex((item) => item.id === openId)}
            initialSelectedIndex={slice.findIndex((item) => item.id === openId)}
            onItemSelect={(item) => openRun(item.id)}
            renderItem={(item, _index, selected) => {
              const open = openId === item.id;
              return (
                <article id={`resume-${item.id}`} className={`lib-card scroll-mt-24${open ? " is-open" : ""}${selected ? " is-selected" : ""}`}>
                  <button type="button" className="lib-run-hit" onClick={() => openRun(item.id)} aria-expanded={open}>
                    <span className="flex min-w-0 items-center gap-3">
                      <span className="lib-mark" aria-hidden="true">
                        {(item.company || "?").slice(0, 1).toUpperCase()}
                      </span>
                      <span className="min-w-0 text-left">
                        <span className="block font-medium">{item.company}</span>
                        <span className="block text-sm text-muted">{item.role}</span>
                      </span>
                    </span>
                    <span className="lib-meta">
                      <span>{ageLabel(item.days_old)} · v{item.version}</span>
                      <span className={item.due ? "lib-due" : ""}>{followLabel(item)}</span>
                      {!open && <span aria-hidden="true">›</span>}
                    </span>
                  </button>
                  {open && (
                    <div className="lib-drawer">
                      <p className="max-w-md text-sm text-muted">
                        {keptId === item.id
                          ? `Follow-up moved forward ${reviewDays} days.`
                          : `Keep moves the follow-up ${reviewDays} days forward.`}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {item.has_pdf && (
                          <button type="button" className="btn" onClick={() => downloadFile(item.id, "resume", "resume.pdf")}>
                            Download resume
                          </button>
                        )}
                        {item.has_cover && (
                          <button type="button" className="btn-ghost" onClick={() => downloadFile(item.id, "cover", "cover_letter.txt")}>
                            Cover letter
                          </button>
                        )}
                        <button type="button" className="btn" onClick={() => onKeep(item.id)}>
                          Keep
                        </button>
                        <button type="button" className="btn-ghost" onClick={() => onDelete(item.id)}>
                          Delete
                        </button>
                      </div>
                    </div>
                  )}
                </article>
              );
            }}
          />
        )}

        {pages > 1 && (
          <nav className="fit-pages" aria-label="Library pages">
            <div className="fit-page-row">
              <button type="button" className="fit-page-arrow" aria-label="Previous page" disabled={safePage <= 1} onClick={() => go(safePage - 1)}>
                ‹
              </button>
              <button type="button" className="fit-page-word" disabled={safePage <= 1} onClick={() => go(1)}>
                First
              </button>
              {pageMarks(safePage, pages).map((mark, index) =>
                mark === "gap" ? (
                  <span key={`gap-${index}`} className="fit-page-gap">
                    …
                  </span>
                ) : (
                  <button
                    key={mark}
                    type="button"
                    className={`fit-page-num${mark === safePage ? " is-on" : ""}`}
                    aria-current={mark === safePage ? "page" : undefined}
                    onClick={() => go(mark)}
                  >
                    {mark}
                  </button>
                ),
              )}
              <button type="button" className="fit-page-word" disabled={safePage >= pages} onClick={() => go(pages)}>
                Last
              </button>
              <button type="button" className="fit-page-arrow" aria-label="Next page" disabled={safePage >= pages} onClick={() => go(safePage + 1)}>
                ›
              </button>
            </div>
          </nav>
        )}
      </section>
    </div>
  );
}

function notifyDue(due: LibraryItem[], force = false) {
  if (!due.length || !("Notification" in window) || Notification.permission !== "granted") return;
  const stamp = due.map((item) => item.id).sort().join(",");
  if (!force && sessionStorage.getItem("rt_due_notified") === stamp) return;
  new Notification("Resume library", {
    body:
      due.length === 1
        ? `${due[0].company} · ${due[0].role} needs a follow-up.`
        : `${due.length} tailored resumes need a follow-up.`,
  });
  sessionStorage.setItem("rt_due_notified", stamp);
}
