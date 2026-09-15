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


class AnalysisJobResponse(BaseModel):
    analysis_id: int
    status: Literal["queued", "processing"]
    status_url: str


class AnalysisStatusResponse(BaseModel):
    analysis_id: int
    status: Literal["queued", "processing", "completed", "failed"]
    source_name: str | None = None
    created_at: str
    result: AnalysisResult | None = None
    error: str | None = None


class AnalysisListResponse(BaseModel):
    items: list[AnalysisStatusResponse]
    limit: int
    offset: int


class CompareRequest(BaseModel):
    analysis_ids: list[int] = Field(min_length=2, max_length=100)


class ComparisonGroup(BaseModel):
    analysis_count: int
    metaphor_count: int
    by_label: dict[str, int]
    by_source_domain: dict[str, int]
    by_target_domain: dict[str, int]


class CompareResponse(BaseModel):
    languages: dict[str, ComparisonGroup]
    analysis_ids: list[int]
    note: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
