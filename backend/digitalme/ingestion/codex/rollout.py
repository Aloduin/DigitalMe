"""Tolerant, streaming adapter for the small Codex prototype surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from digitalme.ingestion.common.schema import CanonicalMessage, CanonicalSession, ParseWarning


@dataclass(frozen=True, slots=True)
class _MessageCandidate:
    line: int
    priority: int
    message: CanonicalMessage


def discover_rollouts(codex_home: Path) -> list[Path]:
    """Find active and archived rollout JSONL files without following unrelated roots."""

    home = codex_home.expanduser().resolve()
    found: set[Path] = set()
    for directory_name in ("sessions", "archived_sessions"):
        root = home / directory_name
        if root.is_dir():
            found.update(path.resolve() for path in root.rglob("rollout-*.jsonl") if path.is_file())
    return sorted(found)


def adapt_rollout(path: Path) -> CanonicalSession:
    """Convert user/assistant messages while retaining line-level provenance and warnings."""

    path = path.expanduser().resolve(strict=True)
    external_id: str | None = None
    cwd: str | None = None
    timestamps: list[datetime] = []
    warnings: list[ParseWarning] = []
    candidates: list[_MessageCandidate] = []
    known_outer_types = {"session_meta", "turn_context", "event_msg", "response_item"}

    with path.open("r", encoding="utf-8", errors="replace") as rollout:
        for line_number, raw_line in enumerate(rollout, start=1):
            if not raw_line.strip():
                continue
            locator = {"path": str(path), "line": line_number}
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                warnings.append(
                    ParseWarning(
                        code="invalid_jsonl_line",
                        message="Skipped malformed JSONL line",
                        locator=locator,
                    )
                )
                continue
            if not isinstance(event, dict):
                continue
            event_type = _text(event.get("type"))
            payload = event.get("payload")
            timestamp = _timestamp(event.get("timestamp"))
            if timestamp is not None:
                timestamps.append(timestamp)
            if event_type == "session_meta" and isinstance(payload, dict):
                external_id = _text(payload.get("id")) or external_id
                cwd = _text(payload.get("cwd")) or cwd
            elif event_type == "response_item" and isinstance(payload, dict):
                message = _response_message(payload, line_number, timestamp, locator)
                if message is not None:
                    candidates.append(_MessageCandidate(line_number, 0, message))
            elif event_type == "event_msg" and isinstance(payload, dict):
                message = _fallback_event_message(payload, line_number, timestamp, locator)
                if message is not None:
                    candidates.append(_MessageCandidate(line_number, 1, message))
            elif event_type not in known_outer_types:
                warnings.append(
                    ParseWarning(
                        code="unknown_event_type",
                        message=f"Preserved unknown event type: {event_type or '(missing)'}",
                        locator=locator,
                    )
                )

    primary_fingerprints = {
        (candidate.message.role, candidate.message.normalized_text)
        for candidate in candidates
        if candidate.priority == 0
    }
    selected = [
        candidate
        for candidate in candidates
        if candidate.priority == 0
        or (candidate.message.role, candidate.message.normalized_text) not in primary_fingerprints
    ]
    selected.sort(key=lambda candidate: candidate.line)
    messages = [
        candidate.message.model_copy(update={"sequence": index})
        for index, candidate in enumerate(selected)
    ]
    first_user = next(
        (
            message.normalized_text
            for message in messages
            if message.role == "user" and message.normalized_text
        ),
        None,
    )
    title = Path(cwd).name if cwd else (first_user[:80] if first_user else path.stem)
    if external_id is None:
        external_id = path.stem
        warnings.append(
            ParseWarning(code="missing_session_meta", message="Used filename as session ID")
        )
    return CanonicalSession(
        external_id=external_id,
        title=title,
        source_created_at=min(timestamps) if timestamps else None,
        source_updated_at=max(timestamps) if timestamps else None,
        messages=messages,
        parse_warnings=warnings,
    )


def _response_message(
    payload: dict[str, Any], line: int, timestamp: datetime | None, locator: dict[str, Any]
) -> CanonicalMessage | None:
    if payload.get("type") != "message":
        return None
    role = _text(payload.get("role"))
    if role not in {"user", "assistant"}:
        return None
    text = _content_text(payload.get("content"))
    if not text:
        return None
    return CanonicalMessage(
        external_id=_text(payload.get("id")) or f"response-line-{line}",
        role=role,
        normalized_text=text,
        source_timestamp=timestamp,
        raw_locator=locator,
    )


def _fallback_event_message(
    payload: dict[str, Any], line: int, timestamp: datetime | None, locator: dict[str, Any]
) -> CanonicalMessage | None:
    payload_type = _text(payload.get("type"))
    role = {"user_message": "user", "agent_message": "assistant"}.get(payload_type or "")
    text = _text(payload.get("message"))
    if role is None or not text:
        return None
    return CanonicalMessage(
        external_id=f"event-line-{line}",
        role=role,
        normalized_text=text,
        source_timestamp=timestamp,
        raw_locator=locator,
    )


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts) if parts else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
