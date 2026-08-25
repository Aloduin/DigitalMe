import json
from pathlib import Path

from digitalme.config import Settings
from digitalme.db.base import Base
from digitalme.db.session import create_engine, create_session_factory
from digitalme.ingestion.codex import CodexImporter, adapt_rollout, discover_rollouts
from digitalme.ingestion.common import ArtifactStore
from digitalme.models import Message, SessionRecord
from sqlalchemy import func, select


def test_codex_discovery_and_adapter_are_tolerant(tmp_path: Path) -> None:
    rollout = _write_rollout(tmp_path)
    archived = tmp_path / "archived_sessions" / "rollout-archived.jsonl"
    archived.parent.mkdir(parents=True)
    archived.write_text("", encoding="utf-8")

    assert discover_rollouts(tmp_path) == sorted([rollout.resolve(), archived.resolve()])
    canonical = adapt_rollout(rollout)

    assert canonical.external_id == "codex-session-1"
    assert canonical.title == "DigitalMe"
    assert [message.role for message in canonical.messages] == ["user", "assistant"]
    assert canonical.messages[0].normalized_text == "Build the prototype"
    assert canonical.messages[0].raw_locator["line"] == 5
    assert {warning.code for warning in canonical.parse_warnings} == {
        "invalid_jsonl_line",
        "unknown_event_type",
    }


def test_codex_scan_is_idempotent_and_redacts_messages(tmp_path: Path) -> None:
    _write_rollout(tmp_path)
    settings = Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    importer = CodexImporter(factory, ArtifactStore(settings.raw_store_path))

    first = importer.scan(tmp_path)
    second = importer.scan(tmp_path)

    assert first.sessions_created == 1
    assert first.messages_created == 2
    assert first.redactions == 1
    assert second.sessions_created == 0
    assert second.sessions_updated == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SessionRecord)) == 1
        assert db.scalar(select(func.count()).select_from(Message)) == 2
        assistant = db.scalar(select(Message).where(Message.role == "assistant"))
        assert assistant is not None
        assert assistant.redacted_text == "API_KEY=[REDACTED:credential_assignment]"
        assert assistant.sensitivity == "secret"
    engine.dispose()


def _write_rollout(root: Path) -> Path:
    path = root / "sessions" / "2026" / "08" / "25" / "rollout-test.jsonl"
    path.parent.mkdir(parents=True)
    fake_secret = "sk-" + "abcdefghijklmnopqrstuvwxyz" + "123456"
    events = [
        {
            "timestamp": "2026-08-25T01:00:00Z",
            "type": "session_meta",
            "payload": {"id": "codex-session-1", "cwd": "D:/projects/DigitalMe"},
        },
        {
            "timestamp": "2026-08-25T01:00:01Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "Build the prototype"},
        },
        {"timestamp": "2026-08-25T01:00:02Z", "type": "future_event", "payload": {}},
        {
            "timestamp": "2026-08-25T01:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Build the prototype"}],
            },
        },
        {
            "timestamp": "2026-08-25T01:00:04Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": f"API_KEY={fake_secret}"}],
            },
        },
    ]
    lines = [json.dumps(event) for event in events]
    lines.insert(2, "{broken")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
