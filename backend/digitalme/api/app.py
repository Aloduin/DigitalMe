"""FastAPI application factory."""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status

from digitalme import __version__
from digitalme.api.schemas import (
    JobDetailResponse,
    JobListResponse,
    SessionDetailResponse,
    SessionListResponse,
)
from digitalme.archive import ArchiveQueryService
from digitalme.config import get_settings
from digitalme.db.session import create_engine, create_session_factory


def create_app() -> FastAPI:
    """Build the API without performing database migrations or external calls."""

    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)

    def archive_queries() -> Iterator[ArchiveQueryService]:
        engine = create_engine(settings)
        try:
            yield ArchiveQueryService(create_session_factory(engine))
        finally:
            engine.dispose()

    query_service = Annotated[ArchiveQueryService, Depends(archive_queries)]

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/sessions", response_model=SessionListResponse, tags=["archive"])
    def list_sessions(
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
    def get_session(session_id: str, service: query_service) -> SessionDetailResponse:
        detail = service.get_session(session_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return SessionDetailResponse.model_validate(detail)

    @app.get("/api/v1/jobs", response_model=JobListResponse, tags=["archive"])
    def list_jobs(
        service: query_service,
        limit: Annotated[int, Query(ge=1, le=500)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        job_status: Annotated[str | None, Query(alias="status")] = None,
        kind: str | None = None,
    ) -> JobListResponse:
        page = service.list_jobs(limit=limit, offset=offset, status=job_status, kind=kind)
        return JobListResponse.model_validate(page)

    @app.get("/api/v1/jobs/{job_id}", response_model=JobDetailResponse, tags=["archive"])
    def get_job(job_id: str, service: query_service) -> JobDetailResponse:
        detail = service.get_job(job_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return JobDetailResponse.model_validate(detail)

    return app


app = create_app()
