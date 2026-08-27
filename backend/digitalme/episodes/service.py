"""Deterministic session segmentation and episode browsing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from digitalme.models import (
    Episode,
    EpisodeMessage,
    MemoryCandidate,
    Message,
    SessionRecord,
    Source,
)

SEGMENTATION_PIPELINE_VERSION = "segment-v1"
DEFAULT_MAX_MESSAGES = 24
DEFAULT_GAP = timedelta(minutes=90)


@dataclass(frozen=True, slots=True)
class EpisodeBuildResult:
    session_id: str
    pipeline_version: str
    episodes_created: int
    messages_linked: int


@dataclass(frozen=True, slots=True)
class EpisodeRebuildResult:
    pipeline_version: str
    sessions_processed: int
    episodes_created: int
    messages_linked: int


@dataclass(frozen=True, slots=True)
class EpisodeSummary:
    id: str
    session_id: str
    source_type: str
    pipeline_version: str
    segment_index: int
    episode_type: str
    title: str
    summary: str | None
    start_at: datetime | None
    end_at: datetime | None
    extraction_status: str
    message_count: int


@dataclass(frozen=True, slots=True)
class EpisodePage:
    items: tuple[EpisodeSummary, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class EpisodeMessageView:
    id: str
    position: int
    role: str | None
    redacted_text: str | None
    sensitivity: str
    source_timestamp: datetime | None
    raw_locator: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EpisodeDetail:
    id: str
    session_id: str
    session_external_id: str
    source_type: str
    pipeline_version: str
    segment_index: int
    episode_type: str
    title: str
    summary: str | None
    start_at: datetime | None
    end_at: datetime | None
    extraction_status: str
    projects: tuple[str, ...]
    decisions: tuple[str, ...]
    open_questions: tuple[str, ...]
    messages: tuple[EpisodeMessageView, ...]


class EpisodeService:
    """Build versioned deterministic segments and expose their safe evidence views."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def rebuild_session(
        self,
        session_id: str,
        *,
        pipeline_version: str = SEGMENTATION_PIPELINE_VERSION,
        max_messages: int = DEFAULT_MAX_MESSAGES,
        gap: timedelta = DEFAULT_GAP,
    ) -> EpisodeBuildResult:
        if max_messages < 1:
            raise ValueError("max_messages must be positive")
        if gap <= timedelta(0):
            raise ValueError("gap must be positive")

        with self.session_factory.begin() as db:
            session = db.get(SessionRecord, session_id)
            if session is None:
                raise LookupError("Session not found")
            messages = db.scalars(select(Message).where(Message.session_id == session.id)).all()
            ordered = _selected_branch_messages(session, messages)
            eligible = [message for message in ordered if message.redacted_text]
            segments = _segment_messages(eligible, max_messages=max_messages, gap=gap)

            protected_memories = int(
                db.scalar(
                    select(func.count(MemoryCandidate.id))
                    .join(Episode, MemoryCandidate.episode_id == Episode.id)
                    .where(
                        Episode.session_id == session.id,
                        Episode.pipeline_version == pipeline_version,
                        MemoryCandidate.status.in_(["confirmed", "rejected"]),
                    )
                )
                or 0
            )
            if protected_memories:
                raise ValueError(
                    "Cannot rebuild Episodes with confirmed or rejected Memory Candidates"
                )

            db.execute(
                delete(Episode).where(
                    Episode.session_id == session.id,
                    Episode.pipeline_version == pipeline_version,
                )
            )
            db.flush()
            for segment_index, segment in enumerate(segments):
                timestamps = [
                    message.source_timestamp
                    for message in segment
                    if message.source_timestamp is not None
                ]
                episode = Episode(
                    session_id=session.id,
                    pipeline_version=pipeline_version,
                    segment_index=segment_index,
                    episode_type="conversation_segment",
                    title=_segment_title(session, segment, segment_index, len(segments)),
                    summary=None,
                    start_at=timestamps[0] if timestamps else session.source_created_at,
                    end_at=timestamps[-1] if timestamps else session.source_updated_at,
                    extraction_status="segmented",
                )
                db.add(episode)
                db.flush()
                db.add_all(
                    EpisodeMessage(
                        episode_id=episode.id,
                        message_id=message.id,
                        position=position,
                    )
                    for position, message in enumerate(segment)
                )
            return EpisodeBuildResult(
                session_id=session.id,
                pipeline_version=pipeline_version,
                episodes_created=len(segments),
                messages_linked=sum(len(segment) for segment in segments),
            )

    def rebuild_all(
        self,
        *,
        pipeline_version: str = SEGMENTATION_PIPELINE_VERSION,
    ) -> EpisodeRebuildResult:
        with self.session_factory() as db:
            session_ids = db.scalars(
                select(SessionRecord.id).order_by(SessionRecord.created_at, SessionRecord.id)
            ).all()
        results = [
            self.rebuild_session(session_id, pipeline_version=pipeline_version)
            for session_id in session_ids
        ]
        return EpisodeRebuildResult(
            pipeline_version=pipeline_version,
            sessions_processed=len(results),
            episodes_created=sum(result.episodes_created for result in results),
            messages_linked=sum(result.messages_linked for result in results),
        )

    def list_episodes(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        session_id: str | None = None,
        source_type: str | None = None,
        pipeline_version: str = SEGMENTATION_PIPELINE_VERSION,
    ) -> EpisodePage:
        _validate_page(limit, offset)
        filters = [Episode.pipeline_version == pipeline_version]
        if session_id is not None:
            filters.append(Episode.session_id == session_id)
        if source_type is not None:
            filters.append(Source.source_type == source_type)
        with self.session_factory() as db:
            total = int(
                db.scalar(
                    select(func.count(Episode.id))
                    .select_from(Episode)
                    .join(SessionRecord, Episode.session_id == SessionRecord.id)
                    .join(Source, SessionRecord.source_id == Source.id)
                    .where(*filters)
                )
                or 0
            )
            rows = db.execute(
                select(Episode, Source.source_type, func.count(EpisodeMessage.message_id))
                .select_from(Episode)
                .join(SessionRecord, Episode.session_id == SessionRecord.id)
                .join(Source, SessionRecord.source_id == Source.id)
                .outerjoin(EpisodeMessage, EpisodeMessage.episode_id == Episode.id)
                .where(*filters)
                .group_by(Episode.id, Source.source_type)
                .order_by(Episode.start_at.desc(), Episode.created_at.desc(), Episode.id)
                .limit(limit)
                .offset(offset)
            ).all()
        return EpisodePage(
            items=tuple(
                _episode_summary(episode, row_source_type, int(message_count))
                for episode, row_source_type, message_count in rows
            ),
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_episode(self, episode_id: str) -> EpisodeDetail | None:
        with self.session_factory() as db:
            row = db.execute(
                select(Episode, SessionRecord.external_id, Source.source_type)
                .select_from(Episode)
                .join(SessionRecord, Episode.session_id == SessionRecord.id)
                .join(Source, SessionRecord.source_id == Source.id)
                .where(Episode.id == episode_id)
            ).one_or_none()
            if row is None:
                return None
            episode, session_external_id, source_type = row
            message_rows = db.execute(
                select(EpisodeMessage.position, Message)
                .select_from(EpisodeMessage)
                .join(Message, EpisodeMessage.message_id == Message.id)
                .where(EpisodeMessage.episode_id == episode.id)
                .order_by(EpisodeMessage.position)
            ).all()
            return EpisodeDetail(
                id=episode.id,
                session_id=episode.session_id,
                session_external_id=session_external_id,
                source_type=source_type,
                pipeline_version=episode.pipeline_version,
                segment_index=episode.segment_index,
                episode_type=episode.episode_type,
                title=episode.title,
                summary=episode.summary,
                start_at=episode.start_at,
                end_at=episode.end_at,
                extraction_status=episode.extraction_status,
                projects=tuple(episode.projects or []),
                decisions=tuple(episode.decisions or []),
                open_questions=tuple(episode.open_questions or []),
                messages=tuple(
                    EpisodeMessageView(
                        id=message.id,
                        position=position,
                        role=message.role,
                        redacted_text=message.redacted_text,
                        sensitivity=message.sensitivity,
                        source_timestamp=message.source_timestamp,
                        raw_locator=dict(message.raw_locator or {}),
                    )
                    for position, message in message_rows
                ),
            )


def _selected_branch_messages(
    session: SessionRecord,
    messages: Sequence[Message],
) -> list[Message]:
    ordered = sorted(messages, key=_message_sort_key)
    head = session.selected_branch_head_external_id
    if head is None:
        return ordered
    by_external_id = {message.external_id: message for message in messages}
    branch: list[Message] = []
    seen: set[str] = set()
    cursor = head
    while cursor not in seen:
        seen.add(cursor)
        message = by_external_id.get(cursor)
        if message is None:
            break
        branch.append(message)
        if message.parent_external_id is None:
            break
        cursor = message.parent_external_id
    return list(reversed(branch)) if branch else ordered


def _segment_messages(
    messages: list[Message],
    *,
    max_messages: int,
    gap: timedelta,
) -> list[list[Message]]:
    segments: list[list[Message]] = []
    current: list[Message] = []
    previous_timestamp: datetime | None = None
    for message in messages:
        starts_new_segment = bool(current) and (
            len(current) >= max_messages
            or _has_time_gap(previous_timestamp, message.source_timestamp, gap)
            or _is_explicit_topic_boundary(message)
        )
        if starts_new_segment:
            segments.append(current)
            current = []
        current.append(message)
        if message.source_timestamp is not None:
            previous_timestamp = message.source_timestamp
    if current:
        segments.append(current)
    return segments


def _message_sort_key(message: Message) -> tuple[bool, int, str, str]:
    return (
        message.sequence is None,
        message.sequence or 0,
        message.source_timestamp.isoformat() if message.source_timestamp is not None else "",
        message.id,
    )


def _has_time_gap(
    previous: datetime | None,
    current: datetime | None,
    gap: timedelta,
) -> bool:
    if previous is None or current is None:
        return False
    return _as_utc_naive(current) - _as_utc_naive(previous) > gap


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _is_explicit_topic_boundary(message: Message) -> bool:
    if message.role != "user" or message.redacted_text is None:
        return False
    text = message.redacted_text.strip().casefold()
    return text.startswith(("[new topic]", "new topic:", "新话题：", "新话题:"))


def _segment_title(
    session: SessionRecord,
    messages: list[Message],
    segment_index: int,
    segment_count: int,
) -> str:
    first_user_text = next(
        (
            message.redacted_text.strip()
            for message in messages
            if message.role == "user" and message.redacted_text
        ),
        "",
    )
    base = session.title or first_user_text[:80] or "Untitled session"
    return f"{base} · Part {segment_index + 1}" if segment_count > 1 else base


def _episode_summary(
    episode: Episode,
    source_type: str,
    message_count: int,
) -> EpisodeSummary:
    return EpisodeSummary(
        id=episode.id,
        session_id=episode.session_id,
        source_type=source_type,
        pipeline_version=episode.pipeline_version,
        segment_index=episode.segment_index,
        episode_type=episode.episode_type,
        title=episode.title,
        summary=episode.summary,
        start_at=episode.start_at,
        end_at=episode.end_at,
        extraction_status=episode.extraction_status,
        message_count=message_count,
    )


def _validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if offset < 0:
        raise ValueError("offset must not be negative")
