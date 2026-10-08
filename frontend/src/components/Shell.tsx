import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { getActiveRun, getRun } from "../api";
import { useAuth } from "../auth";
import { loadRunId, resultSeen } from "../session";
import GradientText from "./GradientText";

function initials(email?: string) {
  const local = (email || "").split("@")[0] || "";
  const parts = local.split(/[._+\-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  const letters = local.replace(/[^a-z0-9]/gi, "");
  return (letters.slice(0, 2) || "RT").toUpperCase();
}

export default function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [accountOpen, setAccountOpen] = useState(false);
  const [notice, setNotice] = useState<"" | "running" | "done" | "error">("");
  const accountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user) return;
    let stop = false;
    async function look() {
      try {
        const body = await getActiveRun();
        if (stop) return;
        if (body.run) {
          setNotice("running");
          return;
        }
        const saved = loadRunId();
        if (!saved) {
          setNotice("");
          return;
        }
        const run = await getRun(saved);
        if (stop) return;
        if (run.status === "done" && !resultSeen()) setNotice("done");
        else if (run.status === "error") setNotice("error");
        else setNotice("");
      } catch {
        if (!stop) setNotice("");
      }
    }
    look();
    const timer = window.setInterval(look, 4000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [user, location.pathname]);

  useEffect(() => {
    if (!accountOpen) return;
    function onPointer(event: PointerEvent) {
      if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setAccountOpen(false);
    }
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [accountOpen]);

  return (
    <div className="min-h-screen bg-bg text-ink">
      <header className="sticky top-0 z-20 border-b border-ink/5 bg-bg/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4">
          <Link to="/home" className="brand inline-flex items-center gap-2.5 text-sm font-medium tracking-tight">
            <img src="/mark.png" alt="" width={28} height={28} className="brand-mark h-7 w-7" />
            <GradientText>Resume Tailor</GradientText>
          </Link>
          <nav className="flex items-center gap-2 sm:gap-3">
            <NavLink
              to="/job"
              className={({ isActive }) =>
                `rounded-full px-3.5 py-1.5 text-sm transition-all ${
                  isActive
                    ? "bg-primary text-white font-semibold shadow-xs"
                    : "text-muted hover:text-ink font-medium"
                }`
              }
            >
              Fit a job
            </NavLink>
            <NavLink
              to="/run"
              className={({ isActive }) =>
                `rounded-full px-3.5 py-1.5 text-sm flex items-center gap-1.5 transition-all ${
                  isActive
                    ? "bg-primary text-white font-semibold shadow-xs"
                    : notice === "running"
                    ? "bg-blue-50 text-primary font-semibold border border-blue-200"
                    : "text-muted hover:text-ink font-medium"
                }`
              }
            >
              {notice === "running" && (
                <span
                  className={`h-2 w-2 rounded-full animate-pulse ${
                    location.pathname === "/run" ? "bg-white" : "bg-primary"
                  }`}
                />
              )}
              Run
            </NavLink>
            <NavLink
              to="/result"
              className={({ isActive }) =>
                `rounded-full px-3 py-1.5 text-sm transition-all ${
                  isActive ? "bg-primary text-white font-semibold shadow-xs" : "text-muted hover:text-ink font-medium"
                }`
              }
            >
              Result
            </NavLink>
            <NavLink
              to="/library"
              className={({ isActive }) =>
                `rounded-full px-3 py-1.5 text-sm transition-all ${
                  isActive ? "bg-primary text-white font-semibold shadow-xs" : "text-muted hover:text-ink font-medium"
                }`
              }
            >
              Library
            </NavLink>

            {user && (
              <div ref={accountRef} className="relative">
                <button
                  type="button"
                  className="rounded-full text-xs font-semibold text-white bg-primary hover:bg-primary/90 flex items-center justify-center w-8 h-8 uppercase tracking-wider"
                  aria-expanded={accountOpen}
                  onClick={() => setAccountOpen((open) => !open)}
                  title={user.email}
                >
                  {initials(user.email)}
                </button>
                {accountOpen && (
                  <div className="absolute right-0 mt-2 w-56 rounded-2xl border border-ink/10 bg-card p-3 shadow-card">
                    <p className="truncate px-2 py-1 text-sm text-muted">{user.email}</p>
                    <button
                      type="button"
                      className="mt-1 w-full rounded-xl px-2 py-2 text-left text-sm text-ink hover:bg-bg"
                      onClick={() => {
                        setAccountOpen(false);
                        logout();
                      }}
                    >
                      Sign out
                    </button>
                  </div>
                )}
              </div>
            )}
          </nav>
        </div>
      </header>
      <main className={location.pathname === "/job" || location.pathname === "/result" || location.pathname === "/run" ? "" : "mx-auto max-w-6xl px-5 py-8 pb-16"}>{children}</main>
    </div>
  );
}
