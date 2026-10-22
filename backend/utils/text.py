"""Text helpers shared across the backend. Pure Python, no third-party deps."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from typing import Iterable

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#./-]*[a-z0-9+#]|[a-z0-9]")

STOPWORDS = frozenset(
    """a an the and or of to in on for with at by from as is are be been being this that these those
    we you your our their they it its will would can could should may might must not no yes our
    about into over under within across per via etc more most less than such other any all each
    who whom whose which what when where why how have has had do does did also including include
    team role job work working experience strong ability skills skill years year plus""".split()
)


def strip_html(value: str | None) -> str:
    """Convert an HTML fragment (as returned by most job APIs) into plain text."""
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"(?i)<\s*br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|div|li|h[1-6]|tr)\s*>", "\n", text)
    text = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return clean_whitespace(text)


def clean_whitespace(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace(" ", " ")
    lines = [_WS_RE.sub(" ", line).strip() for line in value.splitlines()]
    return _MULTI_NL_RE.sub("\n\n", "\n".join(lines)).strip()


def normalize_key(value: str | None) -> str:
    """Lowercase, accent-free, punctuation-light key for comparisons."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9+#]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokenize(value: str | None, drop_stopwords: bool = True) -> list[str]:
    if not value:
        return []
    tokens = _WORD_RE.findall(value.lower())
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens


def token_set(value: str | None) -> set[str]:
    return set(tokenize(value))


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def contains_phrase(haystack: str, phrase: str) -> bool:
    """Whole-word, case-insensitive phrase search that copes with symbols like C++ or C#."""
    if not haystack or not phrase:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9+#])"
    return re.search(pattern, haystack.lower()) is not None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"
