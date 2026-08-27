"""Minimal structured-output provider boundary for the Memory MVP."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from digitalme.config import Settings

MAX_PROVIDER_RESPONSE_BYTES = 4 * 1024 * 1024


class ProviderConfigurationError(ValueError):
    """Raised when a requested provider is not configured."""


class ProviderResponseError(RuntimeError):
    """Raised for a failed or malformed provider response without leaking its body."""


class JsonProvider(Protocol):
    name: str
    model: str
    local: bool

    def generate_json(
        self,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]: ...


class DeepSeekJsonProvider:
    """Call DeepSeek's OpenAI-compatible Chat Completions JSON mode."""

    name = "deepseek"
    local = False

    def __init__(self, settings: Settings) -> None:
        if not settings.deepseek_configured:
            raise ProviderConfigurationError("DeepSeek requires API_KEY and API_BASE_URL")
        assert settings.api_key is not None
        assert settings.api_base_url is not None
        self.api_key = settings.api_key
        self.base_url = settings.api_base_url
        self.model = settings.deepseek_model
        self.timeout = settings.model_timeout_seconds

    def generate_json(
        self,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(input_payload, ensure_ascii=False),
                    },
                ],
                "response_format": {"type": "json_object"},
                "stream": False,
                "max_tokens": 2048,
            },
            ensure_ascii=False,
        ).encode()
        request = urllib.request.Request(
            _chat_completions_url(self.base_url),
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key.get_secret_value()}",
                "Content-Type": "application/json",
                "User-Agent": "DigitalMe/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw_response = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise ProviderResponseError("DeepSeek request failed") from exc
        if len(raw_response) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ProviderResponseError("DeepSeek response exceeds the configured safety bound")
        try:
            payload = json.loads(raw_response)
            content = payload["choices"][0]["message"]["content"]
            generated = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("DeepSeek returned an invalid JSON response") from exc
        if not isinstance(generated, dict):
            raise ProviderResponseError("DeepSeek JSON output must be an object")
        return generated


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"
