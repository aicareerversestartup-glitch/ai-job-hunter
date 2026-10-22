import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { isNative, openExternal, shareText } from "../api/platform";
import { buy, loadPlans, manageSubscriptionUrl, purchasesAvailable, restore, watchRewardedAd, type PlanOption } from "../api/purchases";
import type { BillingStatus, User } from "../api/types";
import { adsConfig, setUserSeesAds } from "../components/Ads";
import Icon from "../components/Icon";
import { formatDate, useToast } from "../components/ui";
import { usePublicConfig } from "./Legal";

const ROWS: [string, string, string][] = [
  ["Applications prepared per day", "free_drafts", "pro_drafts"],
  ["Job searches per day", "free_searches", "pro_searches"],
  ["AI rewriting of CVs and letters", "Your own AI key", "Included"],
  ["Ads", "Yes", "None"],
  ["Country CV formats, truthfulness checks, tracking", "Included", "Included"],
];

export default function Plans({ user }: { user: User }) {
  const toast = useToast();
  const cfg = usePublicConfig();
  const [st, setSt] = useState<BillingStatus | null>(null);
  const [plans, setPlans] = useState<PlanOption[]>([]);
  const [busy, setBusy] = useState("");

  const accept = (s: BillingStatus) => { setSt(s); setUserSeesAds(s.show_ads); };
  useEffect(() => {
    get<BillingStatus>("/api/billing/status").then((s) => {
      accept(s);
      loadPlans(s, user.id).then(setPlans).catch(() => setPlans([]));
    }).catch((e) => toast(e.message, "error"));
  }, []);
  if (!st) return <p className="muted">Loading…</p>;
  const pro = st.plan === "pro";
  const cell = (v: string) => ({ free_drafts: String(st.limits.free_drafts), pro_drafts: `Up to ${st.limits.pro_drafts}`,
    free_searches: String(st.limits.free_searches), pro_searches: String(st.limits.pro_searches) } as Record<string, string>)[v] ?? v;
  const referralLink = st.referral_code ? `${cfg.public_url || window.location.origin}/signup?ref=${st.referral_code}` : "";

  const doBuy = async (p: PlanOption) => {
    setBusy(p.id);
    try {
      const s = await buy(st, user.id, p);
      accept(s);
      toast(s.plan === "pro" ? "Welcome to Pro. Ads are off." : "Purchase received; it may take a minute to activate.");
    } catch (e) {
      const msg = (e as Error).message || "";
      if (!/cancel/i.test(msg)) toast(msg || "The purchase didn't go through.", "error");
    } finally {
      setBusy("");
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{pro ? "You're on Pro" : "Go Pro"}</h1>
          <p>{pro
            ? (st.plan_expires_at ? `Pro until ${formatDate(st.plan_expires_at)}${st.plan_source === "referral" ? " (invite bonus)" : ""}.` : "Thanks for supporting AI Job Hunter.")
            : "More applications a day, AI rewriting included, and no ads."}</p>
        </div>
      </div>

      <section className="panel">
        <div className="table-scroll">
          <table className="compare">
            <thead><tr><th /><th>Free</th><th className="pro">Pro</th></tr></thead>
            <tbody>
              {ROWS.map(([label, f, p]) => <tr key={label}><td>{label}</td><td>{cell(f)}</td><td className="pro">{cell(p)}</td></tr>)}
            </tbody>
          </table>
        </div>

        {!pro && (
          <div style={{ marginTop: 16 }}>
            {plans.length > 0 ? (
              <div className="plan-buttons">
                {plans.map((p) => (
                  <button key={p.id} className="btn primary" disabled={!!busy} onClick={() => doBuy(p)}>
                    {busy === p.id ? "Opening…" : `${p.price}${p.period ? ` / ${p.period}` : ""}`}
                  </button>
                ))}
              </div>
            ) : (
              <p className="faint">{purchasesAvailable(st) ? "Loading prices…" : "Pro isn't available to buy here yet."}</p>
            )}
            <p className="faint" style={{ marginTop: 10 }}>
              {isNative()
                ? "Payment is charged to your Apple ID / Google Play account. The subscription renews automatically unless cancelled at least 24 hours before the end of the period; manage or cancel it in your store account settings."
                : "Billed securely by our payment provider. Cancel any time from the link in your receipt."}{" "}
              <Link to="/terms">Terms of Use</Link> and <Link to="/privacy">Privacy Policy</Link>.
            </p>
          </div>
        )}
        <div className="row" style={{ marginTop: 8 }}>
          {isNative() && purchasesAvailable(st) && (
            <button className="btn quiet" disabled={!!busy} onClick={async () => {
              setBusy("restore");
              try { const s = await restore(st, user.id); accept(s); toast(s.plan === "pro" ? "Pro restored." : "No active Pro subscription found."); }
              catch (e) { toast((e as Error).message, "error"); } finally { setBusy(""); }
            }}>Restore purchases</button>
          )}
          {pro && st.plan_source === "store" && manageSubscriptionUrl() && (
            <button className="btn quiet" onClick={() => openExternal(manageSubscriptionUrl())}>Manage subscription</button>
          )}
        </div>
      </section>

      {!pro && isNative() && st.reward_ads_left > 0 && (
        <section className="panel">
          <h2>Need a few more today?</h2>
          <p className="muted">Watch a short ad and get {st.reward_ad_bonus} extra applications for today ({st.reward_ads_left} left today).</p>
          <button className="btn" disabled={!!busy} onClick={async () => {
            setBusy("ad");
            try {
              const ads = await adsConfig();
              const s = await watchRewardedAd({ android: ads?.admob_rewarded_android ?? "", ios: ads?.admob_rewarded_ios ?? "" }, ads?.test_mode ?? true);
              if (s) { accept(s); toast(`+${s.reward_ad_bonus} applications added for today.`); }
              else toast("The ad was closed before the end, so no bonus this time.");
            } catch (e) { toast((e as Error).message, "error"); } finally { setBusy(""); }
          }}>Watch ad for +{st.reward_ad_bonus}</button>
        </section>
      )}

      {referralLink && (
        <section className="panel">
          <h2>Invite a friend, both get {st.referral_pro_days} days of Pro</h2>
          <p className="muted">Share your link. When a friend creates an account with it, you both get Pro free for {st.referral_pro_days} days.</p>
          <div className="row">
            <input type="text" readOnly value={referralLink} aria-label="Your invite link" style={{ flex: 1, minWidth: 220 }} />
            <button className="btn" onClick={async () => {
              const r = await shareText("Find jobs abroad with AI Job Hunter", `I'm using AI Job Hunter to find jobs abroad. Join with my link and we both get ${st.referral_pro_days} days of Pro: ${referralLink}`);
              toast(r === "copied" ? "Invite copied." : "Shared.");
            }}><Icon name="share" size={16} />Share</button>
          </div>
        </section>
      )}

      <p className="faint">Today: {st.drafts_used_today} of {st.drafts_per_day} applications, {st.searches_used_today} of {st.searches_per_day} searches.</p>
    </>
  );
}
