from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.source_registry.exceptions import InvalidSourceConfigurationError
from app.source_registry.schemas import (
    AuthenticationConfiguration,
    AuthenticationType,
    KeywordConfiguration,
    KeywordMode,
)
from app.source_registry.validation import normalize_domain, validate_boolean_query, validate_source_url


def test_normalize_domain_strips_www_and_port() -> None:
    assert normalize_domain("https://www.example.gov.in:443/news") == "example.gov.in"


def test_validate_source_url_rejects_relative_urls() -> None:
    with pytest.raises(InvalidSourceConfigurationError):
        validate_source_url("/local-feed.xml")


def test_authentication_requires_secret_reference() -> None:
    with pytest.raises(ValidationError):
        AuthenticationConfiguration(type=AuthenticationType.API_KEY)


def test_boolean_keyword_query_rejects_unbalanced_parentheses() -> None:
    with pytest.raises(InvalidSourceConfigurationError):
        validate_boolean_query("(kumbh AND traffic")


def test_boolean_keyword_mode_requires_query() -> None:
    with pytest.raises(ValidationError):
        KeywordConfiguration(mode=KeywordMode.BOOLEAN)

