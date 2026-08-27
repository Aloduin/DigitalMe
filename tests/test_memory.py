from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from digitalme.api.app import create_app
from digitalme.config import Settings, get_settings
from digitalme.db.base import Base
from digitalme.db.session import create_engine, create_session_factory
from digitalme.episodes import EpisodeService
from digitalme.memory import ExtractionValidationError, MemoryService
from digitalme.memory.contracts import EpisodeExtraction
from digitalme.models import (
    Episode,
    EpisodeMessage,
    MemoryCandidate,
    Message,
    SessionRecord,
    Source,
)
from pydantic import ValidationError
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker


class FakeJsonProvider:
    name = "fake"
    model = "fake-json"
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
        assert "JSON" in system_prompt
        self.inputs.append(input_payload)
        return self.output


def test_episode_extraction_rejects_whitespace_semantic_fields() -> None:
    output = _extraction_output("message-id")
    output["summary"] = "   "

    with pytest.raises(ValidationError, match="value must not be blank"):
        EpisodeExtraction.model_validate(output)


def test_memory_extraction_links_evidence_and_preserves_user_status(tmp_path: Path) -> None:
    engine, factory, episode_id, personal_id, secret_id = _episode_fixture(tmp_path)
    provider = FakeJsonProvider()
    provider.output = _extraction_output(personal_id)
    service = MemoryService(factory, provider)

    first = service.extract_episode(episode_id)

    assert first.candidates_created == 2
    assert first.messages_sent == 1
    assert first.messages_excluded == 1
    assert [message["id"] for message in provider.inputs[0]["messages"]] == [personal_id]
    assert secret_id not in str(provider.inputs[0])
    page = service.list_candidates(episode_id=episode_id)
    assert page.total == 2
    assert {item.status for item in page.items} == {"candidate", "hypothesis"}
    assert all(item.evidence_count == 1 for item in page.items)
    decision = next(item for item in page.items if item.candidate_type == "decision")
    detail = service.get_candidate(decision.id)
    assert detail is not None
    assert detail.evidence[0].message_id == personal_id
    assert detail.evidence[0].quote_snapshot == "We decided to build the MVP first."
    assert detail.evidence[0].raw_locator == {"node_id": "personal"}

    confirmed = service.set_candidate_status(decision.id, "confirmed")
    assert confirmed.summary.status == "confirmed"
    with factory() as db:
        stored_episode = db.get(Episode, episode_id)
        assert stored_episode is not None
        session_id = stored_episode.session_id
    with pytest.raises(ValueError, match="confirmed or rejected"):
        EpisodeService(factory).rebuild_session(session_id)
    second = service.extract_episode(episode_id)
    assert second.candidates_created == 1
    page = service.list_candidates(episode_id=episode_id)
    assert page.total == 2
    assert sum(item.status == "confirmed" for item in page.items) == 1
    with factory() as db:
        episode = db.get(Episode, episode_id)
        assert episode is not None
        assert episode.extraction_status == "extracted"
        assert episode.summary == "The project chose an MVP-first path."
        assert episode.projects == ["DigitalMe"]
    engine.dispose()


def test_invalid_candidate_evidence_does_not_persist_extraction(tmp_path: Path) -> None:
    engine, factory, episode_id, _, secret_id = _episode_fixture(tmp_path)
    provider = FakeJsonProvider()
    provider.output = _extraction_output(secret_id)
    service = MemoryService(factory, provider)

    with pytest.raises(ExtractionValidationError, match="outside"):
        service.extract_episode(episode_id)

    with factory() as db:
        episode = db.get(Episode, episode_id)
        assert episode is not None
        assert episode.extraction_status == "segmented"
        assert db.scalar(select(func.count()).select_from(MemoryCandidate)) == 0
    engine.dispose()


