"""Fit confidence calibration of an LLM on expert data (see app/nlp/calibration.py).

A predicted figure counts as correct
* zh: when it overlaps a gold figure of the CMDAG test sample;
* kk: when it overlaps the headword of a dictionary quotation whose sense is «ауыс.»
  (figures elsewhere in the quotation cannot be judged and are skipped).
Platt scaling p = sigmoid(a * logit(confidence) + b) is fitted per language; ECE after
calibration is estimated by 5-fold cross-validation, never on the fitting data.

    python -m scripts.calibrate_llm
"""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from app.nlp.calibration import _logit
from app.nlp.corpus import read_corpus
from app.nlp.usage import added_figures

OUTPUT = Path("data/calibration/llm.json")
MIN_SPANS = 30


def raw(result: dict) -> list[float | None]:
    """Self-reported confidences: runs made with calibration on store them separately.

    None for figures added by the two-stage judge: their confidence is a placeholder."""
    calibration = result.get("method", {}).get("calibration")
    values = (
        calibration["raw_confidence"]
        if calibration
        else [m["confidence"] for m in result["metaphors"]]
    )
    added = added_figures(result.get("method", {}))
    return [
        None if (m["start"], m["end"]) in added else value
        for m, value in zip(result["metaphors"], values, strict=True)
    ]


def zh_pairs(predictions: str, gold: str) -> list[tuple[float, int]]:
    records = {r.id: r for r in read_corpus(gold)}
    pairs = []
    for poem_id, result in json.loads(Path(predictions).read_text(encoding="utf-8")).items():
        if "error" in result:
            continue
        spans = records[poem_id].spans
        for m, confidence in zip(result["metaphors"], raw(result), strict=True):
            if confidence is None:
                continue
            hit = any(m["start"] < g.end and m["end"] > g.start for g in spans)
            pairs.append((confidence, int(hit)))
    return pairs


def kk_pairs(predictions: str, dictionary: str) -> list[tuple[float, int]]:
    records = {}
    for line in Path(dictionary).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        records[record["id"]] = record
    pairs = []
    for quote_id, result in json.loads(Path(predictions).read_text(encoding="utf-8")).items():
        if "error" in result:
            continue
        record = records[quote_id]
        for m, confidence in zip(result["metaphors"], raw(result), strict=True):
            if confidence is not None and m["start"] < record["end"] and m["end"] > record["start"]:
                pairs.append((confidence, int(record["usage_type"] == "metaphorical")))
    return pairs


def ece(confidence, correct, bins: int = 10) -> float:
    confidence, correct = np.asarray(confidence), np.asarray(correct)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for low, high in zip(edges[:-1], edges[1:], strict=True):
        mask = (confidence > low) & (confidence <= high)
        if mask.any():
            total += mask.mean() * abs(confidence[mask].mean() - correct[mask].mean())
    return float(total)


def fit(pairs: list[tuple[float, int]], source: str) -> dict:
    x = np.array([[_logit(c)] for c, _ in pairs])
    y = np.array([k for _, k in pairs])
    model = LogisticRegression(C=100.0).fit(x, y)
    held_out = np.zeros(len(y))
    for train, test in StratifiedKFold(5, shuffle=True, random_state=0).split(x, y):
        held_out[test] = (
            LogisticRegression(C=100.0).fit(x[train], y[train]).predict_proba(x[test])[:, 1]
        )
    raw = [c for c, _ in pairs]
    return {
        "a": float(model.coef_[0][0]),
        "b": float(model.intercept_[0]),
        "source": source,
        "spans": len(pairs),
        "precision": float(y.mean()),
        "mean_self_reported": float(np.mean(raw)),
        "ece_before": ece(raw, y),
        "ece_after": ece(held_out, y),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="openai:gpt-4o-mini")
    parser.add_argument("--zh", default="data/processed/calibration/pred-gpt-4o-mini-cmdag200.json")
    parser.add_argument("--zh-gold", default="data/processed/calibration/cmdag_test200.jsonl")
    parser.add_argument("--kk", default="data/processed/kk_usage/pred-gpt-4o-mini.json")
    parser.add_argument(
        "--kk-dictionary", default="data/processed/kk_usage/kk_usage_dictionary.jsonl"
    )
    args = parser.parse_args()
    table = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    table.setdefault("version", 1)
    fits = table.setdefault("models", {}).setdefault(args.model, {})
    sources = {
        "zh": (zh_pairs(args.zh, args.zh_gold), "CMDAG test sample (gold, 200 sentences)"),
        "kk": (
            kk_pairs(args.kk, args.kk_dictionary),
            "Kazakh explanatory dictionary «ауыс.» quotations (160)",
        ),
    }
    for language, (pairs, source) in sources.items():
        if len(pairs) < MIN_SPANS or len({k for _, k in pairs}) < 2:
            print(f"{language}: {len(pairs)} judged figures, too few to calibrate; skipped")
            continue
        fits[language] = fit(pairs, source)
        print(language, json.dumps(fits[language], ensure_ascii=False))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
