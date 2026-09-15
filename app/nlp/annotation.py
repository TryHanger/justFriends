"""Label Studio import/export. Predictions are never promoted to human gold."""

from app.nlp.corpus import Poem
from app.nlp.contracts import ModelSpan


def export_tasks(records: list[Poem]) -> list[dict]:
    return [{"data": r.model_dump()} for r in records]


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
        regions, choices = {}, {}
        for result in annotation["result"]:
            if result["type"] == "labels" and result["from_name"] == "figure":
                if result["id"] in regions:
                    raise ValueError("Duplicate region ID")
                regions[result["id"]] = result["value"]
            elif result["type"] == "choices":
                key = (result["id"], result["from_name"])
                if key in choices:
                    raise ValueError("Duplicate region choice")
                choices[key] = result["value"]["choices"]
            else:
                raise ValueError("Unsupported annotation field; use the supplied labeling config")
        spans = []
        if any(region_id not in regions for region_id, _ in choices):
            raise ValueError("Region choice has no matching text span")
        for region_id, value in regions.items():
            if len(value["labels"]) != 1:
                raise ValueError("Each region needs exactly one figure label")
            domains = {}
            for field in ("source_domain", "target_domain"):
                selected = choices.get((region_id, field), [])
                if len(selected) != 1:
                    raise ValueError(f"Region {region_id} requires one {field}")
                domains[field] = selected[0]
            start = python_offset(poem.text, value["start"], offset_unit)
            end = python_offset(poem.text, value["end"], offset_unit)
            spans.append(
                ModelSpan(
                    text=value["text"],
                    start=start,
                    end=end,
                    label=value["labels"][0],
                    **domains,
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
            annotation_status="gold" if adjudicator else "draft",
            annotators=[str(completed_by)],
            adjudicator=adjudicator,
        )
        records.append(Poem.model_validate(data))
    if len({r.id for r in records}) != len(records):
        raise ValueError("Duplicate poem IDs in annotation export")
    return records
