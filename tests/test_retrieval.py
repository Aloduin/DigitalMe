from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from digitalme.api.app import create_app
from digitalme.config import Settings, get_settings
from digitalme.db.base import Base
from digitalme.db.session import create_engine, create_session_factory
from digitalme.models import (
    CandidateEvidence,
    Episode,
    MemoryCandidate,
    Message,
    SessionRecord,
    Source,
)
from digitalme.providers import DeepSeekJsonProvider
from digitalme.retrieval import (
    NoRelevantMemoriesError,
    RetrievalService,
    RetrievalValidationError,
)
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


class FakeAskProvider:
    name = "fake"
    model = "fake-ask"
    local = False

    def __init__(self) -> None:
        self.output: dict[str, Any] = {}
        self.inputs: list[dict[str, Any]] = []

    def generate_json(
        self,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        assert "Memory Pack" in system_prompt
        self.inputs.append(input_payload)
        return self.output


def test_retrieval_searches_only_confirmed_memories(tmp_path: Path) -> None:
    engine, factory, safe_id, sensitive_id = _retrieval_fixture(tmp_path)
    service = RetrievalService(factory)

    result = service.retrieve("Why did DigitalMe choose the MVP first?")

    assert result.confirmed_scanned == 3
    assert {hit.candidate_id for hit in result.hits} == {safe_id, sensitive_id}
    assert all(hit.matched_terms for hit in result.hits)
    assert all("pending" not in hit.content for hit in result.hits)
    assert service.retrieve("quantum gardening").hits == ()
    chinese = service.retrieve("为什么先实现最小可用产品？")
    assert chinese.hits[0].candidate_id == safe_id
    engine.dispose()


def test_ask_uses_bounded_eligible_pack_and_validates_citations(tmp_path: Path) -> None:
    engine, factory, safe_id, sensitive_id = _retrieval_fixture(tmp_path)
    provider = FakeAskProvider()
    provider.output = {
        "answer": "DigitalMe explicitly chose the MVP before robustness work.",
        "citation_memory_ids": [safe_id],
    }
    service = RetrievalService(factory, provider)

    result = service.ask("Why did DigitalMe choose the MVP first?")

    assert result.answer.startswith("DigitalMe explicitly")
    assert [citation.candidate_id for citation in result.citations] == [safe_id]
    assert result.memories_sent == 1
    assert result.memories_excluded == 1
    packed_ids = [item["memory_id"] for item in provider.inputs[0]["memories"]]
    assert packed_ids == [safe_id]
    assert sensitive_id not in str(provider.inputs[0])
    assert provider.inputs[0]["memories"][0]["evidence"][0]["quote"] == ("We chose the MVP first.")

    provider.output = {
        "answer": "Unsupported answer.",
        "citation_memory_ids": ["mc_not_in_pack"],
    }
    with pytest.raises(RetrievalValidationError, match="outside"):
        service.ask("Why did DigitalMe choose the MVP first?")
    engine.dispose()


def test_ask_does_not_call_provider_without_relevant_memory(tmp_path: Path) -> None:
    engine, factory, _, _ = _retrieval_fixture(tmp_path)
    provider = FakeAskProvider()
    service = RetrievalService(factory, provider)

    with pytest.raises(NoRelevantMemoriesError, match="No relevant"):
        service.ask("quantum gardening")

    assert provider.inputs == []
    engine.dispose()


@pytest.mark.asyncio
async def test_retrieval_api_returns_local_hits_and_requires_provider_for_ask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _, safe_id, _ = _retrieval_fixture(tmp_path)
    engine.dispose()
    monkeypatch.setenv("DIGITALME_DATABASE_URL", f"sqlite:///{tmp_path / 'digitalme.db'}")
    monkeypatch.setenv("DIGITALME_RAW_STORE_PATH", str(tmp_path / "raw"))
    monkeypatch.setenv("DIGITALME_INCOMING_PATH", str(tmp_path / "incoming"))
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("API_BASE_URL", "")
    get_settings.cache_clear()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        retrieved = await client.post(
            "/api/v1/retrieve",
            json={"query": "DigitalMe MVP first", "limit": 5},
        )
        assert retrieved.status_code == 200
        assert safe_id in [item["candidate_id"] for item in retrieved.json()["hits"]]
        assert retrieved.json()["hits"][0]["matched_terms"]

        ask = await client.post("/api/v1/ask", json={"query": "DigitalMe MVP first"})
        assert ask.status_code == 503
        blank = await client.post("/api/v1/retrieve", json={"query": "   "})
        assert blank.status_code == 422

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_ask_api_returns_validated_clickable_citations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _, safe_id, sensitive_id = _retrieval_fixture(tmp_path)
    engine.dispose()
    captured: dict[str, Any] = {}

    def fake_generate_json(
        _provider: DeepSeekJsonProvider,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        captured["prompt"] = system_prompt
        captured["input"] = input_payload
        return {
            "answer": "The evidence says the MVP was chosen before robustness work.",
            "citation_memory_ids": [safe_id],
        }

    monkeypatch.setattr(DeepSeekJsonProvider, "generate_json", fake_generate_json)
    monkeypatch.setenv("DIGITALME_DATABASE_URL", f"sqlite:///{tmp_path / 'digitalme.db'}")
    monkeypatch.setenv("DIGITALME_RAW_STORE_PATH", str(tmp_path / "raw"))
    monkeypatch.setenv("DIGITALME_INCOMING_PATH", str(tmp_path / "incoming"))
    monkeypatch.setenv("API_KEY", "test-ask-key")
    monkeypatch.setenv("API_BASE_URL", "https://api.example.invalid")
    get_settings.cache_clear()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ask",
            json={"query": "Why did DigitalMe choose the MVP first?"},
        )

    assert response.status_code == 200
    assert response.json()["citations"][0]["candidate_id"] == safe_id
    assert response.json()["provider"] == "deepseek"
    assert sensitive_id not in str(captured["input"])
    assert "normalized_text" not in str(captured["input"])
    get_settings.cache_clear()


def _retrieval_fixture(
    tmp_path: Path,
) -> tuple[Engine, sessionmaker[Session], str, str]:
    settings = Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    now = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)
    with factory.begin() as db:
        source = Source(source_type="chatgpt", name="Retrieval fixture")
        db.add(source)
        db.flush()
        session = SessionRecord(
            source_id=source.id,
            external_id="retrieval-session",
            schema_version=1,
            title="MVP planning",
        )
        db.add(session)
        db.flush()
        message = Message(
            session_id=session.id,
            external_id="mvp-message",
            role="user",
            content_type="text",
            normalized_text="We chose the MVP first.",
            redacted_text="We chose the MVP first.",
            redaction_spans=[],
            sensitivity="personal",
            source_timestamp=now,
            sequence=0,
            raw_locator={"node_id": "mvp-message"},
            parse_warnings=[],
        )
        db.add(message)
        db.flush()
        episode = Episode(
            session_id=session.id,
            pipeline_version="segment-v1",
            segment_index=0,
            episode_type="project_decision",
            title="DigitalMe MVP decision",
            summary="DigitalMe chose an MVP-first implementation path.",
            projects=["DigitalMe"],
            decisions=["Build MVP before robustness."],
            open_questions=[],
            extraction_status="extracted",
        )
        db.add(episode)
        db.flush()
        safe = MemoryCandidate(
            episode_id=episode.id,
            extractor_version="memory-extract-v1",
            content_hash="safe-hash",
            candidate_type="decision",
            content=(
                "DigitalMe will build the MVP before robustness features. "
                "先实现最小可用产品，再开发系统健壮性功能。"
            ),
            scope="project:digitalme",
            confidence=0.98,
            salience=0.95,
            evidence_strength="E4",
            status="confirmed",
            sensitivity="personal",
        )
        sensitive = MemoryCandidate(
            episode_id=episode.id,
            extractor_version="memory-extract-v1",
            content_hash="sensitive-hash",
            candidate_type="decision",
            content="DigitalMe MVP first includes sensitive planning.",
            scope="project:digitalme",
            confidence=0.9,
            salience=0.7,
            evidence_strength="E4",
            status="confirmed",
            sensitivity="sensitive",
        )
        unrelated = MemoryCandidate(
            episode_id=episode.id,
            extractor_version="memory-extract-v1",
            content_hash="unrelated-hash",
            candidate_type="preference",
            content="The user likes jasmine tea.",
            scope="global",
            confidence=0.9,
            salience=0.3,
            evidence_strength="E4",
            status="confirmed",
            sensitivity="personal",
        )
        pending = MemoryCandidate(
            episode_id=episode.id,
            extractor_version="memory-extract-v1",
            content_hash="pending-hash",
            candidate_type="decision",
            content="pending DigitalMe MVP first",
            scope="project:digitalme",
            confidence=1.0,
            salience=1.0,
            evidence_strength="E5",
            status="candidate",
            sensitivity="personal",
        )
        orphan = MemoryCandidate(
            episode_id=episode.id,
            extractor_version="memory-extract-v1",
            content_hash="orphan-hash",
            candidate_type="decision",
            content="orphan DigitalMe MVP first",
            scope="project:digitalme",
            confidence=1.0,
            salience=1.0,
            evidence_strength="E5",
            status="confirmed",
            sensitivity="personal",
        )
        db.add_all([safe, sensitive, unrelated, pending, orphan])
        db.flush()
        db.add_all(
            CandidateEvidence(
                candidate_id=candidate.id,
                message_id=message.id,
                quote_snapshot="We chose the MVP first.",
            )
            for candidate in (safe, sensitive, unrelated)
        )
        return engine, factory, safe.id, sensitive.id
