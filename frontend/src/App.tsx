import { lazy, Suspense, type ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Shell from "./components/Shell";
import Job from "./pages/Job";
import Library from "./pages/Library";
import Result from "./pages/Result";
import Run from "./pages/Run";
import SignIn from "./pages/SignIn";

const Landing = lazy(() => import("./pages/Landing"));

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, ready } = useAuth();
  if (!ready) return <p className="px-5 py-10 text-sm text-muted">Checking the session…</p>;
  if (!user) return <Navigate to="/signin" replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/home" replace />} />
      <Route
        path="/home"
        element={
          <Suspense fallback={<p className="px-5 py-10 text-sm text-muted">Loading…</p>}>
            <Landing />
          </Suspense>
        }
      />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/library" element={<RequireAuth><Library /></RequireAuth>} />
      <Route path="/job" element={<RequireAuth><Job /></RequireAuth>} />
      <Route path="/run" element={<RequireAuth><Run /></RequireAuth>} />
      <Route path="/result" element={<RequireAuth><Result /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}
