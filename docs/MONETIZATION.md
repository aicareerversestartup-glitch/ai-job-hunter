# Earning from AI Job Hunter

Five income streams are built in. All are off until you add your IDs to `.env`, so the app works without them.

| Stream | Where | Set up |
|---|---|---|
| Banner ads | Apps (AdMob), website (AdSense) | §1 |
| Rewarded ads (+5 applications today) | Apps | §1 |
| Pro subscription | Apps (Apple/Google billing) and website (RevenueCat Web Billing / Stripe) | §2 |
| Invite-a-friend (both get Pro days) | Everywhere | Works automatically; tune `REFERRAL_PRO_DAYS` |
| Partner / affiliate links | Resources page | §3 |

What the app will never do to earn money: sell or share users' CVs or personal data, show ads on CV editing, application approval, sign-in or account screens, or push users with full-screen/popup ads.

## 1. Ads

**AdMob (Android and iOS apps)**
1. Create an AdMob account, add the Android app and the iOS app (after they're published, or as "not published yet").
2. Create ad units: one **Banner** and one **Rewarded** per platform.
3. Put the **app IDs** (`ca-app-pub-…~…`) in `frontend/.env.app` and run `node scripts/patch-native.mjs`.
4. Put the **ad unit IDs** (`ca-app-pub-…/…`) and your publisher ID in `.env`: `ADMOB_BANNER_*`, `ADMOB_REWARDED_*`, `ADMOB_PUBLISHER_ID`. Set `ADS_ENABLED=true`.
5. Keep `ADS_TEST_MODE=true` until AdMob approves the app. Clicking your own live ads gets accounts banned.
6. In AdMob → Privacy & messaging, create a **GDPR consent message** (required for EEA/UK users) and an **IDFA explainer** for iOS. The app shows them through Google's UMP SDK.
7. Your website serves `https://DOMAIN/app-ads.txt` automatically; add the website URL in both store listings so AdMob can verify it.
8. Optional, recommended: turn on **server-side verification** for the rewarded ad unit. The server caps rewards at `REWARD_ADS_PER_DAY`, but SSV stops anyone faking a completed view.

Where ads appear: one adaptive banner above the tab bar on Overview, Jobs, a job's details, Applications, Interview emails and Target companies; nothing on other screens. Pro users never see ads.

**AdSense (website)**
1. Apply with your domain (Google reviews the site; the public landing page and legal pages help).
2. Create two display ad units (e.g. "waiting" and "in-feed") and set `ADSENSE_CLIENT`, `ADSENSE_SLOT_WAITING`, `ADSENSE_SLOT_FEED`.
3. In AdSense → Privacy & messaging, enable the European regulations message (Google's certified consent banner).
4. `https://DOMAIN/ads.txt` is served automatically.

Website placements: bottom of the content pages, inside the jobs list after every 8 jobs (at most 2), and next to the progress and tips while searching or preparing.

## 2. Pro subscription (RevenueCat)

1. Create products:
   - **App Store Connect**: subscription group "Pro", products e.g. `pro_monthly`, `pro_yearly`.
   - **Google Play Console**: subscription "pro" with monthly and yearly base plans.
   - **Website**: RevenueCat Web Billing (connects to your Stripe account).
2. In RevenueCat: create a project, add the three apps, create entitlement **`pro`**, attach all products, and put monthly + yearly packages in the **default offering**.
3. Copy keys to `.env`: `REVENUECAT_PUBLIC_IOS` (appl_), `REVENUECAT_PUBLIC_ANDROID` (goog_), `REVENUECAT_PUBLIC_WEB` (rcb_), and the server-only `REVENUECAT_SECRET_KEY` (sk_).
4. RevenueCat → Integrations → Webhooks: URL `https://DOMAIN/api/billing/revenuecat`, Authorization header = a long random string you also put in `REVENUECAT_WEBHOOK_AUTH`.

The server never trusts the app about purchases: after every purchase, restore or webhook it asks RevenueCat for the user's real entitlements.

**Pricing** is your decision and is set in each store, not in code. People often test regional prices (stores support price per country) and offer a yearly plan at a discount. Change the free/Pro limits with `FREE_DRAFTS_PER_DAY`, `MAX_DRAFTS_PER_DAY`, `FREE_SEARCHES_PER_DAY`, `PRO_SEARCHES_PER_DAY`.

Store rules to keep: in the apps, Pro may only be bought through Apple/Google billing; don't put a "pay on our website" link inside the iOS app unless you've confirmed it's allowed in your region under Apple's current rules.

**AI cost**: Pro includes AI rewriting with the server's AI key (`AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`). Free users only get AI if they add their own key, unless you set `SERVER_AI_FOR_FREE_USERS=true`. Each tailored application costs a few AI calls; price Pro above that.

## 3. Partner / affiliate links

Edit `data/partners.json`: join each partner's affiliate program (language courses, credential evaluation, money transfer, insurance…), paste your tracking link into `url`, and set `"enabled": true`. The Resources page labels them as partner links. Clicks are counted (no personal data is sent to partners).

## 4. Invites

Every user has an invite link on **Plan & invites** (`https://DOMAIN/signup?ref=CODE`). When someone signs up with it, both get `REFERRAL_PRO_DAYS` of Pro (the inviter is rewarded for up to 20 sign-ups).

## Realistic expectations

Banner ads usually earn little per user; rewarded ads earn more per view; subscriptions are normally the main income for productivity apps. Actual results depend on your audience, country mix and how useful users find the app, so measure for a few weeks before changing prices or limits.
