import json
import zipfile
from pathlib import Path

import pytest
from digitalme.api.app import create_app
from digitalme.api.ingestion import (
    prepare_chatgpt_job_recovery,
    run_chatgpt_import_job,
)
from digitalme.config import Settings, get_settings
from digitalme.db.base import Base
from digitalme.db.session import create_engine, create_session_factory
from digitalme.ingestion.chatgpt import ChatGPTImporter
from digitalme.ingestion.common import ArtifactStore
from digitalme.models import IngestionJob, IngestionJobStatus, SessionRecord
from sqlalchemy import func, select


def test_interrupted_archived_job_recovers_from_raw_store(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    archive_path = tmp_path / "export.zip"
    _write_export(archive_path)
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    artifact_store = ArtifactStore(settings.raw_store_path)
    importer = ChatGPTImporter(factory, artifact_store)
    job_id = importer.create_job(checkpoint={"incoming_file": "upload.zip"})

    source_id = importer._claim_job(job_id)
    descriptor = artifact_store.put_file(
        archive_path,
        source_type="chatgpt",
        media_type="application/zip",
    )
    artifact_id = importer._register_artifact(source_id, job_id, descriptor)
    raw_path = artifact_store.resolve(descriptor.relative_path)
    engine.dispose()

    recoverable = prepare_chatgpt_job_recovery(settings)

    assert len(recoverable) == 1
    recovered = recoverable[0]
    assert recovered.job_id == job_id
    assert recovered.input_path == raw_path
    assert recovered.remove_input_after_run is False
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    with factory() as db:
        job = db.get(IngestionJob, job_id)
        assert job is not None
        assert job.status == IngestionJobStatus.PENDING.value
        assert job.stage == "recovery_queued"
        assert job.retry_count == 1
        assert job.checkpoint == {"artifact_id": artifact_id}
    engine.dispose()

    run_chatgpt_import_job(
        settings,
        recovered.job_id,
        recovered.input_path,
        remove_input_after_run=recovered.remove_input_after_run,
    )

    assert raw_path.is_file()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    with factory() as db:
        job = db.get(IngestionJob, job_id)
        assert job is not None
        assert job.status == IngestionJobStatus.COMPLETED.value
        assert db.scalar(select(func.count()).select_from(SessionRecord)) == 1
    engine.dispose()


def test_recovery_fails_job_with_untrusted_or_missing_input(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    importer = ChatGPTImporter(factory, ArtifactStore(settings.raw_store_path))
    job_id = importer.create_job(checkpoint={"incoming_file": "../outside.zip"})
    engine.dispose()

    assert prepare_chatgpt_job_recovery(settings) == []

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    with factory() as db:
        job = db.get(IngestionJob, job_id)
        assert job is not None
        assert job.status == IngestionJobStatus.FAILED.value
        assert job.stage == "recovery"
        assert job.error_summary == "RecoveryError: Import input is unavailable"
        assert job.finished_at is not None
    engine.dispose()


@pytest.mark.asyncio
async def test_application_startup_resumes_pending_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGITALME_DATABASE_URL", f"sqlite:///{tmp_path / 'digitalme.db'}")
    monkeypatch.setenv("DIGITALME_RAW_STORE_PATH", str(tmp_path / "raw"))
    monkeypatch.setenv("DIGITALME_INCOMING_PATH", str(tmp_path / "incoming"))
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    upload_path = settings.incoming_path / ".chatgpt-upload-recovery.zip"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    _write_export(upload_path)
    job_id = ChatGPTImporter(factory, ArtifactStore(settings.raw_store_path)).create_job(
        checkpoint={
            "incoming_file": upload_path.name,
            "size_bytes": upload_path.stat().st_size,
        }
    )
    engine.dispose()

    app = create_app()
    async with app.router.lifespan_context(app):
        recovery_thread = app.state.ingestion_recovery_thread
        assert recovery_thread is not None
        recovery_thread.join(timeout=5)
        assert not recovery_thread.is_alive()

    assert not upload_path.exists()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    with factory() as db:
        assert db.scalar(select(IngestionJob.status).where(IngestionJob.id == job_id)) == (
            IngestionJobStatus.COMPLETED.value
        )
    engine.dispose()
    get_settings.cache_clear()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        DIGITALME_DATABASE_URL=f"sqlite:///{tmp_path / 'digitalme.db'}",
        DIGITALME_RAW_STORE_PATH=tmp_path / "raw",
        DIGITALME_INCOMING_PATH=tmp_path / "incoming",
    )


def _write_export(path: Path) -> None:
    conversation = {
        "id": "recovery-conversation",
        "title": "Recovery fixture",
        "mapping": {
            "message-1": {
                "parent": None,
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Recover me"]},
                },
            }
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("conversations.json", json.dumps([conversation]))
