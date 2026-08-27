import asyncio
import json
import zipfile
from pathlib import Path
from typing import Any, cast

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
async def test_prototype_ui_is_served_with_safe_dynamic_rendering() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "object-src 'none'" in response.headers["content-security-policy"]
    assert "DigitalMe" in response.text
    assert "/api/v1/ingest/chatgpt" in response.text
    assert "/api/v1/episodes/rebuild" in response.text
    assert "/api/v1/memories" in response.text
    assert "/api/v1/retrieve" in response.text
    assert "/api/v1/ask" in response.text
    assert "textContent" in response.text
    assert "innerHTML" not in response.text


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

        rebuilt = await client.post("/api/v1/episodes/rebuild")
        assert rebuilt.status_code == 200
        assert rebuilt.json()["sessions_processed"] == 2
        assert rebuilt.json()["episodes_created"] == 1
        episodes = await client.get("/api/v1/episodes")
        assert episodes.status_code == 200
        assert episodes.json()["total"] == 1
        episode_detail = await client.get(f"/api/v1/episodes/{episodes.json()['items'][0]['id']}")
        assert episode_detail.status_code == 200
        assert "normalized_text" not in episode_detail.text
        assert fake_secret not in episode_detail.text

        extraction = await client.post(
            f"/api/v1/episodes/{episodes.json()['items'][0]['id']}/extract"
        )
        assert extraction.status_code == 503
        memories = await client.get("/api/v1/memories")
        assert memories.status_code == 200
        assert memories.json()["total"] == 0
        retrieval = await client.post("/api/v1/retrieve", json={"query": "Hello"})
        assert retrieval.status_code == 200
        assert retrieval.json()["hits"] == []
        ask = await client.post("/api/v1/ask", json={"query": "Hello"})
        assert ask.status_code == 503

        missing_episode_rebuild = await client.post(
            "/api/v1/episodes/rebuild",
            params={"session_id": "ses_missing"},
        )
        assert missing_episode_rebuild.status_code == 404

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


@pytest.mark.asyncio
async def test_chatgpt_ingest_api_queues_completes_and_cleans_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "export.zip"
    _write_export(archive_path, "safe-test-value")
    settings = _configure_test_settings(tmp_path, monkeypatch)
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post(
            "/api/v1/ingest/chatgpt",
            content=archive_path.read_bytes(),
            headers={"Content-Type": "application/zip"},
        )

        assert accepted.status_code == 202
        payload = accepted.json()
        assert payload["status"] == "pending"
        assert payload["detail_url"] == f"/api/v1/jobs/{payload['job_id']}"
        assert accepted.headers["Location"] == payload["detail_url"]

        job_payload = await _wait_for_terminal_job(client, payload["job_id"])
        assert job_payload["summary"]["status"] == "completed"
        assert job_payload["summary"]["counts"]["sessions_created"] == 2
        sessions = await client.get("/api/v1/sessions")
        assert sessions.status_code == 200
        assert sessions.json()["total"] == 2

    assert list(settings.incoming_path.glob("*")) == []
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_chatgpt_ingest_api_records_invalid_zip_failure_and_cleans_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_test_settings(tmp_path, monkeypatch)
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post(
            "/api/v1/ingest/chatgpt",
            content=b"not a zip",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert accepted.status_code == 202
        job = await _wait_for_terminal_job(client, accepted.json()["job_id"])
        assert job["summary"]["status"] == "failed"
        assert job["summary"]["stage"] == "parse"
        assert job["summary"]["error_summary"] == (
            "UnsafeChatGPTExportError: Input is not a valid ZIP archive"
        )

    assert list(settings.incoming_path.glob("*")) == []
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_chatgpt_ingest_api_rejects_unsupported_empty_and_oversized_bodies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGITALME_MAX_UPLOAD_BYTES", "4")
    settings = _configure_test_settings(tmp_path, monkeypatch)
    engine = create_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unsupported = await client.post(
            "/api/v1/ingest/chatgpt",
            content=b"zip",
            headers={"Content-Type": "text/plain"},
        )
        assert unsupported.status_code == 415

        empty = await client.post(
            "/api/v1/ingest/chatgpt",
            content=b"",
            headers={"Content-Type": "application/zip"},
        )
        assert empty.status_code == 400

        oversized = await client.post(
            "/api/v1/ingest/chatgpt",
            content=b"12345",
            headers={"Content-Type": "application/zip"},
        )
        assert oversized.status_code == 413

        jobs = await client.get("/api/v1/jobs")
        assert jobs.status_code == 200
        assert jobs.json()["total"] == 0

    assert list(settings.incoming_path.glob("*")) == []
    get_settings.cache_clear()


def _configure_test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("API_BASE_URL", "")
    monkeypatch.setenv(
        "DIGITALME_DATABASE_URL",
        f"sqlite:///{tmp_path / 'digitalme.db'}",
    )
    monkeypatch.setenv("DIGITALME_RAW_STORE_PATH", str(tmp_path / "raw"))
    monkeypatch.setenv("DIGITALME_INCOMING_PATH", str(tmp_path / "incoming"))
    get_settings.cache_clear()
    return get_settings()


async def _wait_for_terminal_job(
    client: httpx.AsyncClient,
    job_id: str,
) -> dict[str, Any]:
    for _ in range(100):
        response = await client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        payload = cast(dict[str, Any], response.json())
        if payload["summary"]["status"] in {
            "completed",
            "completed_with_warnings",
            "failed",
            "cancelled",
        }:
            return payload
        await asyncio.sleep(0.01)
    pytest.fail("Ingestion job did not reach a terminal state")


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
