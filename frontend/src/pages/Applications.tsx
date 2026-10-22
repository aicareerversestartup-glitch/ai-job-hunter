import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import type { ApplicationRow } from "../api/types";
import { formatDate, useToast } from "../components/ui";
import PrepareTop from "../components/PrepareTop";

const COLUMNS: { title: string; statuses: string[]; hint: string }[] = [
  { title: "To review", statuses: ["draft", "ready_for_review"], hint: "Drafted. Check and approve." },
  { title: "Approved", statuses: ["approved", "submitting", "needs_user_action"], hint: "Ready to send." },
  { title: "Submitted", statuses: ["submitted", "in_review"], hint: "Waiting to hear back." },
  { title: "Interviewing", statuses: ["interviewing"], hint: "" },
  { title: "Offers", statuses: ["offer", "accepted"], hint: "" },
  { title: "Closed", statuses: ["rejected", "withdrawn", "discarded"], hint: "" },
];

export default function Applications() {
  const toast = useToast();
  const [rows, setRows] = useState<ApplicationRow[] | null>(null);
  useEffect(() => { get<ApplicationRow[]>("/api/applications").then(setRows).catch((e) => toast(e.message, "error")); }, []);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Applications</h1>
          <p>Every application goes draft, review, your approval, then apply.</p>
        </div>
      </div>
      <PrepareTop />
      {rows && rows.length === 0 && (
        <div className="empty">
          <h3>No applications yet</h3>
          <p className="muted">Open a job and choose Draft application. You'll review everything before anything is sent.</p>
          <Link className="btn primary" to="/jobs">Browse jobs</Link>
        </div>
      )}
      {rows && rows.length > 0 && (
        <div className="board">
          {COLUMNS.map((col) => {
            const items = rows.filter((r) => col.statuses.includes(r.status));
            return (
              <section className="column" key={col.title} aria-label={col.title}>
                <h3>{col.title}<span className="faint">{items.length}</span></h3>
                {items.length === 0 && col.hint && <p className="faint" style={{ margin: "0 4px" }}>{col.hint}</p>}
                {items.map((r) => (
                  <Link className="card" to={`/applications/${r.id}`} key={r.id}>
                    <strong>{r.title}</strong>
                    <span className="muted">{r.company}</span>
                    <div className="spread" style={{ marginTop: 6 }}>
                      <span className="faint">{r.submitted_at ? `Sent ${formatDate(r.submitted_at)}` : `Updated ${formatDate(r.updated_at)}`}</span>
                      <span className={`pill ${r.status === "needs_user_action" ? "warn" : r.match_score >= 75 ? "good" : ""}`}>
                        {r.status === "needs_user_action" ? "Needs you" : r.match_score}
                      </span>
                    </div>
                  </Link>
                ))}
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
