"""Shared read models and queries for CLI and HTTP archive browsing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from digitalme.models import IngestionError, IngestionJob, Message, SessionRecord, Source


@dataclass(frozen=True, slots=True)
class SessionSummary:
    id: str
    source_type: str
    title: str | None
    source_created_at: datetime | None
    source_updated_at: datetime | None
    message_count: int
    warning_count: int


@dataclass(frozen=True, slots=True)
class SessionPage:
    items: tuple[SessionSummary, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class MessageView:
    id: str
    external_id: str
    parent_external_id: str | None
    role: str | None
    content_type: str
    redacted_text: str | None
    sensitivity: str
    source_timestamp: datetime | None
    sequence: int | None
    raw_locator: dict[str, Any]
    parse_warnings: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SessionDetail:
    id: str
    source_type: str
    artifact_id: str | None
    external_id: str
    schema_version: int
    title: str | None
    source_created_at: datetime | None
    source_updated_at: datetime | None
    selected_branch_head_external_id: str | None
    parse_warnings: list[dict[str, Any]]
    messages: tuple[MessageView, ...]


@dataclass(frozen=True, slots=True)
class JobSummary:
    id: str
    source_type: str | None
    kind: str
    status: str
    stage: str | None
    counts: dict[str, int]
    retry_count: int
    error_summary: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class JobPage:
    items: tuple[JobSummary, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class IngestionErrorView:
    id: str
    stage: str
    error_type: str
    safe_summary: str
    raw_locator: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class JobDetail:
    summary: JobSummary
    checkpoint: dict[str, Any]
    errors: tuple[IngestionErrorView, ...]


class ArchiveQueryService:
    """Expose bounded, read-only archive views without leaking normalized source text."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def list_sessions(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        source_type: str | None = None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
    ) -> SessionPage:
        _validate_page(limit, offset)
        activity_at = func.coalesce(
            SessionRecord.source_updated_at,
            SessionRecord.source_created_at,
            SessionRecord.updated_at,
        )
        filters: list[ColumnElement[bool]] = []
        if source_type is not None:
            filters.append(Source.source_type == source_type)
        if updated_after is not None:
            filters.append(activity_at >= updated_after)
        if updated_before is not None:
            filters.append(activity_at <= updated_before)

        with self.session_factory() as db:
            total_query = select(func.count(SessionRecord.id)).join(Source)
            if filters:
                total_query = total_query.where(*filters)
            total = int(db.scalar(total_query) or 0)

            query = (
                select(SessionRecord, Source.source_type, func.count(Message.id))
                .join(Source)
                .outerjoin(Message)
                .group_by(SessionRecord.id, Source.source_type)
                .order_by(activity_at.desc(), SessionRecord.id)
                .limit(limit)
                .offset(offset)
            )
            if filters:
                query = query.where(*filters)
            rows = db.execute(query).all()

        return SessionPage(
            items=tuple(
                SessionSummary(
                    id=record.id,
                    source_type=row_source_type,
                    title=record.title,
                    source_created_at=record.source_created_at,
                    source_updated_at=record.source_updated_at,
                    message_count=int(message_count),
                    warning_count=len(record.parse_warnings or []),
                )
                for record, row_source_type, message_count in rows
            ),
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_session(self, session_id: str) -> SessionDetail | None:
        with self.session_factory() as db:
            row = db.execute(
                select(SessionRecord, Source.source_type)
                .join(Source)
                .where(SessionRecord.id == session_id)
            ).one_or_none()
            if row is None:
                return None
            record, source_type = row
            messages = db.scalars(
                select(Message)
                .where(Message.session_id == record.id)
                .order_by(
                    Message.sequence.is_(None),
                    Message.sequence,
                    Message.source_timestamp,
                    Message.id,
                )
            ).all()
            return SessionDetail(
                id=record.id,
                source_type=source_type,
                artifact_id=record.artifact_id,
                external_id=record.external_id,
                schema_version=record.schema_version,
                title=record.title,
                source_created_at=record.source_created_at,
                source_updated_at=record.source_updated_at,
                selected_branch_head_external_id=record.selected_branch_head_external_id,
                parse_warnings=list(record.parse_warnings or []),
                messages=tuple(_message_view(message) for message in messages),
            )

    def list_jobs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        kind: str | None = None,
    ) -> JobPage:
        _validate_page(limit, offset)
        filters: list[ColumnElement[bool]] = []
        if status is not None:
            filters.append(IngestionJob.status == status)
        if kind is not None:
            filters.append(IngestionJob.kind == kind)

        with self.session_factory() as db:
            total_query = select(func.count(IngestionJob.id))
            if filters:
                total_query = total_query.where(*filters)
            total = int(db.scalar(total_query) or 0)
            query = (
                select(IngestionJob, Source.source_type)
                .outerjoin(Source)
                .order_by(IngestionJob.created_at.desc(), IngestionJob.id)
                .limit(limit)
                .offset(offset)
            )
            if filters:
                query = query.where(*filters)
            rows = db.execute(query).all()

        return JobPage(
            items=tuple(_job_summary(job, source_type) for job, source_type in rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_job(self, job_id: str) -> JobDetail | None:
        with self.session_factory() as db:
            row = db.execute(
                select(IngestionJob, Source.source_type)
                .outerjoin(Source)
                .where(IngestionJob.id == job_id)
            ).one_or_none()
            if row is None:
                return None
            job, source_type = row
            errors = db.scalars(
                select(IngestionError)
                .where(IngestionError.job_id == job.id)
                .order_by(IngestionError.created_at, IngestionError.id)
            ).all()
            return JobDetail(
                summary=_job_summary(job, source_type),
                checkpoint=dict(job.checkpoint or {}),
                errors=tuple(
                    IngestionErrorView(
                        id=error.id,
                        stage=error.stage,
                        error_type=error.error_type,
                        safe_summary=error.safe_summary,
                        raw_locator=dict(error.raw_locator or {}),
                        created_at=error.created_at,
                    )
                    for error in errors
                ),
            )


def _validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if offset < 0:
        raise ValueError("offset must not be negative")


def _message_view(message: Message) -> MessageView:
    return MessageView(
        id=message.id,
        external_id=message.external_id,
        parent_external_id=message.parent_external_id,
        role=message.role,
        content_type=message.content_type,
        redacted_text=message.redacted_text,
        sensitivity=message.sensitivity,
        source_timestamp=message.source_timestamp,
        sequence=message.sequence,
        raw_locator=dict(message.raw_locator or {}),
        parse_warnings=list(message.parse_warnings or []),
    )


def _job_summary(job: IngestionJob, source_type: str | None) -> JobSummary:
    return JobSummary(
        id=job.id,
        source_type=source_type,
        kind=job.kind,
        status=job.status,
        stage=job.stage,
        counts=dict(job.counts or {}),
        retry_count=job.retry_count,
        error_summary=job.error_summary,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
