import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { get, patch, post } from "../api/client";
import { openExternal } from "../api/platform";
import Icon from "../components/Icon";
import type { ApplicationRow, JobRow, MissingRequirement } from "../api/types";
import { MatchBar, REMOTE_LABEL, TYPE_LABEL, formatDate, salaryText, useToast } from "../components/ui";

export function MissingList({ items }: { items: MissingRequirement[] }) {
  if (!items.length) return <p className="muted">Your Master CV covers every requirement we could detect.</p>;
  const sorted = [...items].sort((a, b) => (a.importance === b.importance ? 0 : a.importance === "required" ? -1 : 1));
  return (
    <ul className="missing-list">
      {sorted.map((m, i) => (
        <li key={i} className={m.importance}>
          <div className="missing-label">MISSING REQUIREMENT{m.importance === "preferred" ? " (nice to have)" : ""}</div>
          <strong>{m.requirement}</strong>
          <div className="faint">{m.detail}</div>
        </li>
      ))}
    </ul>
  );
}

export default function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [job, setJob] = useState<JobRow | null>(null);
  const [existing, setExisting] = useState<ApplicationRow | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    get<JobRow>(`/api/jobs/${id}`).then(setJob).catch((e) => toast(e.message, "error"));
    get<ApplicationRow[]>("/api/applications").then((rows) =>
      setExisting(rows.find((r) => r.job_id === Number(id) && r.status !== "discarded") ?? null)).catch(() => {});
  };
  useEffect(load, [id]);

  if (!job) return <p className="muted">Loading…</p>;
  const result = job.match?.result;
  const flagged = job.risk_level === "high" && !job.quality.user_override;

  const draft = async () => {
    setBusy(true);
    try {
      const app = await post<{ id: number }>("/api/applications", { job_id: job.id });
      navigate(`/applications/${app.id}`);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const overrideRisk = async () => {
    await patch(`/api/jobs/${job.id}`, { override_risk: true });
    toast("Marked as checked by you.");
    load();
  };

  return (
    <>
      <p><Link to="/jobs">Back to jobs</Link></p>
      <div className="page-head">
        <div>
          <h1>{job.title}</h1>
          <p>
            {job.company}{job.location ? `, ${job.location}` : ""}
            {REMOTE_LABEL[job.remote_type] ? ` (${REMOTE_LABEL[job.remote_type]})` : ""}
          </p>
        </div>
        <div className="row">
          <button className="btn" onClick={() => openExternal(job.url)}><Icon name="external" size={16} />Original posting</button>
          {existing
            ? <Link className="btn primary" to={`/applications/${existing.id}`}>Open application</Link>
            : <button className="btn primary" onClick={draft} disabled={busy || flagged || !job.match}>
                {busy ? "Drafting…" : "Draft application"}
              </button>}
        </div>
      </div>
      {!job.match && <div className="notice warn">Verify your Master CV to score this job and draft an application.</div>}

      <div className="review-grid">
        <div>
          {job.quality.flags.length > 0 && (
            <section className={`notice ${job.risk_level === "high" ? "bad" : "warn"}`}>
              <p><strong>{job.risk_level === "high" ? "This posting looks risky." : "Things to check about this posting"}</strong></p>
              <ul>{job.quality.flags.map((f) => <li key={f.code}>{f.message}</li>)}</ul>
              {flagged && (
                <p>
                  Drafting is disabled for high-risk postings. If you have confirmed the employer is genuine,{" "}
                  <button className="btn small" onClick={overrideRisk}>I checked, it's genuine</button>
                </p>
              )}
            </section>
          )}
          <section className="panel">
            <h2>Job description</h2>
            <div className="job-meta">
              {TYPE_LABEL[job.employment_type] && <span>{TYPE_LABEL[job.employment_type]}</span>}
              {job.seniority !== "unknown" && <span>Level: {job.seniority}</span>}
              {salaryText(job.salary_min, job.salary_max, job.salary_currency) && <span>{salaryText(job.salary_min, job.salary_max, job.salary_currency)}</span>}
              {job.posted_at && <span>Posted {formatDate(job.posted_at)}</span>}
              <span>Source: {job.source}</span>
            </div>
            {job.snippet_only && (
              <div className="notice warn"><p>This source only shares a short snippet. Open the original posting for the full job description before drafting.</p></div>
            )}
            {job.jd_sections && job.jd_sections.length > 1 ? (
              job.jd_sections.map((sec) => (
                <div key={sec.key} style={{ marginBottom: 14 }}>
                  <h3>{sec.label}</h3>
                  {sec.lines.length > 1
                    ? <ul style={{ paddingLeft: 20, margin: 0 }}>{sec.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
                    : <p>{sec.lines[0]}</p>}
                </div>
              ))
            ) : <div className="desc">{job.description_text}</div>}
            {job.also_seen_on.length > 0 && (
              <p className="faint" style={{ marginTop: 12 }}>
                Also listed on: {job.also_seen_on.map((s) => <button key={s.url} className="btn quiet small" onClick={() => openExternal(s.url)}>{s.source}</button>)}
              </p>
            )}
          </section>
        </div>

        <aside className="review-side">
          {result && (
            <section className="panel">
              <h3>Match</h3>
              <MatchBar score={result.score} components={result.components} />
              {result.dealbreakers.length > 0 && (
                <div className="notice bad" style={{ marginTop: 12 }}>
                  <ul>{result.dealbreakers.map((d) => <li key={d}>{d}</li>)}</ul>
                </div>
              )}
              <ul style={{ paddingLeft: 18, marginTop: 12 }}>{result.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              <p className="faint">Experience on your CV: about {result.years_experience} years.</p>
            </section>
          )}
          {result && (
            <section className="panel">
              <h3>Skills you have</h3>
              <div className="tags">
                {result.matched_skills.length ? result.matched_skills.map((s) => <span className="tag verified" key={s}>{s}</span>)
                  : <span className="muted">None of the listed skills were found on your CV.</span>}
              </div>
            </section>
          )}
          {result && (
            <section className="panel">
              <h3>What you're missing</h3>
              <MissingList items={result.missing_requirements} />
              <p className="faint" style={{ marginTop: 12 }}>These are never added to your CV. Mention genuine related experience in your own words if you have it.</p>
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
