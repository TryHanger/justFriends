"""Fine-tune the XLM-R BIO detector on expert-sourced data for both languages.

Sources
* Kazakh explanatory dictionary (scripts/build_kk_usage_set.py): in every quotation only
  the headword is labelled (figurative «ауыс.» or literal). Partial supervision: the loss
  is computed on the headword's tokens only (B/I-METAPHOR or O); every other token is
  ignored (-100), because the dictionary says nothing about the other words.
* Kazakh silver (data/processed/pilot/kk_weak_train.jsonl) and a CMDAG gold sample with
  full BIO labels, so the model keeps both languages and does not forget Chinese.

Evaluation (no test data is used for fitting)
* Kazakh: 5 folds grouped by headword, the model is scored on words it never saw: a
  headword counts as figurative when a predicted figure overlaps it, compared with the
  dictionary (Cohen κ), as for the LLMs in data/processed/kk_usage/.
* Chinese: CMDAG test (exact-span F1, must not regress) and recall of Wang Yi's images
  (data/processed/wangyi/chuci_wangyi.jsonl, never trained on) as a poetry probe.
The base model is scored the same way. The final model is fitted on all folds.

    python -m scripts.finetune_xlmr_expert
"""

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import cohen_kappa_score
from sklearn.model_selection import StratifiedGroupKFold
from transformers import AutoModelForTokenClassification, AutoTokenizer

from app.nlp.corpus import read_corpus
from app.nlp.evaluation import evaluate
from app.nlp.xlmr import XLMRDetector, align_labels, token_windows

DICTIONARY = Path("data/processed/kk_usage/kk_usage_dictionary.jsonl")
KK_SILVER = Path("data/processed/pilot/kk_weak_train.jsonl")
CMDAG_TRAIN = Path("data/gold/cmdag/train.jsonl")
CMDAG_TEST = Path("data/gold/cmdag/test.jsonl")
WANGYI = Path("data/processed/wangyi/chuci_wangyi.jsonl")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def encode(tokenizer, text: str):
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    return encoded["input_ids"], encoded["offset_mapping"]


def partial_labels(offsets, start: int, end: int, figurative: bool) -> list[int]:
    """Labels only on the headword's tokens; -100 elsewhere (no claim about other words)."""
    labels, first = [], True
    for a, b in offsets:
        if a < end and b > start and a < b:
            labels.append((1 if first else 2) if figurative else 0)
            first = False
        else:
            labels.append(-100)
    return labels


def features(tokenizer, records, args):
    """records: ("partial", dict) or ("full", Poem)."""
    out = []
    for kind, record in records:
        if kind == "partial":
            ids, offsets = encode(tokenizer, record["text"])
            labels = partial_labels(
                offsets, record["start"], record["end"], record["usage_type"] == "metaphorical"
            )
        else:
            ids, offsets = encode(tokenizer, record.text)
            try:
                labels = align_labels(record.text, offsets, record.spans)
            except ValueError:
                continue  # unrepresentable boundaries are skipped, as in app/nlp/training.py
        for _, _, feature in token_windows(
            ids, offsets, tokenizer, args.max_length, args.stride, labels
        ):
            if any(label != -100 for label in feature["labels"]):
                out.append(feature)
    return out


def pad(batch, width, key, value, device):
    return torch.tensor([f[key] + [value] * (width - len(f[key])) for f in batch], device=device)


