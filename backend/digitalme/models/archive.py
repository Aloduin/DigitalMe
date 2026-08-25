"""Core historical archive models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from digitalme.db.base import Base, TimestampMixin, utc_now


def new_id(prefix: str) -> str:
    """Generate an opaque application ID without exposing upstream identifiers."""

    return f"{prefix}_{uuid4().hex}"


class SourceType(StrEnum):
    CHATGPT = "chatgpt"
    CODEX = "codex"
    CHATGPT_MEMORY = "chatgpt_memory"
    CODEX_MEMORY = "codex_memory"


class IngestionJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageSensitivity(StrEnum):
    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"
    UNCLASSIFIED = "unclassified"


class Source(TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("source_type", "name", name="uq_sources_type_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("src"))
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    root_uri: Mapped[str | None] = mapped_column(Text)
    external_account_id: Mapped[str | None] = mapped_column(String(255))

    artifacts: Mapped[list[Artifact]] = relationship(back_populates="source")
    sessions: Mapped[list[SessionRecord]] = relationship(back_populates="source")
    jobs: Mapped[list[IngestionJob]] = relationship(back_populates="source")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("art"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    relative_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    source: Mapped[Source] = relationship(back_populates="artifacts")
    sessions: Mapped[list[SessionRecord]] = relationship(back_populates="artifact")


class SessionRecord(TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "external_id", "schema_version", name="uq_sessions_external_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ses"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(512))
    schema_version: Mapped[int] = mapped_column(default=1)
    title: Mapped[str | None] = mapped_column(Text)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_branch_head_external_id: Mapped[str | None] = mapped_column(String(512))
    parse_warnings: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)

    source: Mapped[Source] = relationship(back_populates="sessions")
    artifact: Mapped[Artifact | None] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("session_id", "external_id", name="uq_messages_session_external"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("msg"))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(512))
    parent_external_id: Mapped[str | None] = mapped_column(String(512), index=True)
    role: Mapped[str | None] = mapped_column(String(64), index=True)
    content_type: Mapped[str] = mapped_column(String(64), default="text")
    normalized_text: Mapped[str | None] = mapped_column(Text)
    redacted_text: Mapped[str | None] = mapped_column(Text)
    redaction_spans: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    sensitivity: Mapped[str] = mapped_column(
        String(32), default=MessageSensitivity.UNCLASSIFIED.value, index=True
    )
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sequence: Mapped[int | None]
    raw_locator: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    parse_warnings: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)

    session: Mapped[SessionRecord] = relationship(back_populates="messages")


class IngestionJob(TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("job"))
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=IngestionJobStatus.PENDING.value, index=True
    )
    stage: Mapped[str | None] = mapped_column(String(64))
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    retry_count: Mapped[int] = mapped_column(default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source | None] = relationship(back_populates="jobs")
    errors: Mapped[list[IngestionError]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class IngestionError(Base):
    __tablename__ = "ingestion_errors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("err"))
    job_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(64))
    error_type: Mapped[str] = mapped_column(String(255))
    safe_summary: Mapped[str] = mapped_column(Text)
    raw_locator: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    job: Mapped[IngestionJob] = relationship(back_populates="errors")
