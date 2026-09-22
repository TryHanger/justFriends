"""Strict model output and validation against the unmodified original text."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import AnalysisResult, MetaphorSpan
from app.schemas.taxonomy import DOMAINS, Domain


class NLPInputError(ValueError):
    """Input needs correction, as opposed to a malformed model response."""


class ModelSpan(MetaphorSpan):
    source_domain: Domain
    target_domain: Domain
    rationale: str = Field(
        min_length=1,
        description=(
            "Write the explanation exclusively in Russian using Cyrillic. Never use Chinese, "
            "Kazakh, or English here; leave the quoted source expression unchanged."
        ),
    )


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["zh", "kk"]
    metaphors: list[ModelSpan]


def output_schema() -> dict:
    schema = ModelOutput.model_json_schema()
    for field in ("source_domain", "target_domain"):
        schema["$defs"]["ModelSpan"]["properties"][field]["enum"] = list(DOMAINS)
    return schema


def validate_spans(text: str, spans: list[MetaphorSpan]) -> None:
    previous_end = 0
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        if span.end > len(text) or text[span.start : span.end] != span.text:
            raise ValueError("Span must exactly match original text[start:end]")
        if span.start < previous_end:
            raise ValueError("Overlapping or duplicate spans require adjudication")
        previous_end = span.end


def validate_result(text: str, language: str, result: AnalysisResult) -> AnalysisResult:
    if language not in {"auto", "zh", "kk"}:
        raise ValueError("language must be auto, zh or kk")
    if language != "auto" and result.language != language:
        raise ValueError("Returned language differs from requested language")
    validate_spans(text, result.metaphors)
    for span in result.metaphors:
        ModelSpan.model_validate(span.model_dump())
    return result


def resolve_language(text: str, language: str) -> str:
    if language in {"zh", "kk"}:
        return language
    if language != "auto":
        raise NLPInputError("Unsupported language")
    has_han = any("\u3400" <= c <= "\u9fff" or "\U00020000" <= c <= "\U0002fa1f" for c in text)
    has_kazakh = any(c in "ӘәҒғҚқҢңӨөҰұҮүҺһІі" for c in text)
    if has_han and not has_kazakh:
        return "zh"
    if has_kazakh and not has_han:
        return "kk"
    raise NLPInputError("Language is ambiguous; specify zh or kk explicitly")
