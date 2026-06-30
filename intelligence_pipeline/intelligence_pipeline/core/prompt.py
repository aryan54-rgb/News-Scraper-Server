"""Versioned prompt construction for taxonomy classification."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from .models import PromptBundle, TaxonomyConfig


class PromptTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    version: str
    system_prompt: str
    user_prompt_intro: str


class PromptBuilder:
    _templates: Dict[str, PromptTemplate] = {
        "classification-v1": PromptTemplate(
            version="classification-v1",
            system_prompt=(
                "You are a strict JSON classification engine for Kumbh Monitor. "
                "Return only valid JSON. Do not add Markdown, commentary, or fields "
                "outside the schema. Use only taxonomy values supplied in the prompt."
            ),
            user_prompt_intro=(
                "Classify the article using the allowed taxonomy values.\n"
                "Required JSON object fields: theme, genre, event_type, stakeholders, "
                "geography, outcomes, evidence_snippets, confidence, rationale.\n"
                "Array fields may contain multiple values. stakeholders must be objects "
                "with name, type, and role string fields. evidence_snippets must quote "
                "short article text spans that support the classification."
            ),
        )
    }

    def __init__(self, taxonomy: TaxonomyConfig, prompt_version: str = "classification-v1") -> None:
        self.taxonomy = taxonomy
        self.prompt_version = prompt_version

    @classmethod
    def register_template(cls, template: PromptTemplate) -> None:
        cls._templates[template.version] = template

    def build(self, article: Any) -> PromptBundle:
        template = self._templates.get(self.prompt_version)
        if template is None:
            raise PromptTemplateError(f"Unknown prompt version: {self.prompt_version}")
        article_payload = {
            "title": getattr(article, "title", None),
            "subtitle": getattr(article, "subtitle", None),
            "summary": getattr(article, "summary", None),
            "author": getattr(article, "author", None),
            "authors": getattr(article, "authors", []),
            "categories": getattr(article, "categories", []),
            "tags": getattr(article, "tags", []),
            "metadata": getattr(article, "metadata", {}),
            "source": getattr(article, "source", None),
            "published_at": self._serialize_date(
                getattr(article, "published_at", None) or getattr(article, "publication_date", None)
            ),
            "body_text": self._truncate(
                getattr(article, "body", None)
                or getattr(article, "body_text", None)
                or getattr(article, "content_plain", None)
            ),
        }
        schema = {
            "theme": self.taxonomy.themes,
            "genre": self.taxonomy.genres,
            "event_type": self.taxonomy.event_types,
            "stakeholders[].type": self.taxonomy.stakeholder_types,
            "geography": self.taxonomy.geographies,
            "outcomes": self.taxonomy.outcomes,
        }
        user_prompt = (
            f"{template.user_prompt_intro}\n\n"
            f"Taxonomy version: {self.taxonomy.version}\n"
            f"Allowed values: {json.dumps(schema, ensure_ascii=False)}\n"
            f"Article: {json.dumps(article_payload, ensure_ascii=False, default=str)}"
        )
        return PromptBundle(
            version=template.version,
            system_prompt=template.system_prompt,
            user_prompt=user_prompt,
        )

    @staticmethod
    def _truncate(text: str | None, max_chars: int = 12000) -> str:
        if not text:
            return ""
        return text[:max_chars]

    @staticmethod
    def _serialize_date(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
