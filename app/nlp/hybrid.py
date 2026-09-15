"""Conservative fusion: discrepancies remain visible for human review."""

from app.nlp.contracts import validate_result
from app.schemas.analysis import AnalysisResult


class HybridDetector:
    def __init__(self, detector, llm, threshold=0.8):
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be in [0, 1]")
        self.detector, self.llm, self.threshold = detector, llm, threshold

    def analyze(self, text: str, language: str = "auto") -> AnalysisResult:
        primary = validate_result(text, language, self.detector.analyze(text, language))
        # Check negatives too: no predicted span is not evidence of high confidence.
        secondary = validate_result(
            text, primary.language, self.llm.analyze(text, primary.language)
        )
        spans = []
        warnings = list(dict.fromkeys(primary.warnings + secondary.warnings))
        remaining = {(s.start, s.end): s for s in secondary.metaphors}
        for first in primary.metaphors:
            second = remaining.pop((first.start, first.end), None)
            if second:
                spans.append(
                    second.model_copy(
                        update={
                            "confidence": min(first.confidence, second.confidence),
                            "rationale": "XLM-R and LLM agree on boundaries. " + second.rationale,
                        }
                    )
                )
            else:
                spans.append(first)
                warnings.append(f"LLM did not confirm span [{first.start}, {first.end}).")
        for second in remaining.values():
            if any(second.start < s.end and second.end > s.start for s in spans):
                warnings.append(
                    f"Conflicting LLM boundary [{second.start}, {second.end}); "
                    "kept primary boundary for manual adjudication."
                )
            else:
                spans.append(second)
                warnings.append(f"LLM-only span [{second.start}, {second.end}).")
        if any(s.confidence < self.threshold for s in spans):
            warnings.append(f"Candidate confidence is below review threshold {self.threshold}.")
        # Agreement alone does not establish calibrated reliability.
        result = AnalysisResult(
            language=primary.language,
            model_version=f"hybrid({primary.model_version},{secondary.model_version})",
            metaphors=sorted(spans, key=lambda s: s.start),
            needs_review=True,
            warnings=list(dict.fromkeys(warnings)),
        )
        return validate_result(text, language, result)
