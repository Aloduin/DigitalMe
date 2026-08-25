import json
import zipfile
from pathlib import Path

import pytest
from digitalme.config import Settings
from digitalme.db.base import Base
from digitalme.db.session import create_engine, create_session_factory
from digitalme.ingestion.chatgpt import ChatGPTImporter
from digitalme.ingestion.chatgpt.export import UnsafeChatGPTExportError
from digitalme.ingestion.common import ArtifactStore
from digitalme.models import Artifact, IngestionJob, IngestionJobStatus, Message, SessionRecord
from sqlalchemy import func, select


def test_import_is_idempotent(tmp_path: Path) -> None:
    archive_path = tmp_path / "chatgpt-export.zip"
    write_export(archive_path)
    settings = Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    importer = ChatGPTImporter(factory, ArtifactStore(settings.raw_store_path))

    first = importer.import_zip(archive_path)
    second = importer.import_zip(archive_path)

    assert first.sessions_created == 1
    assert first.messages_created == 3
    assert second.sessions_created == 0
    assert second.sessions_updated == 1
    assert second.messages_created == 0
    assert second.messages_updated == 3
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Artifact)) == 1
        assert db.scalar(select(func.count()).select_from(SessionRecord)) == 1
        assert db.scalar(select(func.count()).select_from(Message)) == 3
        assert db.scalar(select(func.count()).select_from(IngestionJob)) == 2
        statuses = db.scalars(select(IngestionJob.status).order_by(IngestionJob.created_at)).all()
        assert statuses == [
            IngestionJobStatus.COMPLETED.value,
            IngestionJobStatus.COMPLETED.value,
        ]
        stored = db.scalar(select(Message).where(Message.external_id == "assistant-1"))
        assert stored is not None
        assert stored.normalized_text == "Hello from the assistant"
        assert stored.redacted_text == "Hello from the assistant"
        assert stored.redaction_spans == []
        assert stored.sensitivity == "personal"
        assert stored.raw_locator["node_id"] == "assistant-1"
    engine.dispose()


def test_failed_import_preserves_job_and_artifact_provenance(tmp_path: Path) -> None:
    archive_path = tmp_path / "invalid.zip"
    archive_path.write_bytes(b"not a zip")
    settings = Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    importer = ChatGPTImporter(factory, ArtifactStore(settings.raw_store_path))

    with pytest.raises(UnsafeChatGPTExportError, match="valid ZIP"):
        importer.import_zip(archive_path)

    with factory() as db:
        job = db.scalar(select(IngestionJob))
        assert job is not None
        assert job.status == IngestionJobStatus.FAILED.value
        assert job.stage == "parse"
        assert job.checkpoint["artifact_id"]
        assert job.error_summary == "UnsafeChatGPTExportError: Input is not a valid ZIP archive"
        artifact = db.scalar(select(Artifact))
        assert artifact is not None
        assert (settings.raw_store_path / artifact.relative_path).read_bytes() == b"not a zip"
    engine.dispose()


def test_import_persists_secret_only_in_raw_and_normalized_layers(tmp_path: Path) -> None:
    archive_path = tmp_path / "secret-export.zip"
    fake_secret = "sk-" + "abcdefghijklmnopqrstuvwxyz" + "123456"
    conversation = {
        "id": "secret-conversation",
        "mapping": {
            "message-1": {
                "parent": None,
                "message": {
                    "author": {"role": "user"},
                    "content": {
                        "content_type": "text",
                        "parts": [f"API_KEY={fake_secret}"],
                    },
                },
            }
        },
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("conversations.json", json.dumps([conversation]))
    settings = Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
    )
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    result = ChatGPTImporter(factory, ArtifactStore(settings.raw_store_path)).import_zip(
        archive_path
    )

    assert result.redactions == 1
    with factory() as db:
        stored = db.scalar(select(Message))
        assert stored is not None
        assert stored.normalized_text == f"API_KEY={fake_secret}"
        assert stored.redacted_text == "API_KEY=[REDACTED:credential_assignment]"
        assert stored.sensitivity == "secret"
        assert stored.redaction_spans == [
            {
                "start": 8,
                "end": 43,
                "kind": "credential_assignment",
                "replacement": "[REDACTED:credential_assignment]",
            }
        ]
    engine.dispose()


def write_export(path: Path) -> None:
    conversation = {
        "id": "conversation-1",
        "title": "Fixture conversation",
        "create_time": 1_700_000_000,
        "update_time": 1_700_000_100,
        "current_node": "assistant-1",
        "mapping": {
            "root": {"id": "root", "parent": None, "message": None},
            "user-1": {
                "id": "user-1",
                "parent": "root",
                "message": {
                    "author": {"role": "user"},
                    "create_time": 1_700_000_001,
                    "content": {"content_type": "text", "parts": ["Hello"]},
                },
            },
            "assistant-1": {
                "id": "assistant-1",
                "parent": "user-1",
                "message": {
                    "author": {"role": "assistant"},
                    "create_time": 1_700_000_002,
                    "content": {
                        "content_type": "text",
                        "parts": ["Hello from the assistant"],
                    },
                },
            },
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("conversations.json", json.dumps([conversation]))
