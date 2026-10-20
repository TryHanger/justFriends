#!/usr/bin/env python3
"""Build a reproducible Chinese-Gold + Kazakh-Silver training corpus.

This does not upgrade Silver labels to Gold.  Chinese validation remains Gold,
while Kazakh Silver control is kept separate for diagnostic-only reporting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.nlp.corpus import assert_disjoint, manifest, read_corpus, write_corpus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zh-train", type=Path, required=True)
    parser.add_argument("--zh-validation", type=Path, required=True)
    parser.add_argument("--kk-silver-train", type=Path, required=True)
    parser.add_argument("--kk-silver-control", type=Path, required=True)
    parser.add_argument("--train-output", type=Path, required=True)
    parser.add_argument("--validation-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    zh_train = read_corpus(args.zh_train)
    zh_validation = read_corpus(args.zh_validation)
    kk_train = read_corpus(args.kk_silver_train)
    kk_control = read_corpus(args.kk_silver_control)
    train = [*zh_train, *kk_train]
    assert_disjoint(train, zh_validation, kk_control)
    write_corpus(args.train_output, train)
    write_corpus(args.validation_output, zh_validation)
    report = {
        "supervision": "mixed-gold-silver-pilot",
        "training": {
            "zh_gold": len(zh_train),
            "kk_silver": len(kk_train),
            "total": len(train),
            "manifest": manifest(train),
        },
        "validation": {
            "zh_gold": len(zh_validation),
            "manifest": manifest(zh_validation),
        },
        "kazakh_diagnostic_control": {
            "records": len(kk_control),
            "warning": "Model-consensus Silver only; not an independent Gold evaluation.",
            "manifest": manifest(kk_control),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"train_records": len(train), "zh_validation": len(zh_validation), "kk_control": len(kk_control)}))


if __name__ == "__main__":
    main()
