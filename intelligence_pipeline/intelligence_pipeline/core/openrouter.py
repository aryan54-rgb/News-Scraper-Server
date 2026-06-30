"""OpenRouter chat-completions client boundary."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

import httpx

from .models import ClassificationConfig, ModelUsage, PromptBundle


class ClassificationClientError(RuntimeError):
    pass


class ClassificationRateLimitError(ClassificationClientError):
    pass


class ClassificationTimeoutError(ClassificationClientError):
    pass


@dataclass
class LLMResponse:
    content: str
    model: str
    latency_ms: float
    usage: ModelUsage = field(default_factory=ModelUsage)
    raw: Dict[str, Any] = field(default_factory=dict)


class ClassificationClient(Protocol):
    def complete(self, prompt: PromptBundle, model: str) -> LLMResponse:
        ...


class OpenRouterClient:
    def __init__(
        self,
        config: ClassificationConfig,
        *,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.config = config
        self.http_client = http_client or httpx.Client(timeout=config.timeout_seconds)
        self._owns_client = http_client is None

    def complete(self, prompt: PromptBundle, model: str) -> LLMResponse:
        if not self.config.openrouter_api_key:
            raise ClassificationClientError("OpenRouter API key is not configured")

        headers = {
            "Authorization": f"Bearer {self.config.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.config.site_url:
            headers["HTTP-Referer"] = self.config.site_url
        if self.config.app_name:
            headers["X-Title"] = self.config.app_name

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        started = time.perf_counter()
        try:
            response = self.http_client.post(
                f"{self.config.openrouter_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise ClassificationTimeoutError("OpenRouter request timed out") from exc
        except httpx.RequestError as exc:
            raise ClassificationClientError(f"OpenRouter network failure: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code == 429:
            raise ClassificationRateLimitError("OpenRouter rate limit exceeded")
        if response.status_code >= 500:
            raise ClassificationClientError(f"OpenRouter model/server failure: {response.status_code}")
        if response.status_code >= 400:
            raise ClassificationClientError(f"OpenRouter request failed: {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise ClassificationClientError("OpenRouter response was not valid JSON") from exc
        if not isinstance(data, dict):
            raise ClassificationClientError("OpenRouter response JSON was not an object")
        choices: List[Dict[str, Any]] = data.get("choices") or []
        if not choices:
            raise ClassificationClientError("OpenRouter response contained no choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ClassificationClientError("OpenRouter response choice was not an object")
        message = first_choice.get("message") or {}
        if not isinstance(message, dict):
            raise ClassificationClientError("OpenRouter response message was not an object")
        content = message.get("content")
        if not isinstance(content, str):
            raise ClassificationClientError("OpenRouter response content was not a string")
        usage_data = data.get("usage") or {}
        usage = ModelUsage(
            prompt_tokens=int(usage_data.get("prompt_tokens") or 0),
            completion_tokens=int(usage_data.get("completion_tokens") or 0),
            total_tokens=int(usage_data.get("total_tokens") or 0),
        )
        return LLMResponse(
            content=content,
            model=data.get("model") or model,
            latency_ms=latency_ms,
            usage=usage,
            raw=data,
        )

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()
