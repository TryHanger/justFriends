"""Small lexical baseline; every match is an unverified candidate."""

import re

from app.nlp.contracts import resolve_language
from app.schemas.analysis import AnalysisResult, MetaphorSpan

LEXICON = {
    "zh": [
        ("心海", "water", "emotion"),
        ("心火", "fire", "emotion"),
        ("时间的河", "water", "time"),
        ("时间是一条河", "water", "time"),
        ("希望的种子", "plant", "mind"),
    ],
    "kk": [
        ("өмір өзені", "water", "life"),
        ("жүрек оты", "fire", "emotion"),
        ("үміт сәулесі", "light", "mind"),
        ("көңіл теңізі", "water", "emotion"),
    ],
}


class LexicalDetector:
    def analyze(self, text: str, language: str = "auto") -> AnalysisResult:
        language = resolve_language(text, language)
        spans = []
        for phrase, source, target in LEXICON[language]:
            pattern = re.escape(phrase)
            if language == "kk":
                pattern = rf"(?<!\w){pattern}(?!\w)"
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                spans.append(
                    MetaphorSpan(
                        text=match.group(),
                        start=match.start(),
                        end=match.end(),
                        label="metaphor",
                        source_domain=source,
                        target_domain=target,
                        confidence=0.5,
                        rationale="Lexical candidate; context requires human verification.",
                    )
                )
        return AnalysisResult(
            language=language,
            model_version="lexical-demo-v1",
            metaphors=sorted(spans, key=lambda s: s.start),
            needs_review=True,
            warnings=["Lexical baseline has limited coverage; confidence is not calibrated."],
        )
