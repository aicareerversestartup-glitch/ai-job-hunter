import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { get, post } from "../api/client";
import { isNative } from "../api/platform";
import type { User } from "../api/types";
import { Field } from "../components/ui";

type Mode = "login" | "register" | "forgot";

function Brand() {
  return <div className="brand"><span className="brand-mark" aria-hidden="true">JH</span><b>AI Job Hunter</b></div>;
}

export default function Login({ onSignedIn, initial = "login" }: { onSignedIn: (u: User) => void; initial?: Mode }) {
  const [params] = useSearchParams();
  const ref = (params.get("ref") ?? "").toUpperCase();
  const [mode, setMode] = useState<Mode>(initial);
  const [registrationOpen, setRegistrationOpen] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => setMode(initial), [initial]);
  useEffect(() => {
    get<{ has_users: boolean; registration_open: boolean }>("/api/auth/status")
      .then((s) => setRegistrationOpen(s.registration_open)).catch(() => {});
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setInfo("");
    try {
      if (mode === "forgot") {
        const r = await post<{ message: string; email_enabled: boolean }>("/api/auth/forgot-password", { email });
        setInfo(r.email_enabled ? r.message : "Password reset by email isn't set up on this server yet. Contact support.");
      } else {
        const body = mode === "login" ? { email, password } : { email, password, full_name: fullName, ref };
        const res = await post<{ user: User }>(`/api/auth/${mode}`, body);
        onSignedIn(res.user);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const heading = { login: "Welcome back", register: "Create your free account", forgot: "Reset your password" }[mode];
  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <Brand />
        <h1>{heading}</h1>
        <p className="muted">
          {mode === "login" && "Sign in to see your matches and applications."}
          {mode === "register" && (ref ? "You were invited: you'll both get free Pro days. " : "") + "Upload your CV next. Nothing is sent to an employer without your approval."}
          {mode === "forgot" && "Enter your email and we'll send you a link to choose a new password."}
        </p>
        {mode === "register" && (
          <Field label="Full name"><input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" /></Field>
        )}
        <Field label="Email"><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" inputMode="email" /></Field>
        {mode !== "forgot" && (
          <Field label="Password" hint={mode === "register" ? "At least 10 characters." : undefined}>
            <input type="password" required minLength={mode === "register" ? 10 : 1} value={password}
                   onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </Field>
        )}
        {mode === "register" && (
          <label className="check">
            <input type="checkbox" required checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            <span>I'm 18 or older and agree to the <Link to="/terms">Terms</Link> and <Link to="/privacy">Privacy Policy</Link>.</span>
          </label>
        )}
        {error && <div className="notice bad" role="alert">{error}</div>}
        {info && <div className="notice good" role="status">{info}</div>}
        <button className="btn primary block" type="submit" disabled={busy}>
          {mode === "login" ? "Sign in" : mode === "register" ? "Create account" : "Send reset link"}
        </button>
        <div className="spread" style={{ marginTop: 14 }}>
          {mode === "login" && <button className="btn quiet" type="button" onClick={() => setMode("forgot")}>Forgot password?</button>}
          {mode !== "login" && <button className="btn quiet" type="button" onClick={() => setMode("login")}>I have an account</button>}
          {mode === "login" && registrationOpen && <button className="btn quiet" type="button" onClick={() => setMode("register")}>Create an account</button>}
        </div>
        {isNative() && (
          <p className="faint" style={{ marginTop: 14 }}>
            <Link to="/privacy">Privacy Policy</Link> · <Link to="/terms">Terms</Link>
          </p>
        )}
      </form>
    </div>
  );
}

export function ResetPassword({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await post<{ user: User }>("/api/auth/reset-password", { token: params.get("token") ?? "", password });
      onSignedIn(res.user);
      navigate("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <Brand />
        <h1>Choose a new password</h1>
        <Field label="New password" hint="At least 10 characters. You'll be signed out on other devices.">
          <input type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </Field>
        {error && <div className="notice bad" role="alert">{error}</div>}
        <button className="btn primary block" disabled={busy}>Save password</button>
      </form>
    </div>
  );
}
