import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { PublicFooter } from "./Legal";

const DEMO = [
  { code: "DE", title: "Operations Manager", place: "Hamburg · your country #1, your role", score: 86, listed: true },
  { code: "NL", title: "Warehouse Manager", place: "Rotterdam · suggested from your CV", score: 81, listed: true },
  { code: "CA", title: "Supply Chain Manager", place: "Toronto · your country #3", score: 77, listed: true, missing: "CSCP certification" },
  { code: "AE", title: "Logistics Manager", place: "Dubai · outside your list", score: 64, listed: false },
];

const SOURCES = ["Greenhouse", "Lever", "Ashby", "Workable", "SmartRecruiters", "Adzuna", "Jooble", "Remotive", "Arbeitnow"];

// code, country, pages, photo rule (matches backend/cv/formats.py)
const FORMATS: [string, string, number, "No photo" | "Photo optional" | "Photo"][] = [
  ["DE", "Germany", 2, "Photo"], ["GB", "UK", 2, "No photo"], ["US", "USA", 2, "No photo"],
  ["CA", "Canada", 2, "No photo"], ["EU", "Europass", 2, "No photo"], ["NL", "Netherlands", 2, "No photo"],
  ["AE", "UAE", 2, "Photo"], ["SA", "Saudi Arabia", 2, "Photo"], ["QA", "Qatar", 2, "Photo"],
  ["IE", "Ireland", 2, "No photo"], ["CH", "Switzerland", 2, "Photo"], ["FR", "France", 2, "Photo optional"],
  ["DK", "Denmark", 2, "Photo optional"], ["AU", "Australia", 3, "No photo"], ["NZ", "New Zealand", 3, "No photo"],
  ["SG", "Singapore", 3, "Photo optional"], ["IN", "India", 2, "Photo optional"], ["CN", "China", 2, "Photo"],
];

const FAQ = [
  ["Is it free?", "Yes. The free plan covers job search, matching and a set number of tailored applications each day. Pro adds more applications, AI rewriting and no ads."],
  ["Will it apply to jobs without asking me?", "No. Every application goes draft, review, your approval, then apply. You can open the employer's page and apply yourself, or let the app fill the form while you watch."],
  ["Can the AI make my CV look better than it is?", "It can reword and reorder what you already did. It cannot add an employer, a degree, a certification, a skill or a number you didn't give it; those lines are removed before you see the draft."],
  ["Does it guarantee interviews?", "No tool can. Employers decide who they interview. The app helps you spend your applications on jobs that genuinely fit, shows you every missing requirement, and tracks your real interview rate."],
  ["Which jobs does it search?", "Official job APIs and employers' own career boards, in the countries you choose and in the order you choose. You can also add target companies or paste any job link."],
  ["What happens to my CV?", "It's stored for your account only, never sold, and never sent to advertisers. You can export everything or delete your account at any time."],
];

