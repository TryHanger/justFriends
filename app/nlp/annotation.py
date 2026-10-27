"""Label Studio import/export. Predictions are never promoted to human gold.

Regions of the `figure` control are figurative expressions with per-region source/target
domains and optional sentiment and semantic label. Regions of the `entity` control are
candidate entities (module B) with an entity type and a literal/metaphorical decision
(module C). An entity region inside a figure region becomes that expression's Entity.
"""

from app.nlp.contracts import ModelSpan
from app.nlp.corpus import Poem
from app.nlp.llm import locate_tenor
from app.schemas.analysis import EntityCandidate

FIGURE_FIELDS = ("source_domain", "target_domain")
OPTIONAL_FIGURE_FIELDS = ("sentiment",)
ENTITY_FIELDS = ("entity_type", "usage_type")
# Free-text attributes of a figure region: meaning, tenor ("тема") and ground ("основание").
TEXT_FIELDS = ("semantic_label", "tenor", "ground")


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
            elif kind == "textarea" and name in TEXT_FIELDS:
                value = " ".join(t.strip() for t in result["value"]["text"]).strip()
                texts[(result["id"], name)] = value
            else:
                raise ValueError("Unsupported annotation field; use the supplied labeling config")
        regions = set(figures) | set(entities)
        if any(region_id not in regions for region_id, _ in choices) or {
            region_id for region_id, _ in texts
        } - set(figures):
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
            tenor = texts.get((region_id, "tenor")) or None
            tenor_bounds = locate_tenor(poem.text, tenor, start, end) if tenor else None
            spans.append(
                ModelSpan(
                    text=value["text"],
                    start=start,
                    end=end,
                    label=value["labels"][0],
                    **{f: _one(choices, region_id, f, True) for f in FIGURE_FIELDS},
                    sentiment=_one(choices, region_id, "sentiment", False),
                    semantic_label=texts.get((region_id, "semantic_label")) or None,
                    tenor=tenor,
                    tenor_start=tenor_bounds[0] if tenor_bounds else None,
                    tenor_end=tenor_bounds[1] if tenor_bounds else None,
                    ground=texts.get((region_id, "ground")) or None,
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


def review_report(tasks: list[dict]) -> dict:
    """How annotators treated model suggestions (Label Studio `origin` of each region).

    `prediction` = accepted unchanged, `prediction-changed` = edited, `manual` = added by the
    annotator; suggestions missing from the annotation were deleted. A high share of
    unchanged acceptances means the "gold" may simply repeat the model and needs a check.
    """
    per_task, totals = [], {"accepted": 0, "edited": 0, "added": 0, "deleted": 0}
    for task in tasks:
        annotations = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
        if not annotations:
            continue
        regions = {}
        for result in annotations[0]["result"]:
            if result["type"] == "labels":
                regions[result["id"]] = result.get("origin", "manual")
        # Label Studio exports the suggestion inside the annotation; task-level
        # "predictions" are full objects only in import files, plain IDs in exports.
        sources = [annotations[0].get("prediction")] + list(task.get("predictions", []))
        suggested = {
            r["id"]
            for p in sources
            if isinstance(p, dict)
            for r in p.get("result", [])
            if r["type"] == "labels"
        }
        counts = {
            "accepted": sum(o == "prediction" for o in regions.values()),
            "edited": sum(o == "prediction-changed" for o in regions.values()),
            "added": sum(o not in {"prediction", "prediction-changed"} for o in regions.values()),
            "deleted": len(suggested - set(regions)),
        }
        totals = {k: totals[k] + v for k, v in counts.items()}
        per_task.append(
            {
                "id": task["data"].get("id"),
                **counts,
                "seconds": annotations[0].get("lead_time"),
                "untouched": bool(suggested)
                and counts["accepted"] == len(suggested)
                and not (counts["edited"] or counts["added"] or counts["deleted"]),
            }
        )
    reviewed = len(per_task)
    untouched = sum(t["untouched"] for t in per_task)
    times = sorted(t["seconds"] for t in per_task if isinstance(t["seconds"], (int, float)))
    return {
        "summary": {
            "tasks": reviewed,
            **totals,
            "tasks_accepted_without_changes": untouched,
            # Very short times suggest the poem was not actually read.
            "median_seconds_per_task": times[len(times) // 2] if times else None,
            "warning": (
                "Most suggestions were accepted unchanged; verify that experts reviewed them."
                if reviewed and untouched / reviewed > 0.5
                else None
            ),
        },
        "tasks": per_task,
    }
