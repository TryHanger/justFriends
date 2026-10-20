#!/usr/bin/env python3
"""Create Label Studio tasks with GPT metaphor suggestions.

The generated regions are Label Studio *predictions*, never human annotations.
They are deliberately kept separate from Gold data: an annotator must review and
submit every suggestion before it can be exported as a draft annotation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.nlp.__main__ import make_pipeline
from app.nlp.corpus import read_corpus


def prediction_result(analysis) -> list[dict]:
    """Convert validated NLP spans into the supplied Label Studio XML format."""
    result: list[dict] = []
    for index, span in enumerate(analysis.metaphors):
        region_id = f"gpt-figure-{index}"
        result.append(
            {
                "id": region_id,
                "type": "labels",
                "from_name": "figure",
                "to_name": "poem",
                "value": {
                    "start": span.start,
                    "end": span.end,
                    "text": span.text,
                    "labels": [span.label],
                },
            }
        )
        for name, value in (
            ("source_domain", span.source_domain),
            ("target_domain", span.target_domain),
            ("sentiment", span.sentiment),
        ):
            if value:
                result.append(
                    {
                        "id": region_id,
                        "type": "choices",
                        "from_name": name,
                        "to_name": "poem",
                        "value": {"choices": [value]},
                    }
                )
        if span.semantic_label:
            result.append(
                {
                    "id": region_id,
                    "type": "textarea",
                    "from_name": "semantic_label",
                    "to_name": "poem",
                    "value": {"text": [span.semantic_label]},
                }
            )
    return result


def load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON task list")
    return payload


def save(path: Path, tasks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Clean JSONL corpus")
    parser.add_argument("--output", required=True, help="Label Studio task JSON")
    parser.add_argument("--limit", type=int, help="Maximum number of new records")
    args = parser.parse_args()

    output = Path(args.output)
    tasks = load_existing(output)
    completed = {task.get("data", {}).get("id") for task in tasks}
    records = [record for record in read_corpus(args.input) if record.id not in completed]
    if args.limit is not None:
        records = records[: args.limit]

    pipeline = make_pipeline("openai", "zero_shot")
    # The review UI consumes spans and their domains, not free-text rationales.
    # Avoid a second provider call solely to force a Russian rationale: on Chinese
    # poems this validation can reject an otherwise valid structured prediction.
    pipeline.detector._ensure_russian = lambda result: result
    total = len(records)
    for number, record in enumerate(records, 1):
        analysis = pipeline.analyze(record.text, record.language)
        regions = prediction_result(analysis)
        tasks.append(
            {
                "data": record.model_dump(),
                "predictions": [
                    {
                        "model_version": analysis.model_version,
                        "score": (
                            sum(span.confidence for span in analysis.metaphors)
                            / len(analysis.metaphors)
                            if analysis.metaphors
                            else 0.0
                        ),
                        "result": regions,
                    }
                ],
            }
        )
        # Persist after every provider call: safe to resume after an interruption.
        save(output, tasks)
        print(f"[{number}/{total}] {record.id}: {len(analysis.metaphors)} predictions")

    print(f"Wrote {len(tasks)} Label Studio tasks to {output}")


if __name__ == "__main__":
    main()
