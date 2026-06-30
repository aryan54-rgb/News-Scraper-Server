"""
Cleaning Layer.

Operates on a BeautifulSoup tree (or a sub-tree believed to contain the
article) and strips boilerplate elements: navigation, headers, footers, ads,
sidebars, related-article widgets, comments, cookie banners, newsletter
popups, and social-share widgets -- while preserving paragraphs, headings,
lists, blockquotes, tables, and captions.
"""
from __future__ import annotations

import re
from typing import Iterable

from bs4 import BeautifulSoup, Comment, Tag

# Tags removed outright regardless of content
_HARD_REMOVE_TAGS = {
    "script", "style", "noscript", "iframe", "svg", "form",
    "button", "input", "select", "textarea", "nav", "footer", "header",
    "aside", "object", "embed", "applet",
}

# Tags whose structure/content we want to keep when they appear inside the
# article body (used by the DOM heuristic extractor to score candidates)
PRESERVED_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "table", "thead", "tbody", "tr", "td", "th",
    "figure", "figcaption", "img", "a", "strong", "em", "b", "i", "br",
}

# Class/id substrings that strongly indicate boilerplate. Matched
# case-insensitively against the element's id+class attribute string.
_BOILERPLATE_PATTERNS = [
    r"\bnav(igation)?\b", r"\bmenu\b", r"\bbreadcrumb", r"\bsidebar\b",
    r"\bfooter\b", r"\bheader\b", r"\bmasthead\b",
    r"\bad[-_]?(slot|unit|wrapper|container|banner)\b", r"\badvert", r"\bsponsor",
    r"\bcomment", r"\bdisqus\b",
    r"\brelated[-_]?(post|article|content|stories)\b", r"\bmore[-_]?stories\b",
    r"\bnewsletter\b", r"\bsubscribe\b", r"\bsignup\b",
    r"\bcookie\b", r"\bgdpr\b", r"\bconsent\b",
    r"\bsocial[-_]?(share|widget|icons|links)\b", r"\bshare[-_]?(bar|buttons|tools)\b",
    r"\bpopup\b", r"\bmodal\b", r"\boverlay\b",
    r"\bpromo\b", r"\bwidget\b", r"\btag[-_]?cloud\b",
    r"\bauthor[-_]?bio\b", r"\bbyline[-_]?social\b",
    r"\bpaywall\b", r"\bpremium[-_]?banner\b",
    r"\bskip[-_]?link\b", r"\bsite[-_]?search\b",
]
_BOILERPLATE_RE = re.compile("|".join(_BOILERPLATE_PATTERNS), re.IGNORECASE)


def _attr_signature(tag: Tag) -> str:
    classes = " ".join(tag.get("class", []) or [])
    el_id = tag.get("id", "") or ""
    role = tag.get("role", "") or ""
    return f"{classes} {el_id} {role}".strip()


def is_boilerplate_element(tag: Tag) -> bool:
    if not isinstance(tag, Tag):
        return False
    if tag.name in _HARD_REMOVE_TAGS:
        return True
    sig = _attr_signature(tag)
    if sig and _BOILERPLATE_RE.search(sig):
        return True
    if tag.get("aria-hidden") == "true":
        return True
    return False


def strip_comments(soup: BeautifulSoup) -> None:
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()


def remove_hard_tags(soup: BeautifulSoup) -> None:
    for tag_name in _HARD_REMOVE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()


def remove_boilerplate(soup: BeautifulSoup) -> None:
    """Walk the tree and decompose any element whose id/class/role signature
    matches known boilerplate patterns. Operates top-down so removing a
    container also removes its (irrelevant) children in one pass."""
    strip_comments(soup)
    remove_hard_tags(soup)

    # Collect first, then decompose, to avoid mutating during traversal
    to_remove = []
    for tag in soup.find_all(True):
        if tag.name in ("html", "body"):
            continue
        if is_boilerplate_element(tag):
            to_remove.append(tag)

    removed_ids = set()
    for tag in to_remove:
        if id(tag) in removed_ids:
            continue
        # Skip if an ancestor is already queued for removal (avoid double work)
        if any(id(parent) in removed_ids for parent in tag.parents):
            continue
        removed_ids.add(id(tag))
        tag.decompose()


def clean_for_extraction(html: str) -> BeautifulSoup:
    """Top-level entry point: parse HTML and return a cleaned soup with
    boilerplate removed but article-relevant structure intact."""
    soup = BeautifulSoup(html, "lxml")
    remove_boilerplate(soup)
    return soup


def estimate_boilerplate_ratio(original_html: str, cleaned_text_len: int) -> float:
    """Rough diagnostic: fraction of the original document's text content
    that was discarded as boilerplate during cleaning."""
    try:
        original_soup = BeautifulSoup(original_html, "lxml")
        original_len = len(original_soup.get_text(strip=True))
    except Exception:
        return 0.0
    if original_len <= 0:
        return 0.0
    discarded = max(original_len - cleaned_text_len, 0)
    return min(discarded / original_len, 1.0)


def html_fragment_to_text(tag: Tag, preserve_breaks: bool = True) -> str:
    """Convert a cleaned content tag to plain text, inserting paragraph
    breaks at block-level boundaries so downstream paragraph splitting works."""
    if tag is None:
        return ""
    block_tags = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6",
                  "blockquote", "tr", "figcaption"}
    pieces = []
    for el in tag.descendants:
        if isinstance(el, Tag) and el.name in block_tags:
            text = el.get_text(" ", strip=True)
            if text:
                pieces.append(text)
    if not pieces:
        return tag.get_text("\n", strip=True)
    return "\n\n".join(pieces) if preserve_breaks else " ".join(pieces)
