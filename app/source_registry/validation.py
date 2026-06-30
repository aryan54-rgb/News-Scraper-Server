"""Validation helpers for source registry commands."""

from __future__ import annotations

from urllib.parse import urlparse

from app.database.enums import SourceTypeEnum
from app.source_registry.exceptions import InvalidSourceConfigurationError
from app.source_registry.schemas import KeywordConfiguration, SourceMetadata

RSS_CAPABILITIES = {"rss", "feed"}
WEBSITE_CAPABILITIES = {"html", "website"}
GOVERNMENT_CAPABILITIES = {"government", "html", "api"}
SOCIAL_CAPABILITIES = {"social", "x"}


def normalize_domain(url: str, provided_domain: str | None = None) -> str:
    """Resolve a normalized lowercase domain from a URL or explicit domain."""
    if provided_domain:
        return provided_domain.strip().lower().removeprefix("www.")
    parsed = urlparse(url)
    domain = parsed.netloc.lower().split("@")[-1].split(":")[0]
    return domain.removeprefix("www.")


def validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidSourceConfigurationError({"url": "must be an absolute http or https URL"})


def validate_boolean_query(query: str | None) -> None:
    if not query:
        return

    tokens = query.replace("(", " ( ").replace(")", " ) ").split()
    if not tokens:
        return

    balance = 0
    previous_operator = True
    operators = {"AND", "OR", "NOT"}
    for token in tokens:
        upper = token.upper()
        if token == "(":
            balance += 1
            previous_operator = True
            continue
        if token == ")":
            balance -= 1
            if balance < 0 or previous_operator:
                raise InvalidSourceConfigurationError({"keywords.boolean_query": "invalid parentheses"})
            previous_operator = False
            continue
        if upper in operators:
            if upper != "NOT" and previous_operator:
                raise InvalidSourceConfigurationError({"keywords.boolean_query": "operator without left operand"})
            previous_operator = True
            continue
        previous_operator = False

    if balance != 0:
        raise InvalidSourceConfigurationError({"keywords.boolean_query": "unbalanced parentheses"})
    if previous_operator:
        raise InvalidSourceConfigurationError({"keywords.boolean_query": "query cannot end with an operator"})


def validate_keywords(keywords: KeywordConfiguration) -> None:
    if keywords.mode == "boolean" and not keywords.boolean_query:
        raise InvalidSourceConfigurationError({"keywords.boolean_query": "required for boolean keyword mode"})
    validate_boolean_query(keywords.boolean_query)


def validate_collector_compatibility(
    *,
    type_code: SourceTypeEnum,
    source_type_slug: str,
    capabilities: list[str],
    metadata: SourceMetadata,
) -> list[str]:
    """Validate collector-facing config without invoking any collector."""
    warnings: list[str] = []
    capability_set = {capability.lower() for capability in capabilities}
    slug = source_type_slug.lower()
    url = str(metadata.collector.get("feed_url") or "")

    if type_code == SourceTypeEnum.RSS or "rss" in slug:
        if capability_set and not capability_set.intersection(RSS_CAPABILITIES):
            raise InvalidSourceConfigurationError({"source_type": "RSS feeds require rss/feed capability"})
        if metadata.scheduling.refresh_interval_seconds < 300:
            warnings.append("RSS sources below five minutes may hit publisher rate limits.")
    elif type_code == SourceTypeEnum.WEBSITE:
        if capability_set and not capability_set.intersection(WEBSITE_CAPABILITIES):
            raise InvalidSourceConfigurationError({"source_type": "Websites require html/website capability"})
    elif type_code == SourceTypeEnum.GOVERNMENT:
        if capability_set and not capability_set.intersection(GOVERNMENT_CAPABILITIES):
            raise InvalidSourceConfigurationError(
                {"source_type": "Government portals require government/html/api capability"}
            )
    elif type_code == SourceTypeEnum.SOCIAL:
        if capability_set and not capability_set.intersection(SOCIAL_CAPABILITIES):
            raise InvalidSourceConfigurationError({"source_type": "Social sources require social capability"})

    if url:
        validate_source_url(url)
    validate_keywords(metadata.keywords)
    return warnings

