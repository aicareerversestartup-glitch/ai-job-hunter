// Advertising: AdMob banners in the Android/iOS apps, AdSense on the website.
// Rules kept here so screens can't break ad policies by accident:
//  - Ads appear only next to real content (progress + curated tips, or the jobs list).
//  - Never on CV editing, application review/approval, sign-in, account or legal screens.
//  - Consent first: Google UMP (EEA/UK) and, on iOS, App Tracking Transparency.
//  - Nothing renders until ad IDs are configured on the server (ADS_ENABLED=true).
import { useEffect, useRef, useState } from "react";
import { get } from "../api/client";
import { isNative, platform } from "../api/platform";

export interface AdsConfig {
  enabled: boolean; test_mode: boolean; adsense_client: string; adsense_slot_waiting: string;
  adsense_slot_feed: string; admob_banner_android: string; admob_banner_ios: string;
  admob_rewarded_android: string; admob_rewarded_ios: string;
}

// Pro users never see ads. The Layout sets this from /api/billing/status.
let userSeesAds = false;
const listeners = new Set<(v: boolean) => void>();
export function setUserSeesAds(v: boolean) { userSeesAds = v; listeners.forEach((l) => l(v)); }
function useUserSeesAds(): boolean {
  const [v, setV] = useState(userSeesAds);
  useEffect(() => { listeners.add(setV); return () => { listeners.delete(setV); }; }, []);
  return v;
}

let configPromise: Promise<AdsConfig | null> | null = null;
export function adsConfig(): Promise<AdsConfig | null> {
  configPromise ??= get<{ ads: AdsConfig }>("/api/auth/config").then((c) => (c.ads?.enabled ? c.ads : null)).catch(() => null);
  return configPromise;
}

// Google's public test banner IDs: safe to use before your own ad units are approved.
const TEST_BANNER = { android: "ca-app-pub-3940256099942544/6300978111", ios: "ca-app-pub-3940256099942544/2934735716" };

let nativeReady: Promise<boolean> | null = null;
async function initNativeAds(cfg: AdsConfig): Promise<boolean> {
  nativeReady ??= (async () => {
    try {
      const { AdMob, AdmobConsentStatus } = await import("@capacitor-community/admob");
      await AdMob.initialize({ initializeForTesting: cfg.test_mode });
      const info = await AdMob.requestConsentInfo();
      if (info.isConsentFormAvailable && info.status === AdmobConsentStatus.REQUIRED) {
        await AdMob.showConsentForm();
      }
      if (platform() === "ios") {
        const tracking = await AdMob.trackingAuthorizationStatus();
        if (tracking.status === "notDetermined") await AdMob.requestTrackingAuthorization();
      }
      return true;
    } catch {
      return false; // ads are optional; the app works without them
    }
  })();
  return nativeReady;
}

/** Let users change their ad consent later (required where UMP applies). */
export async function showAdPrivacyOptions(): Promise<boolean> {
  if (!isNative()) return false;
  try {
    const { AdMob } = await import("@capacitor-community/admob");
    await AdMob.showPrivacyOptionsForm();
    return true;
  } catch {
    return false;
  }
}

let adsenseLoaded = false;
function loadAdsense(client: string) {
  if (adsenseLoaded) return;
  adsenseLoaded = true;
  const s = document.createElement("script");
  s.async = true;
  s.crossOrigin = "anonymous";
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
  document.head.appendChild(s);
}

function WebAd({ client, slot, test }: { client: string; slot: string; test: boolean }) {
  const ref = useRef<HTMLModElement>(null);
  useEffect(() => {
    loadAdsense(client);
    try {
      const w = window as unknown as { adsbygoogle: unknown[] };
      (w.adsbygoogle = w.adsbygoogle || []).push({});
    } catch {
      /* blocked by an ad blocker: fine */
    }
  }, [client, slot]);
  return (
    <div className="ad-slot" aria-label="Advertisement">
      <span className="ad-label">Advertisement</span>
      <ins ref={ref} className="adsbygoogle" style={{ display: "block" }} data-ad-client={client} data-ad-slot={slot}
           data-ad-format="auto" data-full-width-responsive="true" {...(test ? { "data-adtest": "on" } : {})} />
    </div>
  );
}

/** One native banner at the bottom (above the tab bar) while `active`. Managed once, by the Layout. */
export function useNativeBanner(activeRoute: boolean): boolean {
  const [shown, setShown] = useState(false);
  const allowed = useUserSeesAds();
  const active = activeRoute && allowed;
  useEffect(() => {
    if (!isNative()) return;
    let cancelled = false;
    (async () => {
      const cfg = await adsConfig();
      if (!cfg || !active) {
        const { AdMob } = await import("@capacitor-community/admob");
        await AdMob.removeBanner().catch(() => {});
        setShown(false);
        return;
      }
      if (!(await initNativeAds(cfg)) || cancelled) return;
      const { AdMob, BannerAdPosition, BannerAdSize } = await import("@capacitor-community/admob");
      const own = platform() === "ios" ? cfg.admob_banner_ios : cfg.admob_banner_android;
      const adId = cfg.test_mode || !own ? (platform() === "ios" ? TEST_BANNER.ios : TEST_BANNER.android) : own;
      await AdMob.showBanner({ adId, adSize: BannerAdSize.ADAPTIVE_BANNER, position: BannerAdPosition.BOTTOM_CENTER,
                               margin: 64, isTesting: cfg.test_mode });
      if (!cancelled) setShown(true);
    })().catch(() => setShown(false));
    return () => { cancelled = true; };
  }, [active]);
  return shown;
}

/** Website ad slots. "bottom": end of a page. "feed": between jobs. "waiting": beside progress + tips.
 *  In the apps these render nothing; the single bottom banner is handled by the Layout. */
export default function AdSlot({ placement }: { placement: "bottom" | "feed" | "waiting" }) {
  const [cfg, setCfg] = useState<AdsConfig | null>(null);
  const allowed = useUserSeesAds();
  useEffect(() => { if (!isNative()) adsConfig().then(setCfg); }, []);
  if (!cfg || isNative() || !allowed) return null;
  const slot = placement === "feed" ? cfg.adsense_slot_feed : cfg.adsense_slot_waiting;
  if (!cfg.adsense_client || !slot) return null;
  return <WebAd client={cfg.adsense_client} slot={slot} test={cfg.test_mode} />;
}

/** Pages where ads are allowed. Everything else (CV editing, review/approval, sign-in, account, legal)
 *  never shows ads. */
export const AD_ROUTES = [/^\/$/, /^\/jobs$/, /^\/jobs\/\d+$/, /^\/applications$/, /^\/inbox$/, /^\/companies$/];
export const adsAllowedOn = (path: string) => AD_ROUTES.some((r) => r.test(path));

/** Insert at most `max` feed ads, one after every `every` items. */
export function feedAdAfter(index: number, total: number, every = 8, max = 2): boolean {
  const n = index + 1;
  return n % every === 0 && n / every <= max && n < total;
}
