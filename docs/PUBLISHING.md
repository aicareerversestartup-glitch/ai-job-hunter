# Store Submission Kit: website, Google Play and App Store

This app was built to pass review first time: account deletion inside the app and on the web, Privacy Policy and Terms in the app and on the website, a demo account for reviewers, a report button for AI-generated content, honest store text, no third-party login, minimal permissions, ads only beside real content, consent for ads, and subscriptions through Apple/Google billing. Approval is still decided by the stores; this kit removes the usual reasons for rejection.

---

## 0. Decide these first (they can't easily change later)

| Item | Where | Notes |
|---|---|---|
| **App name** | stores, `frontend/capacitor.config.ts` (`appName`), `public/manifest.webmanifest` | Search both stores first. "AI Job Hunter" may already be taken or trademarked; a distinctive name avoids rejection and confusion. |
| **App ID / bundle ID** | `frontend/capacitor.config.ts` (`appId`) | Reverse domain you control, e.g. `com.yourcompany.jobhunter`. Permanent after the first upload. |
| **Domain** | `.env` → `DOMAIN`, `PUBLIC_URL`; `frontend/.env.app` → `VITE_API_BASE` | The apps talk to this server. Must be HTTPS. |
| **Operator name and support email** | `.env` → `OPERATOR_NAME`, `SUPPORT_EMAIL` | Shown in the Privacy Policy, Terms and account-deletion page. Must match your developer account. |
| **Google Play account type** | Play Console | New **personal** accounts must run a closed test with **12+ testers for 14 days** before production. Google documents this for personal accounts; an **organization** account (needs a D-U-N-S number) is the usual way to avoid it. Confirm in Play Console when you sign up. |

## 1. Put the website and server online

On any Linux server (2 GB RAM is enough to start) with Docker:

```bash
git clone <your copy> && cd ai-job-hunter
cp .env.example .env        # fill DOMAIN, PUBLIC_URL, SECRET_KEY, POSTGRES_PASSWORD, OPERATOR_NAME, SUPPORT_EMAIL, SMTP_*
docker compose up -d --build
docker compose exec app python scripts/seed_demo.py --email reviewer@yourdomain.com --password "<long password>"
```

Point the domain's DNS A record at the server first; Caddy gets the HTTPS certificate automatically. Check:
`https://DOMAIN/`, `/privacy`, `/terms`, `/delete-account`, `/api/health`.

The server runs the browser headless, so the "Fill the form for me" feature switches off automatically on the website and in the apps (`APPLY_ASSIST_ENABLED`). Users open the employer page and paste their approved answers instead.

## 2. Build the Android app

Needs Node.js 22, Android Studio (latest), JDK 21.

```bash
cd frontend
cp .env.app.example .env.app          # VITE_API_BASE=https://DOMAIN and your AdMob APP ids
npm install
npx cap add android
node scripts/patch-native.mjs         # AdMob id, AD_ID permission
npx @capacitor/assets generate --iconBackgroundColor "#0f1b2d" --splashBackgroundColor "#0f1b2d"
npm run android                        # builds, syncs, opens Android Studio
```

In Android Studio: *Build → Generate Signed App Bundle* → AAB. Keep the keystore safe (or enrol in Play App Signing). Capacitor 8 targets Android API 36, which Google Play requires for new apps and updates from 31 August 2026.

## 3. Build the iOS app

Needs a Mac with Xcode, or a cloud Mac build service such as Codemagic.

```bash
cd frontend
npm install
npx cap add ios
node scripts/patch-native.mjs         # GADApplicationIdentifier, tracking/photo/camera texts, export compliance
npx @capacitor/assets generate --iconBackgroundColor "#0f1b2d" --splashBackgroundColor "#0f1b2d"
npm run ios                            # opens Xcode
```

In Xcode: set your Team under Signing, add the **In-App Purchase** capability, then *Product → Archive → Distribute → App Store Connect*.

---

## 4. Google Play Console answers

