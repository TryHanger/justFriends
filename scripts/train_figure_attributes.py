"""Train the figure type and domain heads used by the XLM-R profiles (app/nlp/figure_attributes.py).

Data: Claude-annotated Chinese (Shijing/Tang/Song) and Kazakh (Abai) poems, every figure
with its type, source and target domain. Features: hidden states of the deployed XLM-R
detector. Evaluation: 5-fold cross-validation grouped by poem, against the majority class.

  python -m scripts.train_figure_attributes --model models/xlmr-zh-kk-expert-v3
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from app.nlp.corpus import read_corpus
from app.nlp.figure_attributes import HEADS, FigureAttributes, simile_marker

CORPORA = (
    "data/processed/pilot/zh_claude_silver_100.jsonl",
    "data/processed/pilot/zh_claude_silver_tang300.jsonl",
    "data/processed/pilot/zh_claude_silver_song150.jsonl",
    "data/processed/kk_ensemble/claude_silver_150.jsonl",
)
LAYERS = [6, 9, 12]


def examples(paths):
    for path in paths:
        for poem in read_corpus(path):
            for span in poem.spans:
                yield poem, span


def fit(x, y, c, balanced=False):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=c, max_iter=3000, class_weight="balanced" if balanced else None)
    model.fit(scaler.transform(x), y)
    return scaler, model


def scores(gold, predicted):
    from sklearn.metrics import accuracy_score, f1_score

    return {
        "accuracy": round(accuracy_score(gold, predicted), 3),
        "macro_f1": round(f1_score(gold, predicted, average="macro", zero_division=0), 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/xlmr-zh-kk-expert-v3")
    parser.add_argument("--output", default=None, help="default: <model>/figure_attributes.json")
    parser.add_argument("--report", default="data/processed/figure_attributes.json")
    parser.add_argument("--c", type=float, nargs="+", default=[0.003, 0.01, 0.03, 0.1])
    parser.add_argument("--balanced", action="store_true", help="weight rare classes up")
    args = parser.parse_args()

    import torch
    from sklearn.model_selection import GroupKFold
    from transformers import AutoModel, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModel.from_pretrained(args.model, local_files_only=True).to(device).eval()

    encoder = FigureAttributes({}, LAYERS)
    rows, features = [], []
    for poem, span in examples(CORPORA):
        vector = encoder.features(model, tokenizer, device, poem.text, span.start, span.end)
        if vector is None:
            continue
        rows.append((poem, span))
        features.append(vector)
    x = np.stack(features)
    groups = [poem.id for poem, _ in rows]
    languages = np.array([poem.language for poem, _ in rows])
    gold = {head: np.array([getattr(span, head) for _, span in rows]) for head in HEADS}
    markers = np.array(
        [simile_marker(p.text, s.start, s.end, p.language) is not None for p, s in rows]
    )
    print(f"{len(rows)} figures, {x.shape[1]} features")

    report = {
        "source": "Claude silver: Shijing/Tang/Song (zh) and Abai (kk)",
        "figures": len(rows),
        "by_language": dict(Counter(languages.tolist())),
        "layers": LAYERS,
        "balanced": args.balanced,
        "cv": {},
    }
    simile = gold["label"] == "simile"
    report["simile_marker"] = {
        "precision": round(float((markers & simile).sum() / max(markers.sum(), 1)), 3),
        "recall": round(float((markers & simile).sum() / max(simile.sum(), 1)), 3),
    }
    print("simile marker", report["simile_marker"])

    folds = list(GroupKFold(n_splits=5).split(x, groups=groups))
    best_c = {}
    for head in HEADS:
        y = gold[head]
        majority = Counter(y.tolist()).most_common(1)[0][0]
        trials = {}
        for c in args.c:
            predicted = np.empty_like(y)
            for train, test in folds:
                scaler, clf = fit(x[train], y[train], c, args.balanced)
                predicted[test] = clf.predict(scaler.transform(x[test]))
            if head == "label":
                predicted = np.where(markers, "simile", predicted)
            trials[c] = (scores(y, predicted), predicted)
        c = max(trials, key=lambda k: trials[k][0]["accuracy"])
        best_c[head] = c
        result, predicted = trials[c]
        result["C"] = c
        result["majority"] = scores(y, np.full_like(y, majority))
        result["by_language"] = {
            lang: scores(y[languages == lang], predicted[languages == lang])
            for lang in sorted(set(languages))
        }
        report["cv"][head] = result
        print(head, json.dumps(result, ensure_ascii=False))

    heads = {}
    for head in HEADS:
        scaler, clf = fit(x, gold[head], best_c[head], args.balanced)
        heads[head] = {
            "classes": clf.classes_.tolist(),
            "coef": clf.coef_.round(6).tolist(),
            "intercept": clf.intercept_.round(6).tolist(),
            "mean": scaler.mean_.round(6).tolist(),
            "scale": scaler.scale_.round(6).tolist(),
        }
    output = Path(args.output or Path(args.model) / "figure_attributes.json")
    output.write_text(
        json.dumps({"layers": LAYERS, "report": report, "heads": heads}), encoding="utf-8"
    )
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", output)


if __name__ == "__main__":
    main()
