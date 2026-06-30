"""Text normalization helpers for deterministic relevance scoring."""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable, Optional

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in ("\n", "\t", " ") or unicodedata.category(ch)[0] != "C")
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


def article_text(article: Any) -> str:
    parts: list[str] = []
    for attr in ("title", "subtitle", "summary", "body", "body_text", "content_plain", "meta_description"):
        value = getattr(article, attr, None)
        if value:
            parts.append(str(value))
    for attr in ("categories", "tags", "meta_keywords"):
        values = getattr(article, attr, None)
        if isinstance(values, Iterable) and not isinstance(values, (str, bytes)):
            parts.extend(str(item) for item in values if item)
    metadata = getattr(article, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("title", "subtitle", "description", "keywords"):
            value = metadata.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, Iterable):
                parts.extend(str(item) for item in value if item)
    return normalize_text("\n".join(parts))


def article_source(article: Any) -> Optional[str]:
    metadata = getattr(article, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("source_id", "source_domain", "source_name", "publisher"):
            if metadata.get(key):
                return normalize_text(str(metadata[key]))
    source = getattr(article, "source", None)
    if isinstance(source, str) and source:
        return normalize_text(source)
    if isinstance(source, dict):
        for key in ("id", "domain", "name", "url"):
            if source.get(key):
                return normalize_text(str(source[key]))
    for attr in ("source_id", "source_domain", "source_name", "publisher"):
        value = getattr(article, attr, None)
        if value:
            return normalize_text(str(value))
    return None


def article_publication_date(article: Any) -> Optional[datetime]:
    for attr in ("published_at", "publication_date", "published_date", "date_published"):
        value = getattr(article, attr, None)
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
    metadata = getattr(article, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("published_at", "publication_date", "published_date", "date_published"):
            value = metadata.get(key)
            if isinstance(value, datetime):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    continue
    return None
