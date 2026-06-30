"""Normalization helpers used before fingerprinting and similarity checks."""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Any, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "icid",
}
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_DASHES = {"\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"}
_SINGLE_QUOTES = {"\u2018", "\u2019", "\u201a", "\u201b"}
_DOUBLE_QUOTES = {"\u201c", "\u201d", "\u201e", "\u201f"}


def normalize_unicode_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    translation = {ord(ch): "-" for ch in _DASHES}
    translation.update({ord(ch): "'" for ch in _SINGLE_QUOTES})
    translation.update({ord(ch): '"' for ch in _DOUBLE_QUOTES})
    text = text.translate(translation)
    text = "".join(
        ch for ch in text
        if ch in ("\n", "\t", " ") or unicodedata.category(ch)[0] != "C"
    )
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_title(title: Optional[str]) -> str:
    text = normalize_unicode_text(title).casefold()
    text = _PUNCT_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_content(text: Optional[str], paragraphs: Optional[Iterable[str]] = None) -> str:
    if text:
        raw = text
    elif paragraphs:
        raw = "\n".join(p for p in paragraphs if p)
    else:
        raw = ""
    return normalize_unicode_text(raw).casefold()


def normalize_canonical_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = normalize_unicode_text(url)
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url or None
    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
    ])
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def article_url(article: Any) -> Optional[str]:
    return normalize_canonical_url(
        getattr(article, "canonical_url", None) or getattr(article, "url", None)
    )


def extract_guid(article: Any) -> Optional[str]:
    metadata = getattr(article, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("guid", "id", "external_id", "entry_id"):
            if metadata.get(key):
                return normalize_unicode_text(str(metadata[key]))

    for attr in ("guid", "external_id", "id"):
        value = getattr(article, attr, None)
        if value:
            return normalize_unicode_text(str(value))

    for block in getattr(article, "json_ld", []) or []:
        if not isinstance(block, dict):
            continue
        for key in ("@id", "identifier", "mainEntityOfPage"):
            value = block.get(key)
            if isinstance(value, dict):
                value = value.get("@id") or value.get("url")
            if value:
                return normalize_unicode_text(str(value))
    return None


def source_identity(candidate_or_article: Any) -> Optional[str]:
    for attr in ("source_id", "source_domain", "source_name"):
        value = getattr(candidate_or_article, attr, None)
        if value:
            return normalize_title(str(value))
    metadata = getattr(candidate_or_article, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("source_id", "source_domain", "source_name", "publisher"):
            if metadata.get(key):
                return normalize_title(str(metadata[key]))
    return None
