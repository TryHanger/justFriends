#!/usr/bin/env python3
"""Split first-pass Kazakh Silver labels from a two-pass consensus control set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.nlp.contracts import ModelSpan
from app.nlp.corpus import Poem, read_corpus, write_corpus
from app.schemas.taxonomy import METAPHOR_LABELS


def first_pass_spans(task: dict) -> list[ModelSpan]:
    prediction = next(iter(task.get("predictions", [])), {})
    regions = prediction.get("result", [])
    labels = [item for item in regions if item.get("type") == "labels"]
    result = []
    for item in labels:
        value = item.get("value", {})
        label = next(iter(value.get("labels", [])), None)
        if label not in METAPHOR_LABELS:
            continue
        region_id = item.get("id")
        choices = {
            choice.get("from_name"): next(iter(choice.get("value", {}).get("choices", [])), None)
            for choice in regions
            if choice.get("id") == region_id and choice.get("type") == "choices"
        }
        semantic = next(
            (
                text
                for text_box in regions
                if text_box.get("id") == region_id and text_box.get("type") == "textarea"
                for text in text_box.get("value", {}).get("text", [])
            ),
            None,
        )
        text = value.get("text", "")
        result.append(
            ModelSpan(
                text=text,
                start=value["start"],
                end=value["end"],
                label=label,
                source_domain=choices.get("source_domain") or "unknown",
                target_domain=choices.get("target_domain") or "unknown",
                confidence=float(prediction.get("score", 0.5)),
                rationale="Первичная автоматическая разметка GPT; требуется проверка.",
                entity=text,
                entity_type="other",
                semantic_label=semantic,
                sentiment=choices.get("sentiment") or "neutral",
            )
        )
    selected = []
    for span in sorted(result, key=lambda item: (item.start, item.end)):
        if selected and span.start < selected[-1].end:
            continue
        selected.append(span)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--consensus", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--train-output", type=Path, required=True)
    parser.add_argument("--control-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    consensus = {record.id: record for record in read_corpus(args.consensus)}
    audit = json.loads(args.audit.read_text(encoding="utf-8"))["items"]
    control_ids = {
        item["id"]
        for item in audit
        if item["status"] in {"consensus_positive", "consensus_negative"}
    }
    control = [consensus[record_id] for record_id in sorted(control_ids)]
    train = []
    for task in tasks:
        source = Poem.model_validate(task["data"])
        if source.id in control_ids:
            continue
        train.append(
            source.model_copy(
                update={
                    "annotation_status": "draft",
                    "annotators": ["OpenAI first-pass prediction"],
                    "adjudicator": "weak supervision; not human adjudicated",
                    "spans": first_pass_spans(task),
                }
            )
        )
    write_corpus(args.train_output, train)
    write_corpus(args.control_output, control)
    report = {
        "supervision": "silver-pilot",
        "train_records": len(train),
        "control_records": len(control),
        "control_warning": "Model-consensus control is not an independent Gold evaluation set.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