def fit(train_records, args, device, output: Path | None = None):
    seed_everything(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForTokenClassification.from_pretrained(args.base_model).to(device)
    data = features(tokenizer, train_records, args)
    weights = torch.tensor([1.0, args.positive_weight, args.positive_weight], device=device)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights, ignore_index=-100)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    steps = args.epochs * ((len(data) + args.batch_size - 1) // args.batch_size)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: min(1.0, (s + 1) / (0.1 * steps)) * max(0.0, 1 - s / steps)
    )
    model.train()
    for _ in range(args.epochs):
        random.shuffle(data)
        for start in range(0, len(data), args.batch_size):
            batch = data[start : start + args.batch_size]
            width = max(len(f["input_ids"]) for f in batch)

            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = model(
                    input_ids=pad(batch, width, "input_ids", tokenizer.pad_token_id, device),
                    attention_mask=pad(batch, width, "attention_mask", 0, device),
                ).logits
            loss = loss_fn(
                logits.float().view(-1, 3), pad(batch, width, "labels", -100, device).view(-1)
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
    path = output or Path(args.scratch)
    # Own version id: inheriting the base model's would share its calibration.
    model.config.nlp_model_version = path.name
    model.save_pretrained(path)
    tokenizer.save_pretrained(path)
    del model
    torch.cuda.empty_cache()
    return path


def headword_predictions(model_path, quotations, args, store=None) -> list[int]:
    detector = XLMRDetector(str(model_path), args.max_length, args.stride)
    result = []
    for q in quotations:
        analysis = detector.analyze(q["text"], "kk")
        if store is not None:  # out-of-fold analyses, e.g. for honest calibration
            store[q["id"]] = analysis.model_dump()
        spans = analysis.metaphors
        result.append(int(any(s.start < q["end"] and s.end > q["start"] for s in spans)))
    return result


def kk_scores(gold, predicted) -> dict:
    gold, predicted = np.array(gold), np.array(predicted)
    tp = int(((gold == 1) & (predicted == 1)).sum())
    fp = int(((gold == 0) & (predicted == 1)).sum())
    fn = int(((gold == 1) & (predicted == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "quotations": len(gold),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if tp else 0.0,
        "cohen_kappa_vs_dictionary": float(cohen_kappa_score(gold, predicted)),
        "false_alarm_on_literal": float(predicted[gold == 0].mean()),
    }


def zh_scores(model_path, args) -> dict:
    detector = XLMRDetector(str(model_path), args.max_length, args.stride)
    test = read_corpus(CMDAG_TEST)[: args.cmdag_test]
    report = evaluate(test, {r.id: detector.analyze(r.text, "zh") for r in test})
    wangyi = read_corpus(WANGYI)
    images = found = 0
    for poem in wangyi:
        spans = detector.analyze(poem.text, "zh").metaphors
        for gold in poem.spans:
            images += 1
            found += any(s.start < gold.end and s.end > gold.start for s in spans)
    return {
        "cmdag_test_sentences": len(test),
        "cmdag_metaphor_detection": report["all"]["metaphor_detection"],
        "cmdag_overlap_detection": report["all"]["overlap_detection"],
        "wangyi_images": images,
        "wangyi_found": found,
        "wangyi_recall": found / images if images else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="models/xlmr-zh-gold-kk-silver-mixed-v1")
    parser.add_argument("--output", default="models/xlmr-zh-kk-expert-v1")
    parser.add_argument("--scratch", default="models/_fold")
    parser.add_argument("--report", default="data/processed/kk_usage/xlmr_expert_finetune.json")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--cmdag-sample", type=int, default=3000)
    parser.add_argument("--cmdag-test", type=int, default=1000)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--positive-weight", type=float, default=3.0)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--stride", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--oof-output",
        default="data/processed/kk_usage/pred-xlmr-expert-oof.json",
        help="out-of-fold analyses of every quotation (for calibration)",
    )
    parser.add_argument("--cv-only", action="store_true", help="skip the base model and final fit")
    parser.add_argument(
        "--extra",
        nargs="*",
        default=[],
        help="more fully labelled corpora (e.g. Claude-annotated poetry, silver)",
    )
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    quotations = [json.loads(line) for line in DICTIONARY.read_text(encoding="utf-8").splitlines()]
    gold = [int(q["usage_type"] == "metaphorical") for q in quotations]
    groups = [q["headword"] for q in quotations]
    cmdag = read_corpus(CMDAG_TRAIN)
    random.Random(args.seed).shuffle(cmdag)
    # Every figure of the extra corpora is a positive: the BIO detector finds figurative
    # expressions, and leaving similes or idioms as O would teach the opposite.
    extra = [
        r.model_copy(
            update={"spans": [s.model_copy(update={"label": "metaphor"}) for s in r.spans]}
        )
        for path in args.extra
        for r in read_corpus(path)
    ]
    full = [("full", r) for r in read_corpus(KK_SILVER) + cmdag[: args.cmdag_sample] + extra]

    report = {
        "task": "XLM-R BIO fine-tuning on expert-sourced Kazakh dictionary quotations "
        "(headword-only labels) + Kazakh silver + CMDAG gold sample",
        "hyperparameters": {k: v for k, v in vars(args).items() if k not in {"report"}},
    }
    if not args.cv_only:
        report["base_model"] = {
            "kk_dictionary_all": kk_scores(
                gold, headword_predictions(args.base_model, quotations, args)
            ),
            "zh": zh_scores(args.base_model, args),
        }
        print("base:", json.dumps(report["base_model"]["kk_dictionary_all"]), flush=True)

    predicted, oof = [0] * len(quotations), {}
    folds = StratifiedGroupKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
    for fold, (train, test) in enumerate(folds.split(quotations, gold, groups)):
        path = fit([("partial", quotations[i]) for i in train] + full, args, device)
        for i, value in zip(
            test, headword_predictions(path, [quotations[i] for i in test], args, oof), strict=True
        ):
            predicted[i] = value
        print(
            f"fold {fold}: κ {cohen_kappa_score([gold[i] for i in test], [predicted[i] for i in test]):.3f}",
            flush=True,
        )
    report["fine_tuned_unseen_words"] = {"kk_dictionary_all": kk_scores(gold, predicted)}
    sample_ids = {r.id for r in read_corpus("data/processed/kk_usage/sample.jsonl")}
    index = [i for i, q in enumerate(quotations) if q["id"] in sample_ids]
    report["fine_tuned_unseen_words"]["kk_dictionary_sample160"] = kk_scores(
        [gold[i] for i in index], [predicted[i] for i in index]
    )
    Path(args.oof_output).write_text(json.dumps(oof, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.cv_only:
        print(json.dumps(report["fine_tuned_unseen_words"], ensure_ascii=False, indent=1))
        return

    output = fit([("partial", q) for q in quotations] + full, args, device, Path(args.output))
    report["final_model"] = {"path": str(output), "zh": zh_scores(output, args)}
    (output / "experiment.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "hyperparameters"},
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
