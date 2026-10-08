import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { library } from "../api";
import { useAuth } from "../auth";
import BlurText from "../components/BlurText";
import GradientText from "../components/GradientText";
import SlidingNumber from "../components/SlidingNumber";
import TailorField, { type TailorFieldHandle } from "../components/TailorField";
import Wave from "../components/Wave";
import type { LibraryItem } from "../types";

const stages = [
  {
    id: "parse",
    label: "Reading the posting",
  },
  {
    id: "select",
    label: "Matching experience",
  },
  {
    id: "score",
    label: "Scoring the fit",
  },
  {
    id: "rewrite",
    label: "Rewriting from facts",
  },
  {
    id: "finalize",
    label: "Writing the PDF",
  },
];

const lensSize = 112;
const lensScale = 1.15;

function ageLabel(days: number) {
  if (days <= 0) return "Today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

export default function Landing() {
  const { user, ready } = useAuth();
  const [index, setIndex] = useState(0);
  const [shown, setShown] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const [paperHeight, setPaperHeight] = useState<number | null>(null);
  const [easeHeight, setEaseHeight] = useState(false);
  const [runs, setRuns] = useState<LibraryItem[] | null>(null);
  const [pill, setPill] = useState({ x: 0, y: 0, w: 0, h: 0 });
  const [hot, setHot] = useState<number | null>(null);
  const pillIndex = hot ?? index;
  const shownRef = useRef(0);
  const navRef = useRef<HTMLDivElement>(null);
  const pending = useRef(0);
  const resizeTarget = useRef(0);
  const phaseRef = useRef<"idle" | "exiting" | "resizing">("idle");
  const leaveTimer = useRef<number | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const lensRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLElement>(null);
  const lensCopyRef = useRef<HTMLDivElement>(null);
  const storyRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<TailorFieldHandle>(null);
  const stage = stages[shown];

  function measureStage(stageIndex: number) {
    const pane = measureRef.current?.querySelector<HTMLElement>(`[data-stage="${stages[stageIndex].id}"]`);
    const last = pane?.lastElementChild as HTMLElement | null;
    if (!pane || !last) return null;
    const top = pane.getBoundingClientRect().top;
    const bottom = last.getBoundingClientRect().bottom;
    const margin = parseFloat(getComputedStyle(last).marginBottom) || 0;
    const height = Math.ceil(bottom - top + margin);
    if (height < 1) return null;
    return height;
  }

  function clearTimer() {
    if (leaveTimer.current != null) {
      window.clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  }

  useLayoutEffect(() => {
    const next = measureStage(0);
    if (next != null) setPaperHeight(next);
    const frame = window.requestAnimationFrame(() => setEaseHeight(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useLayoutEffect(() => {
    const nav = navRef.current;
    const button = nav?.querySelectorAll<HTMLButtonElement>("button")[pillIndex];
    if (!nav || !button) return;
    const navBox = nav.getBoundingClientRect();
    const buttonBox = button.getBoundingClientRect();
    setPill({
      x: buttonBox.left - navBox.left,
      y: buttonBox.top - navBox.top,
      w: buttonBox.width,
      h: buttonBox.height,
    });
  }, [pillIndex]);

  useEffect(() => {
    const onResize = () => {
      if (phaseRef.current === "idle") {
        const next = measureStage(shownRef.current);
        if (next != null) setPaperHeight(next);
      }
      const nav = navRef.current;
      const button = nav?.querySelectorAll<HTMLButtonElement>("button")[pillIndex];
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
  }, [pillIndex]);

  useEffect(() => () => clearTimer(), []);

  useEffect(() => {
    if (!user) {
      setRuns(null);
      return;
    }
    library()
      .then((data) => {
        const recent = [...(data.resumes || [])].sort((a, b) =>
          b.created_at.localeCompare(a.created_at),
        );
        setRuns(recent.slice(0, 3));
      })
      .catch(() => setRuns([]));
  }, [user]);

  function beginExit() {
    phaseRef.current = "exiting";
    setLeaving(true);
    clearTimer();
    leaveTimer.current = window.setTimeout(beginResize, 190);
  }

  function beginResize() {
    const target = pending.current;
    resizeTarget.current = target;
    phaseRef.current = "resizing";
    const next = measureStage(target);
    if (next != null) setPaperHeight(next);
    clearTimer();
    leaveTimer.current = window.setTimeout(finishResize, 400);
  }

  function finishResize() {
    const target = pending.current;
    if (target !== resizeTarget.current) {
      beginResize();
      return;
    }
    shownRef.current = target;
    phaseRef.current = "idle";
    setShown(target);
    setLeaving(false);
  }

  function fireBolt(stageIndex: number) {
    const story = storyRef.current;
    const sheet = sheetRef.current;
    const button = navRef.current?.querySelectorAll<HTMLButtonElement>("button")[stageIndex];
    if (!story || !sheet || !button) return;
    fieldRef.current?.fire(button, sheet);
  }

  function choose(next: number) {
    setIndex(next);
    pending.current = next;
    const same = next === shownRef.current && phaseRef.current === "idle";
    if (!same) {
      if (phaseRef.current === "idle") beginExit();
      fireBolt(next);
    }
    const sheet = sheetRef.current;
    if (!sheet) return;
    const box = sheet.getBoundingClientRect();
    const outOfView = box.bottom < 96 || box.top > window.innerHeight - 140;
    if (outOfView) sheet.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function moveLens(event: ReactPointerEvent<HTMLElement>) {
    const body = bodyRef.current;
    const lens = lensRef.current;
    const copy = lensCopyRef.current;
    if (!body || !lens || !copy) return;
    const box = body.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    const radius = lensSize / 2;
    lens.style.opacity = "1";
    lens.style.transform = `translate(${x - radius}px, ${y - radius}px)`;
    copy.style.width = `${box.width}px`;
    copy.style.transform = `translate(${radius - x * lensScale}px, ${radius - y * lensScale}px) scale(${lensScale})`;
  }

  function hideLens() {
    if (lensRef.current) lensRef.current.style.opacity = "0";
  }

  return (
    <div className="bg-bg text-ink">
      <HomeHeader />

      <div className="relative">
        <div className="home-story" ref={storyRef}>
          <TailorField ref={fieldRef} />
          <div className="home-copy px-6 pt-10 lg:px-0">
            <BlurText
              text="Your resume, fitted to the job."
              className="max-w-full text-[clamp(3rem,6.2vw,5.4rem)] font-medium leading-[0.92] tracking-[-0.045em] text-ink"
            />
            <p className="rise mt-6 max-w-md text-lg leading-relaxed text-muted" style={{ animationDelay: "420ms" }}>
              Tailor your resume to the role, using only the experience already in it.
            </p>
            <Link
              to={user ? "/job" : "/signin"}
              className="home-cta rise mt-8"
              style={{ animationDelay: "620ms" }}
            >
              Fit a job
              <span className="home-cta-arrow" aria-hidden="true">
                →
              </span>
            </Link>
          </div>

          <div className="home-paper-stick px-6 pt-8 lg:px-0 lg:pt-10">
          <article
            ref={sheetRef}
            className="rise sheet mx-auto w-full max-w-md"
            style={{ animationDelay: "520ms" }}
            onPointerMove={moveLens}
            onPointerLeave={hideLens}
          >
            <span className="sheet-ribbon" aria-hidden="true">
              <span className="sheet-ribbon-face" />
            </span>
            <div
              ref={bodyRef}
              className={`sheet-body${easeHeight ? " is-easing" : ""}`}
              style={paperHeight == null ? undefined : { height: paperHeight }}
            >
              <div key={shown}>
                <SheetCopy stage={stage.id} leaving={leaving} />
              </div>
              <div ref={measureRef} className="sheet-measure" aria-hidden="true">
                {stages.map((item) => (
                  <div key={item.id} data-stage={item.id}>
                    <SheetCopy stage={item.id} leaving={false} />
                  </div>
                ))}
              </div>
              <div ref={lensRef} className="sheet-lens" aria-hidden="true">
                <div className="sheet-lens-hole">
                  <div ref={lensCopyRef} className="sheet-lens-copy">
                    <div key={`lens-${shown}`}>
                      <SheetCopy stage={stage.id} leaving={leaving} />
                    </div>
                  </div>
                </div>
                <span className="sheet-lens-label">1.15×</span>
              </div>
            </div>
          </article>
          </div>

          <section className="home-stages-slot bg-card px-6 pb-4 pt-2 lg:bg-transparent lg:px-0">
            <div className="home-stages-copy mx-auto max-w-6xl text-center lg:mx-0 lg:max-w-none lg:text-left">
              <h2 className="text-[clamp(1.8rem,3vw,2.4rem)] font-medium tracking-[-0.03em]">Five stages of tailoring.</h2>
              <p className="mt-2 text-muted">From the job posting to a finished resume.</p>
              <div
                ref={navRef}
                className="home-stages mx-auto mt-8 max-w-4xl"
                onMouseLeave={() => setHot(null)}
              >
                <span
                  className={`home-stage-pill${hot != null ? " is-hot" : ""}`}
                  style={{
                    transform: `translate(${pill.x}px, ${pill.y + (hot != null ? -3 : 0)}px)`,
                    width: pill.w,
                    height: pill.h,
                  }}
                  aria-hidden="true"
                />
                {stages.map((item, itemIndex) => {
                  const selected = itemIndex === index;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => choose(itemIndex)}
                      onMouseEnter={() => setHot(itemIndex)}
                      className={`home-stage-btn${selected ? " is-selected" : ""}`}
                      aria-pressed={selected}
                    >
                      0{itemIndex + 1} {item.label}
                    </button>
                  );
                })}
              </div>
              <p className="mt-4 text-sm text-muted">Select a stage to see the resume transform.</p>
            </div>
            <div className="home-stage-wave mt-10">
              <Wave fill="#eef3fb" />
            </div>
          </section>
        </div>
        <div className="home-divider" aria-hidden="true">
          <Wave fill="#f7f9fc" />
        </div>
      </div>

      <section className="mx-auto max-w-6xl px-6 pb-24 pt-6">
        <h2 className="text-[clamp(1.8rem,3vw,2.4rem)] font-medium tracking-[-0.03em]">Recent runs</h2>
        <History user={!!user} ready={ready} runs={runs} />
      </section>
    </div>
  );
}

function HomeHeader() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!accountRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <header className="sticky top-0 z-30 border-b border-ink/5 bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-6">
          <Link to="/home" className="brand inline-flex items-center gap-3 text-lg font-medium">
            <img src="/mark.png" alt="" width={36} height={36} className="brand-mark h-9 w-9" />
            <GradientText>Resume Tailor</GradientText>
          </Link>
          {user && (
            <nav className="hidden items-center gap-1 sm:flex">
              <Link to="/job" className="rounded-full px-3 py-1 text-sm text-muted hover:text-ink">
                Fit a job
              </Link>
              <Link to="/library" className="rounded-full px-3 py-1 text-sm text-muted hover:text-ink">
                Library
              </Link>
              <Link to="/result" className="rounded-full px-3 py-1 text-sm text-muted hover:text-ink">
                Result
              </Link>
            </nav>
          )}
        </div>
        {user ? (
          <div ref={accountRef} className="relative">
            <button
              type="button"
              className="rounded-full px-3 py-1 text-sm text-muted hover:text-ink"
              aria-expanded={open}
              onClick={() => setOpen((value) => !value)}
            >
              Account
            </button>
            {open && (
              <div className="absolute right-0 mt-2 w-56 rounded-2xl border border-ink/10 bg-card p-3 shadow-card">
                <p className="truncate px-2 py-1 text-sm text-muted">{user.email}</p>
                <button
                  type="button"
                  className="mt-1 w-full rounded-xl px-2 py-2 text-left text-sm text-ink hover:bg-bg"
                  onClick={() => {
                    setOpen(false);
                    logout();
                  }}
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        ) : (
          <Link to="/signin" className="text-sm text-muted hover:text-ink">
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}

function SheetLine({
  at,
  leaving,
  className = "",
  children,
}: {
  at: number;
  leaving: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`sheet-line${leaving ? " is-leaving" : ""}${className ? ` ${className}` : ""}`}
      style={{ animationDelay: leaving ? "0ms" : `${at * 80}ms` }}
    >
      {children}
    </div>
  );
}

function SheetCopy({
  stage,
  leaving,
}: {
  stage: string;
  leaving: boolean;
}) {
  if (stage === "parse") {
    return (
      <>
        <SheetLine at={0} leaving={leaving}>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Reading the posting</p>
        </SheetLine>
        <SheetLine at={1} leaving={leaving} className="mt-3">
          <p className="text-2xl font-medium tracking-tight">Backend Engineer</p>
        </SheetLine>
        <SheetLine at={2} leaving={leaving}>
          <p className="text-sm text-muted">Remote</p>
        </SheetLine>
        <SheetLine at={3} leaving={leaving} className="mt-8 border-t border-ink/10 pt-4">
          <p className="flex flex-wrap gap-2">
            {["Python", "PostgreSQL", "AWS"].map((skill) => (
              <Chip key={skill}>{skill}</Chip>
            ))}
          </p>
        </SheetLine>
      </>
    );
  }

  if (stage === "select") {
    return (
      <>
        <SheetLine at={0} leaving={leaving}>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Matching experience</p>
        </SheetLine>
        <SheetLine at={1} leaving={leaving} className="mt-3">
          <p className="text-sm text-muted">Verifying candidate facts against requirements:</p>
        </SheetLine>
        {["Python", "PostgreSQL", "AWS"].map((skill, skillIndex) => (
          <SheetLine key={skill} at={2 + skillIndex} leaving={leaving} className="mt-2">
            <p className="flex items-center justify-between rounded-lg border border-ink/10 bg-white px-3 py-2 text-sm">
              <span>{skill}</span>
              <span className="text-[11px] font-medium tracking-wide text-primary">✓ Verified</span>
            </p>
          </SheetLine>
        ))}
      </>
    );
  }

  if (stage === "score") {
    return (
      <>
        <SheetLine at={0} leaving={leaving}>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Scoring the fit</p>
        </SheetLine>
        <SheetLine at={1} leaving={leaving} className="mt-2">
          <p className="text-sm text-muted">Example match</p>
        </SheetLine>
        <SheetLine at={2} leaving={leaving} className="mt-1">
          <p className="flex items-baseline gap-2 text-5xl font-medium tracking-[-0.05em] text-primary">
            <SlidingNumber value={86} from={0} delay={160} />
            <span className="text-2xl text-muted">/ 97</span>
          </p>
        </SheetLine>
        <SheetLine at={3} leaving={leaving} className="mt-3">
          <span className="block h-1 overflow-hidden rounded-full bg-ink/10">
            <span className="score-bar block h-full rounded-full bg-primary" />
          </span>
        </SheetLine>
        <SheetLine at={4} leaving={leaving} className="mt-5">
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Matches</p>
        </SheetLine>
        <SheetLine at={5} leaving={leaving} className="mt-2">
          <p className="flex flex-wrap gap-2">
            {["Python", "PostgreSQL", "AWS"].map((skill) => (
              <Chip key={skill}>✓ {skill}</Chip>
            ))}
          </p>
        </SheetLine>
        <SheetLine at={6} leaving={leaving} className="mt-4">
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Gap</p>
        </SheetLine>
        <SheetLine at={7} leaving={leaving} className="mt-2">
          <span className="inline-flex rounded-md bg-[#e7ebf3] px-2 py-1 text-[11px] tracking-wide text-muted">
            — Kubernetes — gap
          </span>
        </SheetLine>
      </>
    );
  }

  if (stage === "rewrite") {
    return (
      <>
        <SheetLine at={0} leaving={leaving}>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Rewriting from facts</p>
        </SheetLine>
        <SheetLine at={1} leaving={leaving} className="mt-4">
          <div className="rounded-lg border border-ink/10 bg-bg px-3 py-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted">Original</p>
            <p className="mt-1 text-sm text-muted line-through">Developed backend APIs using Python.</p>
          </div>
        </SheetLine>
        <SheetLine at={2} leaving={leaving} className="mt-2">
          <div className="rounded-lg border border-ink/10 border-l-2 border-l-primary bg-[#eef3fb] px-3 py-3">
            <p className="flex items-center justify-between gap-3">
              <span className="text-[10px] uppercase tracking-[0.14em] text-primary">Tailored</span>
              <span className="rounded bg-[#dee7ff] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-primary">
                Fact preserved
              </span>
            </p>
            <p className="mt-1 text-sm">Built backend APIs using Python for scalable services.</p>
          </div>
        </SheetLine>
      </>
    );
  }

  return (
    <>
      <SheetLine at={0} leaving={leaving}>
        <p className="flex items-center justify-between gap-3">
          <span className="text-[11px] uppercase tracking-[0.16em] text-muted">Writing the PDF</span>
          <span className="rounded bg-primary/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-primary">
            Ready for export
          </span>
        </p>
      </SheetLine>
      <SheetLine at={1} leaving={leaving} className="mt-4">
        <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Experience</p>
      </SheetLine>
      <SheetLine at={2} leaving={leaving} className="mt-2">
        <div className="rounded-lg border border-ink/10 bg-bg px-3 py-3">
          <p className="font-medium">AWS project</p>
          <p className="mt-1 text-sm text-muted">High-throughput microservices architecture</p>
          <p className="mt-3 flex flex-wrap gap-2">
            {["Python", "PostgreSQL", "AWS"].map((skill) => (
              <Chip key={skill}>{skill}</Chip>
            ))}
          </p>
        </div>
      </SheetLine>
      <SheetLine at={3} leaving={leaving} className="mt-3">
        <p className="text-xs text-primary">ATS-formatted single-column document</p>
      </SheetLine>
    </>
  );
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md border border-ink/10 bg-white px-2 py-1 text-[11px] tracking-wide text-primary">
      {children}
    </span>
  );
}

function History({
  user,
  ready,
  runs,
}: {
  user: boolean;
  ready: boolean;
  runs: LibraryItem[] | null;
}) {
  const rowRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const row = rowRef.current;
    if (!row || !runs?.length) return;
    const check = () => {
      const overflow = row.scrollWidth > row.clientWidth + 2;
      row.dataset.overflow = overflow ? "1" : "0";
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(row);
    return () => observer.disconnect();
  }, [runs]);

  useEffect(() => {
    const row = rowRef.current;
    if (!row || !runs?.length) return;
    let frame = 0;
    let dir = 1;
    let paused = false;
    const enter = () => {
      paused = true;
    };
    const leave = () => {
      paused = false;
    };
    row.addEventListener("pointerenter", enter);
    row.addEventListener("pointerleave", leave);
    const tick = () => {
      if (!paused && row.dataset.overflow === "1") {
        const max = row.scrollWidth - row.clientWidth;
        if (max > 2) {
          if (row.scrollLeft >= max - 1) dir = -1;
          else if (row.scrollLeft <= 0) dir = 1;
          row.scrollLeft += dir * 0.35;
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      row.removeEventListener("pointerenter", enter);
      row.removeEventListener("pointerleave", leave);
    };
  }, [runs]);

  if (!user) {
    return (
      <p className="mt-6 text-lg">
        <Link to="/signin" className="text-primary">
          Tailor your first resume for a job.
        </Link>
      </p>
    );
  }
  if (!ready || runs === null) {
    return <p className="mt-6 text-sm text-muted">Loading your runs…</p>;
  }
  if (runs.length === 0) {
    return <p className="mt-6 text-lg">Your first tailored resume will appear here.</p>;
  }
  return (
    <div className="mt-8">
      <ul ref={rowRef} className="home-runs">
        {runs.map((run, runIndex) => (
          <li key={run.id}>
            <Link
              to={`/library#resume-${run.id}`}
              className="home-run"
              style={{ animationDelay: `${runIndex * 90}ms` }}
            >
              <span>
                <span className="flex items-baseline justify-between gap-3">
                  <span className="font-medium tracking-tight text-ink">{run.company}</span>
                  <span className="text-xs text-muted">{ageLabel(run.days_old)}</span>
                </span>
                <span className="mt-3 block text-sm text-muted">{run.role}</span>
              </span>
              <span className="home-cta-arrow mt-6 self-end text-primary" aria-hidden="true">
                →
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <Link to="/library" className="mt-8 inline-block text-sm font-medium text-primary">
        View library
      </Link>
    </div>
  );
}
