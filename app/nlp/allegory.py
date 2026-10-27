"""Classical Chinese poetry mode: images read in the commentary tradition (Wang Yi).

A single-pass search for figures sees almost none of the Chu Ci allegory (2 of 29 images
that Wang Yi glosses), while a direct question in the commentary tradition — which images
stand for the ruler, worthy or slanderous men, the poet himself — finds 11–15 of 29
(scripts/eval_wangyi_llm.py, the commentary on the tested poem left out). For Chinese texts
that look like classical poetry this question is asked after stage 1 and every image not
already covered by a figure is added, with what it stands for (tenor) and a Russian
explanation. Wang Yi does not gloss every image, so precision is not measured: added
images carry a neutral confidence and are flagged for review.
"""

import json
import logging
import re

from app.nlp.contracts import context_sentence
from app.nlp.rag import format_context
from app.schemas.analysis import AnalysisResult, MetaphorSpan
from app.schemas.taxonomy import DOMAINS

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "You read classical Chinese poetry in the commentary tradition (王逸《楚辞章句》, 毛传, "
    "朱熹), where images stand for something else: fragrant plants for worthy men or the "
    "poet's virtue, weeds and foul plants for slanderers, the beautiful woman or deity for "
    "the ruler, fine horses for the worthy, birds for good or evil men, the poet's "
    "adornment for his integrity, natural openings (興) for the human situation they lead "
    "into. List every image in the poem that stands for something else in this tradition. "
    "For each give `text`: the image word(s) copied exactly from the poem (the shortest "
    "form, e.g. 荃 or 美人); `tenor`: what it stands for, in Chinese; `source_domain` and "
    "`target_domain` from the allowed values; `explanation`: one sentence in Russian "
    "(русский язык, кириллица) on what the image means here. Do not list plain "
    "description. Answer in JSON."
)
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "tenor": {"type": "string"},
                    "source_domain": {"type": "string", "enum": list(DOMAINS)},
                    "target_domain": {"type": "string", "enum": list(DOMAINS)},
                    "explanation": {"type": "string"},
                },
                "required": ["text", "tenor", "source_domain", "target_domain", "explanation"],
            },
        }
    },
    "required": ["images"],
}
# No self-estimate: a neutral placeholder keeps added images below the review threshold.
ADDED_CONFIDENCE = 0.5
_HAN = re.compile(r"[一-鿿]")
_VERSE = re.compile(r"[，。；！？、,.;!?\n]")


def is_classical(text: str) -> bool:
    """Classical verse: 兮 (the Chu Ci particle), or mostly lines of 3–7 characters."""
    if len(_HAN.findall(text)) < 16:
        return False
    if "兮" in text:
        return True
    verses = [len(_HAN.findall(v)) for v in _VERSE.split(text)]
    verses = [n for n in verses if n]
    return len(verses) >= 4 and sum(3 <= n <= 7 for n in verses) / len(verses) >= 0.75


def _overlaps(start: int, end: int, spans) -> bool:
    return any(start < s.end and end > s.start for s in spans)


class AllegoryJudge:
    """Asks `detector` (any LLMDetector, used for its provider call) the tradition question."""

    def __init__(self, detector, knowledge=None, rag_k: int = 8):
        self.detector, self.knowledge, self.rag_k = detector, knowledge, rag_k

    def applies(self, language: str, text: str) -> bool:
        return language == "zh" and is_classical(text)

    def _ask(self, text: str) -> list[dict]:
        context = ""
        if self.knowledge is not None:
            docs = self.knowledge.search(text, "zh", k=self.rag_k)
            if docs:
                context = "\n\nCommentary for the tradition (may concern other passages):\n"
                context += format_context(docs)
        raw, _ = self.detector._complete(
            INSTRUCTIONS,
            f"Poem:\n{text}{context}",
            SCHEMA,
            {"temperature": 0.0, "top_p": None},
        )
        return json.loads(raw)["images"]

    def apply(self, text: str, result: AnalysisResult) -> AnalysisResult:
        self.detector._local.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
        model = self.detector.model_version
        try:
            images = self._ask(text)
        except Exception:  # noqa: BLE001 - stage 1 stays usable; reported in warnings
            logger.exception("Classical poetry question failed")
            return result.model_copy(
                update={
                    "warnings": [
                        *result.warnings,
                        f"Classical poetry mode ({model}) failed; only stage-1 figures are shown.",
                    ]
                }
            )
        figures, added = list(result.metaphors), []
        for image in images:
            word = image.get("text", "").strip()
            start = text.find(word) if word else -1
            # The first occurrence not taken by a figure; an image absent from the poem is dropped.
            while start >= 0 and _overlaps(start, start + len(word), figures + added):
                start = text.find(word, start + 1)
            if start < 0:
                continue
            end = start + len(word)
            tenor = image.get("tenor", "").strip() or None
            added.append(
                MetaphorSpan(
                    text=word,
                    start=start,
                    end=end,
                    label="metaphor",
                    source_domain=image.get("source_domain") or "unknown",
                    target_domain=image.get("target_domain") or "unknown",
                    confidence=ADDED_CONFIDENCE,
                    rationale=image.get("explanation", "").strip()
                    or "Образ в традиции комментария к классической поэзии.",
                    entity=word,
                    tenor=tenor,
                    context_sentence=context_sentence(text, start, end),
                )
            )
        # A candidate the stage-1 pass called literal is the same word the tradition reads
        # as an image: keep one decision, with the classical explanation.
        candidates = []
        for c in result.candidates:
            image = next((a for a in added if a.start < c.end and a.end > c.start), None)
            if image is not None:
                c = c.model_copy(
                    update={"usage_type": "metaphorical", "reasoning": image.rationale}
                )
            candidates.append(c)
        record = {
            "model": model,
            "images": len(images),
            "added": [[s.start, s.end] for s in added],
            "usage": dict(self.detector._local.usage),
        }
        warnings = [
            *result.warnings,
            f"Classical poetry mode ({model}): {len(added)} image(s) read in the commentary "
            "tradition were added; recall on Wang Yi's Chu Ci images about 50%, precision "
            "not measured.",
        ]
        return result.model_copy(
            update={
                "metaphors": sorted(figures + added, key=lambda s: s.start),
                "candidates": candidates,
                "warnings": warnings,
                "needs_review": result.needs_review or bool(added),
                "method": {**result.method, "classical": record},
            }
        )
