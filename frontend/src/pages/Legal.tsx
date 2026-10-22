// Privacy Policy, Terms and the public "delete your account" page required by Google Play.
// TEMPLATES: have them reviewed by a lawyer for the countries you operate in before launch.
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { isNative } from "../api/platform";

interface PublicConfig { operator_name: string; support_email: string; public_url: string; email_enabled: boolean; apply_assist_enabled: boolean }

export function usePublicConfig(): PublicConfig {
  const [cfg, setCfg] = useState<PublicConfig>({ operator_name: "", support_email: "", public_url: "", email_enabled: false, apply_assist_enabled: false });
  useEffect(() => { get<PublicConfig>("/api/auth/config").then(setCfg).catch(() => {}); }, []);
  return cfg;
}

const UPDATED = "22 October 2026";

export function PublicFooter() {
  return (
    <footer className="l-foot">
      <span>© {new Date().getFullYear()} AI Job Hunter</span>
      <Link to="/privacy">Privacy Policy</Link>
      <Link to="/terms">Terms of Use</Link>
      <Link to="/delete-account">Delete your account</Link>
    </footer>
  );
}

function Page({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="landing">
      {!isNative() && (
        <header className="l-nav">
          <Link className="brand" to="/" style={{ textDecoration: "none" }}><span className="brand-mark" aria-hidden="true">JH</span><b>AI Job Hunter</b></Link>
        </header>
      )}
      <article className="legal">
        <h1>{title}</h1>
        <p className="faint">Last updated {UPDATED}</p>
        {children}
      </article>
      <PublicFooter />
    </div>
  );
}

