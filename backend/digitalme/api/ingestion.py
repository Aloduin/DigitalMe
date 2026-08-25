"""Background execution helpers for HTTP ingestion jobs."""

from contextlib import suppress
from pathlib import Path

from sqlalchemy import Engine

from digitalme.config import Settings
from digitalme.db.session import create_engine, create_session_factory
from digitalme.ingestion.chatgpt import ChatGPTImporter
from digitalme.ingestion.common import ArtifactStore


def run_chatgpt_import_job(settings: Settings, job_id: str, upload_path: Path) -> None:
    """Run one queued import and always clean its request-owned temporary file."""

    engine: Engine | None = None
    try:
        # The importer persists a redacted failure summary on the job. Background tasks must
        # not turn a successfully accepted HTTP response into an unhandled server exception.
        with suppress(Exception):
            engine = create_engine(settings)
            importer = ChatGPTImporter(
                create_session_factory(engine),
                ArtifactStore(settings.raw_store_path),
            )
            importer.run_job(job_id, upload_path)
    finally:
        if engine is not None:
            engine.dispose()
        upload_path.unlink(missing_ok=True)
