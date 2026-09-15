"""JSONL corpus, immutable annotated text and leakage checks."""

import hashlib
import json
import random
import re
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.nlp.contracts import ModelSpan, validate_spans


class Poem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    # Original work ID: all excerpts, variants and translations share this ID.
    work_id: str = Field(min_length=1)
    language: Literal["zh", "kk"]
    text: str = Field(min_length=1)
    title: str
    author: str
    source_url: str = Field(min_length=1)
    license: str = Field(min_length=1)
    license_verified: bool = False
    era: str = "unknown"
    genre: str = "poetry"
    synthetic: bool = False
    annotation_status: Literal["unlabeled", "draft", "gold"] = "unlabeled"
    annotators: list[str] = Field(default_factory=list)
    adjudicator: str | None = None
    spans: list[ModelSpan] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_annotation(self):
        if not self.text.strip():
            raise ValueError("Empty poem")
        validate_spans(self.text, self.spans)
        if self.annotation_status == "unlabeled" and self.spans:
            raise ValueError("Unlabeled record cannot contain spans")
        if self.annotation_status == "gold" and (not self.annotators or not self.adjudicator):
            raise ValueError("Gold requires annotators and an adjudicator, including negatives")
        return self


def read_corpus(path: str | Path) -> list[Poem]:
    records = []
    ids = set()
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = Poem.model_validate_json(line)
            if record.id in ids:
                raise ValueError(f"Duplicate ID {record.id}")
        except ValueError as exc:
            raise ValueError(f"{path}:{number}: {exc}") from exc
        ids.add(record.id)
        records.append(record)
    if not records:
        raise ValueError("Corpus is empty")
    return records


def write_corpus(path: str | Path, records: list[Poem]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8")


def fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFC", text))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def clean_corpus(records: list[Poem]) -> tuple[list[Poem], list[dict]]:
    clean, report, seen = [], [], {}
    for record in records:
        text = record.text
        if record.annotation_status == "unlabeled":
            text = unicodedata.normalize("NFC", text.removeprefix("\ufeff"))
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
        key = (record.language, fingerprint(text))
        if key in seen:
            # Do not silently throw away potentially conflicting human annotations.
            if (
                record.annotation_status != "unlabeled"
                or seen[key].annotation_status != "unlabeled"
            ):
                raise ValueError(f"Annotated duplicate: {record.id}, {seen[key].id}")
            report.append({"removed": record.id, "duplicate_of": seen[key].id})
            continue
        item = Poem.model_validate({**record.model_dump(), "text": text})
        seen[key] = item
        clean.append(item)
    return clean, report


def require_gold(records: list[Poem], allow_synthetic: bool = False) -> None:
    if not records:
        raise ValueError("Empty gold set")
    for record in records:
        if record.annotation_status != "gold":
            raise ValueError(f"{record.id}: adjudicated gold annotation required")
        if record.synthetic and not allow_synthetic:
            raise ValueError("Synthetic examples are for smoke tests, not research training")
        if not record.license_verified:
            raise ValueError(f"{record.id}: verify and record source license first")


def assert_disjoint(*splits: list[Poem]) -> None:
    seen_ids, seen_works, seen_texts = set(), set(), set()
    for records in splits:
        ids = {r.id for r in records}
        works = {r.work_id for r in records}
        texts = {fingerprint(r.text) for r in records}
        if seen_ids & ids or seen_works & works or seen_texts & texts:
            raise ValueError("Data leakage: IDs, original works or duplicate texts cross splits")
        seen_ids |= ids
        seen_works |= works
        seen_texts |= texts


def split_corpus(records: list[Poem], seed: int = 42) -> dict[str, list[Poem]]:
    groups = {}
    for record in records:
        groups.setdefault(record.work_id, []).append(record)
    keys = sorted(groups)
    if len(keys) < 3:
        raise ValueError("Need at least three independent works")
    random.Random(seed).shuffle(keys)
    n_test = max(1, round(len(keys) * 0.15))
    n_val = max(1, round(len(keys) * 0.15))
    partitions = (keys[n_test + n_val :], keys[n_test : n_test + n_val], keys[:n_test])
    result = {
        name: [r for key in keys_ for r in groups[key]]
        for name, keys_ in zip(("train", "validation", "test"), partitions)
    }
    assert_disjoint(*result.values())
    return result


def manifest(records: list[Poem]) -> dict:
    raw = "\n".join(r.model_dump_json() for r in sorted(records, key=lambda r: r.id))
    return {
        "sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "records": len(records),
        "ids": [r.id for r in records],
    }


def save_json(path: str | Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
