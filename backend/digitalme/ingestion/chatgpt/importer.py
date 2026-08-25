"""Synchronous, idempotent ChatGPT export import service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from digitalme.ingestion.chatgpt.adapter import adapt_conversation
from digitalme.ingestion.chatgpt.export import discover_conversation_documents
from digitalme.ingestion.common.artifacts import ArtifactDescriptor, ArtifactStore
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
class ChatGPTImportResult:
    job_id: str
    artifact_id: str
    sessions_created: int
    sessions_updated: int
    messages_created: int
    messages_updated: int
    warnings: int
    redactions: int


class ChatGPTImporter:
    """Archive, parse and persist an official ChatGPT export."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_store: ArtifactStore,
    ) -> None:
        self.session_factory = session_factory
        self.artifact_store = artifact_store

    def import_zip(self, archive_path: Path) -> ChatGPTImportResult:
        job_id = self.create_job()
        return self.run_job(job_id, archive_path)

    def create_job(self, *, checkpoint: dict[str, object] | None = None) -> str:
        """Create a pending job that can be safely handed to a background worker."""

        with self.session_factory.begin() as db:
            source = db.scalar(
                select(Source).where(
                    Source.source_type == SourceType.CHATGPT.value,
                    Source.name == "ChatGPT Export",
                )
            )
            if source is None:
                source = Source(source_type=SourceType.CHATGPT.value, name="ChatGPT Export")
                db.add(source)
                db.flush()
            job = IngestionJob(
                source_id=source.id,
                kind="chatgpt_export",
                status=IngestionJobStatus.PENDING.value,
                stage="queued",
                checkpoint=checkpoint or {},
            )
            db.add(job)
            db.flush()
            return job.id

    def run_job(self, job_id: str, archive_path: Path) -> ChatGPTImportResult:
        """Atomically claim and execute one previously-created pending import job."""

        source_id = self._claim_job(job_id)
        try:
            descriptor = self.artifact_store.put_file(
                archive_path,
                source_type=SourceType.CHATGPT.value,
                media_type="application/zip",
            )
            artifact_id = self._register_artifact(source_id, job_id, descriptor)
            documents = discover_conversation_documents(archive_path)
            counts = {
                "sessions_created": 0,
                "sessions_updated": 0,
                "messages_created": 0,
                "messages_updated": 0,
                "warnings": 0,
                "redactions": 0,
            }
            with self.session_factory.begin() as db:
                for document in documents:
                    for index, conversation in enumerate(document.conversations):
                        canonical = adapt_conversation(
                            conversation,
                            member_name=document.member_name,
                            conversation_index=index,
                        )
                        self._persist_session(db, source_id, artifact_id, canonical, counts)
                job = db.get(IngestionJob, job_id)
                if job is None:
                    raise RuntimeError("Ingestion job disappeared during import")
                job.status = (
                    IngestionJobStatus.COMPLETED_WITH_WARNINGS.value
                    if counts["warnings"]
                    else IngestionJobStatus.COMPLETED.value
                )
                job.stage = "completed"
                job.counts = counts
                job.finished_at = datetime.now(UTC)
            return ChatGPTImportResult(job_id=job_id, artifact_id=artifact_id, **counts)
        except Exception as exc:
            self._fail_job(job_id, exc)
            raise

    def _claim_job(self, job_id: str) -> str:
        with self.session_factory.begin() as db:
            source_id = db.scalar(
                update(IngestionJob)
                .where(
                    IngestionJob.id == job_id,
                    IngestionJob.status == IngestionJobStatus.PENDING.value,
                )
                .values(
                    status=IngestionJobStatus.RUNNING.value,
                    stage="archive",
                    started_at=datetime.now(UTC),
                    error_summary=None,
                    finished_at=None,
                )
                .returning(IngestionJob.source_id)
            )
            if source_id is None:
                raise RuntimeError("Ingestion job is missing or is not pending")
            return source_id

    def _fail_job(self, job_id: str, exc: Exception) -> None:
        safe_message = redact_text(str(exc)).text[:500]
        with self.session_factory.begin() as db:
            job = db.get(IngestionJob, job_id)
            if job is not None and job.status == IngestionJobStatus.RUNNING.value:
                job.status = IngestionJobStatus.FAILED.value
                job.error_summary = f"{type(exc).__name__}: {safe_message}"
                job.finished_at = datetime.now(UTC)

    def _register_artifact(
        self,
        source_id: str,
        job_id: str,
        descriptor: ArtifactDescriptor,
    ) -> str:
        with self.session_factory.begin() as db:
            artifact = db.scalar(select(Artifact).where(Artifact.sha256 == descriptor.sha256))
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
            job = db.get(IngestionJob, job_id)
            if job is None:
                raise RuntimeError("Ingestion job disappeared while archiving")
            job.stage = "parse"
            job.checkpoint = {"artifact_id": artifact.id}
            return artifact.id

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
        record.selected_branch_head_external_id = canonical.selected_branch_head_external_id
        record.parse_warnings = [
            warning.model_dump(mode="json") for warning in canonical.parse_warnings
        ]
        counts["warnings"] += len(canonical.parse_warnings)

        existing = {
            message.external_id: message
            for message in db.scalars(select(Message).where(Message.session_id == record.id)).all()
        }
        incoming_ids: set[str] = set()
        for canonical_message in canonical.messages:
            incoming_ids.add(canonical_message.external_id)
            message = existing.get(canonical_message.external_id)
            if message is None:
                message = Message(
                    session_id=record.id,
                    external_id=canonical_message.external_id,
                )
                db.add(message)
                counts["messages_created"] += 1
            else:
                counts["messages_updated"] += 1
            counts["redactions"] += _update_message(message, canonical_message)
            counts["warnings"] += len(canonical_message.parse_warnings)
        stale_ids = set(existing) - incoming_ids
        if stale_ids:
            db.execute(
                delete(Message).where(
                    Message.session_id == record.id,
                    Message.external_id.in_(stale_ids),
                )
            )


def _update_message(message: Message, canonical: CanonicalMessage) -> int:
    message.parent_external_id = canonical.parent_external_id
    message.role = canonical.role
    message.content_type = canonical.content_type
    message.normalized_text = canonical.normalized_text
    if canonical.normalized_text is None:
        message.redacted_text = None
        message.redaction_spans = []
        message.sensitivity = Sensitivity.PERSONAL.value
        redaction_count = 0
    else:
        redacted = redact_text(canonical.normalized_text)
        message.redacted_text = redacted.text
        message.redaction_spans = [span.as_dict() for span in redacted.spans]
        message.sensitivity = redacted.sensitivity.value
        redaction_count = len(redacted.spans)
    message.source_timestamp = canonical.source_timestamp
    message.sequence = canonical.sequence
    message.raw_locator = canonical.raw_locator
    message.parse_warnings = [
        warning.model_dump(mode="json") for warning in canonical.parse_warnings
    ]
    return redaction_count
