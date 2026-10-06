"""Kazakh & Chinese Metaphor IFT Dataset (ТЗ этап 3, ожидаемый результат 2).

Instruction examples are generated only from adjudicated gold records, one split at a time,
so that a test split never leaks into fine-tuning. The system prompt is the same one the
model receives at inference, which keeps fine-tuned and prompted runs comparable (H1).
"""

import json
from pathlib import Path

from app.nlp.contracts import ModelOutput
from app.nlp.corpus import Poem, manifest, require_gold
from app.nlp.lexicon import CandidateExtractor
from app.nlp.prompts import PromptStrategy, build_prompt
from app.schemas.taxonomy import TAXONOMY_VERSION

TASKS = ("analysis", "usage")


def gold_answer(record: Poem) -> dict:
    entities = {(c.start, c.end): c for c in record.candidates}
    metaphors = []
    for span in record.spans:
        entity = span.entity or span.text
        offset = span.start + span.text.find(entity)
        candidate = entities.get((offset, offset + len(entity)))
        metaphors.append(
            {
                "text": span.text,
                "start": span.start,
                "end": span.end,
                "entity": entity,
                "entity_type": span.entity_type
                or (candidate.entity_type if candidate else "other"),
                "label": span.label,
                "source_domain": span.source_domain,
                "target_domain": span.target_domain,
                "semantic_label": span.semantic_label or "",
                "sentiment": span.sentiment or "neutral",
                "confidence": 1.0,
                "rationale": span.rationale,
            }
        )
    covered = [(s.start, s.end) for s in record.spans]
    literals = [
        {
            "text": c.text,
            "start": c.start,
            "end": c.end,
            "entity_type": c.entity_type,
            "reasoning": c.reasoning or "Употреблено в прямом значении.",
        }
        for c in record.candidates
        if c.usage_type == "literal" and not any(c.start < e and c.end > s for s, e in covered)
    ]
    answer = {"language": record.language, "metaphors": metaphors, "literal_candidates": literals}
    ModelOutput.model_validate(answer)  # the target must satisfy the inference contract
    return answer


USAGE_INSTRUCTIONS = (
    "Decide whether the marked candidate is used literally or metaphorically in this poem, "
    "following MIP: compare its contextual meaning with its basic meaning. "
    'Return JSON {"usage_type": "literal" | "metaphorical", "reasoning": "<по-русски>"}.'
)


def build_ift(
    records: list[Poem],
    *,
    strategy: str = "lexicon",
    tasks: tuple[str, ...] = TASKS,
    allow_synthetic: bool = False,
    lexicon_dir: str | None = None,
) -> list[dict]:
    require_gold(records, allow_synthetic)
    if not set(tasks) <= set(TASKS) or not tasks:
        raise ValueError(f"Tasks must be a nonempty subset of {TASKS}")
    parsed = PromptStrategy.parse(strategy)
    if "cot" in parsed:
        raise ValueError("Gold has no MIP step texts; build IFT without the cot component")
    extractor = CandidateExtractor(lexicon_dir)
    rows = []
    for record in records:
        meta = {"record_id": record.id, "work_id": record.work_id, "language": record.language}
        if "analysis" in tasks:
            prompt = build_prompt(
                record.text,
                record.language,
                parsed,
                candidates=extractor.extract(record.text, record.language),
            )
            rows.append(
                {
                    "id": f"{record.id}:analysis",
                    "task": "analysis",
                    **meta,
                    "messages": [
                        {"role": "system", "content": prompt.instructions},
                        {"role": "user", "content": prompt.user},
                        {
                            "role": "assistant",
                            "content": json.dumps(gold_answer(record), ensure_ascii=False),
                        },
                    ],
                }
            )
        if "usage" in tasks:
            for candidate in record.candidates:
                user = json.dumps(
                    {
                        "poem": record.text,
                        "candidate": {
                            "text": candidate.text,
                            "start": candidate.start,
                            "end": candidate.end,
                        },
                    },
                    ensure_ascii=False,
                )
                answer = {
                    "usage_type": candidate.usage_type,
                    "reasoning": candidate.reasoning or "Решение эксперта.",
                }
                rows.append(
                    {
                        "id": f"{record.id}:usage:{candidate.start}-{candidate.end}",
                        "task": "usage",
                        **meta,
                        "messages": [
                            {"role": "system", "content": USAGE_INSTRUCTIONS},
                            {"role": "user", "content": user},
                            {
                                "role": "assistant",
                                "content": json.dumps(answer, ensure_ascii=False),
                            },
                        ],
                    }
                )
    return rows


def write_ift(path: str | Path, rows: list[dict], records: list[Poem], strategy: str) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    card = {
        "dataset": "Kazakh & Chinese Metaphor IFT Dataset",
        "taxonomy_version": TAXONOMY_VERSION,
        "prompt_strategy": PromptStrategy.parse(strategy).name,
        "examples": len(rows),
        "by_task": {t: sum(r["task"] == t for r in rows) for t in TASKS},
        "by_language": {lang: sum(r["language"] == lang for r in rows) for lang in ("zh", "kk")},
        "source_records": manifest(records),
        "licenses": sorted({r.license for r in records}),
    }
    path.with_suffix(".card.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return card


def read_ift(path: str | Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        roles = [m["role"] for m in row["messages"]]
        if roles[-1] != "assistant" or "user" not in roles:
            raise ValueError(f"{row.get('id')}: IFT example must end with an assistant answer")
    if not rows:
        raise ValueError("IFT dataset is empty")
    return rows
