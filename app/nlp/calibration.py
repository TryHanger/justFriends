"""Calibrated confidence for LLM figures (Platt scaling fitted on expert data).

An LLM's self-reported confidence is not a probability: on CMDAG gpt-4o-mini says 0.9 and
is right about half the time. scripts/calibrate_llm.py fits, per model and language,
p(correct) = sigmoid(a * logit(confidence) + b) on expert-labelled data and stores the
parameters in data/calibration/llm.json. Here every figure's confidence is replaced by
that probability, and the analysis is flagged for review figure by figure instead of
as a whole. Models or languages without fitted parameters are left untouched.
"""

import json
import math
from pathlib import Path

from app.nlp.usage import added_figures
from app.schemas.analysis import AnalysisResult

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "calibration" / "llm.json"
UNCALIBRATED = "LLM preliminary annotation; confidence is self-reported and uncalibrated."
XLMR_UNCALIBRATED = "Token probabilities are uncalibrated; domains unknown."
# What remains true of an XLM-R result once its probabilities are calibrated.
XLMR_DOMAINS = "XLM-R does not determine source and target domains."
# An XLM-R result whose type and domains come from the attribute heads: nothing remains
# to say once its probabilities are calibrated.
XLMR_PROBABILITIES = "Token probabilities are uncalibrated."


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def platt(confidence: float, a: float, b: float) -> float:
    return 1 / (1 + math.exp(-(a * _logit(confidence) + b)))


class Calibrator:
    def __init__(self, table: dict, threshold: float):
        self.table, self.threshold = table, threshold

    @classmethod
    def load(cls, threshold: float, path: str | Path | None = None) -> "Calibrator | None":
        path = Path(path or DEFAULT_PATH)
        if not path.exists():
            return None
        return cls(json.loads(path.read_text(encoding="utf-8"))["models"], threshold)

    def apply(self, result: AnalysisResult) -> AnalysisResult:
        fit = self.table.get(result.model_version, {}).get(result.language)
        if fit is None:
            return result
        # Figures added by the two-stage judge have no self-reported confidence to rescale.
        added = added_figures(result.method)
        spans = [
            span
            if (span.start, span.end) in added
            else span.model_copy(
                update={"confidence": round(platt(span.confidence, fit["a"], fit["b"]), 3)}
            )
            for span in result.metaphors
        ]
        low = sum(span.confidence < self.threshold for span in spans)
        warnings = [
            XLMR_DOMAINS if w == XLMR_UNCALIBRATED else w
            for w in result.warnings
            if w not in (UNCALIBRATED, XLMR_PROBABILITIES)
        ]
        warnings.append(
            f"Confidence calibrated on {fit['source']} ({fit['spans']} figures): "
            "the probability that a figure is correct."
        )
        if low:
            warnings.append(
                f"{low} of {len(spans)} figure(s) below the review threshold "
                f"{self.threshold:.0%}: check them first."
            )
        elif not spans:
            warnings.append("No figures found; models miss many figures, so review the text.")
        method = dict(result.method)
        method["calibration"] = {
            "method": "platt",
            "source": fit["source"],
            "spans": fit["spans"],
            "ece_before": fit.get("ece_before"),
            "ece_after": fit.get("ece_after"),
            # Self-reported values in figure order: refitting needs them, not calibrated ones.
            "raw_confidence": [span.confidence for span in result.metaphors],
        }
        return result.model_copy(
            update={
                "metaphors": spans,
                "warnings": warnings,
                # Calibration covers precision only: an empty result may still miss figures.
                # A figure whose head word stage 2 judged literal also needs a reviewer.
                "needs_review": low > 0
                or not spans
                or bool(result.method.get("two_stage", {}).get("disputed")),
                "method": method,
            }
        )
