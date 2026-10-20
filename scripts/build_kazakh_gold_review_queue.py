#!/usr/bin/env python3
"""Create a balanced *human-review queue*, never an automatic Gold corpus.

The queue combines model-consensus positives/negatives with disagreement cases.
After two native-speaker annotations and adjudication it can be exported from
Label Studio and imported as Gold through ``app.nlp label-studio-import``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()
    if args.count < 50:
        parser.error("Use at least 50 records for a meaningful initial review queue")

    tasks = {item["data"]["id"]: item for item in json.loads(args.tasks.read_text(encoding="utf-8"))}
    audit = json.loads(args.audit.read_text(encoding="utf-8"))["items"]
    groups = {
        status: [item["id"] for item in audit if item["status"] == status]
        for status in ("consensus_positive", "consensus_negative", "disagreement")
    }
    selected = [*groups["consensus_positive"], *groups["consensus_negative"]]
    remaining = args.count - len(selected)
    selected.extend(groups["disagreement"][:remaining])
    if len(selected) < args.count:
        raise ValueError(f"Only {len(selected)} reviewable records are available")

    output = []
    for position, record_id in enumerate(selected, 1):
        task = tasks[record_id]
        status = next(item["status"] for item in audit if item["id"] == record_id)
        output.append(
            {
                "data": {
                    **task["data"],
                    "review_queue": "kk-gold-candidate-v1",
                    "review_priority": "consensus" if status.startswith("consensus") else "disagreement",
                    "review_note": "Human annotation required; do not treat prediction as Gold.",
                    "queue_position": position,
                },
                "predictions": task.get("predictions", []),
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "tasks": len(output),
                "composition": {
                    "consensus_positive": len(groups["consensus_positive"]),
                    "consensus_negative": len(groups["consensus_negative"]),
                    "disagreement": remaining,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
