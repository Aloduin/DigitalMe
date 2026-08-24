"""Adapter from ChatGPT export objects to the DigitalMe canonical schema."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from digitalme.ingestion.common.schema import (
    CanonicalMessage,
    CanonicalSession,
    ParseWarning,
)


def adapt_conversation(
    conversation: dict[str, Any],
    *,
    member_name: str,
    conversation_index: int,
) -> CanonicalSession:
    """Preserve every conversation-tree node, including non-message branch nodes."""

    warnings: list[ParseWarning] = []
    external_id = _string(conversation.get("id")) or _fallback_id(conversation)
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict):
        mapping = {}
        warnings.append(
            ParseWarning(code="missing_mapping", message="Conversation has no mapping object")
        )

    messages: list[CanonicalMessage] = []
    for sequence, (mapping_id, raw_node) in enumerate(mapping.items()):
        node_id = _string(mapping_id) or f"node-{sequence}"
        locator = {
            "member": member_name,
            "conversation_index": conversation_index,
            "node_id": node_id,
        }
        if not isinstance(raw_node, dict):
            messages.append(
                CanonicalMessage(
                    external_id=node_id,
                    content_type="invalid_node",
                    sequence=sequence,
                    raw_locator=locator,
                    parse_warnings=[
                        ParseWarning(
                            code="invalid_node",
                            message="Conversation mapping node is not an object",
                            locator=locator,
                        )
                    ],
                )
            )
            continue
        messages.append(_adapt_node(raw_node, node_id, sequence, locator))

    return CanonicalSession(
        external_id=external_id,
        title=_string(conversation.get("title")),
        source_created_at=_timestamp(conversation.get("create_time")),
        source_updated_at=_timestamp(conversation.get("update_time")),
        selected_branch_head_external_id=_string(conversation.get("current_node")),
        messages=messages,
        parse_warnings=warnings,
    )


def _adapt_node(
    node: dict[str, Any],
    node_id: str,
    sequence: int,
    locator: dict[str, Any],
) -> CanonicalMessage:
    raw_message = node.get("message")
    parent_external_id = _string(node.get("parent"))
    if not isinstance(raw_message, dict):
        return CanonicalMessage(
            external_id=node_id,
            parent_external_id=parent_external_id,
            content_type="empty_node",
            sequence=sequence,
            raw_locator=locator,
        )

    author = raw_message.get("author")
    role = _string(author.get("role")) if isinstance(author, dict) else None
    content = raw_message.get("content")
    content_type = "unknown"
    normalized_text: str | None = None
    warnings: list[ParseWarning] = []
    if isinstance(content, dict):
        content_type = _string(content.get("content_type")) or "unknown"
        normalized_text, content_warnings = _normalize_parts(content.get("parts"), locator)
        warnings.extend(content_warnings)
    else:
        warnings.append(
            ParseWarning(
                code="missing_content",
                message="Message has no recognized content object",
                locator=locator,
            )
        )

    return CanonicalMessage(
        external_id=node_id,
        parent_external_id=parent_external_id,
        role=role,
        content_type=content_type,
        normalized_text=normalized_text,
        source_timestamp=_timestamp(raw_message.get("create_time")),
        sequence=sequence,
        raw_locator=locator,
        parse_warnings=warnings,
    )


def _normalize_parts(
    raw_parts: Any,
    locator: dict[str, Any],
) -> tuple[str | None, list[ParseWarning]]:
    if not isinstance(raw_parts, list):
        return None, [
            ParseWarning(
                code="missing_parts",
                message="Message content has no parts list",
                locator=locator,
            )
        ]
    text_parts: list[str] = []
    unsupported_count = 0
    for part in raw_parts:
        if isinstance(part, str):
            text_parts.append(part)
        elif isinstance(part, dict) and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
        else:
            unsupported_count += 1
    warnings = []
    if unsupported_count:
        warnings.append(
            ParseWarning(
                code="unsupported_content_parts",
                message=f"Skipped {unsupported_count} non-text content part(s)",
                locator=locator,
            )
        )
    return "\n".join(text_parts) if text_parts else None, warnings


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _fallback_id(conversation: dict[str, Any]) -> str:
    serialized = json.dumps(conversation, sort_keys=True, ensure_ascii=False, default=str)
    return f"missing-{hashlib.sha256(serialized.encode()).hexdigest()}"
