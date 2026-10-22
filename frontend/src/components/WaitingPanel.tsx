// Shown while the app searches or prepares applications. It carries real, hand-written content
// (tips that help the user right now) so the wait is useful, and an ad slot next to that content.
import { useEffect, useState } from "react";
import AdSlot from "./Ads";

const TIPS: { title: string; body: string }[] = [
  { title: "Numbers get interviews", body: "Recruiters abroad skim for results: team size, % saved, volume handled. Add your real figures in Master CV with the bullet coach." },
  { title: "Apply early", body: "Many international postings get most applications in the first week. New jobs in your country list are worth approving first." },
  { title: "Germany", body: "German recruiters expect a tabular Lebenslauf with MM/YYYY dates. State your German level (A1–C2) even if the job is in English." },
  { title: "Netherlands", body: "Dutch CVs are short and direct: one to two pages, no photo, no date of birth, achievements in numbers." },
  { title: "Canada", body: "No photo, age or marital status on a Canadian resume. Keep it to two pages and avoid 'I' and 'my'." },
  { title: "UAE and the Gulf", body: "A professional photo, nationality and visa status are common under your contact details. Mention notice period in the cover letter." },
  { title: "UK", body: "Two pages, a short personal profile at the top, no photo. Right-to-work questions belong in the application form." },
  { title: "Follow up after a week", body: "No reply after seven days? A short, polite follow-up often gets a response. The app drafts one for you." },
  { title: "Tell one story per job", body: "In interviews, have one example ready for each key requirement: the situation, what you did, and the measurable result." },
  { title: "Missing requirement?", body: "Don't hide it and never claim it. If you have related experience, mention it honestly in the cover letter." },
  { title: "Visa questions", body: "Answer sponsorship questions truthfully. Many employers sponsor skilled hires, and a wrong answer can cancel an offer later." },
  { title: "Same job, many sites", body: "The app merges duplicate postings and keeps the employer's own site, where your application goes straight to the recruiter." },
];

export default function WaitingPanel({ title, done, total, steps }: {
  title: string; done?: number; total?: number; steps?: string[];
}) {
  const [i, setI] = useState(() => Math.floor(Math.random() * TIPS.length));
  useEffect(() => {
    const t = window.setInterval(() => setI((x) => (x + 1) % TIPS.length), 7000);
    return () => window.clearInterval(t);
  }, []);
  const pct = total ? Math.round(((done ?? 0) / total) * 100) : undefined;
  const tip = TIPS[i];
  return (
    <section className="panel waiting" aria-live="polite">
      <div className="spread">
        <h3 style={{ margin: 0 }}>{title}</h3>
        {pct !== undefined && <span className="faint">{done} of {total}</span>}
      </div>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <i style={pct !== undefined ? { width: `${Math.max(4, pct)}%` } : undefined} className={pct === undefined ? "indeterminate" : ""} />
      </div>
      {steps && steps.length > 0 && (
        <ul className="checklist" style={{ marginTop: 12 }}>
          {steps.map((s) => <li key={s}><span className="mark ok">✓</span>{s}</li>)}
        </ul>
      )}
      <div className="tip">
        <strong>{tip.title}</strong>
        <p>{tip.body}</p>
      </div>
      <AdSlot placement="waiting" />
    </section>
  );
}
