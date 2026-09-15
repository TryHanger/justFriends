from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    language: Literal["zh", "kk"]
    context: str = ""


class ComparisonMatch(BaseModel):
    query_id: str
    candidate_id: str
    similarity: float = Field(ge=-1, le=1, allow_inf_nan=False)
    rank: int = Field(ge=1)


class ComparisonResult(BaseModel):
    model_version: str
    matches: list[ComparisonMatch]
    warnings: list[str]
