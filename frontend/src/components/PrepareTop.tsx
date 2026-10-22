import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api/client";
import type { BatchStatus } from "../api/types";
import { useToast } from "./ui";
import WaitingPanel from "./WaitingPanel";

const SKIP_LABEL: Record<string, string> = {
  low_score: "below your minimum match", dealbreaker: "with a dealbreaker", high_risk: "flagged as risky",
  snippet_only: "with only a short description",
};

/** One click: draft tailored applications for the best jobs. Each one still waits for your approval. */
export default function PrepareTop({ count = 10 }: { count?: number }) {
  const toast = useToast();
  const [status, setStatus] = useState<BatchStatus>({ running: false });
  const [limitHit, setLimitHit] = useState("");

  const poll = () => get<BatchStatus>("/api/applications/prepare-top/status").then(setStatus).catch(() => {});
  useEffect(() => { poll(); }, []);
  useEffect(() => {
    if (!status.running) return;
    const t = window.setTimeout(poll, 2500);
    return () => window.clearTimeout(t);
  }, [status]);

  const start = async () => {
    try {
      const s = await post<BatchStatus>("/api/applications/prepare-top", { count });
      setStatus(s);
      if (!s.total) toast("No new jobs qualify right now. Run a search or lower your minimum match.", "error");
    } catch (e) {
      const err = e as Error & { status?: number };
      if (err.status === 422 || err.status === 429) setLimitHit(err.message);
      else toast(err.message, "error");
    }
  };

  const skipped = Object.entries(status.skipped ?? {}).filter(([, n]) => n > 0);
  return (
    <section className="panel">
      <div className="spread">
        <div>
          <h2 style={{ marginBottom: 4 }}>Prepare my top {count} applications</h2>
          <p className="muted" style={{ margin: 0 }}>Your country list first, then your roles, then roles from your CV. Each gets its own CV in that country's format, a cover letter and answers. Nothing is sent until you approve it.</p>
        </div>
        <button className="btn primary" onClick={start} disabled={status.running}>
          {status.running ? `Preparing ${status.done ?? 0} of ${status.total ?? 0}…` : `Prepare top ${count}`}
        </button>
      </div>
      {limitHit && (
        <div className="notice warn" style={{ marginTop: 12 }}>
          <p>{limitHit}</p>
          <Link className="btn small primary" to="/plans">See options</Link>
        </div>
      )}
      {status.running && (
        <div style={{ marginTop: 14 }}>
          <WaitingPanel title="Writing a tailored CV, cover letter and answers for each job" done={status.done} total={status.total} />
        </div>
      )}
      {!status.running && status.created && status.created.length > 0 && (
        <div className="notice good" style={{ marginTop: 12 }}>
          <p>{status.created.length} application(s) ready for your review. <Link to="/applications">Review and approve them</Link>.</p>
        </div>
      )}
      {!status.running && skipped.length > 0 && (
        <p className="faint" style={{ marginTop: 8 }}>Skipped: {skipped.map(([k, n]) => `${n} ${SKIP_LABEL[k] ?? k}`).join(", ")}.</p>
      )}
      {!status.running && (status.errors?.length ?? 0) > 0 && (
        <p className="faint">{status.errors!.length} could not be drafted: {status.errors![0].error}</p>
      )}
    </section>
  );
}
