import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { downloadFile, downloadUrl, getToken } from "../api";
import type { TailorResult } from "../types";
import BlurText from "./BlurText";
import SlidingNumber from "./SlidingNumber";

const VISIBLE = 6;

function skimTitle(call: string) {
  if (call === "Yes") return "Interview.";
  if (call === "No") return "Likely no.";
  return "No yes/no call.";
}

function skimBody(call: string) {
  if (call === "Yes") return "A short skim of this page would likely move it forward.";
  if (call === "No") return "A short skim would likely pass. The gaps are what the posting asked for and your resume does not show.";
  return "The score still counts only skills already on your resume. A yes or no needs a live rewrite.";
}

type Detail = { kind: "gap" | "skill"; label: string };

export default function ResultPanel({ result }: { result: TailorResult }) {
  const audit = result.audit || {
    interview: "Unknown" as const,
    ats_score: 0,
    ats_target: 97,
    gaps: [],
    missing_skills: [],
    reject_reasons: [],
    notes: [],
  };
  const gaps = audit.gaps || [];
  const skills = audit.missing_skills || [];
  const reasons = audit.reject_reasons || [];
  const rewritten = audit.mode === "rewrite";
  const note = audit.notes?.[0];
  const [shelf, setShelf] = useState(false);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const [spot, setSpot] = useState<{ x: number; y: number } | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const shelfRef = useRef<HTMLDivElement>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfState, setPdfState] = useState<"idle" | "loading" | "ready" | "error">("idle");

  useEffect(() => {
    if (result.resume_id == null) return;
    const ctrl = new AbortController();
    let objectUrl = "";
    setPdfUrl(null);
    setPdfState("loading");
    fetch(downloadUrl(result.resume_id, "resume"), {
      headers: { Authorization: `Bearer ${getToken()}` },
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("missing");
        const blob = await res.blob();
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
        setPdfState("ready");
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setPdfState("error");
      });
    return () => {
      ctrl.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [result.resume_id]);

  useEffect(() => {
    if (!detail && !shelf) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDetail(null);
        setShelf(false);
      }
    }
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [detail, shelf]);

  function openShelf(label?: string) {
    setDetail(null);
    setQuery("");
    setPicked(label ?? null);
    setShelf(true);
  }

  function moveSpot(event: MouseEvent<HTMLDivElement>) {
    const box = shelfRef.current?.getBoundingClientRect();
    if (!box) return;
    setSpot({ x: event.clientX - box.left, y: event.clientY - box.top });
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return gaps;
    return gaps.filter((gap) => gap.toLowerCase().includes(needle));
  }, [gaps, query]);

  const hiddenGaps = Math.max(0, gaps.length - VISIBLE);
  const shownGaps = hiddenGaps ? gaps.slice(0, VISIBLE) : gaps;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 pt-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-[0.68rem] uppercase tracking-[0.14em] text-muted">
            Tailoring complete
            <span className="mx-2 text-ink/20">·</span>
            {rewritten ? "Rewritten" : "Original wording kept"}
            {note ? (
              <>
                <span className="mx-2 text-ink/20">·</span>
                {note}
              </>
            ) : null}
          </p>
          <BlurText
            text={`${result.company} — ${result.role}`}
            className="mt-1 text-[clamp(1.7rem,3vw,2.15rem)] font-medium tracking-[-0.03em]"
          />
        </div>
        {result.resume_id != null && (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-ghost" onClick={() => downloadFile(result.resume_id!, "cover", "cover_letter.txt")}>
              Cover letter
            </button>
            <button type="button" className="btn" onClick={() => downloadFile(result.resume_id!, "resume", "resume.pdf")}>
              Download resume
            </button>
          </div>
        )}
      </header>

      <section className="grid gap-4 md:grid-cols-12">
        <article className="res-card md:col-span-4">
          <div className="flex items-center justify-between">
            <p className="text-[0.68rem] uppercase tracking-[0.14em] text-muted">Match</p>
            <span className="rounded-md bg-bg px-2 py-0.5 text-[0.68rem] uppercase tracking-[0.08em] text-primary">Checked</span>
          </div>
          <p className="mt-4 flex items-baseline gap-2 text-6xl font-medium tracking-[-0.04em]">
            <SlidingNumber value={audit.ats_score ?? null} />
            <span className="text-2xl font-normal text-muted">/ {audit.ats_target || 97}</span>
          </p>
          <p className="mt-3 border-t border-ink/5 pt-3 text-[0.68rem] uppercase tracking-[0.12em] text-primary">
            Counted only from skills already on your resume
          </p>
        </article>
        <article className="res-card md:col-span-8">
          <p className="text-[0.68rem] uppercase tracking-[0.14em] text-muted">10-second skim</p>
          <h2 className="mt-3 text-2xl font-medium tracking-tight">{skimTitle(audit.interview || "Unknown")}</h2>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">{skimBody(audit.interview || "Unknown")}</p>
          {audit.facts_used?.length ? (
            <p className="mt-4 border-t border-ink/5 pt-3 text-sm text-muted">
              {audit.facts_used.length} entries from your resume were used on this page.
            </p>
          ) : null}
        </article>
      </section>

      <section className="res-card relative z-10">
        <div className="mb-4 flex items-baseline justify-between border-b border-ink/5 pb-2">
          <h2 className="text-[0.68rem] uppercase tracking-[0.14em] text-muted">What changed the call</h2>
        </div>
        <div className="grid gap-6 md:grid-cols-3 md:divide-x md:divide-ink/5">
          <div className="relative md:pr-5">
            <div className="mb-1 flex items-baseline justify-between">
              <p className="text-[0.72rem] font-medium uppercase tracking-[0.08em]">
                Gaps <span className="text-muted">· {gaps.length}</span>
              </p>
            </div>
            <p className="mb-3 text-[0.68rem] uppercase tracking-[0.12em] text-muted">Asked, not on your resume</p>
            {gaps.length === 0 ? (
              <p className="text-sm text-muted">None flagged.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {shownGaps.map((gap, index) => (
                  <button
                    key={gap}
                    type="button"
                    className={`res-chip${picked === gap && shelf ? " is-on" : ""}`}
                    style={{ ["--i" as string]: index }}
                    onClick={() => openShelf(gap)}
                  >
                    {gap}
                  </button>
                ))}
                {hiddenGaps > 0 && (
                  <button
                    type="button"
                    className="res-more"
                    style={{ ["--i" as string]: shownGaps.length }}
                    aria-expanded={shelf}
                    onClick={() => openShelf()}
                  >
                    +{hiddenGaps} more
                  </button>
                )}
              </div>
            )}
            <p className="mt-3 text-sm leading-relaxed text-muted">These stayed off the page. The tailor does not write them in.</p>
          </div>

          <div className="md:px-5">
            <p className="mb-1 text-[0.72rem] font-medium uppercase tracking-[0.08em]">
              Under-surfaced <span className="text-muted">· {skills.length}</span>
            </p>
            <p className="mb-3 text-[0.68rem] uppercase tracking-[0.12em] text-muted">On your resume, not on this page</p>
            {skills.length === 0 ? (
              <p className="text-sm text-muted">None flagged.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {skills.map((skill, index) => (
                  <button
                    key={skill}
                    type="button"
                    className={`res-chip is-skill${detail?.label === skill ? " is-on" : ""}`}
                    style={{ ["--i" as string]: index }}
                    onClick={() => {
                      setShelf(false);
                      setDetail({ kind: "skill", label: skill });
                    }}
                  >
                    {skill}
                  </button>
                ))}
              </div>
            )}
            <p className="mt-3 text-sm leading-relaxed text-muted">Already true in the source resume. This page did not lead with them.</p>
          </div>

          <div className="md:pl-5">
            <p className="mb-1 text-[0.72rem] font-medium uppercase tracking-[0.08em]">Likely rejection reasons</p>
            <p className="mb-3 text-[0.68rem] uppercase tracking-[0.12em] text-muted">Why a skim might pass</p>
            {reasons.length === 0 ? (
              <p className="text-sm text-muted">None written for this run.</p>
            ) : (
              <ol className="flex flex-col gap-2 rounded-xl bg-bg p-3">
                {reasons.map((reason, index) => (
                  <li key={reason} className="flex gap-2 text-sm">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-white text-[0.68rem] text-primary">
                      {index + 1}
                    </span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </section>

      {result.resume_id != null && (
        <section className="flex flex-col items-center">
          <div className="mb-3 flex w-full max-w-[850px] items-baseline justify-between px-1">
            <p className="text-[0.68rem] uppercase tracking-[0.14em] text-muted">Tailored resume</p>
            <p className="text-[0.68rem] uppercase tracking-[0.12em] text-muted">Saved PDF</p>
          </div>
          <article className="res-paper w-full max-w-[850px]">
            {pdfState === "loading" && <p className="p-10 text-sm text-muted">Opening the saved page…</p>}
            {pdfState === "error" && (
              <p className="p-10 text-sm text-muted">The saved PDF could not be opened here. Download it instead.</p>
            )}
            {pdfState === "ready" && pdfUrl && (
              <iframe title={`${result.company} resume`} src={pdfUrl} className="h-[68rem] w-full border-0 bg-white" />
            )}
          </article>
        </section>
      )}

      <aside className="res-card flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm">
          <span className="font-medium">Nothing was invented.</span>{" "}
          <span className="text-muted">A requirement your resume does not show was left off the PDF.</span>
        </p>
      </aside>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        {result.resume_id != null && (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn" onClick={() => downloadFile(result.resume_id!, "resume", "resume.pdf")}>
              Download resume PDF
            </button>
            <button type="button" className="btn-ghost" onClick={() => downloadFile(result.resume_id!, "cover", "cover_letter.txt")}>
              Cover letter
            </button>
          </div>
        )}
        <div className="flex items-center gap-4 text-sm text-muted">
          <Link to="/job" className="hover:text-ink">
            Fit a job
          </Link>
          <Link to="/library" className="hover:text-ink">
            Library
          </Link>
        </div>
      </div>

      {shelf &&
        typeof document !== "undefined" &&
        createPortal(
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/45 p-4 sm:p-6 backdrop-blur-xs" onClick={() => setShelf(false)}>
            <div
              ref={shelfRef}
              className="res-shelf"
              role="dialog"
              aria-modal="true"
              aria-labelledby="gapShelfTitle"
              onClick={(event) => event.stopPropagation()}
              onMouseMove={moveSpot}
              onMouseLeave={() => setSpot(null)}
            >
              <div
                className="res-shelf-spot"
                style={
                  spot
                    ? { background: `radial-gradient(340px circle at ${spot.x}px ${spot.y}px, rgba(0, 160, 240, 0.22), transparent 68%)` }
                    : undefined
                }
              />
              <div className="relative flex items-start justify-between gap-4">
                <div>
                  <p id="gapShelfTitle" className="text-lg font-medium tracking-tight">
                    Gaps
                  </p>
                  <p className="mt-1 text-[0.68rem] uppercase tracking-[0.12em] text-muted">
                    {filtered.length === gaps.length ? `${gaps.length} left off the PDF` : `${filtered.length} of ${gaps.length}`}
                  </p>
                </div>
                <button type="button" className="btn-ghost" onClick={() => setShelf(false)}>
                  Close
                </button>
              </div>
              <input
                className="res-shelf-find"
                value={query}
                placeholder="Find a phrase"
                aria-label="Find a gap"
                autoFocus
                onChange={(event) => setQuery(event.target.value)}
              />
              {picked && (
                <p className="relative text-sm text-muted">
                  <span className="font-medium text-ink">{picked}</span> was not on the source resume, so it stayed off the PDF.
                </p>
              )}
              <div className="res-shelf-grid">
                {filtered.length === 0 ? (
                  <p className="text-sm text-muted">Nothing matches that.</p>
                ) : (
                  filtered.map((gap, index) => (
                    <button
                      key={gap}
                      type="button"
                      className={`res-chip${picked === gap ? " is-on" : ""}`}
                      style={{ ["--i" as string]: index }}
                      onClick={() => setPicked(gap)}
                    >
                      {gap}
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}

      {detail &&
        typeof document !== "undefined" &&
        createPortal(
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/45 p-4 backdrop-blur-xs" onClick={() => setDetail(null)}>
            <div className="w-full max-w-lg rounded-2xl bg-white shadow-card" role="dialog" aria-modal="true" aria-labelledby="gapTitle" onClick={(event) => event.stopPropagation()}>
              <div className="flex items-start justify-between gap-3 border-b border-ink/5 px-5 py-4">
                <div>
                  <p id="gapTitle" className="font-medium">{detail.label}</p>
                  <p className="mt-1 text-[0.68rem] uppercase tracking-[0.12em] text-muted">
                    {detail.kind === "gap" ? "Not on your resume" : "On your resume, not on this page"}
                  </p>
                </div>
                <button type="button" className="text-sm text-muted" onClick={() => setDetail(null)}>
                  Close
                </button>
              </div>
              <div className="space-y-4 px-5 py-4 text-sm">
                <div>
                  <p className="text-[0.68rem] uppercase tracking-[0.12em] text-muted">From the posting</p>
                  <p className="mt-1">{detail.label}</p>
                </div>
                <div>
                  <p className="text-[0.68rem] uppercase tracking-[0.12em] text-muted">What happened</p>
                  <p className="mt-1 text-muted">
                    {detail.kind === "gap"
                      ? "This was not in the source resume, so it was left off the PDF."
                      : "This is already in the source resume. This tailored page did not lead with it."}
                  </p>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
