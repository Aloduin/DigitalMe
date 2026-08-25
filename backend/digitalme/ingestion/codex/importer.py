"""Minimal synchronous Codex rollout scan for the prototype."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from digitalme.ingestion.codex.rollout import adapt_rollout, discover_rollouts
from digitalme.ingestion.common import ArtifactStore
from digitalme.ingestion.common.schema import CanonicalMessage, CanonicalSession
from digitalme.models import (
    Artifact,
    IngestionJob,
    IngestionJobStatus,
    Message,
    SessionRecord,
    Source,
    SourceType,
)
from digitalme.privacy import Sensitivity, redact_text


@dataclass(frozen=True, slots=True)
class CodexImportResult:
    job_id: str
    files_scanned: int
    sessions_created: int
    sessions_updated: int
    messages_created: int
    messages_updated: int
    warnings: int
    redactions: int


class CodexImporter:
    """Discover and idempotently persist local Codex rollout files."""

    def __init__(
        self, session_factory: sessionmaker[Session], artifact_store: ArtifactStore
    ) -> None:
        self.session_factory = session_factory
        self.artifact_store = artifact_store

    def scan(self, codex_home: Path) -> CodexImportResult:
        home = codex_home.expanduser().resolve()
        source_id, job_id = self._start_job(home)
        counts = {
            "files_scanned": 0,
            "sessions_created": 0,
            "sessions_updated": 0,
            "messages_created": 0,
            "messages_updated": 0,
            "warnings": 0,
            "redactions": 0,
        }
        try:
            for rollout_path in discover_rollouts(home):
                descriptor = self.artifact_store.put_file(
                    rollout_path,
                    source_type=SourceType.CODEX.value,
                    media_type="application/x-ndjson",
                )
                canonical = adapt_rollout(rollout_path)
                with self.session_factory.begin() as db:
                    artifact = db.scalar(
                        select(Artifact).where(Artifact.sha256 == descriptor.sha256)
                    )
                    if artifact is None:
                        artifact = Artifact(
                            source_id=source_id,
                            sha256=descriptor.sha256,
                            relative_path=descriptor.relative_path,
                            size_bytes=descriptor.size_bytes,
                            media_type=descriptor.media_type,
                        )
                        db.add(artifact)
                        db.flush()
                    self._persist_session(db, source_id, artifact.id, canonical, counts)
                counts["files_scanned"] += 1
            with self.session_factory.begin() as db:
                job = db.get(IngestionJob, job_id)
                if job is None:
                    raise RuntimeError("Codex ingestion job disappeared")
                job.status = (
                    IngestionJobStatus.COMPLETED_WITH_WARNINGS.value
                    if counts["warnings"]
                    else IngestionJobStatus.COMPLETED.value
                )
                job.stage = "completed"
                job.counts = counts
                job.finished_at = datetime.now(UTC)
            return CodexImportResult(job_id=job_id, **counts)
        except Exception as exc:
            with self.session_factory.begin() as db:
                job = db.get(IngestionJob, job_id)
                if job is not None:
                    job.status = IngestionJobStatus.FAILED.value
                    job.error_summary = f"{type(exc).__name__}: {redact_text(str(exc)).text[:500]}"
                    job.finished_at = datetime.now(UTC)
            raise

    def _start_job(self, home: Path) -> tuple[str, str]:
        with self.session_factory.begin() as db:
            source = db.scalar(
                select(Source).where(
                    Source.source_type == SourceType.CODEX.value,
                    Source.name == "Codex Rollouts",
                )
            )
            if source is None:
                source = Source(
                    source_type=SourceType.CODEX.value,
                    name="Codex Rollouts",
                    root_uri=str(home),
                )
                db.add(source)
                db.flush()
            else:
                source.root_uri = str(home)
            job = IngestionJob(
                source_id=source.id,
                kind="codex_scan",
                status=IngestionJobStatus.RUNNING.value,
                stage="discovery",
                started_at=datetime.now(UTC),
            )
            db.add(job)
            db.flush()
            return source.id, job.id

    @staticmethod
    def _persist_session(
        db: Session,
        source_id: str,
        artifact_id: str,
        canonical: CanonicalSession,
        counts: dict[str, int],
    ) -> None:
        record = db.scalar(
            select(SessionRecord).where(
                SessionRecord.source_id == source_id,
                SessionRecord.external_id == canonical.external_id,
                SessionRecord.schema_version == canonical.schema_version,
            )
        )
        if record is None:
            record = SessionRecord(
                source_id=source_id,
                external_id=canonical.external_id,
                schema_version=canonical.schema_version,
            )
            db.add(record)
            db.flush()
            counts["sessions_created"] += 1
        else:
            counts["sessions_updated"] += 1
        record.artifact_id = artifact_id
        record.title = canonical.title
        record.source_created_at = canonical.source_created_at
        record.source_updated_at = canonical.source_updated_at
        record.parse_warnings = [
            warning.model_dump(mode="json") for warning in canonical.parse_warnings
        ]
        counts["warnings"] += len(canonical.parse_warnings)
        existing = {
            message.external_id: message
            for message in db.scalars(select(Message).where(Message.session_id == record.id)).all()
        }
        incoming: set[str] = set()
        for canonical_message in canonical.messages:
            incoming.add(canonical_message.external_id)
            message = existing.get(canonical_message.external_id)
            if message is None:
                message = Message(session_id=record.id, external_id=canonical_message.external_id)
                db.add(message)
                counts["messages_created"] += 1
            else:
                counts["messages_updated"] += 1
            counts["redactions"] += _update_message(message, canonical_message)
        stale = set(existing) - incoming
        if stale:
            db.execute(
                delete(Message).where(
                    Message.session_id == record.id, Message.external_id.in_(stale)
                )
            )


def _update_message(message: Message, canonical: CanonicalMessage) -> int:
    message.parent_external_id = canonical.parent_external_id
    message.role = canonical.role
    message.content_type = canonical.content_type
    message.normalized_text = canonical.normalized_text
    redacted = redact_text(canonical.normalized_text or "")
    message.redacted_text = redacted.text if canonical.normalized_text is not None else None
    message.redaction_spans = [span.as_dict() for span in redacted.spans]
    message.sensitivity = (
        redacted.sensitivity.value
        if canonical.normalized_text is not None
        else Sensitivity.PERSONAL.value
    )
    message.source_timestamp = canonical.source_timestamp
    message.sequence = canonical.sequence
    message.raw_locator = canonical.raw_locator
    message.parse_warnings = [
        warning.model_dump(mode="json") for warning in canonical.parse_warnings
    ]
    return len(redacted.spans)
