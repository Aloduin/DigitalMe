"""Safe discovery of conversation documents inside a ChatGPT export ZIP."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class UnsafeChatGPTExportError(ValueError):
    """Raised when an export violates archive safety constraints."""


@dataclass(frozen=True, slots=True)
class ExportLimits:
    max_archive_bytes: int = 2 * 1024 * 1024 * 1024
    max_member_bytes: int = 512 * 1024 * 1024
    max_total_uncompressed_bytes: int = 4 * 1024 * 1024 * 1024
    max_compression_ratio: int = 1_000


@dataclass(frozen=True, slots=True)
class ConversationDocument:
    member_name: str
    conversations: list[dict[str, Any]]


def discover_conversation_documents(
    archive_path: Path,
    limits: ExportLimits | None = None,
) -> list[ConversationDocument]:
    """Read recognized conversation JSON members without extracting the archive."""

    limits = limits or ExportLimits()
    archive_path = archive_path.expanduser().resolve(strict=True)
    if archive_path.stat().st_size > limits.max_archive_bytes:
        raise UnsafeChatGPTExportError("Archive exceeds the configured size limit")

    documents: list[ConversationDocument] = []
    total_uncompressed = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            for member in members:
                _validate_member(member, limits)
                total_uncompressed += member.file_size
                if total_uncompressed > limits.max_total_uncompressed_bytes:
                    raise UnsafeChatGPTExportError(
                        "Archive exceeds the total uncompressed size limit"
                    )

            for member in members:
                if member.is_dir() or not _is_conversation_member(member.filename):
                    continue
                with archive.open(member, "r") as stream:
                    try:
                        payload = json.load(stream)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise UnsafeChatGPTExportError(
                            f"Invalid conversation JSON in {member.filename!r}"
                        ) from exc
                documents.append(
                    ConversationDocument(
                        member_name=member.filename,
                        conversations=_normalize_conversation_payload(payload, member.filename),
                    )
                )
    except zipfile.BadZipFile as exc:
        raise UnsafeChatGPTExportError("Input is not a valid ZIP archive") from exc

    if not documents:
        raise UnsafeChatGPTExportError("No conversation JSON files were found in the export")
    return documents


def _validate_member(member: zipfile.ZipInfo, limits: ExportLimits) -> None:
    normalized_name = member.filename.replace("\\", "/")
    path = PurePosixPath(normalized_name)
    if path.is_absolute() or ".." in path.parts:
        raise UnsafeChatGPTExportError(f"Unsafe archive member path: {member.filename!r}")
    if member.flag_bits & 0x1:
        raise UnsafeChatGPTExportError(
            f"Encrypted archive member is unsupported: {member.filename!r}"
        )
    if member.file_size > limits.max_member_bytes:
        raise UnsafeChatGPTExportError(f"Archive member exceeds size limit: {member.filename!r}")
    if member.file_size and member.compress_size == 0:
        raise UnsafeChatGPTExportError(f"Invalid compression metadata: {member.filename!r}")
    if (
        member.compress_size
        and member.file_size / member.compress_size > limits.max_compression_ratio
    ):
        raise UnsafeChatGPTExportError(f"Suspicious compression ratio: {member.filename!r}")


def _is_conversation_member(name: str) -> bool:
    basename = PurePosixPath(name.replace("\\", "/")).name.lower()
    return basename.startswith("conversations") and basename.endswith(".json")


def _normalize_conversation_payload(payload: Any, member_name: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("conversations"), list):
        payload = payload["conversations"]
    elif isinstance(payload, dict) and "mapping" in payload:
        payload = [payload]
    if not isinstance(payload, list):
        raise UnsafeChatGPTExportError(
            f"Conversation document {member_name!r} must contain a JSON list"
        )
    conversations: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise UnsafeChatGPTExportError(
                f"Conversation {index} in {member_name!r} must be a JSON object"
            )
        conversations.append(item)
    return conversations
