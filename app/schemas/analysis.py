from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.taxonomy import MetaphorLabel

Language = Literal["auto", "zh", "kk"]


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    language: Language = "auto"

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value):
        if not value.strip():
            raise ValueError("Text must not be whitespace only")
        return value


class MetaphorSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    label: MetaphorLabel
    source_domain: str
    target_domain: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    rationale: str

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["zh", "kk"]
    model_version: str
    metaphors: list[MetaphorSpan]
    # Optional additions preserve loading of previously stored responses.
    needs_review: bool = True
    warnings: list[str] = Field(default_factory=list)


class AnalysisResponse(AnalysisResult):
    analysis_id: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
