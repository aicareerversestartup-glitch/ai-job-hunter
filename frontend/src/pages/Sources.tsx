import { useEffect, useState, type FormEvent } from "react";
import { del, get, patch, post } from "../api/client";
import type { JobSource, SourceType } from "../api/types";
import { Field, formatDate, useToast } from "../components/ui";

export default function Sources() {
  const toast = useToast();
  const [sources, setSources] = useState<JobSource[]>([]);
  const [catalog, setCatalog] = useState<SourceType[]>([]);
  const [kind, setKind] = useState("greenhouse");
  const [identifier, setIdentifier] = useState("");

  const load = () => get<JobSource[]>("/api/sources").then(setSources).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); get<SourceType[]>("/api/sources/catalog").then(setCatalog); }, []);

  const selected = catalog.find((c) => c.kind === kind);
  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await post("/api/sources", { kind, identifier });
      setIdentifier("");
      toast("Source added. It's included in the next search.");
      load();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Job sources</h1>
          <p>Official job APIs and employer career boards. Sites that forbid automated access aren't searched; add those jobs by pasting them.</p>
        </div>
      </div>

      <form className="panel" onSubmit={add}>
        <h2>Add a source</h2>
        <p className="muted">The best results come from the career boards of companies you'd like to work for. Find the board name in their careers page link, for example boards.greenhouse.io/<strong>companyname</strong>.</p>
        <div className="entry-grid">
          <Field label="Type">
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {catalog.map((c) => <option key={c.kind} value={c.kind}>{c.name}</option>)}
            </select>
          </Field>
          {selected?.needs_identifier && (
            <Field label={kind === "rss" ? "Feed link" : "Board name"} hint={selected.identifier_help}>
              <input type="text" required value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
            </Field>
          )}
        </div>
        {selected?.terms_note && <p className="faint">{selected.terms_note}</p>}
        <button className="btn primary" type="submit">Add source</button>
      </form>

      <section className="panel">
        <h2>Your sources</h2>
        {sources.map((s) => (
          <div className="entry spread" key={s.id}>
            <div>
              <strong>{s.label || s.kind}</strong>
              <div className="faint">
                {s.last_run_at ? `Last checked ${formatDate(s.last_run_at)}: ${s.last_status === "ok" ? `${s.last_count} postings` : s.last_error}` : "Not checked yet"}
              </div>
            </div>
            <div className="row">
              <label className="check" style={{ margin: 0 }}>
                <input type="checkbox" checked={s.enabled} onChange={async (e) => { await patch(`/api/sources/${s.id}`, { enabled: e.target.checked }); load(); }} />
                <span>Included</span>
              </label>
              <button className="btn small danger" onClick={async () => { await del(`/api/sources/${s.id}`); load(); }}>Remove</button>
            </div>
          </div>
        ))}
      </section>
    </>
  );
}
