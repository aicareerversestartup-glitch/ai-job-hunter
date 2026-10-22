import { Fragment, useEffect, useState, type FormEvent } from "react";
import AdSlot, { feedAdAfter } from "../components/Ads";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { get, patch, post } from "../api/client";
import type { JobRow } from "../api/types";
import { Destination, Field, REMOTE_LABEL, RiskPill, TYPE_LABEL, formatDate, salaryText, useToast } from "../components/ui";

interface Page { total: number; page: number; page_size: number; items: JobRow[] }

export default function Jobs() {
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<Page | null>(null);
  const [adding, setAdding] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const filters = {
    q: params.get("q") ?? "", min_score: params.get("min_score") ?? "0", status: params.get("status") ?? "",
    remote: params.get("remote") ?? "", sort: params.get("sort") ?? "priority", include_high_risk: params.get("risk") === "1",
    page: Number(params.get("page") ?? "1"),
  };

  const load = () => {
    const qs = new URLSearchParams({ q: filters.q, min_score: filters.min_score, sort: filters.sort, page: String(filters.page) });
    if (filters.status) qs.set("status", filters.status);
    if (filters.remote) qs.set("remote", filters.remote);
    if (filters.include_high_risk) qs.set("include_high_risk", "true");
    get<Page>(`/api/jobs?${qs}`).then(setData).catch((e) => toast(e.message, "error"));
  };
  useEffect(load, [params]);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    next.delete("page");
    setParams(next, { replace: true });
  };

  const setStatus = async (job: JobRow, status: string) => {
    await patch(`/api/jobs/${job.id}`, { status }).catch((e) => toast(e.message, "error"));
    load();
  };

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Jobs</h1>
          <p>{data ? `${data.total} postings` : "Loading"} ranked against your verified Master CV.</p>
        </div>
        <button className="btn" onClick={() => setAdding(!adding)}>{adding ? "Close" : "Add a job yourself"}</button>
      </div>

      {adding && <AddJob onAdded={(id) => navigate(`/jobs/${id}`)} />}

      <button className="btn small filters-toggle" onClick={() => setShowFilters(!showFilters)} aria-expanded={showFilters}>
        {showFilters ? "Hide filters" : "Filters and sorting"}
      </button>
      <div className={`filters${showFilters ? " open" : ""}`}>
        <Field label="Search"><input type="text" value={filters.q} placeholder="Title, company or place"
                                     onChange={(e) => setFilter("q", e.target.value)} /></Field>
        <div className="more-filter"><Field label="Minimum match">
          <select value={filters.min_score} onChange={(e) => setFilter("min_score", e.target.value)}>
            <option value="0">Any</option><option value="45">45+</option><option value="60">60+</option><option value="75">75+</option>
          </select>
        </Field></div>
        <div className="more-filter"><Field label="Status">
          <select value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
            <option value="">Active</option><option value="new">New</option><option value="shortlisted">Shortlisted</option>
            <option value="applied">Applied</option><option value="dismissed">Dismissed</option>
          </select>
        </Field></div>
        <div className="more-filter"><Field label="Work setting">
          <select value={filters.remote} onChange={(e) => setFilter("remote", e.target.value)}>
            <option value="">Any</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option>
          </select>
        </Field></div>
        <div className="more-filter"><Field label="Sort by">
          <select value={filters.sort} onChange={(e) => setFilter("sort", e.target.value)}>
            <option value="priority">Best for you</option><option value="score">Highest match score</option><option value="newest">Newest found</option><option value="posted">Recently posted</option>
          </select>
        </Field></div>
      </div>
      <label className="check">
        <input type="checkbox" checked={filters.include_high_risk} onChange={(e) => setFilter("risk", e.target.checked ? "1" : "")} />
        <span>Show postings flagged as high fraud risk</span>
      </label>

      {data && data.items.length === 0 && (
        <div className="empty">
          <h3>No jobs match these filters</h3>
          <p className="muted">Run a search from Overview, add company boards under Job sources, or paste a job you found yourself.</p>
        </div>
      )}

      <div className="job-list">
        {data?.items.map((job, index) => (
          <Fragment key={job.id}>
          <article className="job-card">
            <Destination job={job} />
            <div className="job-body">
              <h3><Link to={`/jobs/${job.id}`}>{job.title}</Link></h3>
              <div className="job-meta">
                <span>{job.company}</span>
                {job.location && <span>{job.location}</span>}
                {REMOTE_LABEL[job.remote_type] && <span>{REMOTE_LABEL[job.remote_type]}</span>}
                {TYPE_LABEL[job.employment_type] && <span>{TYPE_LABEL[job.employment_type]}</span>}
                {salaryText(job.salary_min, job.salary_max, job.salary_currency) && <span>{salaryText(job.salary_min, job.salary_max, job.salary_currency)}</span>}
                <span>{job.posted_at ? `Posted ${formatDate(job.posted_at)}` : `Found ${formatDate(job.discovered_at)}`}</span>
              </div>
              <div className="tags">
                <RiskPill level={job.risk_level} />
                {job.match?.priority?.role_tier === 0 && <span className="tag verified">Your role</span>}
                {job.match?.priority?.role_tier === 1 && <span className="tag">Fits your CV: {job.match.priority.matched_role}</span>}
                {job.match?.matched_skills?.slice(0, 4).map((s) => <span className="tag verified" key={s}>{s}</span>)}
                {!!job.match?.missing_count && <span className="tag missing">{job.match.missing_count} missing requirement{job.match.missing_count > 1 ? "s" : ""}</span>}
                {job.match?.dealbreakers?.map((d) => <span className="tag blocked" key={d}>{d}</span>)}
              </div>
              <div className="job-actions">
                {job.status !== "shortlisted" && job.status !== "applied" && (
                  <button className="btn small" onClick={() => setStatus(job, "shortlisted")}>Shortlist</button>
                )}
                {job.status !== "dismissed"
                  ? <button className="btn small quiet" onClick={() => setStatus(job, "dismissed")}>Dismiss</button>
                  : <button className="btn small quiet" onClick={() => setStatus(job, "new")}>Restore</button>}
              </div>
            </div>
            <div className="job-score">
              {job.match ? <><span className="match-score">{job.match.score}</span><div className="faint">match</div></>
                : <span className="faint">Not scored</span>}
            </div>
          </article>
          {feedAdAfter(index, data.items.length) && <AdSlot placement="feed" />}
          </Fragment>
        ))}
      </div>

      {pages > 1 && (
        <div className="row" style={{ marginTop: 16 }}>
          <button className="btn small" disabled={filters.page <= 1} onClick={() => setFilter("page", String(filters.page - 1))}>Previous</button>
          <span className="faint">Page {filters.page} of {pages}</span>
          <button className="btn small" disabled={filters.page >= pages} onClick={() => setFilter("page", String(filters.page + 1))}>Next</button>
        </div>
      )}
    </>
  );
}

