import json
import zipfile
from pathlib import Path

import httpx
import pytest
from digitalme.api.app import create_app
from digitalme.config import Settings, get_settings
from digitalme.db.base import Base
from digitalme.db.session import create_engine, create_session_factory
from digitalme.ingestion.chatgpt import ChatGPTImporter
from digitalme.ingestion.common import ArtifactStore
from digitalme.models import Message
from sqlalchemy import select


@pytest.mark.asyncio
async def test_health() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


@pytest.mark.asyncio
async def test_archive_api_paginates_and_never_exposes_normalized_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "export.zip"
    fake_secret = "sk-" + "abcdefghijklmnopqrstuvwxyz" + "123456"
    _write_export(archive_path, fake_secret)
    settings = _configure_test_settings(tmp_path, monkeypatch)
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    importer = ChatGPTImporter(
        create_session_factory(engine),
        ArtifactStore(settings.raw_store_path),
    )
    imported = importer.import_zip(archive_path)
    factory = create_session_factory(engine)
    with factory.begin() as db:
        safe_message = db.scalar(select(Message).where(Message.external_id == "message-safe"))
        assert safe_message is not None
        safe_message.normalized_text = f"unclassified {fake_secret}"
        safe_message.redacted_text = None
        safe_message.sensitivity = "unclassified"
    engine.dispose()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_page = await client.get("/api/v1/sessions", params={"limit": 1})
        assert first_page.status_code == 200
        first_payload = first_page.json()
        assert first_payload["total"] == 2
        assert first_payload["limit"] == 1
        assert len(first_payload["items"]) == 1

        second_page = await client.get("/api/v1/sessions", params={"limit": 1, "offset": 1})
        assert second_page.status_code == 200
        assert second_page.json()["total"] == 2
        assert second_page.json()["items"][0]["id"] != first_payload["items"][0]["id"]

        filtered = await client.get("/api/v1/sessions", params={"source_type": "codex"})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 0

        future = await client.get(
            "/api/v1/sessions",
            params={"updated_after": "2030-01-01T00:00:00Z"},
        )
        assert future.status_code == 200
        assert future.json()["total"] == 0

        all_sessions = await client.get("/api/v1/sessions", params={"limit": 20})
        secret_summary = next(
            item for item in all_sessions.json()["items"] if item["title"] == "Secret fixture"
        )
        detail = await client.get(f"/api/v1/sessions/{secret_summary['id']}")
        assert detail.status_code == 200
        message = detail.json()["messages"][0]
        assert message["redacted_text"] == "API_KEY=[REDACTED:credential_assignment]"
        assert message["sensitivity"] == "secret"
        assert "normalized_text" not in message
        assert fake_secret not in detail.text

        safe_summary = next(
            item for item in all_sessions.json()["items"] if item["title"] == "Safe fixture"
        )
        safe_detail = await client.get(f"/api/v1/sessions/{safe_summary['id']}")
        assert safe_detail.status_code == 200
        assert safe_detail.json()["messages"][0]["redacted_text"] is None
        assert "normalized_text" not in safe_detail.json()["messages"][0]
        assert fake_secret not in safe_detail.text

        missing = await client.get("/api/v1/sessions/ses_missing")
        assert missing.status_code == 404

        jobs = await client.get("/api/v1/jobs", params={"status": "completed"})
        assert jobs.status_code == 200
        assert jobs.json()["total"] == 1
        assert jobs.json()["items"][0]["id"] == imported.job_id
        job = await client.get(f"/api/v1/jobs/{imported.job_id}")
        assert job.status_code == 200
        assert job.json()["summary"]["counts"]["redactions"] == 1
        assert fake_secret not in job.text

    get_settings.cache_clear()


def _configure_test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv(
        "DIGITALME_DATABASE_URL",
        f"sqlite:///{tmp_path / 'digitalme.db'}",
    )
    monkeypatch.setenv("DIGITALME_RAW_STORE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()
    return get_settings()


def _write_export(path: Path, fake_secret: str) -> None:
    conversations = [
        {
            "id": "secret-conversation",
            "title": "Secret fixture",
            "create_time": 1_700_000_000,
            "update_time": 1_700_000_100,
            "mapping": {
                "message-secret": {
                    "parent": None,
                    "message": {
                        "author": {"role": "user"},
                        "content": {
                            "content_type": "text",
                            "parts": [f"API_KEY={fake_secret}"],
                        },
                    },
                }
            },
        },
        {
            "id": "safe-conversation",
            "title": "Safe fixture",
            "create_time": 1_700_000_200,
            "update_time": 1_700_000_300,
            "mapping": {
                "message-safe": {
                    "parent": None,
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["Safe content"]},
                    },
                }
            },
        },
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("conversations.json", json.dumps(conversations))
