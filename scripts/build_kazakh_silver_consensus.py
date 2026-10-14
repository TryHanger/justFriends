#!/usr/bin/env python3
"""Create a resumable two-pass *Silver* consensus corpus for Kazakh poetry.

This script intentionally writes ``draft`` records.  Two model passes are useful
for prioritising reliable examples, but they are not a substitute for independent
human annotation and must never be relabelled as Gold.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.nlp.__main__ import make_pipeline
from app.nlp.corpus import Poem, read_corpus, write_corpus
from app.schemas.taxonomy import METAPHOR_LABELS


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def primary_spans(task: dict) -> list[dict]:
    """Read only exact, positive regions from the first-pass Label Studio prediction."""
    predictions = task.get("predictions", [])
    if not predictions:
        return []
    spans = []
    for item in predictions[0].get("result", []):
        if item.get("type") != "labels":
            continue
        value = item.get("value", {})
        label = next(iter(value.get("labels", [])), None)
        if label not in METAPHOR_LABELS:
            continue
        spans.append(
            {
                "text": value.get("text", ""),
                "start": value.get("start"),
                "end": value.get("end"),
                "label": label,
            }
        )
    return sorted(spans, key=lambda item: (item["start"], item["end"], item["label"]))


def positive_spans(analysis) -> list:
    return [span for span in analysis.metaphors if span.label in METAPHOR_LABELS]


def non_overlapping(spans: list) -> list:
    selected = []
    for span in sorted(spans, key=lambda item: (item.start, item.end)):
        if selected and span.start < selected[-1].end:
            continue
        selected.append(span)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True, help="First-pass Label Studio task JSON")
    parser.add_argument("--output", type=Path, required=True, help="Silver draft JSONL")
    parser.add_argument("--audit", type=Path, required=True, help="Two-pass provenance JSON")
    parser.add_argument("--strategy", default="few_shot+cot+rag+lexicon")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    tasks = load_json(args.tasks, [])
    if not isinstance(tasks, list):
        raise ValueError("--tasks must be a Label Studio task JSON array")
    existing = {record.id: record for record in read_corpus(args.output)} if args.output.exists() else {}
    audit = load_json(args.audit, {"kind": "kazakh_silver_two_pass_consensus", "items": []})
    audited = {item["id"] for item in audit["items"]}

    pipeline = make_pipeline("openai", args.strategy)
    # The corpus stores spans and provenance; forcing a second translation-only call
    # would increase cost without changing the consensus decision.
    pipeline.detector._ensure_russian = lambda result: result

    pending = [task for task in tasks if task["data"]["id"] not in audited]
    if args.limit is not None:
        pending = pending[: args.limit]
    total = len(pending)

    for number, task in enumerate(pending, 1):
        source = Poem.model_validate(task["data"])
        first = primary_spans(task)
        review, review_error = None, None
        try:
            review = pipeline.analyze(source.text, "kk")
            review_spans = positive_spans(review)
            first_keys = {(span["start"], span["end"], span["label"]) for span in first}
            accepted = non_overlapping(
                [
                    span
                    for span in review_spans
                    if (span.start, span.end, span.label) in first_keys
                ]
            )
            if not first and not review_spans:
                status = "consensus_negative"
            elif accepted:
                status = "consensus_positive"
            else:
                status = "disagreement"
        except ValueError as exc:
            # Invalid provider output (for example overlapping spans) must not
            # silently become a negative example or stop a resumable run.
            review_error = str(exc)
            review_spans, accepted, status = [], [], "review_invalid"
        record = source.model_copy(
            update={
                "annotation_status": "draft",
                "annotators": ["OpenAI first-pass prediction", "OpenAI independent review pass"],
                "adjudicator": "two-pass model consensus; human review pending",
                "spans": accepted,
                "candidates": [],
            }
        )
        existing[record.id] = record
        audit["items"].append(
            {
                "id": record.id,
                "status": status,
                "first_pass": first,
                "review_pass": [span.model_dump() for span in review_spans],
                "accepted": [span.model_dump() for span in accepted],
                "review_model": getattr(review, "model_version", pipeline.detector.model_version),
                "review_method": getattr(review, "method", {"strategy": args.strategy}),
                "review_error": review_error,
            }
        )
        write_corpus(args.output, list(existing.values()))
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{number}/{total}] {record.id}: {status}, accepted={len(accepted)}", flush=True)

    summary = {
        key: sum(item["status"] == key for item in audit["items"])
        for key in ("consensus_positive", "consensus_negative", "disagreement", "review_invalid")
    }
    print(json.dumps({"records": len(existing), **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
