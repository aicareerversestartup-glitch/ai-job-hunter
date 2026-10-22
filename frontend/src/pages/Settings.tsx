import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post, put } from "../api/client";
import { downloadFile, isNative } from "../api/platform";
import { showAdPrivacyOptions } from "../components/Ads";
import type { AISettings } from "../api/types";
import { Field, useToast } from "../components/ui";

const PROVIDERS: [string, string, string][] = [
  ["none", "No AI", "Everything works without AI: CVs are reordered for relevance and letters use your own wording."],
  ["openai", "OpenAI", "Uses your OpenAI API key."],
  ["anthropic", "Anthropic (Claude)", "Uses your Anthropic API key."],
  ["gemini", "Google Gemini", "Uses your Google AI Studio key."],
  ["ollama", "Ollama (runs on your computer)", "Free and private. Install Ollama and pull a model first."],
  ["openai_compatible", "Other OpenAI-compatible service", "Groq, OpenRouter, LM Studio, Together and similar."],
];

export default function Settings({ onDeleted }: { onDeleted: () => void }) {
  const toast = useToast();
  const [ai, setAi] = useState<AISettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { get<AISettings>("/api/settings/ai").then(setAi).catch((e) => toast(e.message, "error")); }, []);
  if (!ai) return <p className="muted">Loading…</p>;
  const info = PROVIDERS.find((p) => p[0] === ai.provider);

  const save = async () => {
    setBusy(true);
    try {
      setAi(await put<AISettings>("/api/settings/ai", { provider: ai.provider, model: ai.model, base_url: ai.base_url,
        temperature: ai.temperature, api_key: apiKey ? apiKey : null }));
      setApiKey("");
      toast("Saved.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };
  const test = async () => {
    const r = await post<{ ok: boolean; message: string }>("/api/settings/ai/test");
    toast(r.message, r.ok ? "info" : "error");
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Account &amp; AI</h1>
          <p>Your account, your data, and which AI rewrites your documents.</p>
        </div>
      </div>
      <section className="panel" style={{ maxWidth: 640 }}>
        {ai.source === "server-default" && ai.provider !== "none" && <div className="notice"><p>Using the server's default AI. Save your own to override it.</p></div>}
        <Field label="Provider" hint={info?.[2]}>
          <select value={ai.provider} onChange={(e) => setAi({ ...ai, provider: e.target.value })}>
            {PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        {ai.provider !== "none" && (
          <>
            <Field label="Model name" hint="Exactly as the provider names it. Check the provider's model list.">
              <input type="text" value={ai.model} onChange={(e) => setAi({ ...ai, model: e.target.value })} />
            </Field>
            {(ai.provider === "ollama" || ai.provider === "openai_compatible") && (
              <Field label="Service address" hint={ai.provider === "ollama" ? "Leave empty for http://localhost:11434/v1" : "The service's /v1 address."}>
                <input type="url" value={ai.base_url} onChange={(e) => setAi({ ...ai, base_url: e.target.value })} />
              </Field>
            )}
            {ai.provider !== "ollama" && (
              <Field label="API key" hint={ai.api_key_masked ? `Saved key ${ai.api_key_masked}. Leave empty to keep it.` : "Stored encrypted on this server."}>
                <input type="password" value={apiKey} autoComplete="off" onChange={(e) => setApiKey(e.target.value)} />
              </Field>
            )}
            <Field label={`Creativity: ${ai.temperature.toFixed(1)}`} hint="Lower keeps wording closer to your original.">
              <input type="range" min={0} max={1} step={0.1} value={ai.temperature} onChange={(e) => setAi({ ...ai, temperature: Number(e.target.value) })} />
            </Field>
          </>
        )}
        <div className="row">
          <button className="btn primary" onClick={save} disabled={busy}>Save</button>
          {ai.provider !== "none" && <button className="btn" onClick={test}>Test connection</button>}
        </div>
      </section>
      <AccountSection onDeleted={onDeleted} />
    </>
  );
}

function AccountSection({ onDeleted }: { onDeleted: () => void }) {
  const toast = useToast();
  const [pw, setPw] = useState({ current: "", next: "" });
  const [del, setDel] = useState({ password: "", confirm: "" });
  const [busy, setBusy] = useState(false);

  const changePassword = async () => {
    setBusy(true);
    try {
      await post("/api/auth/change-password", { current_password: pw.current, new_password: pw.next });
      setPw({ current: "", next: "" });
      toast("Password changed. Other devices were signed out.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };
  const deleteAccount = async () => {
    setBusy(true);
    try {
      await post("/api/auth/delete-account", del);
      toast("Your account and data were deleted.");
      onDeleted();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <section className="panel" style={{ maxWidth: 680 }}>
        <h2>Password</h2>
        <div className="entry-grid">
          <Field label="Current password"><input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></Field>
          <Field label="New password" hint="At least 10 characters."><input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></Field>
        </div>
        <button className="btn" disabled={busy || !pw.current || pw.next.length < 10} onClick={changePassword}>Change password</button>
      </section>

      <section className="panel" style={{ maxWidth: 680 }}>
        <h2>Your data</h2>
        <p className="muted">Download everything we store about you as a file.</p>
        <div className="row">
          <button className="btn" onClick={() => downloadFile("/api/auth/export", "ai-job-hunter-export.json").catch((e) => toast(e.message, "error"))}>Export my data</button>
          {isNative() && <button className="btn" onClick={async () => { if (!(await showAdPrivacyOptions())) toast("No ad privacy choices are needed in your region."); }}>Ad privacy choices</button>}
          <Link className="btn quiet" to="/privacy">Privacy Policy</Link>
          <Link className="btn quiet" to="/terms">Terms</Link>
        </div>
      </section>

      <section className="panel" style={{ maxWidth: 680, borderColor: "var(--stop)" }}>
        <h2>Delete account</h2>
        <p className="muted">Permanently deletes your account, CVs, profile, jobs, applications, documents and connected inbox. This can't be undone.</p>
        <div className="entry-grid">
          <Field label="Password"><input type="password" autoComplete="current-password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} /></Field>
          <Field label="Type DELETE to confirm"><input type="text" value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} /></Field>
        </div>
        <button className="btn danger" disabled={busy || del.confirm !== "DELETE" || !del.password} onClick={deleteAccount}>Delete my account</button>
      </section>
    </>
  );
}
