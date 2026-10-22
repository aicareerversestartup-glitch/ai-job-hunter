import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { PublicFooter } from "./Legal";

const DEMO = [
  { code: "DE", title: "Operations Manager", place: "Hamburg, your country #1, your role", score: 86, listed: true },
  { code: "NL", title: "Warehouse Manager", place: "Rotterdam, suggested from your CV", score: 81, listed: true },
  { code: "CA", title: "Supply Chain Manager", place: "Toronto, your country #3", score: 77, listed: true },
  { code: "AE", title: "Logistics Manager", place: "Dubai, outside your list", score: 64, listed: false },
];

export default function Landing() {
  return (
    <div className="landing">
      <header className="l-nav">
        <span className="brand"><span className="brand-mark" aria-hidden="true">JH</span><b>AI Job Hunter</b></span>
        <div className="row">
          <Link className="btn quiet" to="/login">Sign in</Link>
          <Link className="btn primary" to="/signup">Sign up free</Link>
        </div>
      </header>

      <section className="l-hero">
        <div>
          <h1>Your next job abroad, prepared properly.</h1>
          <p className="lead">
            Upload your CV once. AI Job Hunter finds openings in the countries you choose, ranks them against your real
            experience, and prepares a CV in each country's format, a cover letter and the application answers.
            You review every word and decide what gets sent.
          </p>
          <div className="l-cta">
            <Link className="btn primary" to="/signup">Start with your CV</Link>
            <a className="btn" href="#how">How it works</a>
          </div>
          <p className="l-fine">Free to use. Nothing is sent to an employer without your approval.</p>
        </div>
        <div className="board-demo" aria-label="Example of ranked jobs">
          <div className="bd-head"><span>Destination</span><span>Match</span></div>
          {DEMO.map((d) => (
            <div className="bd-row flip" key={d.code}>
              <span className={`bd-code${d.listed ? " go" : ""}`}>{d.code}</span>
              <span className="bd-text"><b>{d.title}</b><span>{d.place}</span></span>
              <span className="bd-score">{d.score}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="l-section" id="how">
        <h2>How it works</h2>
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

      <section className="l-band">
        <div className="l-section l-split">
          <div>
            <h2>Truthful by design</h2>
            <p>Recruiters abroad verify what you claim. AI Job Hunter can reword and reorder your experience, but it cannot add an employer, a degree, a skill or a number you didn't give it. Every generated line is checked against your own CV before you see it.</p>
          </div>
          <ul className="l-list">
            <li><Icon name="check" /><span>Missing requirements are listed, never invented.</span></li>
            <li><Icon name="check" /><span>Work-permit and visa answers come only from what you tell us.</span></li>
            <li><Icon name="check" /><span>CAPTCHAs and sign-ins on employer sites stay with you.</span></li>
          </ul>
        </div>
      </section>

      <section className="l-section l-split">
        <div>
          <h2>Built for an international search</h2>
          <p className="muted">CV formats for India, the US, UK, Germany, Europass, the Netherlands, the Gulf, Singapore, Canada, Australia and more: page length, photo, personal details and section order, as recruiters there expect.</p>
        </div>
        <ul className="l-list">
          <li><Icon name="globe" /><span>Search by country and by company, from official job sources.</span></li>
          <li><Icon name="mail" /><span>Interview, assessment and rejection emails spotted for you (web version).</span></li>
          <li><Icon name="shield" /><span>Your data stays yours: export it or delete your account at any time.</span></li>
        </ul>
      </section>

      <section className="l-section">
        <div className="panel" style={{ textAlign: "left" }}>
          <h2>No promises we can't keep</h2>
          <p className="muted" style={{ marginBottom: 0 }}>Employers decide who they interview. What we do is help you apply to the jobs that genuinely fit, with
            documents that are accurate, well-formatted and tailored. Your real interview rate is shown on your dashboard.</p>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
