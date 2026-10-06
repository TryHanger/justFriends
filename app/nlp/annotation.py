"""Label Studio import/export. Predictions are never promoted to human gold.

Regions of the `figure` control are figurative expressions with per-region source/target
domains and optional sentiment and semantic label. Regions of the `entity` control are
candidate entities (module B) with an entity type and a literal/metaphorical decision
(module C). An entity region inside a figure region becomes that expression's Entity.
"""

from app.nlp.contracts import ModelSpan
from app.nlp.corpus import Poem
from app.schemas.analysis import EntityCandidate

FIGURE_FIELDS = ("source_domain", "target_domain")
OPTIONAL_FIGURE_FIELDS = ("sentiment",)
ENTITY_FIELDS = ("entity_type", "usage_type")


def export_tasks(records: list[Poem], *, prefill_candidates: bool = False) -> list[dict]:
    """Tasks for Label Studio. With prefill, soft-lexicon candidates become *predictions*:
    shown to annotators as suggestions (second stage), never imported as gold."""
    tasks = []
    for record in records:
        task = {"data": record.model_dump()}
        if prefill_candidates:
            from app.nlp.lexicon import CandidateExtractor

            result = []
            for i, candidate in enumerate(
                CandidateExtractor().extract(record.text, record.language)
            ):
                region = f"lex{i}"
                result.append(
                    {
                        "id": region,
                        "type": "labels",
                        "from_name": "entity",
                        "to_name": "poem",
                        "value": {
                            "start": candidate.start,
                            "end": candidate.end,
                            "text": candidate.text,
                            "labels": ["entity"],
                        },
                    }
                )
                result.append(
                    {
                        "id": region,
                        "type": "choices",
                        "from_name": "entity_type",
                        "to_name": "poem",
                        "value": {"choices": [candidate.entity_type]},
                    }
                )
            task["predictions"] = [{"model_version": "soft-lexicon", "result": result}]
        tasks.append(task)
    return tasks


def python_offset(text: str, offset: int, unit: str) -> int:
    if type(offset) is not int or offset < 0:
        raise ValueError("Offset must be a nonnegative integer")
    if unit == "codepoint":
        if offset > len(text):
            raise ValueError("Offset exceeds source text")
        return offset
    if unit != "utf16":
        raise ValueError("Offset unit must be utf16 or codepoint")
    encoded = text.encode("utf-16-le")
    if offset * 2 > len(encoded):
        raise ValueError("UTF-16 offset exceeds source text")
    try:
        return len(encoded[: offset * 2].decode("utf-16-le"))
    except UnicodeDecodeError as exc:
        raise ValueError("Offset splits a UTF-16 surrogate pair") from exc


def _one(choices: dict, region_id: str, field: str, required: bool):
    selected = choices.get((region_id, field), [])
    if len(selected) > 1 or (required and len(selected) != 1):
        raise ValueError(f"Region {region_id} requires one {field}")
    return selected[0] if selected else None


def import_tasks(tasks: list[dict], *, offset_unit="utf16", adjudicator=None) -> list[Poem]:
    records = []
    for task in tasks:
        poem = Poem.model_validate(task["data"])
        annotations = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
        if len(annotations) != 1:
            raise ValueError(
                f"{poem.id}: choose exactly one completed human annotation; "
                "predictions and competing annotations are not gold"
            )
        annotation = annotations[0]
        figures, entities, choices, texts = {}, {}, {}, {}
        for result in annotation["result"]:
            kind, name = result["type"], result["from_name"]
            if kind == "labels" and name in {"figure", "entity"}:
                target = figures if name == "figure" else entities
                if result["id"] in figures or result["id"] in entities:
                    raise ValueError("Duplicate region ID")
                target[result["id"]] = result["value"]
            elif kind == "choices":
                key = (result["id"], name)
                if key in choices:
                    raise ValueError("Duplicate region choice")
                choices[key] = result["value"]["choices"]
            elif kind == "textarea" and name == "semantic_label":
                texts[result["id"]] = " ".join(t.strip() for t in result["value"]["text"]).strip()
            else:
                raise ValueError("Unsupported annotation field; use the supplied labeling config")
        regions = set(figures) | set(entities)
        if any(region_id not in regions for region_id, _ in choices) or set(texts) - set(figures):
            raise ValueError("Region choice has no matching text span")

        def bounds(value, text=poem.text):
            return (
                python_offset(text, value["start"], offset_unit),
                python_offset(text, value["end"], offset_unit),
            )

        candidates = []
        for region_id, value in entities.items():
            start, end = bounds(value)
            candidates.append(
                EntityCandidate(
                    text=value["text"],
                    start=start,
                    end=end,
                    entity_type=_one(choices, region_id, "entity_type", True),
                    usage_type=_one(choices, region_id, "usage_type", True),
                    origin="human",
                )
            )
        spans = []
        for region_id, value in figures.items():
            if len(value["labels"]) != 1:
                raise ValueError("Each region needs exactly one figure label")
            start, end = bounds(value)
            inner = [c for c in candidates if start <= c.start and c.end <= end]
            if any(c.usage_type != "metaphorical" for c in inner):
                raise ValueError(f"Region {region_id}: entity inside a figure must be metaphorical")
            entity = inner[0] if len(inner) == 1 else None
            spans.append(
                ModelSpan(
                    text=value["text"],
                    start=start,
                    end=end,
                    label=value["labels"][0],
                    **{f: _one(choices, region_id, f, True) for f in FIGURE_FIELDS},
                    sentiment=_one(choices, region_id, "sentiment", False),
                    semantic_label=texts.get(region_id) or None,
                    entity=entity.text if entity else None,
                    entity_type=entity.entity_type if entity else None,
                    confidence=1.0,
                    rationale="Human annotation; confidence is an annotation marker.",
                )
            )
        completed_by = annotation.get("completed_by")
        if completed_by is None:
            raise ValueError("Human annotator identity is required")
        if isinstance(completed_by, dict):
            completed_by = completed_by.get("id")
        if completed_by is None:
            raise ValueError("Missing annotator ID")
        data = poem.model_dump()
        data.update(
            spans=[s.model_dump() for s in spans],
            candidates=[c.model_dump() for c in candidates],
            annotation_status="gold" if adjudicator else "draft",
            annotators=[str(completed_by)],
            adjudicator=adjudicator,
        )
        records.append(Poem.model_validate(data))
    if len({r.id for r in records}) != len(records):
        raise ValueError("Duplicate poem IDs in annotation export")
    return records
