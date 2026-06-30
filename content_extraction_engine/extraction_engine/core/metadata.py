"""
Metadata Utilities.

Shared helpers for pulling OpenGraph, Twitter Card, JSON-LD, and standard
<meta> tag metadata out of a parsed document. Multiple extractors depend on
this (JSON-LD extractor, OpenGraph extractor, and the manager's final
metadata-merge step all reuse these functions).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup


def extract_open_graph(soup: BeautifulSoup) -> Dict[str, str]:
    """Capture both the og:* namespace and the closely related article:*
    namespace (article:author, article:published_time, etc.) that nearly
    every site bundles alongside OpenGraph tags, even though it's
    technically a separate vocabulary."""
    values: Dict[str, str] = {}
    for tag in soup.find_all("meta"):
        prop = tag.get("property") or tag.get("name")
        if not prop:
            continue
        prop_lower = prop.lower()
        content = tag.get("content")
        if content is None:
            continue

        if prop_lower.startswith("og:"):
            key = prop[3:].strip()
        elif prop_lower.startswith("article:"):
            key = prop.strip()
        else:
            continue

        if key in values:
            continue
        values[key] = content.strip()
    return values


def extract_twitter_card(soup: BeautifulSoup) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property")
        if not name or not name.lower().startswith("twitter:"):
            continue
        content = tag.get("content")
        if content is None:
            continue
        key = name[len("twitter:"):].strip()
        if key in values:
            continue
        values[key] = content.strip()
    return values


def extract_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Parse every <script type="application/ld+json"> block. Tolerant of
    malformed JSON (common in the wild) -- skips blocks that fail to parse
    rather than raising. Flattens @graph arrays and top-level lists."""
    results: List[Dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw or not raw.strip():
            continue
        # Some sites embed trailing commas / comments -- best-effort cleanup
        cleaned = raw.strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            cleaned2 = re.sub(r",\s*([\]}])", r"\1", cleaned)
            try:
                data = json.loads(cleaned2)
            except json.JSONDecodeError:
                continue

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    results.extend(_flatten_graph(item))
        elif isinstance(data, dict):
            results.extend(_flatten_graph(data))
    return results


def _flatten_graph(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "@graph" in node and isinstance(node["@graph"], list):
        out = []
        for item in node["@graph"]:
            if isinstance(item, dict):
                out.extend(_flatten_graph(item))
        return out
    return [node]


def find_jsonld_by_type(blocks: List[Dict[str, Any]], type_names: List[str]) -> Optional[Dict[str, Any]]:
    """Return the first JSON-LD block whose @type matches one of type_names
    (case-insensitive, supports @type being a list)."""
    lowered_targets = {t.lower() for t in type_names}
    for block in blocks:
        t = block.get("@type")
        if t is None:
            continue
        candidates = t if isinstance(t, list) else [t]
        if any(str(c).lower() in lowered_targets for c in candidates):
            return block
    return None


def extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def extract_meta_keywords(soup: BeautifulSoup) -> List[str]:
    tag = soup.find("meta", attrs={"name": "keywords"})
    if tag and tag.get("content"):
        return [k.strip() for k in tag["content"].split(",") if k.strip()]
    return []


def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find("link", attrs={"rel": lambda v: v and "canonical" in v})
    if tag and tag.get("href"):
        return tag["href"].strip()
    return None


def extract_language(soup: BeautifulSoup) -> Optional[str]:
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        return html_tag["lang"].strip()
    meta = soup.find("meta", attrs={"http-equiv": re.compile("content-language", re.I)})
    if meta and meta.get("content"):
        return meta["content"].strip()
    og_locale = soup.find("meta", attrs={"property": "og:locale"})
    if og_locale and og_locale.get("content"):
        return og_locale["content"].strip()
    return None


def jsonld_authors(value: Any) -> List[str]:
    """Normalize JSON-LD `author` field (string, dict, or list of either)
    into a flat list of author name strings."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    names = []
    for item in items:
        if isinstance(item, str):
            names.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("name")
            if name:
                names.append(str(name).strip())
    return [n for n in names if n]
