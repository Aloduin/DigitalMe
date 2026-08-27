"""Strict structured-output contracts for Episode and Memory extraction."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryType(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    BELIEF = "belief"
    GOAL = "goal"
    DECISION = "decision"
    DECISION_RULE = "decision_rule"
    PROJECT_STATE = "project_state"
    PROCEDURE = "procedure"
    SKILL = "skill"
    LESSON = "lesson"
    RELATIONSHIP_CONTEXT = "relationship_context"
    COMMITMENT = "commitment"
    CONSTRAINT = "constraint"
    INTEREST = "interest"
    OPEN_LOOP = "open_loop"


class EvidenceStrength(StrEnum):
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"


class CandidateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MemoryType
    content: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default="global", min_length=1, max_length=255)
    confidence: float = Field(ge=0, le=1)
    salience: float = Field(ge=0, le=1)
    evidence_strength: EvidenceStrength
    evidence_message_ids: list[str] = Field(min_length=1)

    @field_validator("content", "scope")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("evidence_message_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_message_ids must be unique")
        return value


class EpisodeExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=4000)
    projects: list[str] = Field(default_factory=list, max_length=50)
    decisions: list[str] = Field(default_factory=list, max_length=50)
    open_questions: list[str] = Field(default_factory=list, max_length=50)
    candidates: list[CandidateProposal] = Field(default_factory=list, max_length=50)

    @field_validator(
        "episode_type",
        "title",
        "summary",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped
