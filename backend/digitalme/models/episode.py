"""Deterministic episodic-memory models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from digitalme.db.base import Base, TimestampMixin
from digitalme.models.archive import new_id


class Episode(TimestampMixin, Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "pipeline_version",
            "segment_index",
            name="uq_episodes_session_pipeline_segment",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ep"))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    pipeline_version: Mapped[str] = mapped_column(String(64), index=True)
    segment_index: Mapped[int] = mapped_column(Integer)
    episode_type: Mapped[str] = mapped_column(String(64), default="conversation_segment")
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_status: Mapped[str] = mapped_column(String(32), default="segmented", index=True)
    projects: Mapped[list[str]] = mapped_column(JSON, default=list)
    decisions: Mapped[list[str]] = mapped_column(JSON, default=list)
    open_questions: Mapped[list[str]] = mapped_column(JSON, default=list)

    message_links: Mapped[list[EpisodeMessage]] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="EpisodeMessage.position",
    )


class EpisodeMessage(Base):
    __tablename__ = "episode_messages"
    __table_args__ = (
        UniqueConstraint("episode_id", "position", name="uq_episode_messages_position"),
    )

    episode_id: Mapped[str] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer)

    episode: Mapped[Episode] = relationship(back_populates="message_links")