function AddJob({ onAdded }: { onAdded: (id: number) => void }) {
  const toast = useToast();
  const [tab, setTab] = useState<"url" | "paste">("url");
  const [url, setUrl] = useState("");
  const [form, setForm] = useState({ title: "", company: "", location: "", url: "", apply_url: "", description: "" });
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = tab === "url"
        ? await post<{ id: number; duplicate: boolean }>("/api/jobs/import-url", { url })
        : await post<{ id: number; duplicate: boolean }>("/api/jobs/manual", form);
      toast(res.duplicate ? "You already have this job." : "Job added and scored.");
      onAdded(res.id);
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel" onSubmit={submit}>
      <div className="tabs" role="tablist">
        <button type="button" role="tab" className="tab" aria-selected={tab === "url"} onClick={() => setTab("url")}>From a link</button>
        <button type="button" role="tab" className="tab" aria-selected={tab === "paste"} onClick={() => setTab("paste")}>Paste the details</button>
      </div>
      {tab === "url" ? (
        <Field label="Job page link" hint="Works for most company career pages. LinkedIn, Indeed and similar sites block automated reading; paste those instead.">
          <input type="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
        </Field>
      ) : (
        <>
          <div className="entry-grid">
            <Field label="Job title"><input type="text" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
            <Field label="Company"><input type="text" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></Field>
            <Field label="Location"><input type="text" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
            <Field label="Posting link"><input type="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></Field>
          </div>
          <Field label="Application page link" hint="Where you'll actually apply, if different from the posting.">
            <input type="url" value={form.apply_url} onChange={(e) => setForm({ ...form, apply_url: e.target.value })} />
          </Field>
          <Field label="Job description">
            <textarea required minLength={50} rows={10} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
        </>
      )}
      <button className="btn primary" type="submit" disabled={busy}>{busy ? "Adding…" : "Add job"}</button>
    </form>
  );
}
