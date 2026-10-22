import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post, put } from "../api/client";
import type { Answer, Application, CVData, CvFormatChoice, FollowUp, FormatCatalog, GuardReport, Violation } from "../api/types";
import { Field, MatchBar, StatusPill, TagInput, formatDate, statusLabel, useToast } from "../components/ui";
import { MissingList } from "./JobDetail";
import Icon from "../components/Icon";
import { downloadFile, openExternal, scheduleReminder, shareText } from "../api/platform";

type Tab = "job" | "cv" | "letter" | "answers" | "changes";
const EDITABLE = ["draft", "ready_for_review", "approved", "needs_user_action"];
const TRACKING_NEXT: Record<string, string[]> = {
  submitted: ["in_review", "interviewing", "rejected", "withdrawn"],
  in_review: ["interviewing", "offer", "rejected", "withdrawn"],
  interviewing: ["offer", "rejected", "withdrawn"],
  offer: ["accepted", "rejected", "withdrawn"],
};

function highlight(text: string, violations: Violation[]): ReactNode {
  const values = violations.map((v) => v.value.trim()).filter((v) => v && v.length < 200 && text.includes(v));
  if (!values.length) return text;
  const v = values[0];
  const i = text.indexOf(v);
  const sev = violations.find((x) => x.value.trim() === v)?.severity ?? "warning";
  return <>{text.slice(0, i)}<mark className={`flag-${sev}`} title="Not verified against your Master CV">{v}</mark>{highlight(text.slice(i + v.length), violations)}</>;
}

function at(report: GuardReport | undefined, prefix: string) {
  return (report?.violations ?? []).filter((v) => v.location === prefix || v.location.startsWith(prefix + ".") || v.location.startsWith(prefix + "["));
}

function CVPreview({ cv, guard }: { cv: CVData; guard?: GuardReport }) {
  const c = cv.contact;
  return (
    <div className="document">
      <h1>{c.full_name}</h1>
      <div className="doc-contact">{[c.email, c.phone, c.location, ...c.links].filter(Boolean).join("  |  ")}</div>
      {cv.summary && (<><h2>Summary</h2><p>{highlight(cv.summary, at(guard, "summary"))}</p></>)}
      {cv.experience.length > 0 && <h2>Experience</h2>}
      {cv.experience.map((e, i) => (
        <div key={i}>
          <h3>{e.title}, {e.employer}</h3>
          <div className="doc-meta">{[e.start && `${e.start} to ${e.end}`, e.location].filter(Boolean).join(", ")}</div>
          <ul>{e.bullets.map((b, j) => <li key={j}>{highlight(b, at(guard, `experience[${i}].bullets[${j}]`))}</li>)}</ul>
        </div>
      ))}
      {cv.skills.length > 0 && (<><h2>Skills</h2><p>{highlight(cv.skills.join(", "), at(guard, "skills"))}</p></>)}
      {cv.projects.length > 0 && <h2>Projects</h2>}
      {cv.projects.map((p, i) => (
        <div key={i}><h3>{p.name}</h3>{p.description && <p>{p.description}</p>}<ul>{p.bullets.map((b, j) => <li key={j}>{b}</li>)}</ul></div>
      ))}
      {cv.education.length > 0 && <h2>Education</h2>}
      {cv.education.map((e, i) => (
        <p key={i}><strong>{[e.degree, e.field].filter(Boolean).join(" in ") || e.institution}</strong>{e.degree ? `, ${e.institution}` : ""}{e.end ? ` (${[e.start, e.end].filter(Boolean).join(" to ")})` : ""}</p>
      ))}
      {cv.certifications.length > 0 && (<><h2>Certifications</h2><ul>{cv.certifications.map((x) => <li key={x}>{x}</li>)}</ul></>)}
      {cv.languages.length > 0 && (<><h2>Languages</h2><p>{cv.languages.join(", ")}</p></>)}
    </div>
  );
}

function GuardList({ report, empty }: { report: GuardReport; empty: string }) {
  if (!report.violations.length) return <div className="notice good"><p>{empty}</p></div>;
  return (
    <ul className="violations">
      {report.violations.map((v, i) => (
        <li key={i} className={v.severity}>
          <strong>{v.severity === "error" ? "Blocked" : "Check"}:</strong> {v.message} {v.value && <code>{v.value}</code>}
        </li>
      ))}
    </ul>
  );
}

