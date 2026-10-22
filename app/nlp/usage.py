"""Stage 2 of the two-stage analysis: a direct usage question for every candidate (module C).

On the Kazakh dictionary set (quotations marked literal/figurative by lexicographers) the
single pass "find all figures in the text" agrees with the dictionary at Cohen κ≈0.11 for
gpt-4o-mini, while the same model asked directly "is word X literal or figurative here?"
reaches κ 0.29 (gpt-4o 0.45). Detection, not language knowledge, is the bottleneck, so for
the configured languages every candidate of stage 1 (soft lexicon and the model's own
figures and literal candidates) is judged again by a direct question.

The prompt and schema are the ones measured by scripts/eval_kk_usage_direct.py, which
imports them from here: a single candidate gets exactly that question, several candidates
of one text share one request.
"""

import json
import logging

from app.nlp.contracts import context_sentence
from app.schemas.analysis import AnalysisResult, EntityCandidate, MetaphorSpan

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "You judge Kazakh literary quotations. For the marked word, decide whether it is used "
    "in its direct (literal) sense or in a figurative (metaphorical, transferred) sense in "
    "this context. Conventional figurative senses count as figurative. Answer in JSON."
)
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "usage": {"type": "string", "enum": ["literal", "metaphorical"]},
        "reason": {"type": "string"},
    },
    "required": ["usage", "reason"],
}
# Additions for the pipeline only: the direct evaluation script asks exactly INSTRUCTIONS.
RUSSIAN_REASON = (
    " Write reason in Russian (русский язык, кириллица), one or two sentences; "
    "quoted source words stay unchanged."
)
BATCH = (
    " Several words of one text are listed, each shown in its line. Judge every word "
    "independently in its own context and return exactly one judgement per id."
)
BATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "judgements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"id": {"type": "integer"}, **SCHEMA["properties"]},
                "required": ["id", "usage", "reason"],
            },
        }
    },
    "required": ["judgements"],
}
# Stage 2 gives no self-estimate. A neutral placeholder keeps added figures below the review
# threshold; the calibrator leaves them alone because its fit describes stage-1 figures.
ADDED_CONFIDENCE = 0.5
_FALLBACK_REASON = "Прямой вопрос об употреблении: слово употреблено в переносном смысле."


def instructions(language: str) -> str:
    """The measured Kazakh wording; other languages only change the language name."""
    return INSTRUCTIONS if language == "kk" else INSTRUCTIONS.replace("Kazakh", "Chinese")


def mark(text: str, start: int, end: int) -> str:
    return f"{text[:start]}[[{text[start:end]}]]{text[end:]}"


def direct_question(text: str, start: int, end: int, word: str | None = None) -> str:
    """The measured direct question; `word` is the dictionary headword when it is known."""
    marked = mark(text, start, end)
    return f"Word: {word or text[start:end]}\nQuotation (word marked with [[ ]]):\n{marked}"


def batch_question(text: str, spans: list[tuple[int, int]]) -> str:
    lines = [f"Quotation:\n{text}\n", "Words to judge (each marked with [[ ]] in its line):"]
    for number, (start, end) in enumerate(spans, 1):
        # The marked copy is 4 characters longer: "[[" before and "]]" after the word.
        line = context_sentence(mark(text, start, end), start, end + 4)
        lines.append(f"{number}. Word: {text[start:end]}\n   Line: {line}")
    return "\n".join(lines)


def _overlaps(start: int, end: int, spans) -> bool:
    return any(start < span.end and end > span.start for span in spans)


