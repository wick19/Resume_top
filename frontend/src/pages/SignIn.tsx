import { lazy, Suspense, FormEvent, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { changePassword, login, register, setToken } from "../api";
import { useAuth } from "../auth";
import BlurText from "../components/BlurText";
import GradientText from "../components/GradientText";

const SilkStage = lazy(() => import("../components/SilkStage"));

export default function SignIn() {
  const { user, ready, refresh } = useAuth();
  const next = "/home";
  const [mode, setMode] = useState<"signin" | "reset">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (ready && user) return <Navigate to={next} replace />;

  async function submit(path: "login" | "register") {
    setError("");
    setBusy(true);
    try {
      const data = path === "login" ? await login(email, password) : await register(email, password);
      setToken(data.token);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth failed");
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword() {
    setError("");
    if (password !== confirm) {
      setError("Those passwords don’t match.");
      return;
    }
    setBusy(true);
    try {
      const data = await changePassword(email, password);
      setToken(data.token);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the password");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (mode === "reset") resetPassword();
    else submit("login");
  }

  return (
    <div className="grid min-h-screen bg-bg lg:grid-cols-[1.12fr_0.88fr]">
      <section className="relative min-h-[46vh] overflow-hidden lg:min-h-screen">
        <div className="absolute inset-0">
          <Suspense fallback={<div className="h-full bg-[#0040f0]" />}>
            <SilkStage ribbon />
          </Suspense>
        </div>
        <div className="relative z-10 flex h-full flex-col justify-center px-8 py-14 sm:px-14">
          <Link to="/home" className="brand inline-flex items-center gap-3 text-lg font-medium">
            <img src="/mark.png" alt="" width={48} height={48} className="brand-mark h-12 w-12" />
            <GradientText tone="light">Resume Tailor</GradientText>
          </Link>
          <BlurText
            text="Your resume, fitted to the job."
            className="mt-10 max-w-xl text-[clamp(2.6rem,5vw,4.4rem)] font-medium leading-[0.95] tracking-[-0.04em] text-[#eef3fb]"
          />
          <p className="mt-5 max-w-sm text-base leading-relaxed text-[#eef3fb]/80">
            Tailor your resume to the role you are applying for.
          </p>
        </div>
        <svg
          className="pointer-events-none absolute inset-y-0 -right-px hidden h-full w-28 lg:block"
          viewBox="0 0 120 800"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path fill="#eef3fb" d="M120,0 C70,80 110,180 62,300 C20,410 96,520 48,640 C24,720 70,770 40,800 L120,800 L120,0 Z" />
        </svg>
      </section>

      <div className="flex items-center justify-center px-6 py-12">
        <form className="signin-sheet w-full max-w-md rounded-[28px] bg-card px-8 py-10" onSubmit={onSubmit}>
          <h1 className="text-3xl font-medium tracking-[-0.03em]">
            {mode === "reset" ? "Change password" : "Welcome back"}
          </h1>
          <p className="mt-2 text-sm text-muted">
            {mode === "reset"
              ? "Set a new password for this account."
              : "Sign in to continue tailoring your resume."}
          </p>
          <label className="mt-8 block text-sm text-muted">
            Email address
            <input
              className="signin-field mt-1.5"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="mt-4 block text-sm text-muted">
            <span className="flex items-baseline justify-between gap-3">
              <span>{mode === "reset" ? "New password" : "Password"}</span>
              {mode === "signin" && (
                <button
                  type="button"
                  className="font-medium text-primary"
                  onClick={() => {
                    setError("");
                    setMode("reset");
                  }}
                >
                  Forgot password?
                </button>
              )}
            </span>
            <PasswordField
              value={password}
              shown={show}
              onChange={setPassword}
              onToggle={() => setShow((value) => !value)}
              autoComplete={mode === "reset" ? "new-password" : "current-password"}
            />
          </label>
          {mode === "reset" && (
            <label className="mt-4 block text-sm text-muted">
              Confirm password
              <PasswordField
                value={confirm}
                shown={showConfirm}
                onChange={setConfirm}
                onToggle={() => setShowConfirm((value) => !value)}
                autoComplete="new-password"
              />
            </label>
          )}
          {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
          <button className={`signin-submit btn mt-6 w-full py-2.5 ${busy ? "trail" : ""}`} type="submit" disabled={busy}>
            {mode === "reset" ? "Change password" : "Sign in"}
          </button>
          {mode === "signin" ? (
            <p className="mt-6 text-center text-sm text-muted">
              Don’t have an account?{" "}
              <button
                type="button"
                className="font-medium text-primary"
                disabled={busy}
                onClick={() => submit("register")}
              >
                Create one
              </button>
            </p>
          ) : (
            <p className="mt-6 text-center text-sm text-muted">
              <button
                type="button"
                className="font-medium text-primary"
                onClick={() => {
                  setError("");
                  setConfirm("");
                  setMode("signin");
                }}
              >
                Back to sign in
              </button>
            </p>
          )}
        </form>
      </div>
    </div>
  );
}

function PasswordField({
  value,
  shown,
  onChange,
  onToggle,
  autoComplete,
}: {
  value: string;
  shown: boolean;
  onChange: (value: string) => void;
  onToggle: () => void;
  autoComplete: string;
}) {
  return (
    <span className="relative mt-1.5 block">
      <input
        className="signin-field pr-11"
        type={shown ? "text" : "password"}
        autoComplete={autoComplete}
        placeholder="••••••••"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
      <button
        type="button"
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
        aria-label={shown ? "Hide password" : "Show password"}
        onClick={onToggle}
      >
        <Eye open={shown} />
      </button>
    </span>
  );
}

function Eye({ open }: { open: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <circle cx="12" cy="12" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      {open && <path d="M4 20 20 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />}
    </svg>
  );
}