**Store listing**
- Short description (80): `Find jobs abroad that fit your CV, with a truthful CV for each country.`
- Full description: see [Store text](#7-store-text).
- Graphics: icon 512×512 (`frontend/public/icons/icon-512.png`), feature graphic 1024×500 (`frontend/assets/play-feature-graphic.png`), at least 2 phone screenshots (take them from the app with the demo account).
- Category: Business. Contact email: your support email. Privacy Policy: `https://DOMAIN/privacy`.

**App content**
| Question | Answer |
|---|---|
| App access | Some functionality is restricted → give the demo account email and password from step 1, and: "Sign in, open Jobs, open a job, open Applications → review the prepared application." |
| Ads | Yes, the app contains ads. |
| Content rating | Business/productivity; no violence, sexual content, gambling, drugs or user-to-user chat. |
| Target audience | 18 and over. Not designed for children. |
| News app / Government app / Health / Financial features | No. |
| Data safety | See the table below. |
| Account deletion | Yes. In-app: Account & AI → Delete account. Web URL: `https://DOMAIN/delete-account`. |
| Generative AI | The app generates CV and cover-letter text. Users can report problems with the in-app "Report a problem with this AI content" button. |

**Data safety form**
| Data type | Collected | Shared | Purpose | Optional? |
|---|---|---|---|---|
| Name, email address | Yes | No | App functionality, Account management | Required |
| Phone number, address (from the CV) | Yes | No | App functionality | Optional |
| Other info: CV content, work history, education | Yes | No* | App functionality | Required for core features |
| Files and docs (uploaded CV, photo) | Yes | No | App functionality | Required (CV), optional (photo) |
| Purchase history | Yes | No | App functionality (Pro status) | Optional |
| Device or other IDs (advertising ID) | Yes | Yes, with Google (AdMob) | Advertising | Free plan |
| App interactions (ad performance) | Yes | Yes, with Google (AdMob) | Advertising, analytics | Free plan |

\*Processing by service providers on your behalf (hosting, the AI provider you configure) is not "sharing" in Google's definition. Data is encrypted in transit: Yes. Users can request deletion: Yes.

## 5. App Store Connect answers

**App Privacy ("nutrition label")**
- Contact Info (name, email, phone, physical address): App Functionality, linked to the user, not used for tracking.
- User Content (CV, documents, photo): App Functionality, linked, not tracking.
- Identifiers: User ID (App Functionality, linked); Device ID (Third-Party Advertising; tracking only if the user allows it in the ATT prompt).
- Purchases: App Functionality, linked.
- Usage Data → Advertising Data: Third-Party Advertising (AdMob).
- Diagnostics: only if you add a crash reporter.

**Review notes (paste and edit)**
> AI Job Hunter helps job seekers find international jobs and prepares a tailored CV, cover letter and answers for each job. Nothing is sent to an employer automatically: the user reviews and approves every application and applies on the employer's own website. Demo account: reviewer@yourdomain.com / <password>. The account already has a CV, jobs and one prepared application (Applications tab). Account deletion: More → Account & AI → Delete account. Pro is an auto-renewing subscription sold with In-App Purchase; "Restore purchases" is on More → Plan & invites. The free version shows AdMob banner ads and asks for tracking permission before any personalised ads.

**Subscriptions**: create a subscription group "Pro" with monthly and yearly products, localized names/descriptions and a review screenshot of the Plan page. Sign the Paid Apps agreement. Add the Terms of Use link (`https://DOMAIN/terms`) to the App Description or the EULA field, and the Privacy Policy URL in App Information.

**Age rating**: 4+ content, but you can set 17+/18+ if you prefer; the Terms require 18+.

## 6. Why apps get rejected, and how this one avoids it

| Rejection reason | How it's handled |
|---|---|
| 4.2 Minimum functionality / "just a website" | Native share sheet for CV PDFs, in-app browser, local follow-up reminders, native ads and purchases, offline shell. |
| 5.1.1(v) No account deletion | In-app deletion with password confirmation, plus the public web page Google requires. |
| 2.1 Reviewer can't log in / app looks empty | Demo account script with sample CV, jobs and an application. |
| 3.1.1 Digital goods sold outside IAP | Pro is sold only through Apple/Google in the apps (RevenueCat). Web payments appear only on the website. |
| 3.1.2 Subscription info missing | Paywall shows price, period, auto-renewal terms, Terms and Privacy links; Restore purchases button. |
| 5.1.2 / ATT | Tracking permission asked before personalised ads; UMP consent in the EEA/UK. |
| 2.3 Misleading metadata | Store text promises no interviews; screenshots from the real app. |
| AdMob "ads on screens without content" | Ads only on content screens; none on loading/error/navigation, CV editing, approval, sign-in or account screens. |
| Google AI-generated content policy | In-app report button for AI content. |
| Third-party credentials | Gmail app-password setup is website-only, not in the apps. |

## 7. Store text

**Title**: AI Job Hunter (or your chosen name)

**Subtitle (iOS, 30)**: Jobs abroad, CVs that fit

**Description**
> Find jobs abroad that genuinely fit your experience, and apply with documents recruiters in that country expect.
>
> • Upload any CV. We suggest the roles your experience fits; you confirm every detail.
> • Choose your countries in order. Jobs appear country by country, your chosen roles first.
> • See your match score and every requirement you don't meet, stated plainly.
> • Each job gets its own CV in that country's format (Germany, UK, US, Canada, UAE, Netherlands, Europass and more), a cover letter and application answers.
> • Truthful by design: the app can reword and reorder your experience but never adds an employer, degree, skill or number you didn't give it.
> • Review and approve everything, then apply on the employer's own site. Track replies, interviews and offers.
> • Search by company too: DHL, Maersk, Nestlé, Unilever and others.
>
> Free with ads, or go Pro for more applications a day, AI rewriting and no ads.
>
> Employers decide who they interview; we help you apply to the right jobs with accurate, well-formatted documents.

**Keywords (iOS, 100)**: jobs abroad,resume,CV,visa jobs,Germany jobs,Canada jobs,Dubai jobs,job search,cover letter

## 8. Final checks before you submit

- [ ] Signed in on a real phone with the demo account; every tab loads.
- [ ] Created a new account, uploaded a CV, verified it, prepared an application, deleted the account.
- [ ] Privacy, Terms and Delete-account pages open from the app and the website.
- [ ] Test purchase (sandbox/licence tester) unlocks Pro and removes ads; Restore works.
- [ ] Ads show Google **test** ads (`ADS_TEST_MODE=true`) until AdMob approves the app; never click your own live ads.
- [ ] `https://DOMAIN/app-ads.txt` returns your publisher line once ads are enabled.
