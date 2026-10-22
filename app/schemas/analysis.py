from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.limits import MAX_ANALYSIS_CHARS
from app.schemas.taxonomy import EntityType, MetaphorLabel, Sentiment, UsageType

Language = Literal["auto", "zh", "kk"]
ModelProfile = Literal["default", "experimental_kk", "xlmr_zh_gold_v2", "baseline"]


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_ANALYSIS_CHARS)
    language: Language = "auto"
    model_profile: ModelProfile = "default"

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
    # Evidence_Reasoning in the ТЗ output format.
    rationale: str
    # ТЗ п. 4.1 fields. Optional so that earlier stored results and detectors that do not
    # produce them (baseline, XLM-R) remain valid; None means "not produced", not "absent".
    entity: str | None = Field(default=None, description="Entity: key image word inside text")
    entity_type: EntityType | None = None
    usage_type: UsageType = "metaphorical"
    context_sentence: str | None = Field(
        default=None, description="Line or sentence of the source text containing the span"
    )
    semantic_label: str | None = Field(
        default=None, description="Short conventional meaning, e.g. 'благородный муж' for 兰"
    )
    sentiment: Sentiment | None = None
    # Tenor ("тема"): what the image describes; vehicle is the span itself. Offsets are
    # set only when the tenor occurs literally in the source text (it may be implicit).
    tenor: str | None = Field(default=None, description="Tenor: what is described, e.g. 火")
    tenor_start: int | None = Field(default=None, ge=0, strict=True)
    tenor_end: int | None = Field(default=None, gt=0, strict=True)
    # Ground ("основание сравнения"): the property shared by tenor and vehicle.
    ground: str | None = Field(default=None, description="Ground: shared property, e.g. 折磨的感觉")

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if self.entity is not None and self.entity not in self.text:
            raise ValueError("entity must be a substring of the span text")
        if (self.tenor_start is None) != (self.tenor_end is None):
            raise ValueError("tenor_start and tenor_end must be set together")
        if self.tenor_start is not None:
            if self.tenor is None or self.tenor_end <= self.tenor_start:
                raise ValueError("tenor offsets need tenor text and ordered bounds")
            if self.tenor_end - self.tenor_start != len(self.tenor):
                raise ValueError("tenor offsets must cover exactly the tenor text")
        return self


class EntityCandidate(BaseModel):
    """Module B output: a possible carrier of figurative meaning and its usage decision."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    entity_type: EntityType
    usage_type: UsageType | None = Field(
        default=None, description="None: extracted but not yet classified (module C)"
    )
    origin: str = Field(default="model", description="lexicon, model or human")
    lexicon_meaning: str | None = None
    reasoning: str | None = None

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


StanzaType = Literal["賦", "比", "興"]


class StanzaLabel(BaseModel):
    """Stanza type after Zhu Xi (詩經集傳): 賦 description, 比 comparison, 興 evocative image.

    A model suggestion with its probabilities, not an expert annotation.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    label: StanzaType
    probabilities: dict[StanzaType, float]

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if not all(0 <= p <= 1 for p in self.probabilities.values()):
            raise ValueError("probabilities must lie in [0, 1]")
        return self


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["zh", "kk"]
    model_version: str
    metaphors: list[MetaphorSpan]
    # Optional additions preserve loading of previously stored responses.
    needs_review: bool = True
    warnings: list[str] = Field(default_factory=list)
    candidates: list[EntityCandidate] = Field(default_factory=list)
    method: dict = Field(
        default_factory=dict,
        description="Reproducibility record: prompt strategy, decoding parameters, lexicon version",
    )
    stanzas: list[StanzaLabel] = Field(
        default_factory=list, description="Chinese only: stanza types 賦/比/興 suggested by a model"
    )


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


class ModelInfo(BaseModel):
    id: ModelProfile
    name: str
    description: str
    languages: list[Literal["zh", "kk", "auto"]]
    supervision: str
    training_records: int | None = None
    metric_label: str | None = None
    metric_value: float | None = None
    available: bool


class CompareRequest(BaseModel):
    analysis_ids: list[int] = Field(min_length=2, max_length=100)


class ComparisonGroup(BaseModel):
    analysis_count: int
    metaphor_count: int
    by_label: dict[str, int]
    by_source_domain: dict[str, int]
    by_target_domain: dict[str, int]
    # ТЗ п. 2.2.4: cross-cultural mapping of source domains, images and sentiment.
    by_sentiment: dict[str, int] = Field(default_factory=dict)
    by_entity_type: dict[str, int] = Field(default_factory=dict)
    by_domain_pair: dict[str, int] = Field(default_factory=dict)
    top_semantic_labels: dict[str, int] = Field(default_factory=dict)
    candidate_usage: dict[str, int] = Field(default_factory=dict)


class CompareResponse(BaseModel):
    languages: dict[str, ComparisonGroup]
    analysis_ids: list[int]
    note: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
