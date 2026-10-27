"""Score predictions against Zhu Xi's stanza labels (see scripts/extract_zhuxi.py).

A stanza is predicted figurative when a predicted figure overlaps it. Zhu Xi's 比 and 興
are the positive class, 賦 the negative one. Reported per label: how many 比 and 興
stanzas got a figure (recall) and how many 賦 stanzas got one anyway (false alarms).

    python -m scripts.eval_zhuxi data/processed/zhuxi/pred-xlmr.json [more.json ...]
"""

import argparse
import json
from pathlib import Path

from app.nlp.evaluation import cohen_kappa

STANZAS = Path("data/processed/zhuxi/shijing_zhuxi_stanzas.jsonl")


def flagged(prediction: dict, stanza: dict) -> bool:
    return any(
        m["start"] < stanza["end"] and m["end"] > stanza["start"]
        for m in prediction.get("metaphors", [])
    )


def score(stanzas: list[dict], predictions: dict) -> dict:
    rows = [(s, flagged(predictions[s["poem_id"]], s)) for s in stanzas]
    gold = [s["figurative"] for s, _ in rows]
    predicted = [p for _, p in rows]
    tp = sum(g and p for g, p in zip(gold, predicted, strict=True))
    fp = sum(p and not g for g, p in zip(gold, predicted, strict=True))
    fn = sum(g and not p for g, p in zip(gold, predicted, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0

    def share(kind):
        hits = [p for s, p in rows if kind(s["label"])]
        return {"stanzas": len(hits), "flagged": sum(hits), "rate": sum(hits) / len(hits)}

    return {
        "stanzas": len(rows),
        "figurative_precision": precision,
        "figurative_recall": recall,
        "figurative_f1": 2 * precision * recall / (precision + recall) if tp else 0.0,
        "accuracy": sum(g == p for g, p in zip(gold, predicted, strict=True)) / len(rows),
        "cohen_kappa_vs_zhuxi": cohen_kappa(gold, predicted),
        "bi_flagged": share(lambda label: "比" in label),
        "xing_flagged": share(lambda label: "興" in label and "比" not in label),
        "fu_flagged_false_alarm": share(lambda label: label == "賦"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", nargs="+")
    parser.add_argument("--output", default="data/processed/zhuxi/evaluation.json")
    args = parser.parse_args()
    stanzas = [json.loads(line) for line in STANZAS.read_text(encoding="utf-8").splitlines()]
    report = {}
    for path in args.predictions:
        predictions = json.loads(Path(path).read_text(encoding="utf-8"))
        ok = {k for k, v in predictions.items() if "error" not in v}
        subset = [s for s in stanzas if s["poem_id"] in ok]
        report[Path(path).stem] = score(subset, predictions)
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