class UsageJudge:
    """Asks `detector` (any LLMDetector, used only for its provider call) about candidates."""

    def __init__(self, detector, languages=("kk",), batch_size: int = 8):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.detector, self.languages = detector, frozenset(languages)
        self.batch_size = batch_size

    def applies(self, language: str) -> bool:
        return language in self.languages

    def _ask(
        self, text: str, language: str, batch: list[EntityCandidate]
    ) -> tuple[list[dict | None], bool]:
        sampling = {"temperature": 0.0, "top_p": None}
        if len(batch) == 1:
            c = batch[0]
            question = direct_question(text, c.start, c.end)
            raw, applied = self.detector._complete(
                instructions(language) + RUSSIAN_REASON, question, SCHEMA, sampling
            )
            return [json.loads(raw)], applied
        raw, applied = self.detector._complete(
            instructions(language) + BATCH + RUSSIAN_REASON,
            batch_question(text, [(c.start, c.end) for c in batch]),
            BATCH_SCHEMA,
            sampling,
        )
        answers: dict[int, dict] = {}
        for item in json.loads(raw)["judgements"]:
            answers.setdefault(item["id"], item)  # the first answer wins over a repeated id
        return [answers.get(number) for number in range(1, len(batch) + 1)], applied

    def judge(
        self, text: str, language: str, candidates: list[EntityCandidate]
    ) -> tuple[list, dict]:
        """One judgement ({usage, reason} or None when missing) per candidate, and a record."""
        judgements: list[dict | None] = []
        failed, applied = 0, True
        # The provider's token counter is per thread, so concurrent analyses stay apart.
        self.detector._local.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
        for first in range(0, len(candidates), self.batch_size):
            batch = candidates[first : first + self.batch_size]
            try:
                answers, ok = self._ask(text, language, batch)
                applied = applied and ok
            except Exception:  # noqa: BLE001 - stage 1 stays usable; reported in warnings
                logger.exception("Usage judgement failed for %d candidate(s)", len(batch))
                answers, failed = [None] * len(batch), failed + 1
            judgements += [
                a if a and a.get("usage") in {"literal", "metaphorical"} else None for a in answers
            ]
        usage = dict(self.detector._local.usage)
        record = {
            "model": self.detector.model_version,
            "candidates": len(candidates),
            "judged": sum(j is not None for j in judgements),
            "failed_requests": failed,
            "temperature": 0.0 if applied else None,
            "usage": usage,
        }
        return judgements, record

    def apply(self, text: str, result: AnalysisResult) -> AnalysisResult:
        candidates = list(result.candidates)
        judgements, record = self.judge(text, result.language, candidates)
        figures = list(result.metaphors)
        heads = {}
        for index, span in enumerate(figures):
            if span.entity:
                offset = span.start + span.text.find(span.entity)
                heads[(offset, offset + len(span.entity))] = index
        updated, added, disputed = [], [], []
        for candidate, judgement in zip(candidates, judgements, strict=True):
            if judgement is None:
                updated.append(candidate)
                continue
            # Providers without strict decoding (Ollama) may omit the reason.
            usage, reason = judgement["usage"], str(judgement.get("reason") or "").strip()
            candidate = candidate.model_copy(
                update={"usage_type": usage, "reasoning": reason or candidate.reasoning}
            )
            updated.append(candidate)
            bounds = (candidate.start, candidate.end)
            if usage == "literal" and bounds in heads:
                disputed.append(figures[heads[bounds]])
            elif usage == "metaphorical" and not _overlaps(*bounds, figures + added):
                added.append(
                    MetaphorSpan(
                        text=candidate.text,
                        start=candidate.start,
                        end=candidate.end,
                        label="metaphor",
                        source_domain="unknown",
                        target_domain="unknown",
                        confidence=ADDED_CONFIDENCE,
                        rationale=reason or _FALLBACK_REASON,
                        entity=candidate.text,
                        entity_type=candidate.entity_type,
                        usage_type="metaphorical",
                        context_sentence=context_sentence(text, *bounds),
                    )
                )
        record["metaphorical"] = sum(c.usage_type == "metaphorical" for c in updated)
        record["added"] = [[span.start, span.end] for span in added]
        record["disputed"] = [[span.start, span.end] for span in disputed]
        model = record["model"]
        warnings = list(result.warnings)
        warnings.append(
            f"Stage 2 ({model}) judged {record['judged']} of {len(candidates)} candidate(s) "
            f"by a direct question; {len(added)} figure(s) added from its answers."
        )
        for span in disputed:
            warnings.append(
                f"Stage 2 ({model}) judged the head word «{span.entity}» of figure "
                f"«{span.text}» [{span.start}, {span.end}) literal: check this figure."
            )
        if record["failed_requests"]:
            warnings.append(
                f"Stage 2 failed for {len(candidates) - record['judged']} candidate(s); "
                "their stage-1 decision is kept."
            )
        return result.model_copy(
            update={
                "metaphors": sorted(figures + added, key=lambda s: s.start),
                "candidates": updated,
                "warnings": warnings,
                "needs_review": result.needs_review or bool(disputed),
                "method": {**result.method, "two_stage": record},
            }
        )


def added_figures(method: dict) -> set[tuple[int, int]]:
    """Bounds of the figures stage 2 added: they carry no stage-1 confidence."""
    return {tuple(bounds) for bounds in method.get("two_stage", {}).get("added", [])}
