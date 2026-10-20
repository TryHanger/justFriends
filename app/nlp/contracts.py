"""Strict model output and validation against the unmodified original text."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import AnalysisResult, EntityCandidate, MetaphorSpan
from app.schemas.taxonomy import (
    DOMAINS,
    Domain,
    EntityType,
    MetaphorLabel,
    Sentiment,
)

RUSSIAN = (
    "Write exclusively in Russian using Cyrillic. Never use Chinese, Kazakh, or English here; "
    "quoted source words stay unchanged."
)


class NLPInputError(ValueError):
    """Input needs correction, as opposed to a malformed model response."""


class ModelSpan(MetaphorSpan):
    source_domain: Domain
    target_domain: Domain
    rationale: str = Field(min_length=1, description=RUSSIAN)


class _Offsets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(description="Exact substring of the poem")
    start: int = Field(description="Zero-based Unicode code point offset")
    end: int = Field(description="Exclusive end offset")


class LLMMetaphor(_Offsets):
    """Modules C+D for one figurative expression; every field is required for strict outputs."""

    entity: str = Field(description="Key image word inside text, e.g. 兰 or бөрі")
    entity_type: EntityType
    label: MetaphorLabel
    source_domain: Domain
    target_domain: Domain
    semantic_label: str = Field(description="Short meaning of the image in context. " + RUSSIAN)
    sentiment: Sentiment
    confidence: float = Field(description="Self-estimate 0..1, not a calibrated probability")
    rationale: str = Field(description="Evidence-based reasoning. " + RUSSIAN)


class LLMMetaphorCoT(_Offsets):
    """Chain-of-Thought variant: MIP/MIPVU steps are generated before the decision fields."""

    basic_meaning: str = Field(description="MIP step 2: concrete basic meaning. " + RUSSIAN)
    contextual_meaning: str = Field(description="MIP step 1: meaning in this context. " + RUSSIAN)
    contrast: str = Field(
        description="MIP step 3: does the contextual meaning contrast with the basic one "
        "and is it understood by comparison with it? " + RUSSIAN
    )
    entity: str = Field(description="Key image word inside text, e.g. 兰 or бөрі")
    entity_type: EntityType
    label: MetaphorLabel
    source_domain: Domain
    target_domain: Domain
    semantic_label: str = Field(description="Short meaning of the image in context. " + RUSSIAN)
    sentiment: Sentiment
    confidence: float = Field(description="Self-estimate 0..1, not a calibrated probability")
    rationale: str = Field(description="Evidence-based reasoning. " + RUSSIAN)


class LLMLiteral(_Offsets):
    """A candidate entity that the model judged to be used literally."""

    entity_type: EntityType
    reasoning: str = Field(description=RUSSIAN)


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["zh", "kk"]
    metaphors: list[LLMMetaphor]
    literal_candidates: list[LLMLiteral]


class ModelOutputCoT(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["zh", "kk"]
    metaphors: list[LLMMetaphorCoT]
    literal_candidates: list[LLMLiteral]


# Validation keywords unsupported by some providers' constrained decoding. Pydantic still
# enforces the full contract after parsing, so removing them never weakens validation.
_PROVIDER_UNSUPPORTED = {
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "default",
    "title",
}


def _clean(node):
    if isinstance(node, dict):
        return {k: _clean(v) for k, v in node.items() if k not in _PROVIDER_UNSUPPORTED}
    if isinstance(node, list):
        return [_clean(v) for v in node]
    return node


def output_model(cot: bool = False) -> type[BaseModel]:
    return ModelOutputCoT if cot else ModelOutput


def output_schema(cot: bool = False) -> dict:
    return _clean(output_model(cot).model_json_schema())


def validate_spans(text: str, spans: list[MetaphorSpan]) -> None:
    previous_end = 0
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        if span.end > len(text) or text[span.start : span.end] != span.text:
            raise ValueError("Span must exactly match original text[start:end]")
        if span.start < previous_end:
            raise ValueError("Overlapping or duplicate spans require adjudication")
        previous_end = span.end


def validate_candidates(text: str, candidates: list[EntityCandidate]) -> None:
    seen = set()
    for candidate in candidates:
        if candidate.end > len(text) or text[candidate.start : candidate.end] != candidate.text:
            raise ValueError("Candidate must exactly match original text[start:end]")
        if (candidate.start, candidate.end) in seen:
            raise ValueError("Duplicate candidate boundaries")
        seen.add((candidate.start, candidate.end))


def validate_result(text: str, language: str, result: AnalysisResult) -> AnalysisResult:
    if language not in {"auto", "zh", "kk"}:
        raise ValueError("language must be auto, zh or kk")
    if language != "auto" and result.language != language:
        raise ValueError("Returned language differs from requested language")
    validate_spans(text, result.metaphors)
    validate_candidates(text, result.candidates)
    for span in result.metaphors:
        ModelSpan.model_validate(span.model_dump())
    return result


_SENTENCE_END = set("\n。！？；!?;")


def context_sentence(text: str, start: int, end: int) -> str:
    """Context_Sentence: the poem line or sentence containing [start, end)."""
    left = start
    while left > 0 and text[left - 1] not in _SENTENCE_END:
        left -= 1
    right = end
    while right < len(text) and text[right] not in _SENTENCE_END:
        right += 1
    if right < len(text) and text[right] != "\n":
        right += 1  # keep the closing punctuation of the sentence
    return text[left:right].strip()


def resolve_language(text: str, language: str) -> str:
    if language in {"zh", "kk"}:
        return language
    if language != "auto":
        raise NLPInputError("Unsupported language")
    has_han = any("㐀" <= c <= "鿿" or "\U00020000" <= c <= "\U0002fa1f" for c in text)
    has_kazakh = any(c in "ӘәҒғҚқҢңӨөҰұҮүҺһІі" for c in text)
    if has_han and not has_kazakh:
        return "zh"
    if has_kazakh and not has_han:
        return "kk"
    raise NLPInputError("Language is ambiguous; specify zh or kk explicitly")


__all__ = [
    "DOMAINS",
    "LLMLiteral",
    "LLMMetaphor",
    "LLMMetaphorCoT",
    "ModelOutput",
    "ModelOutputCoT",
    "ModelSpan",
    "NLPInputError",
    "context_sentence",
    "output_model",
    "output_schema",
    "resolve_language",
    "validate_candidates",
    "validate_result",
    "validate_spans",
]
