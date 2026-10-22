"""Detect pages where automation must stop: CAPTCHA, login/MFA, bot protection, or explicit bans.

Detection is intentionally broad. A false positive only means the user finishes the step by hand;
a false negative could mean interacting with a protected flow, which we never want.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CAPTCHA_PATTERNS = (
    r"g-recaptcha", r"recaptcha/api", r"grecaptcha", r"hcaptcha", r"h-captcha", r"cf-turnstile",
    r"challenges\.cloudflare\.com", r"arkoselabs", r"funcaptcha", r"captcha", r"are you a robot",
    r"verify you are human", r"i'?m not a robot", r"geetest",
)
BOT_WALL_PATTERNS = (
    r"cf-browser-verification", r"checking your browser", r"just a moment\.\.\.", r"attention required",
    r"access denied", r"unusual traffic", r"perimeterx", r"px-captcha", r"datadome", r"distil_",
    r"incapsula", r"request unsuccessful",
)
LOGIN_PATTERNS = (
    r"type=[\"']password[\"']", r"\bsign in to (continue|apply)\b", r"\blog ?in to (continue|apply)\b",
    r"\bcreate (an )?account to apply\b",
)
MFA_PATTERNS = (
    r"one[- ]time (pass)?code", r"verification code", r"two[- ]factor", r"2fa", r"authenticator app",
    r"enter the code (we )?sent", r"\botp\b",
)
NO_AUTOMATION_PATTERNS = (
    r"automated (applications|submissions) (are )?(not permitted|prohibited)", r"no bots",
    r"do not use (automated|bots)",
)


@dataclass
class Blocker:
    kind: str  # captcha | bot_protection | login | mfa | automation_prohibited
    detail: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "detail": self.detail}


def detect_blocker(html: str, url: str = "", title: str = "") -> Blocker | None:
    blob = f"{title}\n{url}\n{html}".lower()
    checks = (("automation_prohibited", NO_AUTOMATION_PATTERNS, "The site says automated applications are not allowed."),
              ("captcha", CAPTCHA_PATTERNS, "A CAPTCHA is present."),
              ("bot_protection", BOT_WALL_PATTERNS, "The site is showing bot protection."),
              ("mfa", MFA_PATTERNS, "The site is asking for a verification code."),
              ("login", LOGIN_PATTERNS, "The site requires you to sign in."))
    for kind, patterns, message in checks:
        for pattern in patterns:
            if re.search(pattern, blob):
                return Blocker(kind, message)
    if re.search(r"/(login|signin|sign-in|auth|sso|oauth)\b", url.lower()):
        return Blocker("login", "Redirected to a sign-in page.")
    return None


def detect_ats(url: str) -> str:
    u = url.lower()
    for name, marker in (("greenhouse", "greenhouse.io"), ("lever", "lever.co"), ("ashby", "ashbyhq.com"),
                         ("workable", "workable.com"), ("workday", "myworkdayjobs.com"),
                         ("smartrecruiters", "smartrecruiters.com"), ("icims", "icims.com"),
                         ("taleo", "taleo.net"), ("successfactors", "successfactors")):
        if marker in u:
            return name
    return "unknown"


# Only these ATSs have a simple public application form we know how to fill.
FILLABLE_ATS = {"greenhouse", "lever", "ashby", "workable"}
