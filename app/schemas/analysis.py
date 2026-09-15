from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["auto", "zh", "kk"]
MetaphorLabel = Literal["metaphor", "simile", "personification", "metonymy", "idiom"]


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    language: Language = "auto"


class MetaphorSpan(BaseModel):
    text: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    label: MetaphorLabel
    source_domain: str
    target_domain: str
    confidence: float = Field(ge=0, le=1)
    rationale: str


class AnalysisResult(BaseModel):
    language: Literal["zh", "kk"]
    model_version: str
    metaphors: list[MetaphorSpan]


class AnalysisResponse(AnalysisResult):
    analysis_id: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]

