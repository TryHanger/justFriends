"""Unified profile: the LLM pipeline and the XLM-R model of the text's language together.

Each detector has its own strengths (on Kazakh the two-stage LLM agrees with the dictionary
at κ 0.38, XLM-R at κ 0.20; on Chinese XLM-R reaches span F1 0.67 on CMDAG, the classical
mode finds about half of Wang Yi's Chu Ci images), so the unified result keeps every figure
either of them found and records which detector found it. Both parts are calibrated by
their own pipelines before the merge; agreement is reported, not turned into a new score.
"""

import logging
import re

from app.nlp.contracts import validate_result
from app.schemas.analysis import AnalysisResult

logger = logging.getLogger(__name__)

XLMR_ONLY = "Найдено только XLM-R; LLM эту фигуру не отметила."
# Per-part review summaries of the calibrator; one is recomputed for the merged figures.
_REVIEW_SUMMARY = re.compile(
    r"^(\d+ of \d+ figure\(s\) below the review threshold|No figures found; )"
)


def _overlaps(a, b) -> bool:
    return a.start < b.end and b.start < a.end


def merge(
    text: str,
    language: str,
    llm: AnalysisResult,
    xlmr: AnalysisResult | None,
    threshold: float,
    warnings: tuple[str, ...] | list[str] = (),
) -> AnalysisResult:
    """Merge figures by character overlap.

    A figure found by both keeps the LLM figure (domains, tenor, ground, explanation) with
    the larger of the two calibrated confidences; XLM-R-only figures are added; LLM-only
    figures stay as they are."""
    others = list(xlmr.metaphors) if xlmr else []
    llm_raw = llm.method.get("calibration", {}).get("raw_confidence")
    figures, sources, raw = [], {}, []
    matched = set()
    for index, span in enumerate(llm.metaphors):
        hits = [i for i, other in enumerate(others) if _overlaps(span, other)]
        matched.update(hits)
        if hits:
            confidence = max(span.confidence, *(others[i].confidence for i in hits))
            span = span.model_copy(update={"confidence": confidence})
        figures.append(span)
        sources[(span.start, span.end)] = ["llm", "xlmr"] if hits else ["llm"]
        raw.append(llm_raw[index] if llm_raw else None)
    # With attribute heads XLM-R figures carry a type, domains and an explanation of their own.
    attributes = bool(xlmr and "attributes" in xlmr.method)
    for i, other in enumerate(others):
        if i in matched:
            continue
        update = (
            {"rationale": f"{XLMR_ONLY} {other.rationale}"}
            if attributes
            else {"label": "metaphor", "rationale": XLMR_ONLY}
        )
        figures.append(other.model_copy(update=update))
        sources[(other.start, other.end)] = ["xlmr"]
        raw.append(None)  # no LLM self-estimate exists for this figure
    order = sorted(range(len(figures)), key=lambda i: (figures[i].start, figures[i].end))
    figures = [figures[i] for i in order]

    parts = [llm] + ([xlmr] if xlmr else [])
    merged_warnings = [w for part in parts for w in part.warnings if not _REVIEW_SUMMARY.match(w)]
    merged_warnings += list(warnings)
    low = sum(span.confidence < threshold for span in figures)
    if low:
        merged_warnings.append(
            f"{low} of {len(figures)} figure(s) below the review threshold "
            f"{threshold:.0%}: check them first."
        )
    elif not figures:
        merged_warnings.append("No figures found; models miss many figures, so review the text.")

    counts = {"both": 0, "llm_only": 0, "xlmr_only": 0}
    for found in sources.values():
        counts["both" if len(found) == 2 else f"{found[0]}_only"] += 1
    method = {
        **llm.method,
        "model_profile": "unified",
        "unified": {
            "llm_model": llm.model_version,
            "xlmr_model": xlmr.model_version if xlmr else None,
            "sources": {f"{start}-{end}": found for (start, end), found in sources.items()},
            **counts,
        },
    }
    if llm_raw is not None:
        # Kept aligned with the merged figures so that the LLM refit can still read it.
        method["calibration"] = {
            **method["calibration"],
            "raw_confidence": [raw[i] for i in order],
        }
    if xlmr:
        method["xlmr"] = xlmr.method
    candidates = list(llm.candidates)
    if xlmr:
        seen = {(c.start, c.end) for c in candidates}
        candidates += [c for c in xlmr.candidates if (c.start, c.end) not in seen]
    versions = ",".join(part.model_version for part in parts)
    result = AnalysisResult(
        language=llm.language,
        model_version=f"unified({versions})",
        metaphors=figures,
        needs_review=any(part.needs_review for part in parts),
        warnings=list(dict.fromkeys(merged_warnings)),
        candidates=candidates,
        method=method,
        stanzas=llm.stanzas or (xlmr.stanzas if xlmr else []),
    )
    return validate_result(text, language, result)


class UnifiedPipeline:
    """`xlmr(language)` returns the calibrated XLM-R analysis for that language, as a
    callable of the text, or None when its weights or PyTorch are absent."""

    def __init__(self, llm, xlmr, threshold: float = 0.8):
        self.llm, self.xlmr, self.threshold = llm, xlmr, threshold

    def analyze(self, text: str, language: str = "auto") -> AnalysisResult:
        primary = self.llm.analyze(text, language)
        run, secondary, warnings = self.xlmr(primary.language), None, []
        if run is None:
            warnings.append(
                f"Unified model: XLM-R for {primary.language} is not installed "
                "(weights or PyTorch missing); only LLM figures are shown."
            )
        else:
            try:
                secondary = run(text)
            except Exception as exc:  # noqa: BLE001 - the LLM part stays usable; reported in warnings
                logger.exception("XLM-R part of the unified analysis failed")
                warnings.append(
                    f"Unified model: XLM-R for {primary.language} failed "
                    f"({type(exc).__name__}); only LLM figures are shown."
                )
        return merge(text, language, primary, secondary, self.threshold, warnings)
