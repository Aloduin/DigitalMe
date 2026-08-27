from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from digitalme.config import Settings
from digitalme.db.base import Base
from digitalme.db.session import create_engine, create_session_factory
from digitalme.episodes import EpisodeService
from digitalme.models import Episode, EpisodeMessage, Message, SessionRecord, Source
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_episode_rebuild_segments_selected_branch_with_evidence(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    base_time = datetime(2026, 8, 27, 1, 0, tzinfo=UTC)
    with factory.begin() as db:
        source = Source(source_type="chatgpt", name="Episode fixture")
        db.add(source)
        db.flush()
        session = SessionRecord(
            source_id=source.id,
            external_id="episode-session",
            schema_version=1,
            title="MVP planning",
            selected_branch_head_external_id="assistant-3",
        )
        db.add(session)
        db.flush()
        _add_message(db, session.id, "user-1", None, "Start the MVP", base_time, 0)
        _add_message(
            db,
            session.id,
            "assistant-1",
            "user-1",
            "Start with episodes",
            base_time + timedelta(minutes=1),
            1,
            role="assistant",
        )
        _add_message(
            db,
            session.id,
            "branch-other",
            "user-1",
            "Build a vector database first",
            base_time + timedelta(minutes=2),
            2,
        )
        _add_message(
            db,
            session.id,
            "user-2",
            "assistant-1",
            "Continue after a break",
            base_time + timedelta(hours=3),
            3,
        )
        _add_message(
            db,
            session.id,
            "assistant-2",
            "user-2",
            "Evidence stays linked",
            base_time + timedelta(hours=3, minutes=1),
            4,
            role="assistant",
        )
        _add_message(
            db,
            session.id,
            "user-3",
            "assistant-2",
            "[New Topic] Memory candidates",
            base_time + timedelta(hours=3, minutes=2),
            5,
        )
        _add_message(
            db,
            session.id,
            "assistant-3",
            "user-3",
            "Next slice",
            base_time + timedelta(hours=3, minutes=3),
            6,
            role="assistant",
        )

    service = EpisodeService(factory)
    first = service.rebuild_session(session.id)

    assert first.episodes_created == 3
    assert first.messages_linked == 6
    page = service.list_episodes(session_id=session.id)
    assert page.total == 3
    assert sorted(item.message_count for item in page.items) == [2, 2, 2]
    details = [service.get_episode(item.id) for item in page.items]
    assert all(detail is not None for detail in details)
    evidence_text = {
        message.redacted_text
        for detail in details
        if detail is not None
        for message in detail.messages
    }
    assert "Build a vector database first" not in evidence_text
    assert "Start the MVP" in evidence_text
    assert all(
        message.raw_locator
        for detail in details
        if detail is not None
        for message in detail.messages
    )

    second = service.rebuild_session(session.id)
    assert second.episodes_created == 3
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Episode)) == 3
        assert db.scalar(select(func.count()).select_from(EpisodeMessage)) == 6

    service.rebuild_session(session.id, pipeline_version="segment-v2")
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Episode)) == 6
        assert db.scalar(select(func.count()).select_from(EpisodeMessage)) == 12
    engine.dispose()


def test_episode_rebuild_rejects_missing_session(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    service = EpisodeService(create_session_factory(engine))

    with pytest.raises(LookupError, match="Session not found"):
        service.rebuild_session("ses_missing")
    engine.dispose()


def _add_message(
    db: Session,
    session_id: str,
    external_id: str,
    parent_external_id: str | None,
    text: str,
    timestamp: datetime,
    sequence: int,
    *,
    role: str = "user",
) -> None:
    db.add(
        Message(
            session_id=session_id,
            external_id=external_id,
            parent_external_id=parent_external_id,
            role=role,
            content_type="text",
            normalized_text=text,
            redacted_text=text,
            redaction_spans=[],
            sensitivity="personal",
            source_timestamp=timestamp,
            sequence=sequence,
            raw_locator={"node_id": external_id},
            parse_warnings=[],
        )
    )
