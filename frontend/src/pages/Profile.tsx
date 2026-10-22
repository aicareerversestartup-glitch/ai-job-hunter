import { useEffect, useState } from "react";
import { del, get, put, upload } from "../api/client";
import { imageObjectUrl } from "../api/platform";
import type { CandidateProfile, JobPreferences, ProfileIO } from "../api/types";
import { Field, TagInput, useToast } from "../components/ui";

const EMPLOYMENT = [["full_time", "Full-time"], ["part_time", "Part-time"], ["contract", "Contract"], ["internship", "Internship"], ["temporary", "Temporary"]];
const LEVELS = [["intern", "Intern"], ["entry", "Entry"], ["mid", "Mid"], ["senior", "Senior"], ["lead", "Lead"], ["manager", "Manager"], ["director", "Director"]];

export default function ProfilePage() {
  const toast = useToast();
  const [io, setIo] = useState<ProfileIO | null>(null);
  const [saving, setSaving] = useState(false);
  const [qa, setQa] = useState<{ q: string; a: string }[]>([]);

  useEffect(() => {
    get<ProfileIO>("/api/profile").then((d) => {
      setIo(d);
      setQa(Object.entries(d.profile.saved_answers).map(([q, a]) => ({ q, a })));
    }).catch((e) => toast(e.message, "error"));
  }, []);
  if (!io) return <p className="muted">Loading…</p>;

  const p = io.profile;
  const prefs = io.preferences;
  const setP = (patch: Partial<CandidateProfile>) => setIo({ ...io, profile: { ...p, ...patch } });
  const setPrefs = (patch: Partial<JobPreferences>) => setIo({ ...io, preferences: { ...prefs, ...patch } });
  const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);

  const save = async () => {
    setSaving(true);
    try {
      const saved_answers = Object.fromEntries(qa.filter((x) => x.q.trim() && x.a.trim()).map((x) => [x.q.trim(), x.a.trim()]));
      const body: ProfileIO = {
        ...io,
        profile: { ...p, saved_answers },
        preferences: {
          ...prefs,
          work_authorized_countries: p.work_authorized_countries,
          needs_sponsorship_countries: p.needs_sponsorship_countries,
          willing_to_relocate: p.willing_to_relocate,
        },
      };
      setIo(await put<ProfileIO>("/api/profile", body));
      toast("Saved. Jobs re-scored with your new targets.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Profile and targets</h1>
          <p>What you're looking for, and the facts used to answer application questions.</p>
        </div>
        <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
      </div>

      <div className="grid-2">
        <section className="panel">
          <h2>What you're looking for</h2>
          <Field label="Countries, most wanted first" hint="Jobs in these countries are shown first, in this order.">
            <TagInput value={prefs.preferred_countries} onChange={(preferred_countries) => setPrefs({ preferred_countries })} placeholder="e.g. Germany, Netherlands, Canada" />
          </Field>
          <Field label="Roles you want first (optional)" hint="Jobs for these roles rank above roles suggested from your CV.">
            <TagInput value={prefs.target_roles} onChange={(target_roles) => setPrefs({ target_roles })} placeholder="e.g. Operations Manager" />
          </Field>
          <SuggestedRoles prefs={prefs} onChange={setPrefs} />
          <Field label="Cities (optional)"><TagInput value={prefs.preferred_cities} onChange={(preferred_cities) => setPrefs({ preferred_cities })} placeholder="e.g. Pune" /></Field>
          <Field label="Work setting">
            <select value={prefs.remote_preference} onChange={(e) => setPrefs({ remote_preference: e.target.value as JobPreferences["remote_preference"] })}>
              <option value="any">Any</option><option value="remote_only">Remote only</option>
              <option value="hybrid_ok">Remote or hybrid</option><option value="onsite_ok">Happy on-site</option>
            </select>
          </Field>
          <fieldset className="field" style={{ border: 0, padding: 0 }}>
            <legend style={{ fontWeight: 500, marginBottom: 6 }}>Employment type</legend>
            <div className="row">
              {EMPLOYMENT.map(([v, l]) => (
                <label className="check" key={v} style={{ margin: 0 }}>
                  <input type="checkbox" checked={prefs.employment_types.includes(v)} onChange={() => setPrefs({ employment_types: toggle(prefs.employment_types, v) })} /><span>{l}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="field" style={{ border: 0, padding: 0, marginTop: 12 }}>
            <legend style={{ fontWeight: 500, marginBottom: 6 }}>Seniority (leave empty for any)</legend>
            <div className="row">
              {LEVELS.map(([v, l]) => (
                <label className="check" key={v} style={{ margin: 0 }}>
                  <input type="checkbox" checked={prefs.seniority_levels.includes(v)} onChange={() => setPrefs({ seniority_levels: toggle(prefs.seniority_levels, v) })} /><span>{l}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="entry-grid" style={{ marginTop: 12 }}>
            <Field label="Minimum salary"><input type="number" min={0} value={prefs.min_salary ?? ""} onChange={(e) => setPrefs({ min_salary: e.target.value ? Number(e.target.value) : null })} /></Field>
            <Field label="Currency"><input type="text" value={prefs.salary_currency} placeholder="INR" onChange={(e) => setPrefs({ salary_currency: e.target.value.toUpperCase() })} /></Field>
          </div>
          <Field label="Exclude jobs mentioning"><TagInput value={prefs.exclude_keywords} onChange={(exclude_keywords) => setPrefs({ exclude_keywords })} placeholder="e.g. night shift" /></Field>
          <Field label="Exclude companies"><TagInput value={prefs.exclude_companies} onChange={(exclude_companies) => setPrefs({ exclude_companies })} /></Field>
          <Field label={`Warn me below match score ${prefs.min_apply_score}`} hint="Applying mainly to strong matches is the biggest lever on interview rate.">
            <input type="range" min={40} max={90} step={5} value={prefs.min_apply_score} onChange={(e) => setPrefs({ min_apply_score: Number(e.target.value) })} />
          </Field>
          <label className="check"><input type="checkbox" checked={io.auto_discovery} onChange={(e) => setIo({ ...io, auto_discovery: e.target.checked })} /><span>Search for new jobs automatically</span></label>
        </section>

        <section className="panel">
          <h2>About you</h2>
          <div className="entry-grid">
            <Field label="Full name"><input type="text" value={p.full_name} onChange={(e) => setP({ full_name: e.target.value })} /></Field>
            <Field label="Email"><input type="email" value={p.email} onChange={(e) => setP({ email: e.target.value })} /></Field>
            <Field label="Phone"><input type="text" value={p.phone} onChange={(e) => setP({ phone: e.target.value })} /></Field>
            <Field label="Location"><input type="text" value={p.location} onChange={(e) => setP({ location: e.target.value })} /></Field>
          </div>
          <Field label="LinkedIn"><input type="url" value={p.linkedin_url} onChange={(e) => setP({ linkedin_url: e.target.value })} /></Field>
          <div className="entry-grid">
            <Field label="GitHub"><input type="url" value={p.github_url} onChange={(e) => setP({ github_url: e.target.value })} /></Field>
            <Field label="Portfolio"><input type="url" value={p.portfolio_url} onChange={(e) => setP({ portfolio_url: e.target.value })} /></Field>
          </div>

          <h3 style={{ marginTop: 12 }}>Work authorization</h3>
          <p className="faint">Applications only claim what you state here. If a job is elsewhere, the question is left for you.</p>
          <Field label="Countries where you can work without sponsorship"><TagInput value={p.work_authorized_countries} onChange={(work_authorized_countries) => setP({ work_authorized_countries })} placeholder="e.g. India" /></Field>
          <Field label="Countries where you'd need visa sponsorship"><TagInput value={p.needs_sponsorship_countries} onChange={(needs_sponsorship_countries) => setP({ needs_sponsorship_countries })} /></Field>
          <Field label="Relocation line on your CV" hint="Shown under your contact details only for jobs in countries where you can't already work.">
            <input type="text" value={p.relocation_statement} placeholder="Open to international relocation with visa sponsorship."
                   onChange={(e) => setP({ relocation_statement: e.target.value })} />
          </Field>
          <Field label="Passport" hint="Shown with the relocation line for jobs abroad, e.g. 'Valid Indian Passport'.">
            <input type="text" value={p.passport_status} onChange={(e) => setP({ passport_status: e.target.value })} />
          </Field>
          <label className="check"><input type="checkbox" checked={p.willing_to_relocate} onChange={(e) => setP({ willing_to_relocate: e.target.checked })} /><span>Willing to relocate</span></label>

          <h3 style={{ marginTop: 12 }}>Details some countries expect on a CV</h3>
          <p className="faint">Shown only in formats that use them (e.g. Germany, Gulf countries). Leave empty to never show.</p>
          <div className="entry-grid">
            <Field label="Date of birth" hint="As it should be printed, e.g. 14.03.1990"><input type="text" value={p.date_of_birth} onChange={(e) => setP({ date_of_birth: e.target.value })} /></Field>
            <Field label="Nationality"><input type="text" value={p.nationality} onChange={(e) => setP({ nationality: e.target.value })} /></Field>
            <Field label="Visa status" hint="Your real status, e.g. 'Employment Visa – Transferable'"><input type="text" value={p.visa_status} onChange={(e) => setP({ visa_status: e.target.value })} /></Field>
            <Field label="Driving licence"><input type="text" value={p.driving_licence} placeholder="e.g. India LMV, UAE" onChange={(e) => setP({ driving_licence: e.target.value })} /></Field>
          </div>
          <PhotoField hasPhoto={Boolean(p.photo_path)} include={p.include_photo} onInclude={(v) => setP({ include_photo: v })}
                      onChanged={(has) => setP({ photo_path: has ? "uploaded" : "" })} />

          <h3 style={{ marginTop: 12 }}>Common answers</h3>
          <div className="entry-grid">
            <Field label="Notice period"><input type="text" value={p.notice_period} placeholder="e.g. 60 days" onChange={(e) => setP({ notice_period: e.target.value })} /></Field>
            <Field label="Earliest start date"><input type="text" value={p.earliest_start_date} onChange={(e) => setP({ earliest_start_date: e.target.value })} /></Field>
            <Field label="Salary expectation"><input type="text" value={p.salary_expectation} placeholder="e.g. ₹14 LPA" onChange={(e) => setP({ salary_expectation: e.target.value })} /></Field>
            <Field label="Diversity questions"><input type="text" value={p.eeo_default} onChange={(e) => setP({ eeo_default: e.target.value })} /></Field>
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>Referees</h2>
          <button className="btn small" onClick={() => setP({ referees: [...p.referees, { name: "", title: "", company: "", email: "", phone: "", relationship: "" }] })}>Add referee</button>
        </div>
        <p className="faint">Listed only where expected (Australia, New Zealand). Ask each person first.</p>
        {p.referees.map((r, i) => (
          <div className="entry" key={i}>
            <div className="entry-grid">
              {(["name", "title", "company", "relationship", "email", "phone"] as const).map((k) => (
                <Field key={k} label={k[0].toUpperCase() + k.slice(1)}>
                  <input type="text" value={r[k]} onChange={(e) => setP({ referees: p.referees.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x) })} />
                </Field>
              ))}
            </div>
            <button className="btn small quiet" onClick={() => setP({ referees: p.referees.filter((_, j) => j !== i) })}>Remove</button>
          </div>
        ))}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Saved answers</h2>
          <button className="btn small" onClick={() => setQa([...qa, { q: "", a: "" }])}>Add answer</button>
        </div>
        <p className="faint">Answers you've written once and want reused word for word when a form asks the same question.</p>
        {qa.map((item, i) => (
          <div className="entry" key={i}>
            <Field label="Question"><input type="text" value={item.q} onChange={(e) => setQa(qa.map((x, j) => j === i ? { ...x, q: e.target.value } : x))} /></Field>
            <Field label="Your answer"><textarea rows={3} value={item.a} onChange={(e) => setQa(qa.map((x, j) => j === i ? { ...x, a: e.target.value } : x))} /></Field>
            <button className="btn small quiet" onClick={() => setQa(qa.filter((_, j) => j !== i))}>Remove</button>
          </div>
        ))}
      </section>
    </>
  );
}

function PhotoField({ hasPhoto, include, onInclude, onChanged }: {
  hasPhoto: boolean; include: boolean; onInclude: (v: boolean) => void; onChanged: (has: boolean) => void;
}) {
  const toast = useToast();
  const [version, setVersion] = useState(0);
  const [src, setSrc] = useState("");
  useEffect(() => {
    if (!hasPhoto) { setSrc(""); return; }
    let url = "";
    imageObjectUrl(`/api/profile/photo?v=${version}`).then((u) => { url = u; setSrc(u); }).catch(() => setSrc(""));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [hasPhoto, version]);
  const onFile = async (file?: File) => {
    if (!file) return;
    try {
      await upload("/api/profile/photo", file);
      onChanged(true);
      setVersion(version + 1);
      toast("Photo saved.");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  return (
    <div className="entry">
      <div className="row">
        {src && <img src={src} alt="Your CV photo" style={{ width: 72, height: 90, objectFit: "cover", borderRadius: 4 }} />}
        <div>
          <label className="btn small">{hasPhoto ? "Replace photo" : "Upload photo"}
            <input type="file" accept="image/jpeg,image/png" hidden onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
          {hasPhoto && <button className="btn small quiet" onClick={async () => { await del("/api/profile/photo"); onChanged(false); }}>Remove</button>}
          <label className="check" style={{ marginTop: 8 }}>
            <input type="checkbox" checked={include} onChange={(e) => onInclude(e.target.checked)} />
            <span>Use it where the country expects a photo</span>
          </label>
          <small className="faint">Professional headshot, plain background. Never used for US, UK, Canada, Netherlands or Australia formats.</small>
        </div>
      </div>
    </div>
  );
}

function SuggestedRoles({ prefs, onChange }: { prefs: JobPreferences; onChange: (p: Partial<JobPreferences>) => void }) {
  const [roles, setRoles] = useState<{ title: string; reason: string }[]>([]);
  useEffect(() => {
    get<{ roles: { title: string; reason: string }[] }>("/api/profile/suggested-roles").then((r) => setRoles(r.roles)).catch(() => {});
  }, []);
  const excluded = new Set(prefs.excluded_cv_roles.map((r) => r.toLowerCase()));
  return (
    <div className="entry">
      <label className="check" style={{ marginBottom: 6 }}>
        <input type="checkbox" checked={prefs.include_cv_roles} onChange={(e) => onChange({ include_cv_roles: e.target.checked })} />
        <span><strong>Also search roles that fit my CV</strong></span>
      </label>
      {roles.length === 0 && <p className="faint" style={{ margin: 0 }}>Upload and verify a CV to see roles it fits.</p>}
      {prefs.include_cv_roles && roles.map((r) => (
        <label className="check" key={r.title} style={{ marginBottom: 4 }}>
          <input type="checkbox" checked={!excluded.has(r.title.toLowerCase())} onChange={(e) => onChange({
            excluded_cv_roles: e.target.checked
              ? prefs.excluded_cv_roles.filter((x) => x.toLowerCase() !== r.title.toLowerCase())
              : [...prefs.excluded_cv_roles, r.title],
          })} />
          <span>{r.title} <span className="faint">({r.reason})</span></span>
        </label>
      ))}
    </div>
  );
}
