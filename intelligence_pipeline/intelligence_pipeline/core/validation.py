"""Strict JSON response validation for classification outputs."""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from .models import ClassificationResult, TaxonomyConfig


class ClassificationValidationError(ValueError):
    pass


class ResponseValidator:
    required_fields = {
        "theme",
        "genre",
        "event_type",
        "stakeholders",
        "geography",
        "outcomes",
        "evidence_snippets",
        "confidence",
    }
    optional_fields = {"rationale"}

    def __init__(self, taxonomy: TaxonomyConfig) -> None:
        self.taxonomy = taxonomy

    def validate_json(self, raw_content: str) -> ClassificationResult:
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ClassificationValidationError(f"Invalid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ClassificationValidationError("Classification response must be a JSON object")
        self._reject_unknown_fields(payload)
        missing = self.required_fields - set(payload)
        if missing:
            raise ClassificationValidationError(f"Missing required fields: {sorted(missing)}")

        theme = self._validate_allowed_list(payload["theme"], self.taxonomy.themes, "theme")
        genre = self._validate_allowed_list(payload["genre"], self.taxonomy.genres, "genre")
        event_type = self._validate_allowed_list(payload["event_type"], self.taxonomy.event_types, "event_type")
        geography = self._validate_allowed_list(payload["geography"], self.taxonomy.geographies, "geography")
        outcomes = self._validate_allowed_list(payload["outcomes"], self.taxonomy.outcomes, "outcomes")
        stakeholders = self._validate_stakeholders(payload["stakeholders"])
        evidence = self._validate_string_list(payload["evidence_snippets"], "evidence_snippets")
        confidence = payload["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ClassificationValidationError("confidence must be numeric")
        if confidence < 0 or confidence > 1:
            raise ClassificationValidationError("confidence must be between 0.0 and 1.0")
        rationale = payload.get("rationale")
        if rationale is not None and not isinstance(rationale, str):
            raise ClassificationValidationError("rationale must be a string when provided")
        return ClassificationResult(
            theme=theme,
            genre=genre,
            event_type=event_type,
            stakeholders=stakeholders,
            geography=geography,
            outcomes=outcomes,
            evidence_snippets=evidence,
            confidence=float(confidence),
            rationale=rationale,
        )

    def _reject_unknown_fields(self, payload: Dict[str, Any]) -> None:
        allowed = self.required_fields | self.optional_fields
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ClassificationValidationError(f"Unknown fields: {unknown}")

    def _validate_allowed_list(self, value: Any, allowed: Iterable[str], field_name: str) -> List[str]:
        values = self._validate_string_list(value, field_name)
        allowed_set = set(allowed)
        unknown = sorted(set(values) - allowed_set)
        if unknown:
            raise ClassificationValidationError(f"Unknown {field_name} values: {unknown}")
        return values

    @staticmethod
    def _validate_string_list(value: Any, field_name: str) -> List[str]:
        if not isinstance(value, list):
            raise ClassificationValidationError(f"{field_name} must be a list")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ClassificationValidationError(f"{field_name} must contain non-empty strings")
        return value

    def _validate_stakeholders(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            raise ClassificationValidationError("stakeholders must be a list")
        allowed_types = set(self.taxonomy.stakeholder_types)
        out: List[Dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                raise ClassificationValidationError("stakeholders must contain objects")
            if set(item) != {"name", "type", "role"}:
                raise ClassificationValidationError("stakeholders must contain only name, type, and role")
            if not all(isinstance(item[key], str) and item[key].strip() for key in item):
                raise ClassificationValidationError("stakeholder name, type, and role must be strings")
            if item["type"] not in allowed_types:
                raise ClassificationValidationError(f"Unknown stakeholder type: {item['type']}")
            out.append({"name": item["name"], "type": item["type"], "role": item["role"]})
        return out
