"""Reusable boolean expression evaluator for keyword-style rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

from .models import BooleanRule
from .text import normalize_text


class BooleanRuleSyntaxError(ValueError):
    pass


@dataclass
class BooleanRuleMatch:
    name: str
    expression: str
    weight: float


class BooleanRuleEngine:
    _TOKEN_RE = re.compile(r"\(|\)|\bAND\b|\bOR\b|\bNOT\b|\"[^\"]+\"|[A-Za-z0-9_\-]+", re.IGNORECASE)

    def __init__(self, rules: Iterable[BooleanRule]) -> None:
        self.rules = list(rules)

    def evaluate(self, text: str) -> List[BooleanRuleMatch]:
        normalized = normalize_text(text)
        matches: List[BooleanRuleMatch] = []
        for rule in self.rules:
            if self.evaluate_expression(rule.expression, normalized):
                matches.append(BooleanRuleMatch(rule.name, rule.expression, rule.weight))
        return matches

    def evaluate_expression(self, expression: str, text: str) -> bool:
        tokens = self._tokenize(expression)
        parser = _BooleanParser(tokens, text)
        result = parser.parse_expression()
        if parser.has_remaining:
            raise BooleanRuleSyntaxError(f"Unexpected token: {parser.peek()}")
        return result

    def _tokenize(self, expression: str) -> List[str]:
        tokens: List[str] = []
        position = 0
        for match in self._TOKEN_RE.finditer(expression):
            if expression[position:match.start()].strip():
                raise BooleanRuleSyntaxError(f"Invalid boolean expression syntax: {expression}")
            tokens.append(match.group(0))
            position = match.end()
        if expression[position:].strip():
            raise BooleanRuleSyntaxError(f"Invalid boolean expression syntax: {expression}")
        if not tokens:
            raise BooleanRuleSyntaxError("Empty boolean expression")
        return tokens


class _BooleanParser:
    def __init__(self, tokens: List[str], text: str) -> None:
        self.tokens = tokens
        self.text = text
        self.index = 0

    @property
    def has_remaining(self) -> bool:
        return self.index < len(self.tokens)

    def peek(self) -> str | None:
        if not self.has_remaining:
            return None
        return self.tokens[self.index]

    def consume(self) -> str:
        if not self.has_remaining:
            raise BooleanRuleSyntaxError("Unexpected end of expression")
        token = self.tokens[self.index]
        self.index += 1
        return token

    def parse_expression(self) -> bool:
        return self.parse_or()

    def parse_or(self) -> bool:
        result = self.parse_and()
        while self._accept("OR"):
            rhs = self.parse_and()
            result = result or rhs
        return result

    def parse_and(self) -> bool:
        result = self.parse_not()
        while True:
            if self._accept("AND"):
                rhs = self.parse_not()
                result = result and rhs
            elif self._starts_implicit_not():
                rhs = self.parse_not()
                result = result and rhs
            else:
                break
        return result

    def parse_not(self) -> bool:
        if self._accept("NOT"):
            return not self.parse_not()
        return self.parse_primary()

    def parse_primary(self) -> bool:
        if self._accept("("):
            result = self.parse_expression()
            if not self._accept(")"):
                raise BooleanRuleSyntaxError("Missing closing parenthesis")
            return result
        token = self.consume()
        if token.upper() in {"AND", "OR"} or token == ")":
            raise BooleanRuleSyntaxError(f"Unexpected token: {token}")
        phrase = token[1:-1] if token.startswith('"') and token.endswith('"') else token
        needle = normalize_text(phrase)
        return bool(re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", self.text))

    def _accept(self, expected: str) -> bool:
        token = self.peek()
        if token is not None and token.upper() == expected.upper():
            self.index += 1
            return True
        return False

    def _starts_implicit_not(self) -> bool:
        token = self.peek()
        return token is not None and token.upper() == "NOT"
