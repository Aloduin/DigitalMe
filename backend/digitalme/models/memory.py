"""Evidence-linked memory candidates for the MVP extraction flow."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from digitalme.db.base import Base, TimestampMixin
from digitalme.models.archive import new_id


class MemoryCandidate(TimestampMixin, Base):
    __tablename__ = "memory_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mc"))
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    extractor_version: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    candidate_type: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(255), default="global", index=True)
    confidence: Mapped[float] = mapped_column(Float)
    salience: Mapped[float] = mapped_column(Float)
    evidence_strength: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    sensitivity: Mapped[str] = mapped_column(String(32), index=True)

    evidence_links: Mapped[list[CandidateEvidence]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )


class CandidateEvidence(Base):
    __tablename__ = "candidate_evidence"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("memory_candidates.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    quote_snapshot: Mapped[str] = mapped_column(Text)

    candidate: Mapped[MemoryCandidate] = relationship(back_populates="evidence_links")
