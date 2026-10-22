import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { get, post, setUnauthorizedHandler } from "./api/client";
import { isNative, loadToken, saveToken } from "./api/platform";
import type { User } from "./api/types";
import Layout from "./components/Layout";
import Login, { ResetPassword } from "./pages/Login";
import Landing from "./pages/Landing";
import { DeleteAccountInfo, Privacy, Terms } from "./pages/Legal";
import Overview from "./pages/Overview";
import Jobs from "./pages/Jobs";
import JobDetail from "./pages/JobDetail";
import Applications from "./pages/Applications";
import ApplicationReview from "./pages/ApplicationReview";
import MasterCVPage from "./pages/MasterCV";
import ProfilePage from "./pages/Profile";
import Sources from "./pages/Sources";
import Settings from "./pages/Settings";
import Companies from "./pages/Companies";
import CVFormats from "./pages/CVFormats";
import Inbox from "./pages/Inbox";
import Plans from "./pages/Plans";
import Resources from "./pages/Resources";

function useNativeShell() {
  const navigate = useNavigate();
  useEffect(() => {
    if (!isNative()) return;
    let remove: (() => void) | undefined;
    (async () => {
      const [{ App: CapApp }, { StatusBar, Style }] = await Promise.all([import("@capacitor/app"), import("@capacitor/status-bar")]);
      StatusBar.setStyle({ style: Style.Dark }).catch(() => {});
      const handle = await CapApp.addListener("backButton", ({ canGoBack }) => {
        if (canGoBack) navigate(-1);
        else CapApp.minimizeApp();
      });
      remove = () => handle.remove();
    })();
    return () => remove?.();
  }, [navigate]);
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  useNativeShell();

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    loadToken().then(() => get<User>("/api/auth/me")).then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined) return <div className="auth-wrap"><p className="muted">Loading…</p></div>;

  const legal = [
    <Route key="privacy" path="privacy" element={<Privacy />} />,
    <Route key="terms" path="terms" element={<Terms />} />,
    <Route key="delete" path="delete-account" element={<DeleteAccountInfo />} />,
  ];

  if (user === null) {
    return (
      <Routes>
        <Route path="/" element={isNative() ? <Login onSignedIn={setUser} /> : <Landing />} />
        <Route path="/login" element={<Login onSignedIn={setUser} />} />
        <Route path="/signup" element={<Login onSignedIn={setUser} initial="register" />} />
        <Route path="/r/:code" element={<ReferralRedirect />} />
        <Route path="/reset-password" element={<ResetPassword onSignedIn={setUser} />} />
        {legal}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  const logout = async () => {
    await post("/api/auth/logout").catch(() => {});
    await saveToken(null);
    setUser(null);
  };

  return (
    <Routes>
      {legal}
      <Route element={<Layout user={user} onLogout={logout} />}>
        <Route index element={<Overview />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="jobs/:id" element={<JobDetail />} />
        <Route path="applications" element={<Applications />} />
        <Route path="applications/:id" element={<ApplicationReview />} />
        <Route path="cv" element={<MasterCVPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="sources" element={<Sources />} />
        <Route path="companies" element={<Companies />} />
        <Route path="cv-formats" element={<CVFormats />} />
        <Route path="inbox" element={<Inbox />} />
        <Route path="plans" element={<Plans user={user} />} />
        <Route path="resources" element={<Resources />} />
        <Route path="settings" element={<Settings onDeleted={() => { saveToken(null); setUser(null); }} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function ReferralRedirect() {
  const { code } = useParams();
  return <Navigate to={`/signup?ref=${encodeURIComponent((code ?? "").toUpperCase())}`} replace />;
}
