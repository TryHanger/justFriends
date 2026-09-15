import json

from openai import OpenAI
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.analysis import AnalysisResult

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": ["zh", "kk"]},
        "model_version": {"type": "string"},
        "metaphors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "label": {
                        "type": "string",
                        "enum": ["metaphor", "simile", "personification", "metonymy", "idiom"],
                    },
                    "source_domain": {"type": "string"},
                    "target_domain": {"type": "string"},
                    "confidence": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": [
                    "text", "start", "end", "label", "source_domain", "target_domain",
                    "confidence", "rationale",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["language", "model_version", "metaphors"],
    "additionalProperties": False,
}

INSTRUCTIONS = """Analyze the supplied Chinese or Kazakh poem in its original language.
Find metaphorical spans and classify each span. Do not translate the poem.
Use zh for Chinese and kk for Kazakh. Offsets are zero-based Python string character offsets
into the exact input text; end is exclusive. The span text must exactly match text[start:end].
Confidence must be between 0 and 1. Return no span when no non-literal expression is supported.
Keep rationales short and avoid inventing cultural interpretations unsupported by context."""


class AnalyzerNotConfigured(Exception):
    pass


class AnalyzerOutputInvalid(Exception):
    pass


def analyze_text(text: str, language: str) -> AnalysisResult:
    settings = get_settings()
    if not settings.openai_api_key:
        raise AnalyzerNotConfigured

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.openai_model,
        instructions=INSTRUCTIONS,
        input=f"Requested language: {language}\n\nPoem:\n{text}",
        text={
            "format": {
                "type": "json_schema",
                "name": "metaphor_analysis",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    )
    try:
        result = AnalysisResult.model_validate(json.loads(response.output_text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AnalyzerOutputInvalid from exc

    result = result.model_copy(update={"model_version": settings.openai_model})

    for span in result.metaphors:
        if text[span.start:span.end] != span.text:
            raise AnalyzerOutputInvalid("The returned span does not match the source text")
    return result
