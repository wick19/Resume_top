import { useEffect } from "react";
import { Link } from "react-router-dom";
import Grain from "../components/Grain";
import ResultPanel from "../components/ResultPanel";
import { loadResult, markResultSeen } from "../session";

export default function Result() {
  const result = loadResult();
  useEffect(() => {
    if (result) markResultSeen();
  }, [result]);

  return (
    <div className="fit-page">
      <div className="fit-field" aria-hidden="true">
        <Grain />
      </div>
      <div className="fit-canvas">
        {result ? (
          <ResultPanel result={result} />
        ) : (
          <div>
            <h1 className="text-3xl font-medium tracking-tight">No result yet</h1>
            <p className="mt-2 text-sm text-muted">A finished run lands here, with the score, the skim, and the gaps.</p>
            <Link to="/job" className="btn mt-6">
              Fit a job
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
