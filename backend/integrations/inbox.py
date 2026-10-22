"""Interview email tracking over IMAP (read-only).

Connects with an app password, reads recent messages without marking them read, matches each to
an application by company name/domain, and classifies it (interview, assessment, offer, rejection,
acknowledgement). Results are recorded on the application timeline as suggestions; the user
confirms status changes with one click. Nothing is ever sent, moved or deleted.
"""
from __future__ import annotations

import email
import email.message
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from backend.jobs.normalizer import normalize_company
from backend.utils.text import strip_html, truncate

PROVIDER_HOSTS = {"gmail": ("imap.gmail.com", 993), "yahoo": ("imap.mail.yahoo.com", 993),
                  "zoho": ("imap.zoho.com", 993), "outlook": ("outlook.office365.com", 993),
                  "icloud": ("imap.mail.me.com", 993)}

RULES: list[tuple[str, str]] = [
    ("offer", r"\b(offer letter|pleased to offer|job offer|offer of employment|extend (you )?an offer)\b"),
    ("rejection", r"\b(unfortunately|regret to inform|not (be )?(moving|proceeding) forward|decided to (move|proceed) "
                  r"with other|position has been filled|not selected|other candidates|will not be progressing|"
                  r"unsuccessful)\b"),
    ("interview", r"\b(interview|schedule (a|an|your) (call|chat|conversation)|availability for (a )?(call|meeting)|"
                  r"phone screen|video call|meet the (team|hiring manager)|next round|calendly|book a (time|slot))\b"),
    ("assessment", r"\b(assessment|online test|aptitude test|case study|take[- ]home|hackerrank|codility|"
                   r"psychometric|shl|hirevue)\b"),
    ("acknowledgement", r"\b(thank you for (your )?(applying|application|interest)|application (has been )?received|"
                        r"we have received your application)\b"),
]
SUGGESTED_STATUS = {"interview": "interviewing", "assessment": "in_review", "offer": "offer", "rejection": "rejected",
                    "acknowledgement": "in_review"}
JOB_BOARD_SENDERS = ("linkedin.com", "indeed.com", "glassdoor.com", "naukri.com", "jooble", "adzuna", "monster.")


@dataclass
class InboxMessage:
    message_id: str
    sender: str
    sender_domain: str
    subject: str
    received_at: datetime | None
    body: str


@dataclass
class Detection:
    application_id: int
    classification: str
    suggested_status: str
    message: InboxMessage
    evidence: str


def classify(subject: str, body: str) -> tuple[str, str]:
    text = f"{subject}\n{body[:4000]}"
    for label, pattern in RULES:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 80)
            return label, text[start: m.end() + 80].replace("\n", " ").strip()
    return "other", ""


def match_application(msg: InboxMessage, applications: list[dict]) -> dict | None:
    """applications: [{"id", "company", "company_domain", "title"}]. Requires the company to appear in
    the sender's domain or display name, or in the subject, to avoid false matches."""
    if any(b in msg.sender_domain for b in JOB_BOARD_SENDERS):
        return None
    sender_key = normalize_company(msg.sender.replace("@", " ").replace(".", " "))
    subject_key = f" {normalize_company(msg.subject)} "
    best, best_score = None, 0
    for app in applications:
        company = normalize_company(app["company"])
        if not company:
            continue
        first = company.split()[0]
        score = 0
        if app.get("company_domain") and app["company_domain"] in msg.sender_domain:
            score = 3
        elif len(first) >= 3 and (first in msg.sender_domain.replace("-", "") or f" {first} " in f" {sender_key} "):
            score = 2
        elif f" {company} " in subject_key:
            score = 1
        if score and app.get("title") and normalize_company(app["title"]) in normalize_company(msg.subject + " " + msg.body[:600]):
            score += 1
        if score > best_score:
            best, best_score = app, score
    return best


def _decode(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _body(message: email.message.Message) -> str:
    parts = message.walk() if message.is_multipart() else [message]
    plain, html = "", ""
    for part in parts:
        ctype = part.get_content_type()
        if part.get("Content-Disposition", "").startswith("attachment"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not html:
            html = text
    return plain or strip_html(html)


def fetch_messages(host: str, port: int, username: str, password: str, since: datetime,
                   limit: int = 300) -> list[InboxMessage]:
    """Read-only fetch. Uses BODY.PEEK so messages stay unread."""
    conn = imaplib.IMAP4_SSL(host, port, timeout=30)
    try:
        conn.login(username, password)
        conn.select("INBOX", readonly=True)
        status, data = conn.search(None, "SINCE", since.strftime("%d-%b-%Y"))
        if status != "OK":
            return []
        ids = data[0].split()[-limit:]
        out: list[InboxMessage] = []
        for msg_id in ids:
            status, parts = conn.fetch(msg_id, "(BODY.PEEK[]<0.60000>)")
            if status != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            message = email.message_from_bytes(parts[0][1])
            sender = _decode(message.get("From"))
            address = parseaddr(sender)[1].lower()
            try:
                received = parsedate_to_datetime(message.get("Date")) if message.get("Date") else None
            except (TypeError, ValueError):
                received = None
            out.append(InboxMessage(
                message_id=(message.get("Message-ID") or f"{address}-{message.get('Date')}").strip(),
                sender=sender, sender_domain=address.split("@")[-1], subject=_decode(message.get("Subject")),
                received_at=received, body=_body(message)))
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def detect(messages: list[InboxMessage], applications: list[dict]) -> list[Detection]:
    found: list[Detection] = []
    for msg in messages:
        label, evidence = classify(msg.subject, msg.body)
        if label == "other":
            continue
        app = match_application(msg, applications)
        if app is None:
            continue
        found.append(Detection(app["id"], label, SUGGESTED_STATUS[label], msg, truncate(evidence, 240)))
    return found


def default_since(last_checked: datetime | None) -> datetime:
    if last_checked:
        return last_checked - timedelta(days=1)
    return datetime.now(timezone.utc) - timedelta(days=45)
