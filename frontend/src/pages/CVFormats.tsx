import { useEffect, useState } from "react";
import { api, del, get } from "../api/client";
import { openExternal } from "../api/platform";
import type { FormatCatalog } from "../api/types";
import { Field, useToast } from "../components/ui";

const PHOTO_LABEL: Record<string, string> = { expected: "Photo expected", common: "Photo common", optional: "Photo optional", no: "No photo" };
const DETAIL_LABEL: Record<string, string> = { dob: "date of birth", nationality: "nationality", visa_status: "visa status", driving_licence: "driving licence" };
const SECTION_LABEL: Record<string, string> = {
  summary: "Summary", skills: "Skills", experience: "Experience", projects: "Projects", education: "Education",
  certifications: "Certifications", languages: "Languages", other: "Other", referees: "Referees",
};

export default function CVFormats() {
  const toast = useToast();
  const [catalog, setCatalog] = useState<FormatCatalog | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => get<FormatCatalog>("/api/cv-formats").then(setCatalog).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, []);

  const learn = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", name);
      const body = await api<{ section_order: string[]; max_pages: number }>("/api/cv-layouts/sample", { method: "POST", body: form });
      toast(`Layout learned: ${body.section_order.length} sections, ${body.max_pages} page(s).`);
      setFile(null);
      setName("");
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  if (!catalog) return <p className="muted">Loading…</p>;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>CV formats</h1>
          <p>Each application uses the format of the job's country. You can switch format and style on the review screen.</p>
        </div>
      </div>

      <section className="panel">
        <h2>Use a sample CV's layout</h2>
        <p className="muted">Found a sample CV online that you like? Upload it. Only its structure is kept: section order, headings,
          length, photo, which personal details it shows. Its text is thrown away and never appears in your CV.</p>
        <div className="entry-grid">
          <Field label="Sample CV (PDF or Word)">
            <input type="file" accept=".pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          <Field label="Name for this layout"><input type="text" value={name} placeholder="e.g. Dubai ops manager sample" onChange={(e) => setName(e.target.value)} /></Field>
        </div>
        <button className="btn primary" disabled={!file || busy} onClick={learn}>{busy ? "Reading…" : "Learn layout"}</button>
        {catalog.custom_layouts.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {catalog.custom_layouts.map((l) => (
              <div className="entry spread" key={l.id}>
                <div>
                  <strong>{l.name}</strong>
                  <div className="faint">
                    {l.section_order.map((s) => l.headings[s] || SECTION_LABEL[s]).join(" → ")} · {l.max_pages} page(s) · {l.photo ? "with photo" : "no photo"}
                  </div>
                </div>
                <button className="btn small danger" onClick={async () => { await del(`/api/cv-layouts/${l.id}`); load(); }}>Remove</button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Country formats</h2>
        <p className="faint">Based on public sample CVs and official guidance. Personal details only appear if you filled them in on your profile.</p>
        <div className="grid-2">
          {catalog.countries.map((f) => (
            <div className="entry" key={f.code}>
              <div className="spread">
                <strong>{f.country}</strong>
                <span className="faint">{f.document_title}</span>
              </div>
              <div className="tags" style={{ margin: "6px 0" }}>
                <span className="tag">Up to {f.max_pages} page{f.max_pages > 1 ? "s" : ""}</span>
                <span className={`tag ${f.photo === "no" ? "" : "verified"}`}>{PHOTO_LABEL[f.photo]}</span>
                {f.personal_details.length > 0 && <span className="tag">Shows {f.personal_details.map((d) => DETAIL_LABEL[d]).join(", ")}</span>}
                {f.referees === "list" && <span className="tag">Referees listed</span>}
              </div>
              <div className="faint">{f.section_order.map((s) => SECTION_LABEL[s]).join(" → ")}</div>
              <ul style={{ paddingLeft: 18, margin: "8px 0 0" }}>{f.tips.map((t) => <li key={t} className="faint">{t}</li>)}</ul>
              {f.sources.length > 0 && (
                <div className="faint" style={{ marginTop: 6 }}>
                  Sources: {f.sources.map((s, i) => <button key={s} className="btn quiet small" onClick={() => openExternal(s)}>[{i + 1}]</button>)}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
