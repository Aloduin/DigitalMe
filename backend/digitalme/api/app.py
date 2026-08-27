"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from threading import Thread
from typing import Annotated

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse

from digitalme import __version__
from digitalme.api.ingestion import (
    launch_chatgpt_import_job,
    prepare_chatgpt_job_recovery,
    run_recovered_chatgpt_jobs,
)
from digitalme.api.prototype import PROTOTYPE_HTML
from digitalme.api.schemas import (
    IngestionAcceptedResponse,
    JobDetailResponse,
    JobListResponse,
    SessionDetailResponse,
    SessionListResponse,
)
from digitalme.api.uploads import (
    EmptyUploadError,
    UploadTooLargeError,
    declared_content_length,
    store_request_body,
)
from digitalme.archive import ArchiveQueryService
from digitalme.config import get_settings
from digitalme.db.session import create_engine, create_session_factory
from digitalme.ingestion.chatgpt import ChatGPTImporter
from digitalme.ingestion.common import ArtifactStore


def create_app() -> FastAPI:
    """Build the API without performing database migrations or external calls."""

    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        recoverable = prepare_chatgpt_job_recovery(settings)
        recovery_thread = (
            Thread(
                target=run_recovered_chatgpt_jobs,
                args=(settings, recoverable),
                name="digitalme-ingestion-recovery",
            )
            if recoverable
            else None
        )
        app.state.ingestion_recovery_thread = recovery_thread
        if recovery_thread is not None:
            recovery_thread.start()
            app.state.ingestion_threads.append(recovery_thread)
        try:
            yield
        finally:
            for thread in app.state.ingestion_threads:
                thread.join()

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.state.ingestion_threads = []

    async def archive_queries() -> AsyncIterator[ArchiveQueryService]:
        engine = create_engine(settings)
        try:
            yield ArchiveQueryService(create_session_factory(engine))
        finally:
            engine.dispose()

    query_service = Annotated[ArchiveQueryService, Depends(archive_queries)]

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def prototype(response: Response) -> str:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'"
        )
        return PROTOTYPE_HTML

    @app.post(
        "/api/v1/ingest/chatgpt",
        response_model=IngestionAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["ingestion"],
    )
    async def ingest_chatgpt(
        request: Request,
        background_tasks: BackgroundTasks,
        response: Response,
    ) -> IngestionAcceptedResponse:
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type not in {
            "application/zip",
            "application/x-zip-compressed",
            "application/octet-stream",
        }:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Send the ChatGPT export ZIP as the raw request body",
            )
        try:
            content_length = declared_content_length(request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if content_length is not None and content_length > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Upload exceeds the configured limit of {settings.max_upload_bytes} bytes",
            )
        try:
            upload_path = await store_request_body(
                request,
                settings.incoming_path,
                max_bytes=settings.max_upload_bytes,
            )
        except UploadTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=str(exc),
            ) from exc
        except EmptyUploadError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        try:
            engine = create_engine(settings)
        except Exception:
            upload_path.unlink(missing_ok=True)
            raise
        try:
            importer = ChatGPTImporter(
                create_session_factory(engine),
                ArtifactStore(settings.raw_store_path),
            )
            job_id = importer.create_job(
                checkpoint={
                    "incoming_file": upload_path.name,
                    "size_bytes": upload_path.stat().st_size,
                }
            )
        except Exception:
            upload_path.unlink(missing_ok=True)
            raise
        finally:
            engine.dispose()

        detail_url = f"/api/v1/jobs/{job_id}"
        response.headers["Location"] = detail_url
        background_tasks.add_task(
            launch_chatgpt_import_job,
            settings,
            job_id,
            upload_path,
            request.app.state.ingestion_threads,
        )
        return IngestionAcceptedResponse(
            job_id=job_id,
            status="pending",
            detail_url=detail_url,
        )

    @app.get("/api/v1/sessions", response_model=SessionListResponse, tags=["archive"])
    async def list_sessions(
        service: query_service,
        limit: Annotated[int, Query(ge=1, le=500)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        source_type: str | None = None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
    ) -> SessionListResponse:
        page = service.list_sessions(
            limit=limit,
            offset=offset,
            source_type=source_type,
            updated_after=updated_after,
            updated_before=updated_before,
        )
        return SessionListResponse.model_validate(page)

    @app.get(
        "/api/v1/sessions/{session_id}",
        response_model=SessionDetailResponse,
        tags=["archive"],
    )
    async def get_session(session_id: str, service: query_service) -> SessionDetailResponse:
        detail = service.get_session(session_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return SessionDetailResponse.model_validate(detail)

    @app.get("/api/v1/jobs", response_model=JobListResponse, tags=["archive"])
    async def list_jobs(
        service: query_service,
        limit: Annotated[int, Query(ge=1, le=500)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        job_status: Annotated[str | None, Query(alias="status")] = None,
        kind: str | None = None,
    ) -> JobListResponse:
        page = service.list_jobs(limit=limit, offset=offset, status=job_status, kind=kind)
        return JobListResponse.model_validate(page)

    @app.get("/api/v1/jobs/{job_id}", response_model=JobDetailResponse, tags=["archive"])
    async def get_job(job_id: str, service: query_service) -> JobDetailResponse:
        detail = service.get_job(job_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return JobDetailResponse.model_validate(detail)

    return app


app = create_app()
