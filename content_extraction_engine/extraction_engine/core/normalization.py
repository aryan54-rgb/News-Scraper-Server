"""
Normalization Layer.

Pure functions that take "raw-ish" extracted values (strings, date strings,
relative URLs) and turn them into clean, canonical forms. Nothing in this
module touches the DOM directly -- it's the layer extractors funnel their
output through before it lands in a NormalizedArticle.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse, urlencode, parse_qsl

from dateutil import parser as dateutil_parser

# Tracking / junk query params that should be stripped during URL normalization
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "icid",
}

_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_BLANK_LINE_RE = re.compile(r"^[ \t]+$", re.MULTILINE)


def normalize_unicode(text: Optional[str]) -> Optional[str]:
    """NFC-normalize unicode, strip control chars, collapse curly quotes is NOT
    performed (we keep typographic characters -- only invisible junk is removed)."""
    if text is None:
        return None
    text = unicodedata.normalize("NFC", text)
    # Strip zero-width / control characters except standard whitespace
    text = "".join(
        ch for ch in text
        if ch in ("\n", "\t") or unicodedata.category(ch)[0] != "C"
    )
    return text


def normalize_whitespace(text: Optional[str]) -> Optional[str]:
    """Collapse runs of horizontal whitespace, strip trailing line whitespace,
    cap consecutive blank lines, and trim the overall string."""
    if text is None:
        return None
    text = normalize_unicode(text) or ""
    text = _BLANK_LINE_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()


def normalize_date(value) -> Optional[datetime]:
    """Parse a date from a string, ISO 8601, or epoch-like value into an
    aware UTC datetime. Returns None if unparsable."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            value_str = str(value).strip()
        except Exception:
            return None
        if not value_str:
            return None
        try:
            # Handle raw epoch seconds/millis
            if re.fullmatch(r"\d{10}", value_str):
                dt = datetime.fromtimestamp(int(value_str), tz=timezone.utc)
            elif re.fullmatch(r"\d{13}", value_str):
                dt = datetime.fromtimestamp(int(value_str) / 1000, tz=timezone.utc)
            else:
                dt = dateutil_parser.parse(value_str)
        except (ValueError, OverflowError, TypeError):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def normalize_url(url: Optional[str], base_url: Optional[str] = None) -> Optional[str]:
    """Resolve relative URLs against base_url, strip tracking params, lowercase
    the scheme/host, and drop trailing slashes (except root)."""
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if base_url:
        url = urljoin(base_url, url)

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        # Not a resolvable absolute URL even after join -- return as-is, cleaned
        return url

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    query_pairs = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_pairs)

    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    cleaned = urlunparse((scheme, netloc, path, parsed.params, query, ""))  # drop fragment
    return cleaned


def resolve_image_url(url: Optional[str], base_url: Optional[str]) -> Optional[str]:
    """Image URLs get the same treatment as normal URLs but we never strip
    query params, since CDNs frequently encode required sizing/signing info
    in the query string (e.g. ?w=800&sig=...)."""
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if base_url:
        url = urljoin(base_url, url)
    return url


def dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip().lower() if isinstance(item, str) else item
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip() if isinstance(item, str) else item)
    return out


def dedupe_paragraphs(paragraphs: List[str]) -> List[str]:
    """Remove exact and near-duplicate paragraphs (common in templated
    boilerplate like repeated disclaimers)."""
    seen = set()
    out = []
    for p in paragraphs:
        norm = re.sub(r"\s+", " ", p).strip().lower()
        if not norm:
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(p.strip())
    return out


def strip_empty_sections(paragraphs: List[str], min_length: int = 1) -> List[str]:
    return [p for p in paragraphs if p and len(p.strip()) >= min_length]


def compute_word_count(text: Optional[str]) -> int:
    if not text:
        return 0
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def compute_reading_time_minutes(word_count: int, wpm: int = 225) -> float:
    if word_count <= 0:
        return 0.0
    return round(word_count / wpm, 1)
