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
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("API_BASE_URL", "")
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
    assert "\tchatgpt\t" in listed.output
    assert "\t1\tCLI fixture" in listed.output

    session_id = listed.output.splitlines()[0].split("\t")[0]
    shown = runner.invoke(app, ["sessions", "show", session_id])
    assert shown.exit_code == 0, shown.output
    assert '"redacted_text": "Hello"' in shown.output
    assert "normalized_text" not in shown.output

    jobs = runner.invoke(app, ["jobs", "list"])
    assert jobs.exit_code == 0, jobs.output
    assert "\tcompleted\tcompleted\tchatgpt_export" in jobs.output
    job_id = jobs.output.splitlines()[0].split("\t")[0]
    inspected = runner.invoke(app, ["jobs", "inspect", job_id])
    assert inspected.exit_code == 0, inspected.output
    assert '"status": "completed"' in inspected.output
    assert "Hello" not in inspected.output

    rebuilt = runner.invoke(app, ["episodes", "rebuild"])
    assert rebuilt.exit_code == 0, rebuilt.output
    assert '"episodes_created": 1' in rebuilt.output
    episodes = runner.invoke(app, ["episodes", "list"])
    assert episodes.exit_code == 0, episodes.output
    assert "CLI fixture" in episodes.output
    episode_id = episodes.output.splitlines()[0].split("\t")[0]
    episode = runner.invoke(app, ["episodes", "show", episode_id])
    assert episode.exit_code == 0, episode.output
    assert '"redacted_text": "Hello"' in episode.output
    assert "normalized_text" not in episode.output
    extraction = runner.invoke(app, ["memories", "extract", episode_id])
    assert extraction.exit_code == 2
    assert "No model provider is configured" in extraction.output
    memories = runner.invoke(app, ["memories", "list"])
    assert memories.exit_code == 0
    assert "No memory candidates found" in memories.output
    retrieval = runner.invoke(app, ["retrieve", "Hello"])
    assert retrieval.exit_code == 0
    assert "No relevant confirmed memories found" in retrieval.output
    ask = runner.invoke(app, ["ask", "Hello"])
    assert ask.exit_code == 2
    assert "No model provider is configured" in ask.output
    get_settings.cache_clear()


def test_codex_scan_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "digitalme.db"
    rollout = tmp_path / "codex" / "sessions" / "2026" / "rollout-cli.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"id": "codex-cli", "cwd": "D:/DigitalMe"},
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "Prototype"}],
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DIGITALME_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("DIGITALME_RAW_STORE_PATH", str(tmp_path / "raw"))
    monkeypatch.setenv("DIGITALME_CODEX_HOME", str(tmp_path / "codex"))
    get_settings.cache_clear()
    runner = CliRunner()

    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0
    imported = runner.invoke(app, ["ingest", "codex"])
    assert imported.exit_code == 0, imported.output
    assert "files_scanned=1" in imported.output
    assert "sessions_created=1" in imported.output
    listed = runner.invoke(app, ["sessions", "list", "--source-type", "codex"])
    assert listed.exit_code == 0, listed.output
    assert "\tcodex\t" in listed.output
    assert "DigitalMe" in listed.output
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
