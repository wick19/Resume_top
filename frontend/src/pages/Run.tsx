import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getActiveRun, getRun, stopRun, tailorStream } from "../api";
import Grain from "../components/Grain";
import SlidingNumber from "../components/SlidingNumber";
import ThinkingBlob, { type ThinkingStatus } from "../components/ui/ThinkingBlob";
import { loadRun, loadRunGen, loadRunId, markResultSeen, saveResult, saveRunId } from "../session";
import type { TailorResult, TailorRun } from "../types";

const STAGES = [
  { id: "parse", num: "01", name: "Read", sub: "Posting parsed" },
  { id: "select", num: "02", name: "Match", sub: "Experience aligned" },
  { id: "score", num: "03", name: "Score", sub: "Scoring the fit" },
  { id: "rewrite", num: "04", name: "Rewrite", sub: "Rewriting from facts" },
  { id: "finalize", num: "05", name: "PDF", sub: "Writing the PDF" },
] as const;

const STAGE_HEADLINES: Record<string, string> = {
  parse: "Reading the posting against your resume.",
  select: "Choosing roles and bullets that already match.",
  score: "Scoring only skills already on your resume.",
  rewrite: "Rewriting bullets from those facts.",
  finalize: "Writing the PDF and cover letter.",
};

type LogKind = "info" | "match" | "gap";

type LogEntry = {
  id: number;
  text: string;
  time: string;
  stage: string;
  kind: LogKind;
};

let postedGen = 0;

function nowTime(): string {
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `[${hh}:${mm}:${ss}]`;
}

function classify(text: string): LogKind {
  const lower = text.toLowerCase();
  if (
    lower.includes("not in your fact bank") ||
    lower.includes("stay listed as gaps") ||
    lower.includes("stays a gap") ||
    lower.includes("rejected by the fact-bank")
  ) {
    return "gap";
  }
  if (
    lower.startsWith("keeping ") ||
    lower.includes("fact bank that the jd mentions") ||
    lower.includes("baseline ats") ||
    lower.includes("final ats") ||
    lower.includes("target reached") ||
    /ats \d+%/.test(lower)
  ) {
    return "match";
  }
  return "info";
}

function splitList(raw: string): string[] {
  return raw
    .replace(/\(\+\d+ more\)/gi, "")
    .replace(/\.$/, "")
    .split(/,|;/)
    .map((item) => item.trim())
    .filter((item) => item && item.toLowerCase() !== "none named");
}

function uniquePush(list: string[], items: string[]) {
  items.forEach((item) => {
    if (!list.some((have) => have.toLowerCase() === item.toLowerCase())) list.push(item);
  });
}

function blobStatus(stage: string, active: boolean, stopped: boolean, error: boolean): ThinkingStatus {
  if (stopped || error) return "paused";
  if (!active) return "complete";
  switch (stage) {
    case "select":
      return "matching";
    case "score":
      return "scoring";
    case "rewrite":
      return "rewriting";
    case "finalize":
      return "generating";
    default:
      return "thinking";
  }
}

