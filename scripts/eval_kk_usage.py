"""Score models on the dictionary usage set (scripts/build_kk_usage_set.py).

`prepare` writes the quotations as a corpus (all of them, plus a class-balanced sample
for paid LLMs); run any backend over it with scripts/kk_ensemble_predict.py. `score`
counts the headword as used metaphorically when a predicted figure overlaps it and
compares with the dictionary's «ауыс.» decision.

The pipeline runs in two-stage mode for Kazakh by default (docs/NLP.md); for such runs the
report adds `two_stage`: how often the headword was among the judged candidates and how
stage 2 decided it. Compare with the single pass by running it with the mode switched off:

    NLP_TWO_STAGE_LANGUAGES= python -m scripts.kk_ensemble_predict --input \
        data/processed/kk_usage/sample.jsonl --backend openai \
        --output data/processed/kk_usage/pred-gpt-4o-mini-one-stage.json

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


def _usage_scores(gold: list[bool], predicted: list[bool]) -> dict:
    pairs = list(zip(gold, predicted, strict=True))
    tp = sum(g and p for g, p in pairs)
    fp = sum(p and not g for g, p in pairs)
    fn = sum(g and not p for g, p in pairs)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "quotations": len(pairs),
        "metaphorical": sum(gold),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if tp else 0.0,
        "accuracy": sum(g == p for g, p in pairs) / len(pairs) if pairs else None,
        "cohen_kappa_vs_dictionary": cohen_kappa(gold, predicted) if pairs else None,
    }


def evaluate_predictions(records: dict, predictions: dict) -> dict:
    """Headword usage from predicted figures; for two-stage runs also stage-2 diagnostics."""
    gold, predicted, judged = [], [], []
    tokens, two_stage = [], {}
    for poem_id, result in predictions.items():
        if "error" in result:
            continue
        record = records[poem_id]

        def overlaps(item, record=record):
            return item["start"] < record["end"] and item["end"] > record["start"]

        gold.append(record["usage_type"] == "metaphorical")
        predicted.append(any(overlaps(m) for m in result["metaphors"]))
        method = result.get("method", {})
        stage = method.get("two_stage")
        usage = [method.get("usage") or {}, (stage or {}).get("usage") or {}]
        tokens.append(
            [sum(u.get(key, 0) for u in usage) for key in ("input_tokens", "output_tokens")]
        )
        if stage:
            two_stage.setdefault("model", stage["model"])
            # Stage 2 judges candidates only: a headword missing from them cannot be fixed.
            heads = [c for c in result.get("candidates", []) if overlaps(c) and c["usage_type"]]
            judged.append((gold[-1], predicted[-1], heads))
    literal = [p for g, p in zip(gold, predicted, strict=True) if not g]
    report = {
        **_usage_scores(gold, predicted),
        "false_alarm_on_literal": sum(literal) / len(literal) if literal else None,
        "mean_tokens": [sum(t[i] for t in tokens) / len(tokens) for i in (0, 1)]
        if tokens
        else None,
    }
    if two_stage:
        # Figures whose head word stage 2 judged literal are kept with a warning, so the score
        # above still counts them; here stage 2 decides wherever it judged the headword.
        decided = [
            (g, any(c["usage_type"] == "metaphorical" for c in heads) if heads else figure)
            for g, figure, heads in judged
        ]
        covered = [pair for pair, (_, _, heads) in zip(decided, judged, strict=True) if heads]
        two_stage["headword_is_candidate"] = len(covered) / len(judged)
        # Comparable with scripts/eval_kk_usage_direct.py on the same quotations.
        two_stage["stage_2_decides"] = _usage_scores(
            [g for g, _ in decided], [p for _, p in decided]
        )
        two_stage["headword_candidates_only"] = _usage_scores(
            [g for g, _ in covered], [p for _, p in covered]
        )
        report["two_stage"] = two_stage
    return report


def score(paths: list[str]) -> None:
    records = {r["id"]: r for r in load()}
    report = {
        Path(path).stem: evaluate_predictions(
            records, json.loads(Path(path).read_text(encoding="utf-8"))
        )
        for path in paths
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
