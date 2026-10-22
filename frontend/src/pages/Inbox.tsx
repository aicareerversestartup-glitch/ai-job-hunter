import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post, put } from "../api/client";
import { isNative } from "../api/platform";
import type { EmailDetection, InboxSettings } from "../api/types";
import { Field, formatDate, statusLabel, useToast } from "../components/ui";

const PROVIDERS: [string, string][] = [["gmail", "Gmail"], ["yahoo", "Yahoo Mail"], ["zoho", "Zoho Mail"],
  ["icloud", "iCloud Mail"], ["outlook", "Outlook / Microsoft 365"], ["other", "Other (IMAP)"]];
const LABEL: Record<string, [string, string]> = {
  interview: ["Interview", "good"], assessment: ["Assessment", "info"], offer: ["Offer", "good"],
  rejection: ["Rejection", "bad"], acknowledgement: ["Received", ""],
};

export default function Inbox() {
  const toast = useToast();
  const [settings, setSettings] = useState<InboxSettings | null>(null);
  const [password, setPassword] = useState("");
  const [items, setItems] = useState<EmailDetection[]>([]);
  const [busy, setBusy] = useState(false);

  const load = () => {
    get<InboxSettings>("/api/inbox/settings").then(setSettings).catch((e) => toast(e.message, "error"));
    get<EmailDetection[]>("/api/inbox/detections").then(setItems).catch(() => {});
  };
  useEffect(load, []);
  if (!settings) return <p className="muted">Loading…</p>;

  const save = async () => {
    setBusy(true);
    try {
      setSettings(await put<InboxSettings>("/api/inbox/settings", { ...settings, password: password || null }));
      setPassword("");
      toast("Saved. Checking your inbox…");
      const r = await post<{ message: string }>("/api/inbox/check");
      toast(r.message);
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };
  const check = async () => {
    setBusy(true);
    const r = await post<{ message: string }>("/api/inbox/check").catch((e) => ({ message: (e as Error).message }));
    toast(r.message);
    setBusy(false);
    load();
  };
  const resolve = async (d: EmailDetection, apply: boolean) => {
    try {
      await post(`/api/inbox/detections/${d.event_id}/resolve`, { apply });
      toast(apply ? `Marked as ${statusLabel(d.suggested_status)}.` : "Dismissed.");
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Interview emails</h1>
          <p>Reads your inbox (read-only) and spots replies from companies you applied to.</p>
        </div>
        {settings.configured && <button className="btn" onClick={check} disabled={busy}>Check now</button>}
      </div>

      {isNative() ? (
        <div className="notice"><p>Connect your inbox on the AI Job Hunter website (Account menu → Interview emails). Replies found there appear here too.</p></div>
      ) : (
      <section className="panel" style={{ maxWidth: 680 }}>
        <h2>Connect your inbox</h2>
        <p className="muted">Use an <strong>app password</strong>, not your normal password. In Gmail: Google Account → Security →
          2-Step Verification → App passwords. The app only reads messages; it never sends, deletes or marks them read.</p>
        <div className="entry-grid">
          <Field label="Email provider">
            <select value={settings.provider} onChange={(e) => setSettings({ ...settings, provider: e.target.value })}>
              {PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Email address"><input type="email" value={settings.username} onChange={(e) => setSettings({ ...settings, username: e.target.value })} /></Field>
        </div>
        {settings.provider === "other" && (
          <div className="entry-grid">
            <Field label="IMAP server"><input type="text" value={settings.host} onChange={(e) => setSettings({ ...settings, host: e.target.value })} /></Field>
            <Field label="Port"><input type="number" value={settings.port} onChange={(e) => setSettings({ ...settings, port: Number(e.target.value) })} /></Field>
          </div>
        )}
        {settings.provider === "outlook" && <p className="faint">Microsoft has been switching off app-password access for many Outlook accounts. If sign-in fails, forward job emails to a Gmail address and connect that.</p>}
        <Field label="App password" hint={settings.has_password ? "Saved. Leave empty to keep it." : "Stored encrypted on this server."}>
          <input type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <label className="check"><input type="checkbox" checked={settings.enabled} onChange={(e) => setSettings({ ...settings, enabled: e.target.checked })} /><span>Check automatically every hour</span></label>
        <button className="btn primary" onClick={save} disabled={busy || !settings.username}>Save and check</button>
        {settings.last_checked_at && (
          <p className="faint" style={{ marginTop: 10 }}>Last checked {formatDate(settings.last_checked_at)}{settings.last_error ? `: ${settings.last_error}` : "."}</p>
        )}
      </section>
      )}

      <section className="panel">
        <h2>What we found</h2>
        {items.length === 0 && <p className="muted">No replies matched to your applications yet. Phone calls can't be detected; record them on the application.</p>}
        {items.map((d) => {
          const [label, tone] = LABEL[d.classification] ?? [d.classification, ""];
          return (
            <div className="entry" key={d.event_id}>
              <div className="spread">
                <div>
                  <span className={`pill ${tone}`}>{label}</span>{" "}
                  <Link to={`/applications/${d.application_id}`}><strong>{d.title}</strong>, {d.company}</Link>
                </div>
                <span className="faint">{formatDate(d.occurred_at)}</span>
              </div>
              <div style={{ marginTop: 6 }}><strong>{d.subject}</strong> <span className="faint">from {d.from}</span></div>
              {d.evidence && <div className="faint">“{d.evidence}”</div>}
              {!d.resolved && d.suggested_status && (
                <div className="row" style={{ marginTop: 8 }}>
                  <button className="btn small primary" onClick={() => resolve(d, true)}>Mark as {statusLabel(d.suggested_status)}</button>
                  <button className="btn small quiet" onClick={() => resolve(d, false)}>Not related</button>
                </div>
              )}
              {d.resolved && <div className="faint" style={{ marginTop: 6 }}>{d.applied ? "Status updated." : "Dismissed."}</div>}
            </div>
          );
        })}
      </section>
    </>
  );
}
