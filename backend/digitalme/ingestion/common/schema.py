"""Versioned canonical session contracts shared by source adapters."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CANONICAL_SCHEMA_VERSION = 1


class ParseWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    locator: dict[str, Any] = Field(default_factory=dict)


class CanonicalMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str
    parent_external_id: str | None = None
    role: str | None = None
    content_type: str = "text"
    normalized_text: str | None = None
    source_timestamp: datetime | None = None
    sequence: int | None = None
    raw_locator: dict[str, Any] = Field(default_factory=dict)
    parse_warnings: list[ParseWarning] = Field(default_factory=list)


class CanonicalSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str
    schema_version: int = CANONICAL_SCHEMA_VERSION
    title: str | None = None
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    selected_branch_head_external_id: str | None = None
    messages: list[CanonicalMessage] = Field(default_factory=list)
    parse_warnings: list[ParseWarning] = Field(default_factory=list)
