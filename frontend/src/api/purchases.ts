// Pro subscription through RevenueCat: Apple In-App Purchase on iOS, Google Play Billing on Android,
// RevenueCat Web Billing (Stripe) on the website. The server confirms with RevenueCat after each purchase.
import { post } from "./client";
import { isNative, platform } from "./platform";
import type { BillingStatus } from "./types";

export interface PlanOption { id: string; title: string; price: string; period: string; raw: unknown }

let configuredFor: string | null = null;

function keyFor(status: BillingStatus): string {
  const p = platform();
  return p === "ios" ? status.purchases.ios : p === "android" ? status.purchases.android : status.purchases.web;
}

export function purchasesAvailable(status: BillingStatus): boolean {
  return Boolean(keyFor(status));
}

async function nativeSdk(status: BillingStatus, userId: number) {
  const { Purchases } = await import("@revenuecat/purchases-capacitor");
  if (configuredFor !== String(userId)) {
    await Purchases.configure({ apiKey: keyFor(status), appUserID: String(userId) });
    configuredFor = String(userId);
  }
  return Purchases;
}

async function webSdk(status: BillingStatus, userId: number) {
  const { Purchases } = await import("@revenuecat/purchases-js");
  if (configuredFor !== String(userId)) {
    Purchases.configure(keyFor(status), String(userId));
    configuredFor = String(userId);
  }
  return Purchases.getSharedInstance();
}

const PERIODS: Record<string, string> = { P1M: "month", P1Y: "year", P1W: "week", P3M: "3 months", P6M: "6 months" };

export async function loadPlans(status: BillingStatus, userId: number): Promise<PlanOption[]> {
  if (!purchasesAvailable(status)) return [];
  if (isNative()) {
    const sdk = await nativeSdk(status, userId);
    const offerings = await sdk.getOfferings();
    const pkgs = offerings.current?.availablePackages ?? [];
    return pkgs.map((p: any) => ({ id: p.identifier, title: p.product.title, price: p.product.priceString,
      period: PERIODS[p.product.subscriptionPeriod ?? ""] ?? "", raw: p }));
  }
  const sdk = await webSdk(status, userId);
  const offerings = await sdk.getOfferings();
  const pkgs = offerings.current?.availablePackages ?? [];
  return pkgs.map((p: any) => ({ id: p.identifier, title: p.webBillingProduct?.title ?? p.identifier,
    price: p.webBillingProduct?.currentPrice?.formattedPrice ?? "",
    period: PERIODS[p.webBillingProduct?.normalPeriodDuration ?? ""] ?? "", raw: p }));
}

export async function buy(status: BillingStatus, userId: number, plan: PlanOption): Promise<BillingStatus> {
  if (isNative()) {
    const sdk = await nativeSdk(status, userId);
    await sdk.purchasePackage({ aPackage: plan.raw as any });
  } else {
    const sdk = await webSdk(status, userId);
    await sdk.purchase({ rcPackage: plan.raw as any });
  }
  return post<BillingStatus>("/api/billing/sync");
}

export async function restore(status: BillingStatus, userId: number): Promise<BillingStatus> {
  if (isNative()) {
    const sdk = await nativeSdk(status, userId);
    await sdk.restorePurchases();
  }
  return post<BillingStatus>("/api/billing/sync");
}

export function manageSubscriptionUrl(): string {
  const p = platform();
  if (p === "ios") return "https://apps.apple.com/account/subscriptions";
  if (p === "android") return "https://play.google.com/store/account/subscriptions";
  return "";
}

/** Rewarded ad (apps only): the user chooses to watch, the server grants today's bonus. */
export async function watchRewardedAd(adUnits: { android: string; ios: string }, testMode: boolean): Promise<BillingStatus | null> {
  if (!isNative()) return null;
  const { AdMob, RewardAdPluginEvents } = await import("@capacitor-community/admob");
  const TEST = { android: "ca-app-pub-3940256099942544/5224354917", ios: "ca-app-pub-3940256099942544/1712485313" };
  const own = platform() === "ios" ? adUnits.ios : adUnits.android;
  const adId = testMode || !own ? (platform() === "ios" ? TEST.ios : TEST.android) : own;
  let rewarded = false;
  const handle = await AdMob.addListener(RewardAdPluginEvents.Rewarded, () => { rewarded = true; });
  try {
    await AdMob.prepareRewardVideoAd({ adId, isTesting: testMode });
    await AdMob.showRewardVideoAd();
  } finally {
    handle.remove();
  }
  return rewarded ? post<BillingStatus>("/api/billing/reward-ad") : null;
}
