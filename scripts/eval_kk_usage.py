"""Score models on the dictionary usage set (scripts/build_kk_usage_set.py).

`prepare` writes the quotations as a corpus (all of them, plus a class-balanced sample
for paid LLMs); run any backend over it with scripts/kk_ensemble_predict.py. `score`
counts the headword as used metaphorically when a predicted figure overlaps it and
compares with the dictionary's «ауыс.» decision.

    python -m scripts.eval_kk_usage prepare --sample 80
    python -m scripts.kk_ensemble_predict --input data/processed/kk_usage/sample.jsonl \
        --backend openai --output data/processed/kk_usage/pred-gpt-4o-mini.json
    python -m scripts.eval_kk_usage score data/processed/kk_usage/pred-*.json
"""

import argparse
import json
import random
from pathlib import Path

from app.nlp.corpus import Poem, write_corpus
from app.nlp.evaluation import cohen_kappa

ROOT = Path("data/processed/kk_usage")
SET = ROOT / "kk_usage_dictionary.jsonl"
LICENSE = "Copyrighted dictionary quotations; research evaluation only, do not redistribute"


def load() -> list[dict]:
    return [json.loads(line) for line in SET.read_text(encoding="utf-8").splitlines()]


def poem(record: dict) -> Poem:
    return Poem(
        id=record["id"],
        work_id=f"kkdict-{record['headword']}",
        language="kk",
        text=record["text"],
        title=f"{record['headword']} ({record['citation']})",
        author="unknown",
        source_url=record["entry_url"],
        license=LICENSE,
        license_verified=False,
        era="unknown",
        genre="dictionary-quotation",
    )


def prepare(sample: int, seed: int) -> None:
    records = load()
    write_corpus(ROOT / "all.jsonl", [poem(r) for r in records])
    chosen = []
    for usage in ("metaphorical", "literal"):
        group = [r for r in records if r["usage_type"] == usage]
        chosen += random.Random(seed).sample(group, min(sample, len(group)))
    write_corpus(ROOT / "sample.jsonl", [poem(r) for r in sorted(chosen, key=lambda r: r["id"])])
    print(f"all: {len(records)}, balanced sample: {len(chosen)}")


def score(paths: list[str]) -> None:
    records = {r["id"]: r for r in load()}
    report = {}
    for path in paths:
        predictions = json.loads(Path(path).read_text(encoding="utf-8"))
        gold, predicted = [], []
        for poem_id, result in predictions.items():
            if "error" in result:
                continue
            record = records[poem_id]
            gold.append(record["usage_type"] == "metaphorical")
            predicted.append(
                any(
                    m["start"] < record["end"] and m["end"] > record["start"]
                    for m in result["metaphors"]
                )
            )
        pairs = list(zip(gold, predicted, strict=True))
        tp = sum(g and p for g, p in pairs)
        fp = sum(p and not g for g, p in pairs)
        fn = sum(g and not p for g, p in pairs)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        literal = [p for g, p in pairs if not g]
        report[Path(path).stem] = {
            "quotations": len(pairs),
            "metaphorical": sum(gold),
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if tp else 0.0,
            "accuracy": sum(g == p for g, p in pairs) / len(pairs),
            "cohen_kappa_vs_dictionary": cohen_kappa(gold, predicted),
            "false_alarm_on_literal": sum(literal) / len(literal) if literal else None,
        }
    (ROOT / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--sample", type=int, default=80, help="quotations per class")
    prep.add_argument("--seed", type=int, default=0)
    sc = commands.add_parser("score")
    sc.add_argument("predictions", nargs="+")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.sample, args.seed)
    else:
        score(args.predictions)


if __name__ == "__main__":
    main()
