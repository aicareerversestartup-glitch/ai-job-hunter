import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { get } from "../api/client";
import { isNative } from "../api/platform";
import type { BillingStatus, Dashboard, User } from "../api/types";
import Icon from "./Icon";
import AdSlot, { adsAllowedOn, setUserSeesAds, useNativeBanner } from "./Ads";

type Link = { to: string; label: string; icon: string; count?: (d: Dashboard) => number; webOnly?: boolean };

const GROUPS: { title: string; links: Link[] }[] = [
  { title: "", links: [
    { to: "/", label: "Overview", icon: "home" },
    { to: "/jobs", label: "Jobs", icon: "jobs" },
    { to: "/applications", label: "Applications", icon: "apps", count: (d) => d.awaiting_review + d.needs_action },
    { to: "/inbox", label: "Interview emails", icon: "mail", count: (d) => d.pending_emails },
  ] },
  { title: "Your profile", links: [
    { to: "/cv", label: "Master CV", icon: "cv" },
    { to: "/profile", label: "Profile & targets", icon: "user" },
    { to: "/companies", label: "Target companies", icon: "building" },
    { to: "/cv-formats", label: "CV formats", icon: "layout" },
  ] },
  { title: "More", links: [
    { to: "/resources", label: "Resources", icon: "globe" },
    { to: "/plans", label: "Plan & invites", icon: "shield" },
    { to: "/sources", label: "Job sources", icon: "plug" },
    { to: "/settings", label: "Account & AI", icon: "spark" },
  ] },
];
const ALL = GROUPS.flatMap((g) => g.links);
const TABS = ["/", "/jobs", "/applications", "/inbox"];

export default function Layout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [stats, setStats] = useState<Dashboard | null>(null);
  const [sheet, setSheet] = useState(false);
  const location = useLocation();
  useEffect(() => setSheet(false), [location.pathname]);
  const [plan, setPlan] = useState<BillingStatus | null>(null);
  useEffect(() => {
    get<BillingStatus>("/api/billing/status").then((b) => { setPlan(b); setUserSeesAds(b.show_ads); }).catch(() => {});
  }, [location.pathname === "/plans"]);

  useEffect(() => {
    const load = () => get<Dashboard>("/api/dashboard").then(setStats).catch(() => {});
    load();
    const t = window.setInterval(load, 30000);
    return () => window.clearInterval(t);
  }, []);
  const adsHere = adsAllowedOn(location.pathname);
  const bannerShown = useNativeBanner(adsHere && !sheet);
  const count = (l: Link) => (stats && l.count ? l.count(stats) : 0);
  const title = ALL.find((l) => (l.to === "/" ? location.pathname === "/" : location.pathname.startsWith(l.to)))?.label ?? "AI Job Hunter";

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">JH</span>
          <span><b>AI Job Hunter</b><small>{user.full_name || user.email}</small></span>
        </div>
        {GROUPS.map((g) => (
          <div key={g.title || "main"}>
            {g.title && <div className="nav-group">{g.title}</div>}
            {g.links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.to === "/"} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
                <Icon name={l.icon} size={18} />
                {l.label}
                {count(l) > 0 && <span className="nav-count" aria-label={`${count(l)} need attention`}>{count(l)}</span>}
              </NavLink>
            ))}
          </div>
        ))}
        {plan?.plan === "free" && (
          <NavLink to="/plans" className="go-pro">
            <b>Go Pro</b><span>No ads, more applications, AI rewriting</span>
          </NavLink>
        )}
        <div className="sidebar-foot">
          {!isNative() && <a href="/privacy">Privacy</a>}
          <button type="button" onClick={onLogout}>Sign out</button>
        </div>
      </nav>

      <header className="appbar">
        <span className="brand-mark" aria-hidden="true">JH</span>
        <strong>{title}</strong>
        <button className="icon-btn" aria-label="Sign out" onClick={onLogout}><Icon name="out" /></button>
      </header>

      <main className={`main${bannerShown ? " with-banner" : ""}`} id="main">
        <Outlet />
        {adsHere && <AdSlot placement="bottom" />}
      </main>

      <nav className="tabbar" aria-label="Main">
        {ALL.filter((l) => TABS.includes(l.to)).map((l) => (
          <NavLink key={l.to} to={l.to} end={l.to === "/"} className={({ isActive }) => `tab-link${isActive ? " active" : ""}`}>
            <Icon name={l.icon} size={22} />
            {l.label === "Interview emails" ? "Emails" : l.label}
            {count(l) > 0 && <span className="nav-count">{count(l)}</span>}
          </NavLink>
        ))}
        <button className={`tab-link${sheet ? " active" : ""}`} onClick={() => setSheet(true)} aria-haspopup="dialog">
          <Icon name="menu" size={22} />More
        </button>
      </nav>

      <div className={`sheet-backdrop${sheet ? " open" : ""}`} onClick={() => setSheet(false)} />
      {sheet && (
        <div className="sheet" role="dialog" aria-label="More">
          <div className="sheet-grip" />
          {ALL.filter((l) => !TABS.includes(l.to)).map((l) => (
            <NavLink key={l.to} to={l.to} className="nav-link"><Icon name={l.icon} size={20} />{l.label}</NavLink>
          ))}
          <button className="nav-link" style={{ border: 0, background: "none", width: "100%", font: "inherit", cursor: "pointer" }} onClick={onLogout}>
            <Icon name="out" size={20} />Sign out
          </button>
        </div>
      )}
    </div>
  );
}
