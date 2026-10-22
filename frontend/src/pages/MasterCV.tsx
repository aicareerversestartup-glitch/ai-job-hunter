import { useEffect, useState } from "react";
import { get, post, put, upload } from "../api/client";
import { downloadFile } from "../api/platform";
import type { CVData, Education, Experience, MasterCV } from "../api/types";
import { Field, TagInput, formatDate, useToast } from "../components/ui";

interface CoachTip { role_index: number; bullet_index: number; role: string; bullet: string; suggestion: string }

interface Strength {
  years: number; senior: boolean; score: number; quantified_bullets: number; total_bullets: number;
  tenure: { employers: number; average_months: number; longest_months: number; longest_employer: string;
            short_stints: number; promotions: number; suggest_hybrid: boolean; progression_line: string };
  items: { key: string; label: string; found: boolean; evidence: string[]; question: string }[];
}

function StrengthPanel({ s, onUseLine }: { s: Strength; onUseLine: (line: string) => void }) {
  const missing = s.items.filter((i) => !i.found);
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>What recruiters look for{s.senior ? " at 7+ years" : ""}</h2>
        <span className={`pill ${s.score >= 75 ? "good" : s.score >= 50 ? "warn" : "bad"}`}>{s.score} / 100</span>
      </div>
      <p className="muted">
        About {s.years} years of experience. {s.quantified_bullets} of {s.total_bullets} bullet points have numbers.
        Managers are judged on team size, budget/P&L, savings, vendors, clients and scale.
      </p>
      {s.tenure.employers > 0 && (
        <p className="muted">
          {s.tenure.employers} employer{s.tenure.employers > 1 ? "s" : ""}, average stay {Math.round(s.tenure.average_months / 12 * 10) / 10} years,
          longest {Math.round(s.tenure.longest_months / 12 * 10) / 10} years at {s.tenure.longest_employer}
          {s.tenure.promotions > 0 ? `, ${s.tenure.promotions} internal promotion(s) shown together` : ""}.
          {s.tenure.suggest_hybrid && " Several short stays: choose the Hybrid layout when you review an application, so your results come first."}
        </p>
      )}
      {s.tenure.progression_line && (
        <div className="notice good">
          <p>Your titles show career growth. A summary opening built from your own titles and dates:</p>
          <p><em>{s.tenure.progression_line}</em></p>
          <button className="btn small" onClick={() => onUseLine(s.tenure.progression_line)}>Put it at the start of my summary</button>
        </div>
      )}
      <ul className="checklist">
        {s.items.filter((i) => i.found).map((i) => (
          <li key={i.key}><span className="mark ok">✓</span><span><strong>{i.label}</strong> <span className="faint">“{i.evidence[0]}”</span></span></li>
        ))}
      </ul>
      {missing.length > 0 && (
        <div className="notice warn">
          <p><strong>Not visible on your CV yet.</strong> If these are true for you, add them to the right role's bullet points below, with your real numbers. The app will never invent them.</p>
          <ul>{missing.map((i) => <li key={i.key}><strong>{i.label}:</strong> {i.question}</li>)}</ul>
        </div>
      )}
    </section>
  );
}

interface Summary { id: number; version: number; original_filename: string; status: string; is_active: boolean; created_at: string }

const emptyExp: Experience = { employer: "", title: "", location: "", start: "", end: "", bullets: [] };
const emptyEdu: Education = { institution: "", degree: "", field: "", start: "", end: "", details: [] };

