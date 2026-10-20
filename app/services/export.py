"""Export in the output format of ТЗ п. 4.1 (one row per figurative expression or literal candidate)."""

from app.nlp.contracts import context_sentence
from app.schemas.analysis import AnalysisResult

TZ_COLUMNS = (
    "Entity",
    "Type",
    "Context_Sentence",
    "Usage_Type",
    "Source_Domain",
    "Target_Domain",
    "Semantic_Label",
    "Sentiment",
    "Evidence_Reasoning",
    "Figure",
    "Expression",
)


def tz_rows(result: AnalysisResult, text: str | None = None) -> list[dict]:
    rows = []
    for span in result.metaphors:
        rows.append(
            {
                "Entity": span.entity or span.text,
                "Type": span.entity_type,
                "Context_Sentence": span.context_sentence
                or (context_sentence(text, span.start, span.end) if text else None),
                "Usage_Type": span.usage_type,
                "Source_Domain": span.source_domain,
                "Target_Domain": span.target_domain,
                "Semantic_Label": span.semantic_label,
                "Sentiment": span.sentiment,
                "Evidence_Reasoning": span.rationale,
                "Figure": span.label,
                "Expression": span.text,
                "start": span.start,
                "end": span.end,
                "confidence": span.confidence,
            }
        )
    for candidate in result.candidates:
        if candidate.usage_type != "literal":
            continue
        rows.append(
            {
                "Entity": candidate.text,
                "Type": candidate.entity_type,
                "Context_Sentence": context_sentence(text, candidate.start, candidate.end)
                if text
                else None,
                "Usage_Type": "literal",
                "Source_Domain": None,
                "Target_Domain": None,
                "Semantic_Label": None,
                "Sentiment": None,
                "Evidence_Reasoning": candidate.reasoning,
                "Figure": None,
                "Expression": candidate.text,
                "start": candidate.start,
                "end": candidate.end,
                "confidence": None,
            }
        )
    return sorted(rows, key=lambda r: (r["start"], r["end"]))