export default function Landing() {
  return (
    <div className="landing">
      <header className="l-nav">
        <span className="brand"><span className="brand-mark" aria-hidden="true">JH</span><b>AI Job Hunter</b></span>
        <nav className="l-links" aria-label="Sections">
          <a href="#how">How it works</a>
          <a href="#truth">Truthful CVs</a>
          <a href="#formats">Country formats</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="row">
          <Link className="btn quiet" to="/login">Sign in</Link>
          <Link className="btn primary" to="/signup">Sign up free</Link>
        </div>
      </header>

      <section className="l-hero">
        <div>
          <span className="l-eyebrow"><span className="dot" aria-hidden="true" />18 country CV formats · Web, Android and iPhone</span>
          <h1>Your next job abroad, <em>prepared properly.</em></h1>
          <p className="lead">
            Upload your CV once. AI Job Hunter finds openings in the countries you choose, ranks them against your real
            experience, and prepares a CV in each country's format, a cover letter and the application answers.
            You review every word and decide what gets sent.
          </p>
          <div className="l-cta">
            <Link className="btn primary" to="/signup">Start with your CV</Link>
            <a className="btn" href="#how">How it works</a>
          </div>
          <ul className="l-ticks">
            <li><Icon name="check" />Free to start</li>
            <li><Icon name="check" />Nothing sent without your approval</li>
            <li><Icon name="check" />Delete your data any time</li>
          </ul>
        </div>
        <div className="board-demo" aria-label="Example of ranked jobs">
          <div className="bd-head"><span>Destination</span><span>Match</span></div>
          {DEMO.map((d) => (
            <div className="bd-row flip" key={d.code}>
              <span className={`bd-code${d.listed ? " go" : ""}`}>{d.code}</span>
              <span className="bd-text">
                <b>{d.title}</b><span>{d.place}</span>
                {d.missing && <i className="bd-miss">MISSING REQUIREMENT: {d.missing}</i>}
              </span>
              <span className="bd-score">{d.score}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="l-sources" aria-label="Where jobs come from">
        <span>Jobs from official sources</span>
        <ul>{SOURCES.map((s) => <li key={s}>{s}</li>)}</ul>
      </section>

      <section className="l-section" id="how">
        <span className="l-kicker">How it works</span>
        <h2>From one CV to applications you're proud to send</h2>
        <div className="l-steps">
          <div className="l-step">
            <h3>Upload any CV</h3>
            <p>We read your roles, skills and results, and suggest the job titles your experience fits. You check and confirm every detail.</p>
          </div>
          <div className="l-step">
            <h3>See jobs in your order</h3>
            <p>Your countries first, in the order you set. Within them, the roles you asked for, then roles your CV supports. Every requirement you don't meet is shown plainly.</p>
          </div>
          <div className="l-step">
            <h3>Review, approve, apply</h3>
            <p>Each job gets its own CV in that country's format, a cover letter and answers. Approve them, open the employer's page and apply. Replies are tracked for you.</p>
          </div>
        </div>
      </section>

      <section className="l-section l-showcase" aria-label="The app">
        <figure className="l-browser">
          <div className="l-browser-bar" aria-hidden="true"><i /><i /><i /><span>Jobs · ranked against your CV</span></div>
          <img src="/landing/jobs-desktop.webp" alt="The Jobs screen: postings ranked by country and match score, with matched skills and missing requirements" width={1280} height={900} loading="lazy" />
        </figure>
        <figure className="l-phone">
          <img src="/landing/review-mobile.webp" alt="Reviewing a tailored CV on a phone" width={390} height={844} loading="lazy" />
        </figure>
      </section>

      <section className="l-band" id="truth">
        <div className="l-section l-split">
          <div>
            <span className="l-kicker">Truthful by design</span>
            <h2>AI writes the draft. Your CV decides what's true.</h2>
            <p>Recruiters abroad verify what you claim. AI Job Hunter can reword and reorder your experience, but it cannot add an employer, a degree, a skill or a number you didn't give it. Every generated line is checked against your own CV before you see it.</p>
            <ul className="l-list">
              <li><Icon name="check" /><span>Missing requirements are listed, never invented.</span></li>
              <li><Icon name="check" /><span>Work-permit and visa answers come only from what you tell us.</span></li>
              <li><Icon name="check" /><span>CAPTCHAs and sign-ins on employer sites stay with you.</span></li>
            </ul>
          </div>
          <div className="l-guard" aria-label="Example of the truthfulness check">
            <div className="g-label">Your CV says</div>
            <p className="g-line">Ran static and fatigue FEA in ANSYS, reducing bracket mass by <mark className="ok">12%</mark>.</p>
            <div className="g-label">AI draft said</div>
            <p className="g-line">Ran FEA in ANSYS and <mark className="bad">Kubernetes</mark>, reducing bracket mass by <mark className="bad">35%</mark>.</p>
            <ul className="g-flags">
              <li><b>Invented number</b><span>35% isn't in your CV</span></li>
              <li><b>Unsupported skill</b><span>Kubernetes isn't in your CV</span></li>
            </ul>
            <div className="g-result"><Icon name="shield" />Both removed before you see the draft</div>
          </div>
        </div>
      </section>

      <section className="l-section" id="formats">
        <div className="l-head-split">
          <div>
            <span className="l-kicker">Country formats</span>
            <h2>A CV that looks right where you're applying</h2>
          </div>
          <p className="muted">Page length, photo, personal details, date style and section order follow what recruiters in each country expect. Details only appear if you entered them.</p>
        </div>
        <ul className="l-formats">
          {FORMATS.map(([code, name, pages, photo]) => (
            <li key={code}>
              <span className="f-code">{code}</span>
              <span className="f-name">{name}</span>
              <span className="f-meta">{pages} pages<br />{photo === "Photo" ? "Photo expected" : photo}</span>
            </li>
          ))}
        </ul>
        <div className="l-features">
          <div><Icon name="globe" /><h3>Search by country and company</h3><p>Pick DHL, Maersk, Nestlé or any employer and the countries you want.</p></div>
          <div><Icon name="mail" /><h3>Replies spotted for you</h3><p>Interview, assessment and rejection emails are flagged, with follow-up drafts (web version).</p></div>
          <div><Icon name="flag" /><h3>Your real interview rate</h3><p>See which applications turn into interviews, so you know what's working.</p></div>
        </div>
      </section>

      <section className="l-section" id="faq">
        <div className="l-head-split">
          <div>
            <span className="l-kicker">Questions</span>
            <h2>Straight answers</h2>
          </div>
          <p className="muted">Employers decide who they interview. What we do is help you apply to the jobs that genuinely fit, with documents that are accurate, well formatted and tailored.</p>
        </div>
        <div className="l-faq">
          {FAQ.map(([q, a]) => (
            <details key={q}>
              <summary>{q}</summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="l-section">
        <div className="l-final">
          <div>
            <h2>Start with the CV you already have.</h2>
            <p>Upload it, choose your countries, and see which jobs fit in a few minutes.</p>
          </div>
          <Link className="btn primary" to="/signup">Sign up free</Link>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
