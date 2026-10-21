"""Stanza classifier 賦 / 比 / 興 trained on Zhu Xi's labels (scripts/extract_zhuxi.py).

Combined labels are reduced to one class: anything with 比 is 比 (the stanza as a whole
compares), otherwise anything with 興 is 興, otherwise 賦. Quality is measured by 5-fold
cross-validation grouped by poem: Shijing stanzas of one poem repeat each other almost
word for word, so a stanza-level split would leak. Baselines run on the same folds.
Finally one model is fitted on all stanzas and saved for use.

    python -m scripts.train_stanza_classifier --base-model models/cmdag-xlmr-mps-full-v2
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, cohen_kappa_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from transformers import AutoModelForSequenceClassification, AutoTokenizer

CLASSES = ["賦", "比", "興"]
STANZAS = Path("data/processed/zhuxi/shijing_zhuxi_stanzas.jsonl")


def reduce(label: str) -> str:
    return "比" if "比" in label else "興" if "興" in label else "賦"


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def fit_transformer(texts, labels, args, device):
    seed_everything(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=len(CLASSES),
        id2label=dict(enumerate(CLASSES)),
        label2id={c: i for i, c in enumerate(CLASSES)},
        ignore_mismatched_sizes=True,  # the base checkpoint may carry a token-level head
    ).to(device)
    counts = Counter(labels)
    weights = torch.tensor(
        [len(labels) / (len(CLASSES) * counts[i]) for i in range(len(CLASSES))],
        dtype=torch.float,
        device=device,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    steps = args.epochs * ((len(texts) + args.batch_size - 1) // args.batch_size)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda step: min(1.0, (step + 1) / (0.1 * steps)) * max(0.0, 1 - step / steps)
    )
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)
    model.train()
    for _ in range(args.epochs):
        order = np.random.permutation(len(texts))
        for start in range(0, len(order), args.batch_size):
            batch = order[start : start + args.batch_size]
            encoded = tokenizer(
                [texts[i] for i in batch],
                truncation=True,
                max_length=args.max_length,
                padding=True,
                return_tensors="pt",
            ).to(device)
            target = torch.tensor([labels[i] for i in batch], device=device)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = model(**encoded).logits
            loss = loss_fn(logits.float(), target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
    return tokenizer, model


@torch.no_grad()
def predict(tokenizer, model, texts, args, device) -> list[int]:
    model.eval()
    result = []
    for start in range(0, len(texts), 64):
        encoded = tokenizer(
            texts[start : start + 64],
            truncation=True,
            max_length=args.max_length,
            padding=True,
            return_tensors="pt",
        ).to(device)
        result.extend(model(**encoded).logits.argmax(-1).tolist())
    return result


def metrics(gold: list[int], predicted: list[int]) -> dict:
    figurative = [g != 0 for g in gold], [p != 0 for p in predicted]
    return {
        "macro_f1": f1_score(gold, predicted, average="macro"),
        "accuracy": float(np.mean(np.array(gold) == np.array(predicted))),
        "cohen_kappa_vs_zhuxi": cohen_kappa_score(gold, predicted),
        "figurative_f1": f1_score(*figurative),
        "figurative_kappa": cohen_kappa_score(*figurative),
        "per_class": {
            CLASSES[int(k)]: {m: v[m] for m in ("precision", "recall", "f1-score", "support")}
            for k, v in classification_report(
                gold, predicted, labels=[0, 1, 2], output_dict=True, zero_division=0
            ).items()
            if k in {"0", "1", "2"}
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="models/cmdag-xlmr-mps-full-v2")
    parser.add_argument("--output", default="models/zhuxi-stanza-xlmr-v1")
    parser.add_argument("--report", default="data/processed/zhuxi/stanza_classifier.json")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--text-field",
        choices=["text_simplified", "text"],
        default="text_simplified",
        help="text = traditional script, as in models pretrained on classical texts",
    )
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    stanzas = [json.loads(line) for line in STANZAS.read_text(encoding="utf-8").splitlines()]
    texts = [s[args.text_field] for s in stanzas]
    labels = [CLASSES.index(reduce(s["label"])) for s in stanzas]
    groups = [s["poem_id"] for s in stanzas]
    first = [[int(s["stanza"] == 0)] for s in stanzas]

    predictions = {
        "majority": [0] * len(texts),
        "first_stanza": [0] * len(texts),
        "char_ngram_logreg": [0] * len(texts),
        "transformer": [0] * len(texts),
    }
    folds = StratifiedGroupKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
    for fold, (train, test) in enumerate(folds.split(texts, labels, groups)):
        y = [labels[i] for i in train]
        majority = Counter(y).most_common(1)[0][0]
        position = LogisticRegression(class_weight="balanced").fit([first[i] for i in train], y)
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), sublinear_tf=True)
        ngram = LogisticRegression(class_weight="balanced", max_iter=2000, C=3.0).fit(
            vectorizer.fit_transform([texts[i] for i in train]), y
        )
        tokenizer, model = fit_transformer([texts[i] for i in train], y, args, device)
        test_texts = [texts[i] for i in test]
        outputs = {
            "majority": [majority] * len(test),
            "first_stanza": position.predict([first[i] for i in test]).tolist(),
            "char_ngram_logreg": ngram.predict(vectorizer.transform(test_texts)).tolist(),
            "transformer": predict(tokenizer, model, test_texts, args, device),
        }
        for name, values in outputs.items():
            for i, value in zip(test, values, strict=True):
                predictions[name][i] = int(value)
        fold_f1 = f1_score([labels[i] for i in test], outputs["transformer"], average="macro")
        print(f"fold {fold}: transformer macro-F1 {fold_f1:.3f}", flush=True)
        del model
        torch.cuda.empty_cache()

    report = {
        "task": "Shijing stanza classification 賦/比/興 (Zhu Xi 詩經集傳 labels)",
        "stanzas": len(texts),
        "poems": len(set(groups)),
        "class_counts": {CLASSES[k]: v for k, v in sorted(Counter(labels).items())},
        "evaluation": f"{args.folds}-fold cross-validation grouped by poem",
        "hyperparameters": {k: v for k, v in vars(args).items() if k not in {"output", "report"}},
        "results": {name: metrics(labels, values) for name, values in predictions.items()},
    }
    tokenizer, model = fit_transformer(texts, labels, args, device)
    output = Path(args.output)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    (output / "experiment.json").write_text(
        json.dumps(
            {k: v for k, v in report.items() if k != "results"}
            | {
                "cross_validation": report["results"]["transformer"],
                "status": "expert-sourced labels (Zhu Xi), automatic extraction",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for name, result in report["results"].items():
        print(
            f"{name:18} macro-F1 {result['macro_f1']:.3f}  κ {result['cohen_kappa_vs_zhuxi']:.3f}"
            f"  figurative F1 {result['figurative_f1']:.3f}  "
            + "  ".join(f"{c} F1 {v['f1-score']:.2f}" for c, v in result["per_class"].items())
        )


if __name__ == "__main__":
    main()
