import { createContext, useCallback, useContext, useState, type KeyboardEvent, type ReactNode } from "react";
import type { MatchResult } from "../api/types";

/* ------------------------------------------------------------------ toast */
type ToastFn = (message: string, kind?: "info" | "error") => void;
const ToastContext = createContext<ToastFn>(() => {});
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ message: string; kind: string } | null>(null);
  const show = useCallback<ToastFn>((message, kind = "info") => {
    setToast({ message, kind });
    window.setTimeout(() => setToast(null), kind === "error" ? 7000 : 3500);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <div className={`toast ${toast.kind}`} role="status" aria-live="polite">
          {toast.message}
        </div>
      )}
    </ToastContext.Provider>
  );
}

/* ------------------------------------------------------------- match bar */
const COMPONENTS: { key: string; label: string; weight: number }[] = [
  { key: "skills", label: "Skills", weight: 40 },
  { key: "role", label: "Role fit", weight: 25 },
  { key: "experience", label: "Experience", weight: 15 },
  { key: "preferences", label: "Your preferences", weight: 10 },
  { key: "education", label: "Education", weight: 5 },
  { key: "other", label: "Other", weight: 5 },
];

export function MatchBar({ score, components, compact = false }: {
  score: number; components?: MatchResult["components"]; compact?: boolean;
}) {
  return (
    <div className="match" aria-label={`Match score ${score} out of 100`}>
      <div className="match-top">
        <span className={`match-score${compact ? " compact" : ""}`}>{score}</span>
        <span className="faint">/ 100</span>
      </div>
      {components && (
        <>
          <div className="match-bar" aria-hidden="true">
            {COMPONENTS.map((c) => {
              const v = components[c.key] ?? 0;
              return (
                <span key={c.key} className={`match-seg${v >= 0.99 ? " full" : v < 0.5 ? " low" : ""}`}
                      style={{ flex: c.weight }} title={`${c.label}: ${Math.round(v * 100)}%`}>
                  <i style={{ width: `${Math.round(v * 100)}%` }} />
                </span>
              );
            })}
          </div>
          {!compact && (
            <div className="match-legend">
              {COMPONENTS.map((c) => (
                <span key={c.key}>{c.label} <b>{Math.round((components[c.key] ?? 0) * c.weight)}</b>/{c.weight}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------ status pill */
const STATUS_LABELS: Record<string, [string, string]> = {
  draft: ["Draft", ""], ready_for_review: ["Ready for review", "info"], approved: ["Approved", "good"],
  submitting: ["Applying…", "info"], needs_user_action: ["Needs you", "warn"], submitted: ["Submitted", "good"],
  in_review: ["In review", "info"], interviewing: ["Interviewing", "good"], offer: ["Offer", "good"],
  accepted: ["Accepted", "good"], rejected: ["Rejected", "bad"], withdrawn: ["Withdrawn", ""], discarded: ["Discarded", ""],
};
export function statusLabel(status: string) {
  return STATUS_LABELS[status]?.[0] ?? status;
}
export function StatusPill({ status }: { status: string }) {
  const [label, tone] = STATUS_LABELS[status] ?? [status, ""];
  return <span className={`pill ${tone}`}>{label}</span>;
}

export function RiskPill({ level }: { level: string }) {
  if (level === "low") return null;
  return <span className={`pill ${level === "high" ? "bad" : "warn"}`}>{level === "high" ? "High fraud risk" : "Check posting"}</span>;
}

/* -------------------------------------------------------------- tag input */
export function TagInput({ value, onChange, placeholder, id }: {
  value: string[]; onChange: (v: string[]) => void; placeholder?: string; id?: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const parts = draft.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length) onChange([...value, ...parts.filter((p) => !value.includes(p))]);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
    else if (e.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
  };
  return (
    <div className="tag-input">
      {value.map((t) => (
        <span className="tag" key={t}>
          {t}
          <button type="button" aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((x) => x !== t))}>×</button>
        </span>
      ))}
      <input id={id} type="text" value={draft} placeholder={value.length ? "" : placeholder}
             onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={add} />
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function salaryText(min: number | null, max: number | null, currency: string) {
  if (!min && !max) return "";
  const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  const range = min && max ? `${fmt(min)}–${fmt(max)}` : fmt((min || max) as number);
  return `${currency ? currency + " " : ""}${range}`;
}

export const REMOTE_LABEL: Record<string, string> = { remote: "Remote", hybrid: "Hybrid", onsite: "On-site", unknown: "" };
export const TYPE_LABEL: Record<string, string> = {
  full_time: "Full-time", part_time: "Part-time", contract: "Contract", internship: "Internship",
  temporary: "Temporary", unknown: "",
};

const COUNTRY_CODES: Record<string, string> = {
  India: "IN", "United States": "US", "United Kingdom": "UK", Germany: "DE", Canada: "CA", Australia: "AU",
  "United Arab Emirates": "AE", Singapore: "SG", Netherlands: "NL", Ireland: "IE", France: "FR", Japan: "JP",
  "Saudi Arabia": "SA", Qatar: "QA", Sweden: "SE", Poland: "PL", Spain: "ES", Switzerland: "CH",
  "New Zealand": "NZ", Denmark: "DK", China: "CN", Austria: "AT", Belgium: "BE", Italy: "IT", Norway: "NO",
};

/** The destination tile: country code, city, and whether it's in your country list. */
export function Destination({ job }: { job: { country: string; location: string; remote_type: string;
  match: null | { priority?: { in_country_list: boolean; country_rank: number } } } }) {
  const remote = job.remote_type === "remote" && !job.country;
  const code = remote ? "RM" : COUNTRY_CODES[job.country] ?? (job.country ? job.country.slice(0, 2).toUpperCase() : "··");
  const listed = job.match?.priority?.in_country_list;
  const city = remote ? "Remote" : (job.location.split(",")[0] || job.country || "Unknown");
  return (
    <div className={`dest${listed ? " listed" : ""}${remote ? " remote" : ""}`}
         title={listed ? `Your country #${(job.match?.priority?.country_rank ?? 0) + 1}` : job.country || "Location not given"}>
      <b>{code}</b>
      <small>{listed ? `#${(job.match?.priority?.country_rank ?? 0) + 1} ${city}` : city}</small>
    </div>
  );
}
