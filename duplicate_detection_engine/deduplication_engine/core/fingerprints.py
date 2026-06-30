"""Deterministic article fingerprint generation."""
from __future__ import annotations

import hashlib
from typing import Any, Optional

from .models import FingerprintSet
from .normalization import article_url, normalize_content, normalize_title


def _sha256(value: str) -> Optional[str]:
    value = value.strip()
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class FingerprintGenerator:
    algorithm = "sha256:v1"

    def generate(self, article: Any) -> FingerprintSet:
        canonical_url = article_url(article)
        title = normalize_title(getattr(article, "title", None))
        content = normalize_content(
            getattr(article, "body_text", None) or getattr(article, "content_plain", None),
            getattr(article, "paragraphs", None),
        )
        combined_parts = [part for part in (canonical_url, title, content) if part]
        return FingerprintSet(
            canonical_url=_sha256(canonical_url or ""),
            title=_sha256(title),
            content=_sha256(content),
            combined=_sha256("\n".join(combined_parts)),
            algorithm=self.algorithm,
        )
