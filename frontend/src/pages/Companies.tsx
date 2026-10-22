import { useEffect, useState, type FormEvent } from "react";
import { del, get, post } from "../api/client";
import { openExternal } from "../api/platform";
import type { RegistryCompany, TargetCompany } from "../api/types";
import { Field, TagInput, useToast } from "../components/ui";

const KIND_LABEL: Record<string, string> = {
  company_search: "Job-search APIs", greenhouse: "Greenhouse board", lever: "Lever board", ashby: "Ashby board",
  workable: "Workable board", smartrecruiters: "SmartRecruiters board",
};

export default function Companies() {
  const toast = useToast();
  const [targets, setTargets] = useState<TargetCompany[]>([]);
  const [catalog, setCatalog] = useState<RegistryCompany[]>([]);
  const [name, setName] = useState("");
  const [countries, setCountries] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const load = () => get<TargetCompany[]>("/api/companies").then(setTargets).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
    get<RegistryCompany[]>("/api/companies/catalog").then(setCatalog).catch(() => {});
  }, []);
  // Board detection runs in the background; refresh a few times after changes.
  useEffect(() => {
    if (!targets.some((t) => t.sources.some((s) => s.detection === "running"))) return;
    const t = window.setTimeout(load, 5000);
    return () => window.clearTimeout(t);
  }, [targets]);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await post("/api/companies", { name, countries });
      toast(`${name} added. Looking for its job boards…`);
      setName("");
      setCountries([]);
      load();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const addAll = async () => {
    setBusy(true);
    try {
      const r = await post<{ added: number }>("/api/companies/add-all-from-list");
      toast(`${r.added} companies added with their hub countries.`);
      load();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const hint = catalog.find((c) => c.name.toLowerCase() === name.trim().toLowerCase());

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Target companies</h1>
          <p>Name a company and the countries you want. Jobs are searched for each pair on every run.</p>
        </div>
        {catalog.length > 0 && (
          <button className="btn" onClick={addAll} disabled={busy}>Add all {catalog.length} from my list</button>
        )}
      </div>

      <div className="notice">
        <p>Large employers like DHL, Amazon or Nestlé run their own careers portals with no public API. For those, jobs come
          from Adzuna and Jooble (add the free keys in <code>.env</code>). You can also open the official careers page below,
          copy a job link and use <strong>Jobs → Add a job yourself → From a link</strong>.</p>
      </div>

      <form className="panel" onSubmit={add}>
        <div className="entry-grid">
          <Field label="Company">
            <input type="text" list="company-list" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Maersk" />
            <datalist id="company-list">{catalog.map((c) => <option key={c.name} value={c.name} />)}</datalist>
          </Field>
          <Field label="Countries" hint={hint ? `Leave empty to use its hubs: ${hint.hubs.join(", ")}` : "Leave empty to use the countries in your profile."}>
            <TagInput value={countries} onChange={setCountries} placeholder="e.g. Germany, Netherlands" />
          </Field>
        </div>
        <button className="btn primary" type="submit" disabled={busy}>Add company</button>
      </form>

      {targets.length === 0 && <div className="empty"><p className="muted">No companies yet.</p></div>}
      <div className="job-list">
        {targets.map((t) => (
          <article className="panel" key={t.name} style={{ marginBottom: 0 }}>
            <div className="spread">
              <div>
                <h3 style={{ margin: 0 }}>{t.name}</h3>
                <div className="job-meta">
                  {t.industry && <span>{t.industry}</span>}
                  <span>Countries: {t.countries.join(", ") || "from your profile"}</span>
                </div>
              </div>
              <div className="row">
                {t.careers_url && <button className="btn small" onClick={() => openExternal(t.careers_url)}>Official careers page</button>}
                <button className="btn small danger" onClick={async () => { await del(`/api/companies/${encodeURIComponent(t.name)}`); load(); }}>Remove</button>
              </div>
            </div>
            {t.sponsorship_note && <p className="faint">Visa note from your list (not verified): {t.sponsorship_note}</p>}
            {t.suggested_roles.length > 0 && (
              <div className="tags" style={{ marginBottom: 8 }}>{t.suggested_roles.map((r) => <span className="tag" key={r}>{r}</span>)}</div>
            )}
            <ul className="checklist">
              {t.sources.map((s) => (
                <li key={s.id}>
                  <span className={`mark ${s.last_status === "error" ? "no" : "ok"}`}>{s.last_status === "error" ? "!" : "•"}</span>
                  <span>
                    {KIND_LABEL[s.kind] ?? s.kind}
                    {s.kind === "company_search" && s.detection === "running" && <span className="faint"> (checking for direct job boards…)</span>}
                    {s.last_status === "ok" && <span className="faint"> {s.last_count} postings last run</span>}
                    {s.last_error && <span className="faint"> {s.last_error}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </>
  );
}