export default function Run() {
  const navigate = useNavigate();
  const request = loadRun();
  const [stage, setStage] = useState("parse");
  const [inspectedStage, setInspectedStage] = useState<string | null>(null);
  const [message, setMessage] = useState("Starting…");
  const [pct, setPct] = useState(0);
  const [score, setScore] = useState<number | null>(null);
  const [target, setTarget] = useState<number | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [waiting, setWaiting] = useState(false);
  const [active, setActive] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [runId, setRunId] = useState<number | null>(loadRunId());
  const [stopModalOpen, setStopModalOpen] = useState(false);
  const [elapsed, setElapsed] = useState("00:00");
  const [logFilter, setLogFilter] = useState<"all" | "match" | "gap">("all");
  const [logSearch, setLogSearch] = useState("");
  const [copiedLog, setCopiedLog] = useState(false);
  const [userScrolledUp, setUserScrolledUp] = useState(false);

  const sent = useRef(false);
  const startTime = useRef(Date.now());
  const logScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => {
      const diff = Date.now() - startTime.current;
      const mins = String(Math.floor(diff / 60000)).padStart(2, "0");
      const secs = String(Math.floor((diff % 60000) / 1000)).padStart(2, "0");
      setElapsed(`${mins}:${secs}`);
    }, 250);
    return () => clearInterval(interval);
  }, [active]);

  const handleLogScroll = () => {
    if (!logScrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logScrollRef.current;
    setUserScrolledUp(scrollHeight - scrollTop - clientHeight >= 36);
  };

  useEffect(() => {
    if (!userScrolledUp && logScrollRef.current) {
      logScrollRef.current.scrollTop = logScrollRef.current.scrollHeight;
    }
  }, [log.length, userScrolledUp]);

  function goResult(next: TailorResult) {
    if (sent.current) return;
    sent.current = true;
    saveResult(next);
    markResultSeen();
    navigate("/result", { replace: true });
  }

  const appendLog = useCallback((rawText: string, lineStage = "") => {
    const clean = rawText.trim();
    if (!clean) return;
    setLog((prev) => {
      if (prev.some((entry) => entry.text === clean)) return prev;
      return [
        ...prev,
        {
          id: prev.length + 1,
          text: clean,
          time: nowTime(),
          stage: lineStage,
          kind: classify(clean),
        },
      ];
    });
  }, []);

  const apply = useCallback(
    (run: TailorRun) => {
      setStage(run.stage || "parse");
      setMessage(run.message || "Working…");
      setPct(Math.min(100, run.pct || 0));
      setScore(run.score);
      setTarget(run.target ?? null);
      setActive(run.status === "running");
      setMissing(false);
      if (Array.isArray(run.log)) {
        run.log.forEach((line) => {
          if (line?.message) appendLog(line.message, line.stage || "");
        });
      }
    },
    [appendLog],
  );

  useEffect(() => {
    let stop = false;
    let timer = 0;
    let quiet = window.setTimeout(() => {
      if (!stop) setWaiting(true);
    }, 8000);

    function poke() {
      window.clearTimeout(quiet);
      setWaiting(false);
      quiet = window.setTimeout(() => {
        if (!stop) setWaiting(true);
      }, 8000);
    }

    async function follow(id: number) {
      saveRunId(id);
      setRunId(id);
      let watchedLive = false;
      const tick = async () => {
        if (stop) return;
        try {
          const run = await getRun(id);
          if (stop) return;
          poke();
          apply(run);
          if (run.status === "running") watchedLive = true;
          if (run.status === "done" && run.result) {
            if (watchedLive) {
              goResult(run.result);
              return;
            }
            setActive(false);
            return;
          }
          if (run.status === "stopped") {
            setStopped(true);
            setActive(false);
            setMessage("Stopped. No resume was saved.");
            return;
          }
          if (run.status === "error") {
            setError(run.error || "Tailor failed");
            setActive(false);
            setMessage(run.error || "Tailor failed");
            return;
          }
        } catch (err) {
          if (stop) return;
          setError(err instanceof Error ? err.message : "Could not read the tailor");
          setActive(false);
          return;
        }
        timer = window.setTimeout(tick, 1000);
      };
      await tick();
    }

    async function watchActive() {
      for (let attempt = 0; attempt < 20 && !stop; attempt += 1) {
        const body = await getActiveRun().catch(() => null);
        if (body?.run) {
          await follow(body.run.id);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 300));
      }
      if (!stop) {
        setError("The tailor did not start. Try the job again.");
        setActive(false);
      }
    }

    async function boot() {
      const existing = loadRunId();
      if (existing) {
        await follow(existing);
        return;
      }
      const gen = loadRunGen();
      if (gen && request) {
        if (postedGen === gen) {
          await watchActive();
          return;
        }
        postedGen = gen;
        tailorStream(request, {
          onRun: (id) => {
            saveRunId(id);
            if (!stop) void follow(id);
          },
          onProgress: (event) => {
            if (stop) return;
            poke();
            setStage(event.stage || "parse");
            setMessage(event.message || "");
            setPct(Math.min(100, event.pct || 0));
            if (event.score != null) setScore(event.score);
            if (event.target != null) setTarget(event.target);
            if (event.message) appendLog(event.message, event.stage || "");
          },
          onResult: (next) => {
            if (!stop) goResult(next);
          },
          onError: (detail) => {
            if (stop) return;
            setError(detail);
            setActive(false);
            setMessage(detail);
          },
        }).catch((err: unknown) => {
          if (stop) return;
          setError(err instanceof Error ? err.message : "Tailor failed");
          setActive(false);
        });
        return;
      }
      const body = await getActiveRun().catch(() => null);
      if (stop) return;
      if (body?.run) {
        await follow(body.run.id);
        return;
      }
      setMissing(true);
      setActive(false);
    }

    boot().catch((err: unknown) => {
      if (stop) return;
      setError(err instanceof Error ? err.message : "Tailor failed");
      setActive(false);
    });

    return () => {
      stop = true;
      window.clearTimeout(timer);
      window.clearTimeout(quiet);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apply, appendLog]);

  async function handleConfirmStop() {
    setStopModalOpen(false);
    const id = runId || loadRunId();
    if (!id) return;
    try {
      await stopRun(id);
      setStopped(true);
      setActive(false);
      setMessage("Stopped. No resume was saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not stop the tailor");
    }
  }

  function copyLog() {
    const text = log.map((line) => `${line.time} ${line.text}`).join("\n");
    if (!navigator.clipboard) return;
    void navigator.clipboard.writeText(text);
    setCopiedLog(true);
    window.setTimeout(() => setCopiedLog(false), 2000);
  }

  const facts = useMemo(() => {
    const skills: string[] = [];
    const gaps: string[] = [];
    const kept: string[] = [];
    log.forEach((entry) => {
      const skill = entry.text.match(/fact bank that the JD mentions:\s*([^.]+)/i);
      if (skill) uniquePush(skills, splitList(skill[1]));
      const gap = entry.text.match(/also asks for\s+(.+?),\s*which are not in your fact bank/i);
      if (gap) uniquePush(gaps, splitList(gap[1]));
      if (/stays a gap/i.test(entry.text)) uniquePush(gaps, [entry.text.replace(/\s+That stays a gap\..*$/i, "").trim()]);
      const keep = entry.text.match(/^Keeping (.+)\.$/);
      if (keep) uniquePush(kept, splitList(keep[1]));
    });
    return { skills, gaps, kept };
  }, [log]);

  const filteredLogs = useMemo(() => {
    const query = logSearch.trim().toLowerCase();
    return log.filter((entry) => {
      if (logFilter === "match" && entry.kind !== "match") return false;
      if (logFilter === "gap" && entry.kind !== "gap") return false;
      if (query && !entry.text.toLowerCase().includes(query)) return false;
      return true;
    });
  }, [log, logFilter, logSearch]);

  const matchCount = useMemo(() => log.filter((line) => line.kind === "match").length, [log]);
  const gapCount = useMemo(() => log.filter((line) => line.kind === "gap").length, [log]);

  if (missing) {
    return (
      <div className="fit-page min-h-[calc(100vh-4rem)] flex items-center justify-center p-6">
        <div className="res-card max-w-md w-full text-center p-8">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">No run queued</h1>
          <p className="mt-2 text-sm text-muted">Pick a job or paste a description to start tailoring.</p>
          <Link to="/job" className="btn mt-6">
            Fit a job
          </Link>
        </div>
      </div>
    );
  }

  const viewing = inspectedStage || stage;
  const liveIndex = Math.max(0, STAGES.findIndex((item) => item.id === stage));
  const stageLines = log.filter((line) => (line.stage ? line.stage === viewing : viewing === stage));
  const company = request?.company || "This company";
  const role = request?.target_role || "This role";
  const status = blobStatus(stage, active, stopped, Boolean(error));
  const finished = !active && !stopped && !error;

  return (
    <div className="fit-page relative min-h-[calc(100vh-4rem)]">
      <div className="fit-field" aria-hidden="true">
        <Grain />
      </div>

      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
        <div className="flex flex-col justify-between gap-5 rounded-2xl border border-ink/10 bg-card p-5 shadow-sm md:p-6 lg:flex-row lg:items-center">
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-2">
              {active ? (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 font-mono text-[11px] font-bold text-primary">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
                  Live
                </span>
              ) : (
                <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-muted">
                  {finished ? "Finished" : stopped ? "Stopped" : "Error"}
                </span>
              )}
              {runId != null && (
                <span className="font-mono text-[11px] text-muted">
                  Run <strong className="font-semibold text-ink">#{runId}</strong>
                </span>
              )}
              {active && <span className="font-mono text-[11px] text-muted">{elapsed}</span>}
            </div>
            <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-ink md:text-2xl">
              {company} — {role}
            </h1>
          </div>

          <div className="flex items-center gap-4 self-start rounded-xl border border-ink/10 bg-[#f2f5fb] px-4 py-3 sm:px-5 lg:self-auto">
            {active && <ThinkingBlob status={status} size={28} />}
            <div className="flex max-w-[240px] flex-col">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Latest</span>
              <span className="mt-0.5 truncate text-xs font-medium text-ink/80">{message || "Working…"}</span>
            </div>
            <div className="hidden h-8 w-px bg-ink/10 sm:block" />
            <div className="flex items-baseline gap-1 pl-1">
              <span className="text-2xl font-bold tracking-tight text-primary">
                {score == null ? "—" : <SlidingNumber value={score} />}
              </span>
              <span className="text-base font-normal text-muted">/</span>
              <span className="text-lg font-semibold text-ink/75">
                {target == null ? "—" : <SlidingNumber value={target} />}
              </span>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-ink/10 bg-card p-3 shadow-sm sm:p-4">
          <div className="mb-2 flex items-center justify-between px-1 font-mono text-[11px] text-muted">
            <span className="font-semibold uppercase tracking-wider">Steps</span>
            {inspectedStage ? (
              <button type="button" className="font-bold text-primary hover:underline" onClick={() => setInspectedStage(null)}>
                {active ? "Back to the live step" : "Back to the last step"}
              </button>
            ) : (
              <span>{active ? "Following this run" : "This run's last step"}</span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5 md:gap-3">
            {STAGES.map((item, index) => {
              const isCurrent = active && index === liveIndex;
              const isPast = !isCurrent && (finished || index < liveIndex);
              const isInspected = inspectedStage === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setInspectedStage((current) => (current === item.id ? null : item.id))}
                  className={`flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-left transition-all ${
                    isInspected
                      ? "bg-blue-50 shadow-sm ring-2 ring-primary ring-offset-2"
                      : isCurrent
                        ? "border-2 border-primary bg-blue-50/80"
                        : isPast
                          ? "border border-emerald-200/80 bg-emerald-50/70 hover:bg-emerald-100/60"
                          : "border border-dashed border-ink/15 bg-[#f8fafe] opacity-70 hover:opacity-100"
                  }`}
                >
                  {isCurrent ? (
                    <ThinkingBlob status={status} size={20} />
                  ) : isPast ? (
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-[12px] font-bold text-white">
                      ✓
                    </span>
                  ) : (
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink/10 font-mono text-[11px] text-muted">
                      {index + 1}
                    </span>
                  )}
                  <span className="min-w-0">
                    <span
                      className={`block truncate font-mono text-[10px] font-semibold uppercase tracking-wider ${
                        isCurrent ? "text-primary" : isPast ? "text-emerald-800" : "text-muted"
                      }`}
                    >
                      {item.num} · {isCurrent ? "Now" : item.name}
                    </span>
                    <span className="block truncate text-xs font-medium text-ink/80">{item.sub}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
          <section className="rounded-2xl border border-ink/10 bg-card p-6 shadow-sm lg:col-span-7 md:p-8">
            <div className="flex items-center justify-between border-b border-ink/5 pb-5">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">This step</span>
              <span className="font-mono text-[11px] text-muted/70">US Letter</span>
            </div>

            <div className="flex flex-col gap-5 py-6">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-ink md:text-2xl">
                  {STAGE_HEADLINES[viewing] || "Working through the tailor."}
                </h2>
                {active && (
                  <div className="mt-4">
                    <div className="mb-1.5 flex justify-between font-mono text-xs">
                      <span className="text-muted">Progress</span>
                      <span className="font-semibold text-primary">{Math.round(pct)}%</span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-[#dce4f4]">
                      <div className="h-2.5 rounded-full bg-primary transition-all duration-700" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
                    </div>
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-2">
                {stageLines.length === 0 ? (
                  <p className="rounded-xl bg-[#f3f6fc] px-3 py-2 text-sm text-muted">Nothing from this step yet.</p>
                ) : (
                  stageLines.map((line) => (
                    <p
                      key={line.id}
                      className={`rounded-xl px-3 py-2 text-sm leading-relaxed ${
                        line.kind === "gap"
                          ? "border border-amber-200 bg-amber-50 text-amber-950"
                          : line.kind === "match"
                            ? "border border-blue-100 bg-blue-50/70 text-ink"
                            : "bg-[#f3f6fc] text-ink"
                      }`}
                    >
                      {line.text}
                    </p>
                  ))
                )}
              </div>

              {facts.skills.length > 0 && (
                <div>
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">On your resume and in the posting</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {facts.skills.map((skill) => (
                      <span key={skill} className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 font-mono text-[12px] text-primary">
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {facts.kept.length > 0 && (viewing === "select" || viewing === "score" || viewing === "rewrite" || viewing === "finalize") && (
                <div>
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Roles kept</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {facts.kept.map((roleKept) => (
                      <span key={roleKept} className="rounded-lg border border-ink/10 bg-[#f3f6fc] px-2.5 py-1 text-[12px] text-ink">
                        {roleKept}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {facts.gaps.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-3">
                  <p className="font-mono text-[11px] font-bold uppercase tracking-wide text-amber-900">Left off the page</p>
                  <p className="mt-1 text-[13px] leading-snug text-amber-950">{facts.gaps.join(", ")}</p>
                </div>
              )}
            </div>

            <p className="border-t border-ink/5 pt-4 font-mono text-[11px] uppercase tracking-wider text-muted">
              Only what is already on your resume is written onto the page.
            </p>
          </section>

          <section className="flex min-h-[520px] flex-col justify-between rounded-2xl border border-ink/10 bg-card p-5 shadow-sm lg:col-span-5 md:p-6">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between border-b border-ink/5 pb-3">
                <h2 className="text-base font-semibold text-ink">Activity</h2>
                <button type="button" className="font-mono text-[11px] text-muted hover:text-primary" onClick={copyLog}>
                  {copiedLog ? "Copied" : "Copy"}
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {(
                  [
                    ["all", `All (${log.length})`],
                    ["match", `Matches (${matchCount})`],
                    ["gap", `Gaps (${gapCount})`],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setLogFilter(id)}
                    className={`rounded-md px-2.5 py-1 font-mono text-[11px] ${
                      logFilter === id ? "bg-primary font-semibold text-white" : "bg-ink/5 text-muted hover:text-ink"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <input
                type="text"
                value={logSearch}
                onChange={(event) => setLogSearch(event.target.value)}
                placeholder="Search this run"
                className="w-full rounded-lg border border-ink/10 bg-bg px-3 py-1.5 font-mono text-xs text-ink placeholder:text-muted/60 focus:border-primary focus:outline-none"
              />

              <div className="relative">
                <div
                  ref={logScrollRef}
                  onScroll={handleLogScroll}
                  className="flex max-h-[440px] flex-col gap-2 overflow-y-auto pr-1 font-mono text-[12px] leading-relaxed"
                >
                  {filteredLogs.length === 0 && (
                    <p className="rounded bg-[#f3f6fc] px-2.5 py-2 text-muted">
                      {logSearch ? `No lines matching “${logSearch}”.` : "Waiting for the first note from this run."}
                    </p>
                  )}
                  {filteredLogs.map((entry, index) => {
                    const latest = active && index === filteredLogs.length - 1;
                    const tone =
                      entry.kind === "gap"
                        ? "border border-amber-200 bg-amber-50 text-amber-950"
                        : entry.kind === "match"
                          ? "border border-blue-100 bg-blue-50/70 text-primary"
                          : latest
                            ? "border-l-4 border-primary bg-blue-100/70 text-primary"
                            : "bg-[#f3f6fc] text-ink/80";
                    return (
                      <div key={entry.id} className={`flex items-start gap-2 rounded px-2.5 py-1.5 ${tone}`}>
                        <span className="shrink-0 select-none opacity-60">{entry.time}</span>
                        <span>
                          {entry.text}
                          {latest && <span className="ml-1 inline-block h-3.5 w-1.5 bg-primary align-middle animate-terminal-cursor" />}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {userScrolledUp && (
                  <button
                    type="button"
                    onClick={() => {
                      if (logScrollRef.current) logScrollRef.current.scrollTop = logScrollRef.current.scrollHeight;
                      setUserScrolledUp(false);
                    }}
                    className="absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 font-mono text-[11px] text-white shadow-md"
                  >
                    Jump to latest
                  </button>
                )}
              </div>
            </div>

            {active && (
              <p className="mt-4 border-t border-ink/5 pt-4 font-mono text-[11px] text-muted">
                <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${waiting ? "animate-pulse bg-amber-400" : "bg-emerald-500"}`} />
                {waiting ? "Waiting on the model." : "This run is still going."}
              </p>
            )}
          </section>
        </div>

        <div className="flex flex-col justify-between gap-4 rounded-2xl border border-ink/10 bg-card p-4 shadow-sm md:flex-row md:items-center md:p-5">
          <p className="text-sm font-medium text-ink">
            {active
              ? "You can leave this page open. The tailor keeps going."
              : finished
                ? "This run is finished."
                : stopped
                  ? "This run was stopped. Your source resume was not changed."
                  : error || "This run stopped."}
          </p>
          <div className="flex shrink-0 items-center gap-3 self-end md:self-auto">
            {finished && (
              <Link to="/result" className="btn text-xs">
                Open result
              </Link>
            )}
            {active && (
              <button
                type="button"
                className="rounded-xl border border-ink/15 px-4 py-2 text-xs font-semibold text-muted transition-colors hover:border-red-300 hover:bg-red-50/50 hover:text-red-700"
                onClick={() => setStopModalOpen(true)}
              >
                Stop tailoring
              </button>
            )}
            <Link to="/job" className="text-xs font-semibold text-primary hover:text-primary/80">
              Start a new tailor →
            </Link>
          </div>
        </div>

        {error && (
          <div className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 p-4 text-red-900">
            <span>{error}</span>
            <Link to="/job" className="btn">
              Try again
            </Link>
          </div>
        )}
      </div>

      {stopModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm" onClick={() => setStopModalOpen(false)}>
          <div
            className="flex w-full max-w-md flex-col gap-4 rounded-2xl border border-ink/10 bg-card p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <h3 className="text-lg font-semibold text-ink">Stop this tailoring run?</h3>
            <p className="text-sm leading-relaxed text-muted">
              Your source resume stays as it is. This draft will not be saved.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button type="button" className="btn-ghost text-xs" onClick={() => setStopModalOpen(false)}>
                Keep running
              </button>
              <button
                type="button"
                className="rounded-full bg-red-600 px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-red-700"
                onClick={handleConfirmStop}
              >
                Stop tailoring
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
