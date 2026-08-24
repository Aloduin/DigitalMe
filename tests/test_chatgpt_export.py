import json
import zipfile
from pathlib import Path

import pytest
from digitalme.ingestion.chatgpt.export import (
    UnsafeChatGPTExportError,
    discover_conversation_documents,
)


def test_discovers_multiple_conversation_documents(tmp_path: Path) -> None:
    archive_path = tmp_path / "export.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("conversations.json", json.dumps([{"id": "one", "mapping": {}}]))
        archive.writestr("nested/conversations-1.json", json.dumps([{"id": "two", "mapping": {}}]))
        archive.writestr("user.json", "{}")

    documents = discover_conversation_documents(archive_path)

    assert [document.member_name for document in documents] == [
        "conversations.json",
        "nested/conversations-1.json",
    ]
    assert [item["id"] for document in documents for item in document.conversations] == [
        "one",
        "two",
    ]


def test_rejects_archive_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../conversations.json", "[]")

    with pytest.raises(UnsafeChatGPTExportError, match="Unsafe archive member path"):
        discover_conversation_documents(archive_path)


def test_rejects_export_without_conversations(tmp_path: Path) -> None:
    archive_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("user.json", "{}")

    with pytest.raises(UnsafeChatGPTExportError, match="No conversation JSON"):
        discover_conversation_documents(archive_path)