@pytest.mark.asyncio
async def test_memory_api_browses_evidence_and_updates_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory, episode_id, personal_id, _ = _episode_fixture(tmp_path)
    provider = FakeJsonProvider()
    provider.output = _extraction_output(personal_id)
    MemoryService(factory, provider).extract_episode(episode_id)
    engine.dispose()
    monkeypatch.setenv("DIGITALME_DATABASE_URL", f"sqlite:///{tmp_path / 'digitalme.db'}")
    monkeypatch.setenv("DIGITALME_RAW_STORE_PATH", str(tmp_path / "raw"))
    monkeypatch.setenv("DIGITALME_INCOMING_PATH", str(tmp_path / "incoming"))
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("API_BASE_URL", "")
    get_settings.cache_clear()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        memories = await client.get("/api/v1/memories")
        assert memories.status_code == 200
        assert memories.json()["total"] == 2
        candidate_id = memories.json()["items"][0]["id"]
        detail = await client.get(f"/api/v1/memories/{candidate_id}")
        assert detail.status_code == 200
        assert detail.json()["evidence"][0]["quote_snapshot"]
        assert "normalized_text" not in detail.text

        confirmed = await client.patch(
            f"/api/v1/memories/{candidate_id}",
            json={"status": "confirmed"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["summary"]["status"] == "confirmed"
        invalid = await client.patch(
            f"/api/v1/memories/{candidate_id}",
            json={"status": "active"},
        )
        assert invalid.status_code == 422

    get_settings.cache_clear()


def _episode_fixture(
    tmp_path: Path,
) -> tuple[Engine, sessionmaker[Session], str, str, str]:
    settings = Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    now = datetime(2026, 8, 27, 2, 0, tzinfo=UTC)
    with factory.begin() as db:
        source = Source(source_type="chatgpt", name="Memory fixture")
        db.add(source)
        db.flush()
        session = SessionRecord(
            source_id=source.id,
            external_id="memory-session",
            schema_version=1,
            title="MVP decision",
        )
        db.add(session)
        db.flush()
        personal = Message(
            session_id=session.id,
            external_id="personal",
            role="user",
            content_type="text",
            normalized_text="We decided to build the MVP first.",
            redacted_text="We decided to build the MVP first.",
            redaction_spans=[],
            sensitivity="personal",
            source_timestamp=now,
            sequence=0,
            raw_locator={"node_id": "personal"},
            parse_warnings=[],
        )
        secret = Message(
            session_id=session.id,
            external_id="secret",
            role="user",
            content_type="text",
            normalized_text="API_KEY=raw-secret",
            redacted_text="API_KEY=[REDACTED:credential_assignment]",
            redaction_spans=[],
            sensitivity="secret",
            source_timestamp=now,
            sequence=1,
            raw_locator={"node_id": "secret"},
            parse_warnings=[],
        )
        db.add_all([personal, secret])
        db.flush()
        episode = Episode(
            session_id=session.id,
            pipeline_version="segment-v1",
            segment_index=0,
            episode_type="conversation_segment",
            title="MVP decision",
            extraction_status="segmented",
        )
        db.add(episode)
        db.flush()
        db.add_all(
            [
                EpisodeMessage(episode_id=episode.id, message_id=personal.id, position=0),
                EpisodeMessage(episode_id=episode.id, message_id=secret.id, position=1),
            ]
        )
        return engine, factory, episode.id, personal.id, secret.id


def _extraction_output(evidence_message_id: str) -> dict[str, Any]:
    return {
        "episode_type": "project_decision",
        "title": "MVP-first decision",
        "summary": "The project chose an MVP-first path.",
        "projects": ["DigitalMe"],
        "decisions": ["Build the MVP before robustness work."],
        "open_questions": [],
        "candidates": [
            {
                "type": "decision",
                "content": "DigitalMe will build the MVP before robustness features.",
                "scope": "project:digitalme",
                "confidence": 0.98,
                "salience": 0.9,
                "evidence_strength": "E4",
                "evidence_message_ids": [evidence_message_id],
            },
            {
                "type": "preference",
                "content": "The user may prefer validating product value first.",
                "scope": "global",
                "confidence": 0.55,
                "salience": 0.6,
                "evidence_strength": "E1",
                "evidence_message_ids": [evidence_message_id],
            },
        ],
    }
