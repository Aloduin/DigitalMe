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


class EpisodeRebuildResponse(ApiModel):
    pipeline_version: str
    sessions_processed: int
    episodes_created: int
    messages_linked: int


class EpisodeSummaryResponse(ApiModel):
    id: str
    session_id: str
    source_type: str
    pipeline_version: str
    segment_index: int
    episode_type: str
    title: str
    summary: str | None
    start_at: datetime | None
    end_at: datetime | None
    extraction_status: str
    message_count: int


class EpisodeListResponse(ApiModel):
    items: list[EpisodeSummaryResponse]
    total: int
    limit: int
    offset: int


class EpisodeMessageResponse(ApiModel):
    id: str
    position: int
    role: str | None
    redacted_text: str | None
    sensitivity: str
    source_timestamp: datetime | None
    raw_locator: dict[str, Any]


class EpisodeDetailResponse(ApiModel):
    id: str
    session_id: str
    session_external_id: str
    source_type: str
    pipeline_version: str
    segment_index: int
    episode_type: str
    title: str
    summary: str | None
    start_at: datetime | None
    end_at: datetime | None
    extraction_status: str
    projects: list[str]
    decisions: list[str]
    open_questions: list[str]
    messages: list[EpisodeMessageResponse]


class ExtractionResponse(ApiModel):
    episode_id: str
    extractor_version: str
    provider: str
    model: str
    candidates_created: int
    messages_sent: int
    messages_excluded: int


class CandidateSummaryResponse(ApiModel):
    id: str
    episode_id: str
    candidate_type: str
    content: str
    scope: str
    confidence: float
    salience: float
    evidence_strength: str
    status: str
    sensitivity: str
    evidence_count: int


class CandidateListResponse(ApiModel):
    items: list[CandidateSummaryResponse]
    total: int
    limit: int
    offset: int


class CandidateEvidenceResponse(ApiModel):
    message_id: str
    role: str | None
    quote_snapshot: str
    source_timestamp: datetime | None
    raw_locator: dict[str, Any]


class CandidateDetailResponse(ApiModel):
    summary: CandidateSummaryResponse
    episode_title: str
    extractor_version: str
    evidence: list[CandidateEvidenceResponse]


class CandidateStatusRequest(ApiModel):
    status: str


class RetrievalRequest(ApiModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=20)


class RetrievalHitResponse(ApiModel):
    candidate_id: str
    episode_id: str
    episode_title: str
    candidate_type: str
    content: str
    scope: str
    confidence: float
    salience: float
    evidence_strength: str
    sensitivity: str
    score: float
    matched_terms: list[str]


class RetrievalResponse(ApiModel):
    query: str
    hits: list[RetrievalHitResponse]
    confirmed_scanned: int


class AskRequest(ApiModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)


class AskResponse(ApiModel):
    query: str
    answer: str
    citations: list[RetrievalHitResponse]
    provider: str
    model: str
    memories_sent: int
    memories_excluded: int


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