export default function MasterCVPage() {
  const toast = useToast();
  const [cv, setCv] = useState<MasterCV | null | undefined>(undefined);
  const [data, setData] = useState<CVData | null>(null);
  const [versions, setVersions] = useState<Summary[]>([]);
  const [busy, setBusy] = useState("");
  const [showRaw, setShowRaw] = useState(false);
  const [strength, setStrength] = useState<Strength | null>(null);
  const [coach, setCoach] = useState<CoachTip[]>([]);

  const accept = (record: MasterCV | null) => {
    setCv(record);
    setData(record?.data ?? null);
    if (record) {
      get<Strength>(`/api/cv/${record.id}/strength`).then(setStrength).catch(() => {});
      get<CoachTip[]>(`/api/cv/${record.id}/coach`).then(setCoach).catch(() => {});
    }
  };
  const load = () => {
    get<MasterCV | null>("/api/cv/active").then(accept).catch((e) => toast(e.message, "error"));
    get<Summary[]>("/api/cv").then(setVersions).catch(() => {});
  };
  useEffect(load, []);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy("upload");
    try {
      accept(await upload<MasterCV>("/api/cv/upload", file));
      get<Summary[]>("/api/cv").then(setVersions);
      toast("CV read. Check every section, then verify it.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy("");
    }
  };

  const save = async () => {
    if (!cv || !data) return;
    setBusy("save");
    try {
      const saved = await put<MasterCV>(`/api/cv/${cv.id}`, data);
      accept(saved);
      get<Summary[]>("/api/cv").then(setVersions);
      toast(saved.id !== cv.id ? `Saved as version ${saved.version}. Verify it to use it.` : "Saved.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy("");
    }
  };

  const verify = async () => {
    if (!cv) return;
    setBusy("verify");
    try {
      accept(await post<MasterCV>(`/api/cv/${cv.id}/verify`));
      get<Summary[]>("/api/cv").then(setVersions);
      toast("Verified. Jobs are being re-scored against it.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy("");
    }
  };

  const dirty = cv && data && JSON.stringify(cv.data) !== JSON.stringify(data);
  const set = (patch: Partial<CVData>) => data && setData({ ...data, ...patch });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Master CV</h1>
          <p>The only source of facts for every tailored CV, cover letter and answer. Your original file is kept unchanged.</p>
        </div>
        <label className="btn">
          {busy === "upload" ? "Reading…" : cv ? "Upload a new version" : "Upload CV"}
          <input type="file" accept=".pdf,.docx,.txt,.md" hidden onChange={(e) => onFile(e.target.files?.[0])} />
        </label>
      </div>

      {cv === null && (
        <div className="empty">
          <h3>Upload your CV to start</h3>
          <p className="muted">PDF, Word (.docx) or plain text. Scanned PDFs are read with OCR when Tesseract is installed.</p>
        </div>
      )}

      {cv && data && (
        <>
          <div className={`notice ${cv.status === "verified" ? "good" : "warn"}`}>
            <p>
              <strong>Version {cv.version} {cv.status === "verified" ? `verified ${formatDate(cv.verified_at)}` : "needs your review"}.</strong>{" "}
              {cv.status === "verified"
                ? "Edits create a new version, which you verify before it's used."
                : "Fix anything parsed wrongly, then verify. Nothing is matched or tailored until you do."}
            </p>
            {cv.parse_notes.map((n) => <p key={n} className="faint">{n}</p>)}
          </div>

          <div className="row" style={{ marginBottom: 16 }}>
            <button className="btn primary" onClick={save} disabled={!dirty || !!busy}>{busy === "save" ? "Saving…" : "Save changes"}</button>
            {cv.status !== "verified" && <button className="btn primary" onClick={verify} disabled={!!dirty || !!busy}>Verify this CV</button>}
            <button className="btn" onClick={() => downloadFile(`/api/cv/${cv.id}/original`, cv.original_filename).catch((e) => toast(e.message, "error"))}>Download original</button>
            <button className="btn quiet" onClick={() => setShowRaw(!showRaw)}>{showRaw ? "Hide" : "Show"} text read from the file</button>
          </div>
          {showRaw && <pre className="raw">{cv.raw_text}</pre>}

          {strength && <StrengthPanel s={strength} onUseLine={(line) => {
            if (data && !data.summary.startsWith(line)) set({ summary: `${line} ${data.summary}`.trim() });
            toast("Added to your summary. Review it and save.");
          }} />}
          {coach.length > 0 && (
            <section className="panel">
              <h2>Make bullet points result-oriented</h2>
              <p className="muted">
                These {coach.length} lines have no numbers. Recruiters abroad look for what you achieved: team size, %, cost,
                volume, time. Use the template, then replace every [__] with your real figure, or delete the part that doesn't apply.
              </p>
              {coach.map((t) => (
                <div className="entry" key={`${t.role_index}-${t.bullet_index}`}>
                  <div className="faint">{t.role}</div>
                  <div><s className="faint">{t.bullet}</s></div>
                  <div style={{ margin: "4px 0 8px" }}>{t.suggestion}</div>
                  <button className="btn small" disabled={!data} onClick={() => {
                    if (!data) return;
                    set({ experience: data.experience.map((e, i) => i !== t.role_index ? e
                      : { ...e, bullets: e.bullets.map((b, j) => (j === t.bullet_index && b === t.bullet ? t.suggestion : b)) }) });
                    setCoach(coach.filter((c) => c !== t));
                    toast("Template added below. Fill in the blanks with your real numbers, then save.");
                  }}>Use this template</button>
                </div>
              ))}
            </section>
          )}

          <section className="panel">
            <h2>Contact</h2>
            <div className="entry-grid">
              <Field label="Full name"><input type="text" value={data.contact.full_name} onChange={(e) => set({ contact: { ...data.contact, full_name: e.target.value } })} /></Field>
              <Field label="Email"><input type="email" value={data.contact.email} onChange={(e) => set({ contact: { ...data.contact, email: e.target.value } })} /></Field>
              <Field label="Phone"><input type="text" value={data.contact.phone} onChange={(e) => set({ contact: { ...data.contact, phone: e.target.value } })} /></Field>
              <Field label="Location"><input type="text" value={data.contact.location} onChange={(e) => set({ contact: { ...data.contact, location: e.target.value } })} /></Field>
            </div>
            <Field label="Links"><TagInput value={data.contact.links} onChange={(links) => set({ contact: { ...data.contact, links } })} /></Field>
            <Field label="Headline"><input type="text" value={data.headline} onChange={(e) => set({ headline: e.target.value })} /></Field>
            <Field label="Summary"><textarea rows={4} value={data.summary} onChange={(e) => set({ summary: e.target.value })} /></Field>
          </section>

          <section className="panel">
            <div className="panel-head"><h2>Experience</h2><button className="btn small" onClick={() => set({ experience: [...data.experience, { ...emptyExp }] })}>Add role</button></div>
            {data.experience.map((exp, i) => {
              const upd = (p: Partial<Experience>) => set({ experience: data.experience.map((x, j) => (j === i ? { ...x, ...p } : x)) });
              return (
                <div className="entry" key={i}>
                  <div className="entry-grid four">
                    <Field label="Job title"><input type="text" value={exp.title} onChange={(e) => upd({ title: e.target.value })} /></Field>
                    <Field label="Employer"><input type="text" value={exp.employer} onChange={(e) => upd({ employer: e.target.value })} /></Field>
                    <Field label="Start"><input type="text" value={exp.start} placeholder="Jan 2021" onChange={(e) => upd({ start: e.target.value })} /></Field>
                    <Field label="End"><input type="text" value={exp.end} placeholder="Present" onChange={(e) => upd({ end: e.target.value })} /></Field>
                  </div>
                  <div className="entry-grid">
                    <Field label="Location"><input type="text" value={exp.location} onChange={(e) => upd({ location: e.target.value })} /></Field>
                    <Field label="Type of role" hint="Mark Contract or Consulting only if it really was. Employers verify this.">
                      <select value={exp.employment_type ?? ""} onChange={(e) => upd({ employment_type: e.target.value })}>
                        <option value="">Permanent</option><option value="contract">Contract</option>
                        <option value="consulting">Consulting assignment</option><option value="freelance">Freelance</option>
                        <option value="internship">Internship</option>
                      </select>
                    </Field>
                  </div>
                  <Field label="What you did" hint="One bullet per line. Tailored CVs can only reword these, never add to them.">
                    <textarea rows={Math.max(3, exp.bullets.length + 1)} value={exp.bullets.join("\n")}
                              onChange={(e) => upd({ bullets: e.target.value.split("\n").filter((b) => b.trim()) })} />
                  </Field>
                  <button className="btn small danger" onClick={() => set({ experience: data.experience.filter((_, j) => j !== i) })}>Remove role</button>
                </div>
              );
            })}
          </section>

          <section className="panel">
            <div className="panel-head"><h2>Education</h2><button className="btn small" onClick={() => set({ education: [...data.education, { ...emptyEdu }] })}>Add education</button></div>
            {data.education.map((edu, i) => {
              const upd = (p: Partial<Education>) => set({ education: data.education.map((x, j) => (j === i ? { ...x, ...p } : x)) });
              return (
                <div className="entry" key={i}>
                  <div className="entry-grid four">
                    <Field label="Degree"><input type="text" value={edu.degree} onChange={(e) => upd({ degree: e.target.value })} /></Field>
                    <Field label="Field"><input type="text" value={edu.field} onChange={(e) => upd({ field: e.target.value })} /></Field>
                    <Field label="Start"><input type="text" value={edu.start} onChange={(e) => upd({ start: e.target.value })} /></Field>
                    <Field label="End"><input type="text" value={edu.end} onChange={(e) => upd({ end: e.target.value })} /></Field>
                  </div>
                  <Field label="Institution"><input type="text" value={edu.institution} onChange={(e) => upd({ institution: e.target.value })} /></Field>
                  <button className="btn small danger" onClick={() => set({ education: data.education.filter((_, j) => j !== i) })}>Remove</button>
                </div>
              );
            })}
          </section>

          <section className="panel">
            <h2>Skills, certifications and languages</h2>
            <Field label="Skills"><TagInput value={data.skills} onChange={(skills) => set({ skills })} /></Field>
            <Field label="Certifications"><TagInput value={data.certifications} onChange={(certifications) => set({ certifications })} /></Field>
            <Field label="Languages"><TagInput value={data.languages} onChange={(languages) => set({ languages })} /></Field>
          </section>

          {data.projects.length > 0 && (
            <section className="panel">
              <h2>Projects</h2>
              {data.projects.map((p, i) => (
                <div className="entry" key={i}>
                  <Field label="Name"><input type="text" value={p.name} onChange={(e) => set({ projects: data.projects.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} /></Field>
                  <Field label="Description"><textarea rows={3} value={p.description} onChange={(e) => set({ projects: data.projects.map((x, j) => j === i ? { ...x, description: e.target.value } : x) })} /></Field>
                </div>
              ))}
            </section>
          )}

          {versions.length > 1 && (
            <section className="panel">
              <h2>Versions</h2>
              <ul>{versions.map((v) => <li key={v.id}>Version {v.version}: {v.original_filename}, {v.status.replace("_", " ")}{v.is_active ? " (in use)" : ""}, {formatDate(v.created_at)}</li>)}</ul>
            </section>
          )}
        </>
      )}
    </>
  );
}
