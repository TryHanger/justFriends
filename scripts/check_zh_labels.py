"""Validate Claude's silver labels for the classical Chinese poetry batch.

Checks that every input poem has exactly one label record in the same order, that span
offsets are Python code-point offsets matching the span text, that spans hold no
punctuation or whitespace and do not overlap, that labels and domains belong to the
taxonomy, and that a non-empty tenor is quoted from the poem. Prints counts on success.

    python -m scripts.check_zh_labels
    python -m scripts.check_zh_labels --poems annotation/zh_poetry_tang300_to_label.jsonl \
        --labels annotation/zh_poetry_tang300_claude_labels.jsonl
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from app.schemas.taxonomy import DOMAINS, LABELS

POEMS = Path("annotation/zh_poetry_to_label.jsonl")
LABELS_FILE = Path("annotation/zh_poetry_claude_labels.jsonl")
FIELDS = set("text start end label source_domain target_domain tenor ground rationale".split())
PUNCT = set("，。；：、！？,.;:!?「」『』《》（）()·…—\"'“”‘’")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def check_span(text: str, span: dict) -> list[str]:
    if set(span) != FIELDS:
        return [f"fields {sorted(set(span) ^ FIELDS)} differ from the schema"]
    errors = []
    start, end = span["start"], span["end"]
    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)):
        return [f"bad offsets {start}..{end}"]
    if text[start:end] != span["text"]:
        errors.append(f"text {span['text']!r} != poem[{start}:{end}] {text[start:end]!r}")
    if any(ch in PUNCT or ch.isspace() for ch in span["text"]):
        errors.append(f"span {span['text']!r} contains punctuation or whitespace")
    if span["label"] not in LABELS:
        errors.append(f"label {span['label']!r} not in taxonomy")
    for key in ("source_domain", "target_domain"):
        if span[key] not in DOMAINS:
            errors.append(f"{key} {span[key]!r} not in taxonomy")
    if span["tenor"] and span["tenor"] not in text:
        errors.append(f"tenor {span['tenor']!r} not found in the poem")
    for key in ("ground", "rationale"):
        if not isinstance(span[key], str) or not span[key].strip():
            errors.append(f"empty {key}")
    return errors


def check(poems: list[dict], records: list[dict]) -> list[str]:
    errors = []
    if len(poems) != len(records):
        errors.append(f"{len(records)} label records for {len(poems)} poems")
    for i, (poem, record) in enumerate(zip(poems, records, strict=False), 1):
        where = f"line {i} ({poem['id']})"
        if set(record) != {"id", "spans"}:
            errors.append(f"{where}: record keys {sorted(record)}")
            continue
        if record["id"] != poem["id"]:
            errors.append(f"{where}: id {record['id']} out of order")
            continue
        previous = None
        for span in sorted(record["spans"], key=lambda s: (s.get("start", 0), s.get("end", 0))):
            errors += [f"{where}: {e}" for e in check_span(poem["text"], span)]
            if previous and span.get("start", 0) < previous.get("end", 0):
                errors.append(f"{where}: {previous['text']!r} overlaps {span['text']!r}")
            previous = span
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poems", type=Path, default=POEMS)
    parser.add_argument("--labels", type=Path, default=LABELS_FILE)
    args = parser.parse_args()
    poems, records = read_jsonl(args.poems), read_jsonl(args.labels)
    errors = check(poems, records)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(f"{len(errors)} error(s)")
    eras = {p["id"]: p["era"] for p in poems}
    spans = [(eras[r["id"]], s) for r in records for s in r["spans"]]
    figured = Counter(eras[r["id"]] for r in records if r["spans"])
    summary = {
        "poems": len(poems),
        "poems_with_figures": sum(figured.values()),
        "poems_with_figures_by_era": dict(figured),
        "spans": len(spans),
        "spans_by_label": dict(Counter(s["label"] for _, s in spans).most_common()),
        "spans_by_era": dict(Counter(era for era, _ in spans)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
