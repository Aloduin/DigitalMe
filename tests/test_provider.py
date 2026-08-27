from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, cast

import pytest
from digitalme.config import Settings
from digitalme.providers import DeepSeekJsonProvider, ProviderResponseError


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, _: int) -> bytes:
        return self.payload


def test_deepseek_provider_requests_bounded_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        API_KEY="test-provider-key",
        API_BASE_URL="https://api.example.invalid",
        DEEPSEEK_MODEL="test-model",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    captured: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, *, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        captured["body"] = json.loads(cast(bytes, request.data) or b"{}")
        content = json.dumps({"episode_type": "test"})
        return FakeResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = DeepSeekJsonProvider(settings).generate_json(
        system_prompt="Return JSON only.",
        input_payload={"safe": "value"},
    )

    assert result == {"episode_type": "test"}
    assert captured["url"] == "https://api.example.invalid/chat/completions"
    assert captured["authorization"] == "Bearer test-provider-key"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["model"] == "test-model"


def test_deepseek_provider_hides_malformed_response_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        API_KEY="test-provider-key",
        API_BASE_URL="https://api.example.invalid/chat/completions",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    hidden_value = "provider-body-must-not-leak"
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(hidden_value.encode()),
    )

    with pytest.raises(ProviderResponseError) as raised:
        DeepSeekJsonProvider(settings).generate_json(
            system_prompt="Return JSON only.",
            input_payload={},
        )

    assert hidden_value not in str(raised.value)
