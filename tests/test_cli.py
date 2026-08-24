import json
import zipfile
from pathlib import Path

import pytest
from digitalme.cli import app
from digitalme.config import get_settings
from typer.testing import CliRunner


def test_chatgpt_import_and_session_list_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "digitalme.db"
    raw_store_path = tmp_path / "raw"
    archive_path = tmp_path / "export.zip"
    _write_minimal_export(archive_path)

    monkeypatch.setenv("DIGITALME_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("DIGITALME_RAW_STORE_PATH", str(raw_store_path))
    get_settings.cache_clear()
    runner = CliRunner()

    migration = runner.invoke(app, ["db", "upgrade"])
    assert migration.exit_code == 0, migration.output

    imported = runner.invoke(app, ["ingest", "chatgpt", str(archive_path)])
    assert imported.exit_code == 0, imported.output
    assert "sessions_created=1" in imported.output
    assert "messages_created=1" in imported.output

    listed = runner.invoke(app, ["sessions", "list"])
    assert listed.exit_code == 0, listed.output
    assert "CLI fixture" in listed.output
    assert "\t1\t" in listed.output
    get_settings.cache_clear()


def _write_minimal_export(path: Path) -> None:
    conversation = {
        "id": "cli-conversation",
        "title": "CLI fixture",
        "mapping": {
            "message-1": {
                "parent": None,
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Hello"]},
                },
            }
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("conversations.json", json.dumps([conversation]))