export function Privacy() {
  const cfg = usePublicConfig();
  const who = cfg.operator_name || "the operator of this service";
  const contact = cfg.support_email || "the support address shown in the app";
  return (
    <Page title="Privacy Policy">
      <p>This policy explains what AI Job Hunter ("we") collects, why, and the choices you have. The service is run by {who}. Contact: {contact}.</p>
      <h2>What we collect</h2>
      <ul>
        <li><strong>Account:</strong> your email address, name and a hashed password.</li>
        <li><strong>Your CV and profile:</strong> the CV file you upload and the details in it (work history, education, skills, contact details), plus what you enter in your profile, such as target countries and roles, notice period, salary expectation, work-authorization status, and optionally date of birth, nationality, visa status, passport status and a photo.</li>
        <li><strong>Job and application data:</strong> jobs found for you, match scores, tailored CVs, cover letters, answers, application status and notes.</li>
        <li><strong>Email tracking (website only, optional):</strong> if you connect an inbox, we store your email address and an encrypted app password, and read recent messages to find replies from employers you applied to. We do not send, delete or move email.</li>
        <li><strong>AI settings (optional):</strong> the AI provider you choose and your API key, stored encrypted.</li>
        <li><strong>Technical data:</strong> security logs of sign-ins and important actions. We do not use advertising trackers or sell data.</li>
      </ul>
      <h2>How we use it</h2>
      <p>Only to provide the service: finding and ranking jobs, generating documents for your review, filling application forms when you ask us to, tracking replies, and keeping your account secure.</p>
      <h2>Who we share it with</h2>
      <ul>
        <li><strong>Job search providers</strong> (for example Adzuna, Jooble, Remotive, employer job boards) receive search terms such as role titles and countries, not your CV.</li>
        <li><strong>AI provider</strong> you or we configure (for example OpenAI, Anthropic, Google): when AI is enabled, your CV content and the job description are sent to it to draft documents.</li>
        <li><strong>Employers</strong> receive your documents only when you approve and submit an application.</li>
        <li><strong>Hosting and email providers</strong> that run this service on our behalf.</li>
        <li><strong>Advertising (free plan):</strong> Google AdMob (apps) and Google AdSense (website) show ads and may collect device identifiers such as the advertising ID, IP address and cookies to show, measure and limit ads. Where the law requires it we ask for your consent first, and on iPhone we ask permission before any tracking. You can change your ad choices in <em>Account &amp; AI</em>. Pro has no ads. Ad partners never receive your CV, profile or applications.</li>
        <li><strong>Payments:</strong> Pro is sold through Apple, Google Play or, on the website, our payment provider, managed through RevenueCat. We receive your subscription status, never your card details.</li>
        <li><strong>Partner links:</strong> when you open a partner link we count the click. Nothing about you is shared with the partner.</li>
      </ul>
      <h2>How long we keep it</h2>
      <p>Until you delete it or your account. Security logs are kept for up to 12 months without your personal details after account deletion.</p>
      <h2>Your choices and rights</h2>
      <ul>
        <li>Download all your data: <em>Account &amp; AI → Export my data</em>.</li>
        <li>Delete your account and all data: <em>Account &amp; AI → Delete account</em>, or see <Link to="/delete-account">Delete your account</Link>.</li>
        <li>Correct your data at any time in the app.</li>
        <li>Depending on where you live (for example the EU/UK GDPR or India's DPDP Act) you may have further rights, such as objecting to processing or complaining to a regulator. Contact us to exercise them.</li>
      </ul>
      <h2>Security</h2>
      <p>Passwords are hashed; stored API keys and app passwords are encrypted; all traffic uses HTTPS.</p>
      <h2>Children</h2>
      <p>The service is for people aged 18 or over looking for work.</p>
      <h2>Changes</h2>
      <p>We will update this page and the date above when this policy changes.</p>
    </Page>
  );
}

export function Terms() {
  const cfg = usePublicConfig();
  return (
    <Page title="Terms of Use">
      <p>By using AI Job Hunter you agree to these terms. The service is run by {cfg.operator_name || "the operator of this service"}.</p>
      <h2>What the service does</h2>
      <p>It helps you find jobs, prepares documents for your review and helps you apply. It does not guarantee interviews, offers or visas; employers make those decisions.</p>
      <h2>Your responsibilities</h2>
      <ul>
        <li>Everything you upload and approve must be true. You are responsible for every application you approve and submit.</li>
        <li>Review documents before approving them. AI can make mistakes; report any content problem with the Report button.</li>
        <li>Follow the terms of the job sites and employers you apply to.</li>
        <li>Keep your password safe.</li>
      </ul>
      <h2>Pro subscription</h2>
      <p>Pro renews automatically until you cancel. In the apps it is billed by Apple or Google and managed in your store account; refunds follow their policies. On the website it is billed by our payment provider and you can cancel from your receipt. Free Pro days from invites end automatically.</p>
      <h2>Not allowed</h2>
      <p>Using the service to submit false information, to apply on someone else's behalf without permission, or to overload job sites.</p>
      <h2>Availability</h2>
      <p>We work to keep the service running but can't promise it will always be available or error-free.</p>
      <h2>Ending your account</h2>
      <p>You can delete your account at any time. We may suspend accounts that break these terms.</p>
      <h2>Contact</h2>
      <p>{cfg.support_email || "See the support address shown in the app."}</p>
    </Page>
  );
}

export function DeleteAccountInfo() {
  const cfg = usePublicConfig();
  return (
    <Page title="Delete your AI Job Hunter account">
      <p>You can delete your account and all data linked to it (CVs, profile, jobs, applications, documents, connected inbox and AI settings) at any time.</p>
      <h2>In the app or on the website</h2>
      <ol>
        <li>Sign in.</li>
        <li>Open <strong>Account &amp; AI</strong> (on phones: <em>More → Account &amp; AI</em>).</li>
        <li>Choose <strong>Delete account</strong>, enter your password and type DELETE.</li>
      </ol>
      <p>Deletion is immediate and permanent. Security logs are kept for up to 12 months without your name, email or any CV content.</p>
      <h2>Can't sign in?</h2>
      <p>Email {cfg.support_email ? <a href={`mailto:${cfg.support_email}?subject=Delete%20my%20account`}>{cfg.support_email}</a> : "our support address"} from the address you registered with, with the subject "Delete my account". We will delete it within 30 days and confirm by email.</p>
      {!isNative() && <p><Link className="btn primary" to="/login">Sign in to delete my account</Link></p>}
    </Page>
  );
}
