"""Convert the MIT-licensed CMDAG splits to the project's immutable gold corpus format.

CMDAG records annotate a tenor--vehicle pair in Chinese context.  This detector
training conversion marks literal occurrences of the annotated *vehicle* as
metaphor spans.  It deliberately never fuzzy-matches a vehicle: changing a
character boundary would make the resulting BIO labels unverifiable.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from app.nlp.contracts import ModelSpan
from app.nlp.corpus import Poem, fingerprint, write_corpus
from app.nlp.llm import locate_tenor

CMDAG_REPOSITORY = "https://github.com/JasonShao55/Chinese_Metaphor_Explanation"
SPLITS = {
    "train": "train_data.json",
    "validation": "val_data.json",
    "test": "test_data.json",
}


def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def vehicle_spans(context: str, rows: list[dict]) -> tuple[list[ModelSpan], int, int]:
    spans: list[ModelSpan] = []
    missing = overlapping = 0
    for row in rows:
        vehicle = row.get("vehicle", "").strip()
        if not vehicle:
            missing += 1
            continue
        start = context.find(vehicle)
        if start < 0:
            missing += 1
            continue
        end = start + len(vehicle)
        if any(start < item.end and end > item.start for item in spans):
            overlapping += 1
            continue
        ground = " ".join(row.get("ground", "").split())
        tenor = " ".join(row.get("tenor", "").split()) or None
        # Tenor offsets only for a literal occurrence; an implicit tenor keeps text only.
        tenor_bounds = locate_tenor(context, tenor, start, end) if tenor else None
        rationale = "Внешняя экспертная разметка CMDAG."
        if ground:
            rationale += f" Основание сопоставления: {ground}."
        spans.append(
            ModelSpan(
                text=vehicle,
                start=start,
                end=end,
                label="metaphor",
                source_domain="unknown",
                target_domain="unknown",
                confidence=1.0,
                rationale=rationale,
                tenor=tenor,
                tenor_start=tenor_bounds[0] if tenor_bounds else None,
                tenor_end=tenor_bounds[1] if tenor_bounds else None,
                ground=ground or None,
            )
        )
    return sorted(spans, key=lambda item: (item.start, item.end)), missing, overlapping


def convert_split(rows: list[dict], excluded_fingerprints: set[str]) -> tuple[list[Poem], dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        context = " ".join(row["context"].split())
        if context and fingerprint(context) not in excluded_fingerprints:
            grouped[context].append(row)

    records, missing, overlapping, skipped_empty = [], 0, 0, 0
    for context, group in grouped.items():
        spans, absent, conflict = vehicle_spans(context, group)
        missing += absent
        overlapping += conflict
        # Detection training needs positive contexts; retaining unlabelled negatives here
        # would falsely label known metaphors whose exact boundaries were unavailable.
        if not spans:
            skipped_empty += 1
            continue
        key = stable_id(context)
        records.append(
            Poem(
                id=f"cmdag-{key}",
                work_id=f"cmdag-work-{key}",
                language="zh",
                text=context,
                title="CMDAG annotated context",
                author="unknown",
                source_url=CMDAG_REPOSITORY,
                license="MIT (CMDAG repository)",
                license_verified=True,
                era="unknown",
                genre="metaphor context",
                annotation_status="gold",
                annotators=["CMDAG expert annotation"],
                adjudicator="CMDAG dataset release",
                spans=spans,
            )
        )
    return records, {
        "input_pairs": len(rows),
        "unique_contexts": len(grouped),
        "records_written": len(records),
        "vehicle_not_literal_in_context": missing,
        "overlapping_vehicle_spans_skipped": overlapping,
        "contexts_without_usable_positive_span": skipped_empty,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, required=True, help="CMDAG Data/Splited Data directory"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = {
        name: json.loads((args.input / filename).read_text(encoding="utf-8"))
        for name, filename in SPLITS.items()
    }
    # A context appears in more than one upstream split in a few cases.  Keep the
    # earliest split only so evaluation cannot see training text.
    seen_context_fingerprints: set[str] = set()
    report = {"source": CMDAG_REPOSITORY, "license": "MIT", "splits": {}}
    for name in ("train", "validation", "test"):
        fingerprints = {
            fingerprint(" ".join(row["context"].split()))
            for row in raw[name]
            if row["context"].strip()
        }
        records, stats = convert_split(raw[name], seen_context_fingerprints)
        write_corpus(args.output / f"{name}.jsonl", records)
        report["splits"][name] = {
            **stats,
            "cross_split_contexts_excluded": len(fingerprints & seen_context_fingerprints),
        }
        seen_context_fingerprints |= fingerprints
    (args.output / "conversion_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
