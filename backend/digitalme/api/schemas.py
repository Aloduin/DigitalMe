"""Public response contracts for archive browsing APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class IngestionAcceptedResponse(ApiModel):
    job_id: str
    status: str
    detail_url: str


class SessionSummaryResponse(ApiModel):
    id: str
    source_type: str
    title: str | None
    source_created_at: datetime | None
    source_updated_at: datetime | None
    message_count: int
    warning_count: int


class SessionListResponse(ApiModel):
    items: list[SessionSummaryResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(ApiModel):
    id: str
    external_id: str
    parent_external_id: str | None
    role: str | None
    content_type: str
    redacted_text: str | None = Field(
        description="Safe derived view; null means the message has not been classified."
    )
    sensitivity: str
    source_timestamp: datetime | None
    sequence: int | None
    raw_locator: dict[str, Any]
    parse_warnings: list[dict[str, Any]]


class SessionDetailResponse(ApiModel):
    id: str
    source_type: str
    artifact_id: str | None
    external_id: str
    schema_version: int
    title: str | None
    source_created_at: datetime | None
    source_updated_at: datetime | None
    selected_branch_head_external_id: str | None
    parse_warnings: list[dict[str, Any]]
    messages: list[MessageResponse]


class JobSummaryResponse(ApiModel):
    id: str
    source_type: str | None
    kind: str
    status: str
    stage: str | None
    counts: dict[str, int]
    retry_count: int
    error_summary: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobListResponse(ApiModel):
    items: list[JobSummaryResponse]
    total: int
    limit: int
    offset: int


class IngestionErrorResponse(ApiModel):
    id: str
    stage: str
    error_type: str
    safe_summary: str
    raw_locator: dict[str, Any]
    created_at: datetime


class JobDetailResponse(ApiModel):
    summary: JobSummaryResponse
    checkpoint: dict[str, Any]
    errors: list[IngestionErrorResponse]
