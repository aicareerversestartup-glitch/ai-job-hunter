import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api/client";
import type { Dashboard, DiscoveryRun, ProfileIO } from "../api/types";
import { formatDate, useToast } from "../components/ui";
import PrepareTop from "../components/PrepareTop";
import WaitingPanel from "../components/WaitingPanel";

export default function Overview() {
  const toast = useToast();
  const [stats, setStats] = useState<Dashboard | null>(null);
  const [profile, setProfile] = useState<ProfileIO | null>(null);
  const [runs, setRuns] = useState<{ running: boolean; runs: DiscoveryRun[] }>({ running: false, runs: [] });

  const load = () => {
    get<Dashboard>("/api/dashboard").then(setStats).catch(() => {});
    get<ProfileIO>("/api/profile").then(setProfile).catch(() => {});
    get<{ running: boolean; runs: DiscoveryRun[] }>("/api/discovery/runs").then(setRuns).catch(() => {});
  };
  useEffect(load, []);
  useEffect(() => {
    if (!runs.running) return;
    const t = window.setTimeout(load, 4000);
    return () => window.clearTimeout(t);
  }, [runs]);

  const findJobs = async () => {
    try {
      await post("/api/discovery/run");
      toast("Searching your job sources. New matches will appear in Jobs.");
      setRuns((r) => ({ ...r, running: true }));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const steps = [
    { done: stats?.cv_status === "verified", label: "Upload and verify your Master CV", to: "/cv",
      note: stats?.cv_status === "needs_review" ? "Uploaded. Review the parsed sections and verify them." : "" },
    { done: Boolean(profile?.preferences.preferred_countries.length), label: "Add your countries (in order of preference) and any roles you want first", to: "/profile" },
    { done: Boolean(profile?.profile.work_authorized_countries.length), label: "State where you can work", to: "/profile",
      note: "Used to answer authorization questions. Never guessed." },
    { done: Boolean(profile?.preferences.target_companies?.length), label: "Add target companies and countries", to: "/companies" },
    { done: (stats?.jobs_total ?? 0) > 0, label: "Run your first job search", to: "/jobs" },
  ];
  const setupDone = steps.every((s) => s.done);
  const last = runs.runs[0];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p>Nothing is sent to an employer until you approve it.</p>
        </div>
        <button className="btn primary" onClick={findJobs} disabled={runs.running}>
          {runs.running ? "Searching…" : "Find jobs now"}
        </button>
      </div>

      {!setupDone && (
        <section className="panel">
          <h2>Set up</h2>
          <ul className="checklist">
            {steps.map((s) => (
              <li key={s.label}>
                <span className={`mark ${s.done ? "ok" : ""}`}>{s.done ? "✓" : "○"}</span>
                <span>
                  <Link to={s.to}>{s.label}</Link>
                  {s.note && !s.done && <span className="faint"> {s.note}</span>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {stats && (
        <div className="grid-3" style={{ marginBottom: 20 }}>
          <Link to="/jobs?min_score=75" className="stat" style={{ color: "inherit", textDecoration: "none" }}>
            <b>{stats.strong_matches}</b><span>Strong matches waiting (75+)</span>
          </Link>
          <Link to="/applications" className="stat" style={{ color: "inherit", textDecoration: "none" }}>
            <b>{stats.awaiting_review + stats.needs_action}</b><span>Applications that need you</span>
          </Link>
          <div className="stat">
            <b>{stats.interview_rate !== null ? `${stats.interview_rate}%` : "–"}</b>
            <span>Interview rate ({stats.interviewed} of {stats.submitted} submitted)</span>
          </div>
          <Link to="/inbox" className="stat" style={{ color: "inherit", textDecoration: "none" }}>
            <b>{stats.pending_emails}</b><span>Company emails to confirm</span>
          </Link>
          <Link to="/applications" className="stat" style={{ color: "inherit", textDecoration: "none" }}>
            <b>{stats.follow_ups_due}</b><span>Follow-ups due (no reply after 7 days)</span>
          </Link>
          <div className="stat"><b>{stats.offers}</b><span>Offers</span></div>
        </div>
      )}

      {runs.running && <WaitingPanel title="Searching your countries and companies for new jobs" />}
      {stats?.cv_status === "verified" && <PrepareTop />}

      <section className="panel">
        <div className="panel-head"><h2>Last search</h2><Link to="/sources">Manage sources</Link></div>
        {!last && <p className="muted">No searches yet. Searches also run automatically every few hours once your targets are set.</p>}
        {last && (
          <>
            <p>
              {formatDate(last.started_at)}: checked {last.stats.sources ?? 0} sources, {last.stats.fetched ?? 0} postings,
              {" "}{last.stats.relevant ?? 0} relevant, <strong>{last.stats.new ?? 0} new</strong>,
              {" "}{last.stats.duplicates ?? 0} duplicates merged
              {last.stats.high_risk ? `, ${last.stats.high_risk} hidden as high fraud risk` : ""}.
            </p>
            {last.errors.length > 0 && (
              <div className="notice warn">
                <p>Some sources failed:</p>
                <ul>{last.errors.map((e) => <li key={e.source}><strong>{e.source}</strong>: {e.error}</li>)}</ul>
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}
