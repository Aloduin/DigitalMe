"""Strict structured-output contract for evidence-grounded Ask."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=8_000)
    citation_memory_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("answer")
    @classmethod
    def strip_nonempty_answer(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("answer must not be blank")
        return stripped

    @field_validator("citation_memory_ids")
    @classmethod
    def unique_nonempty_citations(cls, value: list[str]) -> list[str]:
        stripped = [item.strip() for item in value]
        if any(not item for item in stripped):
            raise ValueError("citation IDs must not be blank")
        if len(stripped) != len(set(stripped)):
            raise ValueError("citation IDs must be unique")
        return stripped