export default function ApplicationReview() {
  const { id } = useParams();
  const toast = useToast();
  const [app, setApp] = useState<Application | null>(null);
  const [tab, setTab] = useState<Tab>("cv");
  const [editingCV, setEditingCV] = useState(false);
  const [cvDraft, setCvDraft] = useState<CVData | null>(null);
  const [letter, setLetter] = useState("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [newQuestion, setNewQuestion] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [autoSubmit, setAutoSubmit] = useState(false);
  const [busy, setBusy] = useState("");
  const [outcome, setOutcome] = useState({ status: "", title: "", notes: "", occurred_at: "" });
  const [formats, setFormats] = useState<FormatCatalog | null>(null);
  const [followUp, setFollowUp] = useState<FollowUp | null>(null);

  const accept = (a: Application) => {
    setApp(a);
    setCvDraft(a.tailored_cv);
    setLetter(a.cover_letter);
    setAnswers(a.answers);
  };
  const load = () => get<Application>(`/api/applications/${id}`).then(accept).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); get<FormatCatalog>("/api/cv-formats").then(setFormats).catch(() => {}); }, [id]);
  useEffect(() => {
    if (app && ["submitted", "in_review"].includes(app.status)) {
      get<FollowUp>(`/api/applications/${app.id}/follow-up`).then(setFollowUp).catch(() => {});
    }
  }, [app?.id, app?.status]);
  useEffect(() => {
    if (app?.status !== "submitting") return;
    const t = window.setTimeout(load, 3000);
    return () => window.clearTimeout(t);
  }, [app]);

  const dirty = useMemo(() => app !== null && (
    JSON.stringify(cvDraft) !== JSON.stringify(app.tailored_cv) || letter !== app.cover_letter ||
    JSON.stringify(answers) !== JSON.stringify(app.answers)), [app, cvDraft, letter, answers]);

  if (!app || !cvDraft) return <p className="muted">Loading…</p>;
  const editable = EDITABLE.includes(app.status);
  const job = app.job;
  const unanswered = answers.filter((a) => a.needs_user_input && !a.answer && !a.skip).length;
  const cvErrors = app.cv_guard.violations.filter((v) => v.severity === "error").length;
  const letterErrors = app.cover_guard.violations.filter((v) => v.severity === "error").length;
  const lastOutcome = app.blocker?.last_outcome;

  const dl = (path: string, name: string) => downloadFile(path, name).catch((e) => toast((e as Error).message, "error"));
  const run = async (label: string, fn: () => Promise<Application>, success?: string) => {
    setBusy(label);
    try {
      accept(await fn());
      if (success) toast(success);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy("");
    }
  };

  const save = () => run("save", () => put<Application>(`/api/applications/${app.id}/review`, {
    tailored_cv: cvDraft, cover_letter: letter, answers,
  }), app.status === "approved" ? "Saved. Your changes need approving again." : "Saved and re-checked.");

  const checklist = [
    { ok: !dirty, label: "All edits saved" },
    { ok: cvErrors === 0, label: "CV contains only verified facts" },
    { ok: letterErrors === 0, label: "Cover letter makes no unverified claims" },
    { ok: unanswered === 0, label: unanswered ? `${unanswered} question(s) need your answer` : "Application questions answered" },
  ];

  return (
    <>
      <p><Link to="/applications">Back to applications</Link></p>
      <div className="page-head">
        <div>
          <h1>{job.title}</h1>
          <p>{job.company}{job.location ? `, ${job.location}` : ""} <StatusPill status={app.status} /></p>
        </div>
        <div className="row">
          {editable && <button className="btn" onClick={() => run("regen", () => post<Application>(`/api/applications/${app.id}/regenerate`), "Documents regenerated.")} disabled={!!busy}>
            {busy === "regen" ? "Regenerating…" : "Regenerate"}
          </button>}
          {editable && <button className="btn primary" onClick={save} disabled={!dirty || !!busy}>{busy === "save" ? "Saving…" : "Save changes"}</button>}
        </div>
      </div>

      {app.generation_notes.map((n) => <div className="notice" key={n}><p>{n}</p></div>)}
      {app.status === "needs_user_action" && lastOutcome && (
        <div className={`notice ${lastOutcome.status === "blocked" ? "bad" : "warn"}`}>
          <p><strong>{lastOutcome.status === "blocked" ? "Paused for you." : "Your turn."}</strong> {lastOutcome.message}</p>
          {lastOutcome.unfilled.length > 0 && <p>Left for you: {lastOutcome.unfilled.join("; ")}</p>}
          <div className="row">
            <button className="btn" onClick={() => openExternal(lastOutcome.final_url || app.apply_url)}>Open application page</button>
            {lastOutcome.screenshot && <a className="btn quiet" href={`/api/applications/${app.id}/screenshot`} target="_blank" rel="noreferrer">See screenshot</a>}
          </div>
        </div>
      )}

      <div className="review-grid">
        <div>
          <div className="tabs" role="tablist">
            {([["job", "Job"], ["cv", "Tailored CV"], ["letter", "Cover letter"], ["answers", "Questions"], ["changes", "Changes from Master CV"]] as [Tab, string][]).map(([key, label]) => (
              <button key={key} role="tab" className="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
                {label}
                {key === "cv" && cvErrors > 0 && <span className="pill bad count">{cvErrors}</span>}
                {key === "letter" && letterErrors > 0 && <span className="pill bad count">{letterErrors}</span>}
                {key === "answers" && unanswered > 0 && <span className="pill warn count">{unanswered}</span>}
              </button>
            ))}
          </div>

          {tab === "job" && (
            <section className="panel">
              <p><strong>Company:</strong> {job.company}<br /><strong>Role:</strong> {job.title}<br />
                <strong>Posting:</strong> <button className="btn quiet small" onClick={() => openExternal(job.url)}>Open posting</button><br />
                <strong>Apply at:</strong> <button className="btn quiet small" onClick={() => openExternal(app.apply_url)}>Open application page</button></p>
              <div className="desc">{job.description_text}</div>
            </section>
          )}

          {tab === "cv" && (
            <section>
              <div className="spread" style={{ marginBottom: 12 }}>
                <span className="faint">Generated by: {app.generation_method.cv === "deterministic" ? "relevance ordering (no AI)" : `AI, then checked line by line`}</span>
                <div className="row">
                  <button className="btn small" onClick={() => dl(`/api/applications/${app.id}/documents/cv_pdf`, "CV.pdf")}><Icon name="download" size={16} />PDF</button>
                  <button className="btn small" onClick={() => dl(`/api/applications/${app.id}/documents/cv_docx`, "CV.docx")}>Word</button>
                  {editable && <button className="btn small" onClick={() => setEditingCV(!editingCV)}>{editingCV ? "Preview" : "Edit"}</button>}
                </div>
              </div>
              {formats && (
                <FormatPicker app={app} formats={formats} disabled={!editable || !!busy}
                              onChange={(f) => run("format", () => put<Application>(`/api/applications/${app.id}/format`, f), "Format updated.")} />
              )}
              <div style={{ marginBottom: 14 }}><GuardList report={app.cv_guard} empty="Every line traces back to your verified Master CV." /></div>
              <ReportButton appId={app.id} part="cv" />
              {editingCV ? <CVEditor cv={cvDraft} onChange={setCvDraft} /> : <CVPreview cv={cvDraft} guard={app.cv_guard} />}
            </section>
          )}

          {tab === "letter" && (
            <section>
              <div className="spread" style={{ marginBottom: 12 }}>
                <span className="faint">Generated by: {app.generation_method.cover_letter === "ai" ? "AI, then checked" : "fact-only template"}</span>
                <div className="row">
                  <button className="btn small" onClick={() => dl(`/api/applications/${app.id}/documents/cover_pdf`, "Cover_Letter.pdf")}><Icon name="download" size={16} />PDF</button>
                  <button className="btn small" onClick={() => dl(`/api/applications/${app.id}/documents/cover_docx`, "Cover_Letter.docx")}>Word</button>
                </div>
              </div>
              <div style={{ marginBottom: 14 }}><GuardList report={app.cover_guard} empty="No unverified claims found." /></div>
              <ReportButton appId={app.id} part="cover_letter" />
              {editable
                ? <textarea className="document" style={{ width: "100%", minHeight: 520 }} value={letter} onChange={(e) => setLetter(e.target.value)} aria-label="Cover letter" />
                : <div className="document"><div className="letter">{letter}</div></div>}
            </section>
          )}

          {tab === "answers" && (
            <section className="panel">
              <p className="muted">Answers come from your profile first. Anything we cannot answer truthfully from your CV or profile is left for you.</p>
              {answers.map((a, i) => (
                <div className="entry" key={i}>
                  <div className="spread">
                    <strong>{a.question}</strong>
                    <span className="faint">{a.source === "profile" ? "From your profile" : a.source === "ai" ? "AI draft" : a.source === "blocked" ? "AI draft removed" : ""}</span>
                  </div>
                  {a.needs_user_input && !a.answer && !a.skip && <div className="tag missing" style={{ margin: "6px 0" }}>Needs your answer</div>}
                  <textarea rows={3} value={a.answer} disabled={!editable || a.skip} style={{ marginTop: 6 }}
                            onChange={(e) => setAnswers(answers.map((x, j) => j === i ? { ...x, answer: e.target.value, needs_user_input: !e.target.value } : x))} />
                  {a.guard && !a.guard.passed && <div style={{ marginTop: 6 }}><GuardList report={a.guard} empty="" /></div>}
                  {editable && (
                    <div className="row" style={{ marginTop: 6 }}>
                      <label className="check" style={{ margin: 0 }}>
                        <input type="checkbox" checked={!!a.skip} onChange={(e) => setAnswers(answers.map((x, j) => j === i ? { ...x, skip: e.target.checked } : x))} />
                        <span>Not asked on this application</span>
                      </label>
                      <button className="btn small quiet" onClick={() => setAnswers(answers.filter((_, j) => j !== i))}>Remove</button>
                    </div>
                  )}
                </div>
              ))}
              {editable && (
                <div className="row">
                  <input type="text" value={newQuestion} placeholder="Add a question from the application form" style={{ flex: 1 }}
                         onChange={(e) => setNewQuestion(e.target.value)} />
                  <button className="btn" disabled={!newQuestion.trim()} onClick={() => {
                    setAnswers([...answers, { question: newQuestion.trim(), answer: "", needs_user_input: true, source: "user" }]);
                    setNewQuestion("");
                  }}>Add question</button>
                </div>
              )}
            </section>
          )}

          {tab === "changes" && app.master_cv && <Changes master={app.master_cv} tailored={cvDraft} />}
        </div>

        <aside className="review-side">
          <section className="panel">
            <h3>Match</h3>
            <MatchBar score={app.match_score} components={app.match?.components} compact />
          </section>
          {app.match && (
            <section className="panel">
              <h3>Missing requirements</h3>
              <MissingList items={app.match.missing_requirements} />
            </section>
          )}

          {editable && app.status !== "approved" && (
            <section className="panel">
              <h3>Approve</h3>
              <ul className="checklist">
                {checklist.map((c) => (
                  <li key={c.label}><span className={`mark ${c.ok ? "ok" : "no"}`}>{c.ok ? "✓" : "✕"}</span>{c.label}</li>
                ))}
              </ul>
              <label className="check">
                <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                <span>I reviewed the company, job, source link, missing requirements, CV, cover letter and answers.</span>
              </label>
              {app.auto_submit_available && (
                <label className="check">
                  <input type="checkbox" checked={autoSubmit} onChange={(e) => setAutoSubmit(e.target.checked)} />
                  <span>Submit for me on supported sites when there's no CAPTCHA or sign-in</span>
                </label>
              )}
              <button className="btn primary" disabled={!confirmed || checklist.some((c) => !c.ok) || !!busy}
                      onClick={() => run("approve", () => post<Application>(`/api/applications/${app.id}/approve`, { confirm_reviewed: confirmed, auto_submit: autoSubmit }), "Approved.")}>
                Approve application
              </button>
            </section>
          )}

          {(app.status === "approved" || app.status === "needs_user_action") && (
            <section className="panel">
              <h3>Apply</h3>
              {!app.approval_valid && <div className="notice warn"><p>Changed since approval. Approve again.</p></div>}
              <p className="muted">{app.apply_assist_available
                ? "The assistant opens the application page, fills your details and uploads the approved files. It stops for CAPTCHAs, sign-ins and verification codes."
                : "Open the employer's page, upload your approved CV and paste your answers. Then mark it as submitted here."}</p>
              <div className="stack">
                {app.apply_assist_available && <button className="btn primary" disabled={!app.approval_valid || !!busy}
                        onClick={() => run("apply", () => post<Application>(`/api/applications/${app.id}/apply`, { mode: app.blocker?.auto_submit_requested ? "submit" : "assist" }), "Opening the application page on this computer.")}>
                  Fill the form for me
                </button>}
                <button className="btn" onClick={() => openExternal(app.apply_url)}>{app.apply_assist_available ? "I'll apply myself" : "Open application page"}</button>
                <button className="btn" onClick={async () => {
                  const text = app.answers.filter((a) => a.answer).map((a) => `${a.question}\n${a.answer}`).join("\n\n");
                  const r = await shareText("Application answers", text);
                  toast(r === "copied" ? "Answers copied." : "Shared.");
                }}><Icon name="share" size={16} />Copy answers</button>
                <button className="btn" disabled={!app.approval_valid || !!busy}
                        onClick={() => run("submitted", () => post<Application>(`/api/applications/${app.id}/submitted`, { method: "manual" }), "Marked as submitted.")
                          .then(() => scheduleReminder(app.id, `Follow up: ${job.company}`, `No reply yet about ${job.title}? Send the follow-up from AI Job Hunter.`,
                                                       new Date(Date.now() + 7 * 24 * 3600 * 1000)))}>
                  Mark as submitted
                </button>
              </div>
            </section>
          )}

          {TRACKING_NEXT[app.status] && (
            <section className="panel">
              <h3>Record what happened</h3>
              <Field label="New status">
                <select value={outcome.status} onChange={(e) => setOutcome({ ...outcome, status: e.target.value })}>
                  <option value="">Just add a note</option>
                  {TRACKING_NEXT[app.status].map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                </select>
              </Field>
              <Field label="What" hint="For example: Phone screen with the hiring manager"><input type="text" value={outcome.title} onChange={(e) => setOutcome({ ...outcome, title: e.target.value })} /></Field>
              <Field label="When"><input type="datetime-local" value={outcome.occurred_at} onChange={(e) => setOutcome({ ...outcome, occurred_at: e.target.value })} /></Field>
              <Field label="Notes"><textarea rows={3} value={outcome.notes} onChange={(e) => setOutcome({ ...outcome, notes: e.target.value })} /></Field>
              <button className="btn primary" disabled={!!busy || (!outcome.status && !outcome.title && !outcome.notes)} onClick={() => run("event", () => post<Application>(`/api/applications/${app.id}/events`, {
                status: outcome.status || null,
                kind: outcome.status === "interviewing" || /interview/i.test(outcome.title) ? "interview" : outcome.status ? "status_change" : "note",
                title: outcome.title, notes: outcome.notes,
                occurred_at: outcome.occurred_at ? new Date(outcome.occurred_at).toISOString() : null,
              }), "Saved.").then(() => setOutcome({ status: "", title: "", notes: "", occurred_at: "" }))}>Save</button>
            </section>
          )}

          {followUp && (followUp.due || followUp.already_followed_up) && (
            <section className="panel">
              <h3>Follow up</h3>
              {followUp.already_followed_up ? <p className="muted">You've followed up already.</p> : (
                <>
                  <p className="muted">No reply after {followUp.days_since_submitted} days. A short, polite follow-up often gets a response.</p>
                  <Field label="Subject"><input type="text" readOnly value={followUp.subject} /></Field>
                  <textarea rows={9} readOnly value={followUp.body} aria-label="Follow-up email" />
                  <div className="row" style={{ marginTop: 8 }}>
                    <button className="btn" onClick={async () => { const r = await shareText(followUp.subject, `${followUp.subject}\n\n${followUp.body}`); toast(r === "copied" ? "Copied." : "Shared."); }}><Icon name="share" size={16} />Copy or share</button>
                    <button className="btn primary" onClick={() => run("fu", () => post<Application>(`/api/applications/${app.id}/follow-up/sent`), "Recorded.").then(() => setFollowUp({ ...followUp, due: false, already_followed_up: true }))}>I sent it</button>
                  </div>
                </>
              )}
            </section>
          )}

          <section className="panel">
            <h3>History</h3>
            <ol className="timeline">
              {[...app.events].reverse().map((e) => (
                <li key={e.id}>
                  <strong>{e.kind === "status_change" ? statusLabel(e.to_status) : String(e.details.title || e.kind)}</strong>
                  <div className="faint">{formatDate(e.occurred_at)}</div>
                  {typeof e.details.notes === "string" && e.details.notes && <div>{e.details.notes}</div>}
                  {typeof e.details.message === "string" && <div className="faint">{e.details.message}</div>}
                  {e.kind === "email" && typeof e.details.subject === "string" && <div className="faint">“{e.details.subject}”</div>}
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </>
  );
}

function CVEditor({ cv, onChange }: { cv: CVData; onChange: (cv: CVData) => void }) {
  return (
    <div className="panel">
      <div className="notice"><p>Employers, titles, dates and education are locked to your Master CV. You can reword the summary and bullets, reorder, or remove items. Every change is re-checked when you save.</p></div>
      <Field label="Summary"><textarea rows={4} value={cv.summary} onChange={(e) => onChange({ ...cv, summary: e.target.value })} /></Field>
      {cv.experience.map((exp, i) => (
        <div className="entry" key={i}>
          <div className="spread">
            <strong>{exp.title}, {exp.employer}</strong>
            <button className="btn small quiet" onClick={() => onChange({ ...cv, experience: cv.experience.filter((_, j) => j !== i) })}>Remove role</button>
          </div>
          <span className="faint">{exp.start} to {exp.end}</span>
          <Field label="Bullet points" hint="One per line.">
            <textarea rows={Math.max(3, exp.bullets.length + 1)} value={exp.bullets.join("\n")}
                      onChange={(e) => onChange({ ...cv, experience: cv.experience.map((x, j) => j === i ? { ...x, bullets: e.target.value.split("\n").filter((b) => b.trim()) } : x) })} />
          </Field>
        </div>
      ))}
      <Field label="Skills" hint="Remove or reorder. Skills not on your Master CV will be blocked.">
        <TagInput value={cv.skills} onChange={(skills) => onChange({ ...cv, skills })} />
      </Field>
    </div>
  );
}

function Changes({ master, tailored }: { master: CVData; tailored: CVData }) {
  const masterBullets = new Set(master.experience.flatMap((e) => e.bullets));
  const reworded = tailored.experience.flatMap((e) => e.bullets.filter((b) => !masterBullets.has(b)).map((b) => ({ role: `${e.title}, ${e.employer}`, b })));
  const droppedRoles = master.experience.filter((m) => !tailored.experience.some((t) => t.employer === m.employer && t.title === m.title));
  const droppedSkills = master.skills.filter((s) => !tailored.skills.includes(s));
  return (
    <section className="panel stack">
      <div>
        <h3>Summary</h3>
        {master.summary === tailored.summary ? <p className="muted">Unchanged.</p> : (
          <div className="grid-2"><div><p className="faint">Master CV</p><p>{master.summary || "(none)"}</p></div><div><p className="faint">This application</p><p>{tailored.summary}</p></div></div>
        )}
      </div>
      <div>
        <h3>Reworded bullet points ({reworded.length})</h3>
        {reworded.length === 0 ? <p className="muted">Bullets are your original wording, reordered for relevance.</p> : (
          <ul>{reworded.map((r, i) => <li key={i}><span className="faint">{r.role}:</span> {r.b}</li>)}</ul>
        )}
      </div>
      <div>
        <h3>Skills order</h3>
        <p>{tailored.skills.join(", ")}</p>
        {droppedSkills.length > 0 && <p className="faint">Left out: {droppedSkills.join(", ")}</p>}
      </div>
      {droppedRoles.length > 0 && <div><h3>Roles left out</h3><ul>{droppedRoles.map((r) => <li key={r.employer + r.title}>{r.title}, {r.employer}</li>)}</ul></div>}
    </section>
  );
}

function FormatPicker({ app, formats, disabled, onChange }: {
  app: Application; formats: FormatCatalog; disabled: boolean;
  onChange: (f: CvFormatChoice) => void;
}) {
  const current: CvFormatChoice = app.cv_format?.country_code ? app.cv_format
    : { country_code: "IN", style: "modern", custom_layout_id: "", date_precision: "month", layout: "chronological" };
  const fmt = formats.countries.find((c) => c.code === current.country_code);
  return (
    <div className="panel" style={{ marginBottom: 14 }}>
      <div className="entry-grid" style={{ gridTemplateColumns: "2fr 1fr 2fr" }}>
        <Field label="Country format">
          <select value={current.country_code} disabled={disabled} onChange={(e) => onChange({ ...current, country_code: e.target.value })}>
            {formats.countries.map((c) => <option key={c.code} value={c.code}>{c.country}</option>)}
          </select>
        </Field>
        <Field label="Style">
          <select value={current.style} disabled={disabled} onChange={(e) => onChange({ ...current, style: e.target.value })}>
            {formats.styles.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </Field>
        <Field label="Layout from a sample CV">
          <select value={current.custom_layout_id} disabled={disabled} onChange={(e) => onChange({ ...current, custom_layout_id: e.target.value })}>
            <option value="">Country default</option>
            {formats.custom_layouts.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </Field>
      </div>
      <div className="entry-grid">
        <Field label="Layout" hint="Hybrid puts your strongest numbered results at the top. Good if you changed jobs often.">
          <select value={current.layout ?? "chronological"} disabled={disabled} onChange={(e) => onChange({ ...current, layout: e.target.value })}>
            <option value="chronological">Chronological</option>
            <option value="hybrid">Hybrid (Key Achievements first)</option>
          </select>
        </Field>
        <Field label="Dates" hint={current.date_precision === "year" ? "Online forms and background checks still need exact months; always enter them truthfully there." : undefined}>
          <select value={current.date_precision ?? "month"} disabled={disabled} onChange={(e) => onChange({ ...current, date_precision: e.target.value })}>
            <option value="month">Month and year</option>
            <option value="year">Year only</option>
          </select>
        </Field>
      </div>
      {current.date_precision === "year" && current.country_code === "DE" && (
        <p className="faint">German recruiters usually expect MM/YYYY dates.</p>
      )}
      {fmt && <ul style={{ paddingLeft: 18, margin: 0 }}>{fmt.tips.map((t) => <li key={t} className="faint">{t}</li>)}</ul>}
      {app.format_notes.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary className="faint">{app.format_notes.length} less relevant item(s) left out to fit {fmt?.max_pages ?? 2} page(s)</summary>
          <ul>{app.format_notes.map((n) => <li key={n} className="faint">{n}</li>)}</ul>
        </details>
      )}
      <p className="faint" style={{ marginTop: 8, marginBottom: 0 }}>The preview below shows content. Download the PDF to see the exact country layout.</p>
    </div>
  );
}

function ReportButton({ appId, part }: { appId: number; part: string }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  if (!open) {
    return <button className="btn quiet small" style={{ marginBottom: 10 }} onClick={() => setOpen(true)}><Icon name="flag" size={15} />Report a problem with this AI content</button>;
  }
  return (
    <div className="entry">
      <Field label="What's wrong?" hint="Wrong facts, offensive or harmful wording, anything else. This goes to the app's team.">
        <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div className="row">
        <button className="btn small primary" disabled={!reason.trim()} onClick={async () => {
          try {
            const r = await post<{ message: string }>(`/api/applications/${appId}/report`, { part, reason });
            toast(r.message);
            setOpen(false);
            setReason("");
          } catch (e) { toast((e as Error).message, "error"); }
        }}>Send report</button>
        <button className="btn small quiet" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}
