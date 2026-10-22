"""Browser-based application assistant (Playwright).

Modes
- ``manual``  : no browser. The UI shows the apply link, documents to download and answers to copy.
- ``assist``  : (default) opens the application page in a visible browser, fills the standard fields
                and uploads the approved CV/letter, then STOPS so the user reviews and clicks Submit.
- ``submit``  : as ``assist`` and then clicks Submit. Only allowed when the server has
                ALLOW_AUTO_SUBMIT=true, the user ticked "submit for me" when approving, the ATS is one
                we support, and no CAPTCHA/bot protection/login/MFA is present on the page.

Hard stops (never bypassed): bot-protection walls, sign-in, MFA/verification codes, pages that
forbid automation. On a hard stop nothing is filled; the page is left open for the user.
CAPTCHAs that guard the submit button: fields may be filled, but only the user can submit.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.automation.blockers import FILLABLE_ATS, Blocker, detect_ats, detect_blocker

log = logging.getLogger(__name__)

HARD_STOP_KINDS = {"bot_protection", "login", "mfa", "automation_prohibited"}
SENSITIVE_FIELD_RE = re.compile(
    r"ssn|social security|aadhaa?r|pan\b|passport|bank|account number|iban|routing|credit card|cvv|password|"
    r"date of birth|\bdob\b", re.IGNORECASE)


@dataclass
class ApplyBundle:
    """Everything the user approved, passed to the browser session."""
    application_id: int
    apply_url: str
    first_name: str
    last_name: str
    email: str
    phone: str
    location: str
    linkedin: str
    website: str
    cv_path: Path
    cover_letter_text: str
    cover_letter_path: Path | None
    answers: list[dict]  # {"question", "answer"}
    auto_submit: bool = False


@dataclass
class ApplyOutcome:
    status: str  # submitted | ready_for_user | blocked | failed | manual
    message: str
    blocker: dict | None = None
    filled: list[str] = field(default_factory=list)
    unfilled: list[str] = field(default_factory=list)
    screenshot: str = ""
    final_url: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


STANDARD_FIELDS: list[tuple[str, str]] = [
    (r"first[\s_-]?name|given name|forename", "first_name"),
    (r"last[\s_-]?name|family name|surname", "last_name"),
    (r"^(full )?name$|your name|full[\s_-]?name", "full_name"),
    (r"e-?mail", "email"),
    (r"phone|mobile|telephone", "phone"),
    (r"linkedin", "linkedin"),
    (r"website|portfolio|github|personal site", "website"),
    (r"^location|current location|city", "location"),
]

_FIELD_SCAN_JS = """
() => {
  const out = [];
  const els = document.querySelectorAll('input, textarea, select');
  els.forEach((el, i) => {
    const style = window.getComputedStyle(el);
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) return;
    if (type !== 'file' && (style.display === 'none' || style.visibility === 'hidden')) return;
    let label = el.getAttribute('aria-label') || '';
    if (!label && el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) label = l.innerText;
    }
    if (!label) { const l = el.closest('label'); if (l) label = l.innerText; }
    if (!label) {
      const wrap = el.closest('.field, .application-question, .form-group, [class*=question], [class*=field]');
      if (wrap) { const l = wrap.querySelector('label, legend, .label, .text'); if (l) label = l.innerText; }
    }
    const marker = 'aijh-' + i;
    el.setAttribute('data-aijh', marker);
    out.push({ marker, type, tag: el.tagName.toLowerCase(), name: el.name || '', id: el.id || '',
               placeholder: el.getAttribute('placeholder') || '', label: (label || '').trim().slice(0, 300),
               required: el.required || el.getAttribute('aria-required') === 'true', value: el.value || '' });
  });
  return out;
}
"""


def split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split()
    return (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (full.strip(), "")


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def _best_answer(label: str, answers: list[dict]) -> str | None:
    from difflib import SequenceMatcher

    target = _normalize(label)
    if not target:
        return None
    best, best_score = None, 0.0
    for item in answers:
        q = _normalize(item.get("question", ""))
        if not q or not item.get("answer"):
            continue
        score = SequenceMatcher(None, target, q).ratio()
        if q in target or target in q:
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = item["answer"], score
    return best if best_score >= 0.75 else None


class ApplyAssistant:
    def __init__(self, *, profile_dir: Path, screenshots_dir: Path, headless: bool = False,
                 allow_auto_submit: bool = False, timeout_ms: int = 45000):
        self.profile_dir = profile_dir
        self.screenshots_dir = screenshots_dir
        self.headless = headless
        self.allow_auto_submit = allow_auto_submit
        self.timeout_ms = timeout_ms

    def run(self, bundle: ApplyBundle, mode: str = "assist", on_outcome=None) -> ApplyOutcome:
        """Run a session. ``on_outcome`` is called as soon as the result is known; in a visible browser
        the call then keeps the window open until the user closes it."""
        if mode == "manual":
            return ApplyOutcome("manual", "Open the application page and submit with your approved documents.",
                                final_url=bundle.apply_url)
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError:
            return ApplyOutcome("manual", "Browser automation is not installed (pip install playwright && "
                                "playwright install chromium). Apply manually with the link below.",
                                final_url=bundle.apply_url)

        ats = detect_ats(bundle.apply_url)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        shot = self.screenshots_dir / f"application-{bundle.application_id}.png"
        pw = sync_playwright().start()
        self._context = None
        outcome: ApplyOutcome | None = None
        try:
            outcome = self._session(pw, bundle, mode, ats, shot)
            return outcome
        except PlaywrightError as exc:
            log.exception("Apply session failed")
            outcome = ApplyOutcome("failed", f"Browser automation error: {exc}. Apply manually with the link.",
                                   final_url=bundle.apply_url)
            return outcome
        finally:
            context = getattr(self, "_context", None)
            if on_outcome is not None and outcome is not None:
                on_outcome(outcome)
            if context is not None and not self.headless and outcome is not None and outcome.status != "submitted":
                try:  # leave the page with the user; clean up once they close the window
                    context.wait_for_event("close", timeout=0)
                except Exception:
                    pass
            try:
                if context is not None:
                    context.close()
            except Exception:
                pass
            pw.stop()

    def _session(self, pw, bundle: ApplyBundle, mode: str, ats: str, shot: Path) -> ApplyOutcome:
        # A persistent profile lets the user stay signed in to sites they log in to themselves.
        context = pw.chromium.launch_persistent_context(str(self.profile_dir), headless=self.headless,
                                                        accept_downloads=False)
        self._context = context
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(self.timeout_ms)
        page.goto(bundle.apply_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        if ats in {"lever"} and "/apply" not in page.url:
            page.goto(page.url.rstrip("/") + "/apply", wait_until="domcontentloaded")
        elif ats in {"greenhouse", "ashby", "workable"}:
            self._open_application_tab(page)

        blocker = detect_blocker(page.content(), page.url, page.title())
        if blocker and blocker.kind in HARD_STOP_KINDS:
            page.screenshot(path=str(shot), full_page=False)
            return self._paused(bundle, blocker, shot, page.url)

        if ats not in FILLABLE_ATS:
            page.screenshot(path=str(shot), full_page=False)
            return ApplyOutcome("ready_for_user", f"This site ({ats}) is not supported for form filling. The page "
                                "is open; please complete it using your approved documents.",
                                screenshot=str(shot), final_url=page.url)

        filled, unfilled = self._fill_form(page, bundle)
        page.screenshot(path=str(shot), full_page=True)

        captcha_present = blocker is not None and blocker.kind == "captcha"
        can_submit = (mode == "submit" and bundle.auto_submit and self.allow_auto_submit and not captcha_present
                      and not [u for u in unfilled if u.startswith("REQUIRED:")])
        if not can_submit:
            reason = []
            if captcha_present:
                reason.append("the page has a CAPTCHA, which only you can complete")
            if [u for u in unfilled if u.startswith("REQUIRED:")]:
                reason.append("some required questions need your input")
            if mode != "submit" or not bundle.auto_submit or not self.allow_auto_submit:
                reason.append("final submission is left to you")
            return ApplyOutcome("ready_for_user", "Form filled; " + "; ".join(reason) + ". Review the page "
                                "in the browser window and click Submit, then mark the application as submitted.",
                                blocker=blocker.as_dict() if blocker else None, filled=filled, unfilled=unfilled,
                                screenshot=str(shot), final_url=page.url)
        return self._submit(page, bundle, filled, unfilled, shot)

    # -- helpers ----------------------------------------------------------------------------
    @staticmethod
    def _open_application_tab(page) -> None:
        for selector in ("a:has-text('Apply')", "button:has-text('Apply')", "a:has-text('Application')"):
            try:
                el = page.locator(selector).first
                if el.count() and el.is_visible():
                    el.click()
                    page.wait_for_timeout(1500)
                    return
            except Exception:
                continue

    def _paused(self, bundle: ApplyBundle, blocker: Blocker, shot: Path, url: str) -> ApplyOutcome:
        return ApplyOutcome(
            "blocked", f"Paused: {blocker.detail} Automation does not bypass security checks. The application page "
            "is open in the browser; complete this step yourself, then continue the application manually.",
            blocker=blocker.as_dict(), screenshot=str(shot), final_url=url)

    def _fill_form(self, page, bundle: ApplyBundle) -> tuple[list[str], list[str]]:
        fields = page.evaluate(_FIELD_SCAN_JS)
        values = {"first_name": bundle.first_name, "last_name": bundle.last_name,
                  "full_name": f"{bundle.first_name} {bundle.last_name}".strip(), "email": bundle.email,
                  "phone": bundle.phone, "linkedin": bundle.linkedin, "website": bundle.website,
                  "location": bundle.location}
        filled, unfilled = [], []
        resume_done = cover_done = False
        for f in fields:
            descriptor = " ".join(x for x in (f["label"], f["name"], f["id"], f["placeholder"]) if x)
            selector = f"[data-aijh='{f['marker']}']"
            if SENSITIVE_FIELD_RE.search(descriptor):
                unfilled.append(("REQUIRED: " if f["required"] else "") + f"{f['label'] or f['name']} (sensitive, left for you)")
                continue
            try:
                if f["type"] == "file":
                    lowered = descriptor.lower()
                    if ("cover" in lowered) and bundle.cover_letter_path and not cover_done:
                        page.set_input_files(selector, str(bundle.cover_letter_path))
                        filled.append("Cover letter upload")
                        cover_done = True
                    elif not resume_done and ("resume" in lowered or "cv" in lowered or not lowered.strip()):
                        page.set_input_files(selector, str(bundle.cv_path))
                        filled.append("CV upload")
                        resume_done = True
                    continue
                if f["value"]:
                    continue  # never overwrite something already there
                if f["type"] in ("checkbox", "radio"):
                    if f["required"]:
                        unfilled.append(f"REQUIRED: {f['label'] or f['name']}")
                    continue
                value = None
                for pattern, key in STANDARD_FIELDS:
                    if re.search(pattern, descriptor, re.IGNORECASE):
                        value = values.get(key)
                        break
                if value is None and f["tag"] == "textarea" and re.search(r"cover", descriptor, re.IGNORECASE):
                    value = bundle.cover_letter_text
                if value is None:
                    value = _best_answer(f["label"] or f["placeholder"], bundle.answers)
                if not value:
                    if f["required"] or f["label"]:
                        unfilled.append(("REQUIRED: " if f["required"] else "") + (f["label"] or f["name"]))
                    continue
                if f["tag"] == "select":
                    try:
                        page.select_option(selector, label=value)
                    except Exception:
                        unfilled.append(("REQUIRED: " if f["required"] else "") + (f["label"] or f["name"]))
                        continue
                else:
                    page.fill(selector, value)
                filled.append(f["label"] or f["name"] or f["type"])
            except Exception as exc:  # one awkward widget should not stop the rest
                log.debug("Could not fill %s: %s", descriptor, exc)
                unfilled.append(("REQUIRED: " if f["required"] else "") + (f["label"] or f["name"]))
        return filled, unfilled

    def _submit(self, page, bundle: ApplyBundle, filled, unfilled, shot: Path) -> ApplyOutcome:
        button = None
        for selector in ("button[type=submit]", "input[type=submit]", "button:has-text('Submit application')",
                         "button:has-text('Submit')"):
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                button = loc
                break
        if button is None:
            return ApplyOutcome("ready_for_user", "Form filled but no submit button was found. Please submit yourself.",
                                filled=filled, unfilled=unfilled, screenshot=str(shot), final_url=page.url)
        button.click()
        page.wait_for_timeout(5000)
        blocker = detect_blocker(page.content(), page.url, page.title())
        page.screenshot(path=str(shot), full_page=False)
        if blocker:
            return self._paused(bundle, blocker, shot, page.url)
        text = page.inner_text("body").lower()
        if re.search(r"thank you|application (has been )?(received|submitted)|we('ve| have) received", text):
            return ApplyOutcome("submitted", "Application submitted and confirmation page detected.",
                                filled=filled, unfilled=unfilled, screenshot=str(shot), final_url=page.url)
        return ApplyOutcome("ready_for_user", "Submit was clicked but no confirmation was detected. Check the page "
                            "for errors and finish manually.", filled=filled, unfilled=unfilled,
                            screenshot=str(shot), final_url=page.url)

