"""Background execution and restart recovery for HTTP ingestion jobs."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from digitalme.config import Settings
from digitalme.db.session import create_engine, create_session_factory
from digitalme.ingestion.chatgpt import ChatGPTImporter
from digitalme.ingestion.common import ArtifactStore
from digitalme.models import Artifact, IngestionJob, IngestionJobStatus


@dataclass(frozen=True, slots=True)
class RecoverableChatGPTJob:
    """A non-terminal job and the trusted input from which it can be replayed."""

    job_id: str
    input_path: Path
    remove_input_after_run: bool


async def launch_chatgpt_import_job(
    settings: Settings,
    job_id: str,
    input_path: Path,
    thread_registry: list[Thread],
) -> None:
    """Start an accepted import without requiring an event-loop threadpool callback."""

    thread_registry[:] = [thread for thread in thread_registry if thread.is_alive()]
    worker = Thread(
        target=run_chatgpt_import_job,
        args=(settings, job_id, input_path),
        name=f"digitalme-ingestion-{job_id}",
    )
    worker.start()
    thread_registry.append(worker)


def run_chatgpt_import_job(
    settings: Settings,
    job_id: str,
    input_path: Path,
    *,
    remove_input_after_run: bool = True,
) -> None:
    """Run one queued import and clean request-owned input when appropriate."""

    engine: Engine | None = None
    try:
        # The importer persists a redacted failure summary on the job. Background tasks must
        # not turn a successfully accepted HTTP response into an unhandled server exception.
        with suppress(Exception):
            engine = create_engine(settings)
            importer = ChatGPTImporter(
                create_session_factory(engine),
                ArtifactStore(settings.raw_store_path),
            )
            importer.run_job(job_id, input_path)
    finally:
        if engine is not None:
            engine.dispose()
        if remove_input_after_run:
            input_path.unlink(missing_ok=True)


def prepare_chatgpt_job_recovery(settings: Settings) -> list[RecoverableChatGPTJob]:
    """Reset interrupted HTTP imports and resolve their replay inputs.

    A job interrupted before archival reuses its server-named incoming file. Once an artifact
    checkpoint exists, recovery reads the immutable Raw Store copy and must never delete it.
    """

    engine = create_engine(settings)
    artifact_store = ArtifactStore(settings.raw_store_path)
    recoverable: list[RecoverableChatGPTJob] = []
    try:
        session_factory = create_session_factory(engine)
        with session_factory.begin() as db:
            jobs = db.scalars(
                select(IngestionJob)
                .where(
                    IngestionJob.kind == "chatgpt_export",
                    IngestionJob.status.in_(
                        [
                            IngestionJobStatus.PENDING.value,
                            IngestionJobStatus.RUNNING.value,
                        ]
                    ),
                )
                .order_by(IngestionJob.created_at, IngestionJob.id)
            ).all()
            for job in jobs:
                recovery_input = _resolve_recovery_input(
                    db,
                    settings=settings,
                    artifact_store=artifact_store,
                    checkpoint=job.checkpoint,
                )
                was_running = job.status == IngestionJobStatus.RUNNING.value
                if recovery_input is None:
                    if was_running:
                        job.retry_count += 1
                    job.status = IngestionJobStatus.FAILED.value
                    job.stage = "recovery"
                    job.error_summary = "RecoveryError: Import input is unavailable"
                    job.finished_at = datetime.now(UTC)
                    continue

                if was_running:
                    job.retry_count += 1
                job.status = IngestionJobStatus.PENDING.value
                job.stage = "recovery_queued"
                job.started_at = None
                job.finished_at = None
                job.error_summary = None
                recoverable.append(
                    RecoverableChatGPTJob(
                        job_id=job.id,
                        input_path=recovery_input[0],
                        remove_input_after_run=recovery_input[1],
                    )
                )
    finally:
        engine.dispose()
    return recoverable


def run_recovered_chatgpt_jobs(
    settings: Settings,
    jobs: list[RecoverableChatGPTJob],
) -> None:
    """Replay recovered jobs serially to keep SQLite write contention bounded."""

    for job in jobs:
        run_chatgpt_import_job(
            settings,
            job.job_id,
            job.input_path,
            remove_input_after_run=job.remove_input_after_run,
        )


def _resolve_recovery_input(
    db: Session,
    *,
    settings: Settings,
    artifact_store: ArtifactStore,
    checkpoint: dict[str, object],
) -> tuple[Path, bool] | None:
    artifact_id = checkpoint.get("artifact_id")
    if isinstance(artifact_id, str):
        artifact = db.get(Artifact, artifact_id)
        if artifact is not None:
            try:
                artifact_path = artifact_store.resolve(artifact.relative_path)
            except ValueError:
                return None
            if artifact_path.is_file():
                return artifact_path, False

    incoming_file = checkpoint.get("incoming_file")
    if not isinstance(incoming_file, str) or Path(incoming_file).name != incoming_file:
        return None
    incoming_root = settings.incoming_path.expanduser().resolve()
    unresolved_path = incoming_root / incoming_file
    if unresolved_path.is_symlink():
        return None
    incoming_path = unresolved_path.resolve()
    if incoming_path.parent != incoming_root or not incoming_path.is_file():
        return None
    return incoming_path, True
