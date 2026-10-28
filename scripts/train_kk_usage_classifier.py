"""Kazakh literal vs metaphorical usage classifier on dictionary quotations.

Data: scripts/build_kk_usage_set.py (the 15-volume explanatory dictionary: quotations
under «ауыс.» senses are metaphorical, under direct senses literal). The input is a
window around the headword with the word itself marked: "… [[жылы]] әуез …".

Two cross-validations:
* unseen words (main): folds grouped by headword, the model never saw the test word,
  which is what matters for new poems;
* seen words: stratified folds over quotations, i.e. disambiguating the senses of
  words the model already knows.
Baselines run on the same folds. A final model is fitted on all quotations.

    python -m scripts.train_kk_usage_classifier --base-model models/xlmr-kk-silver-pilot-v2
"""

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.nlp.amp import Amp, amp_dtype

SET = Path("data/processed/kk_usage/kk_usage_dictionary.jsonl")
LABELS = ["literal", "metaphorical"]


def window(record: dict, size: int) -> str:
    text, start, end = record["text"].replace("\n", " / "), record["start"], record["end"]
    left = text[max(0, start - size) : start]
    right = text[end : end + size]
    return f"{left}[[{text[start:end]}]]{right}"


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def fit(texts, labels, args, device):
    seed_everything(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:  # decoder models (SozKZ, Qwen) have no padding token
        tokenizer.pad_token = tokenizer.eos_token
    # LoRA keeps the frozen base in half precision (bf16, or fp16 on T4/P100); adapters stay
    # fp32 below. --load-4bit quantizes it further (QLoRA) for 7-8B models on a 16 GB GPU.
    half = amp_dtype(device) or torch.float32
    extra = {}
    if args.load_4bit:
        from transformers import BitsAndBytesConfig

        extra = {
            "quantization_config": BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=half,
            ),
            "device_map": {"": device.index or 0},
        }
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=2,
        id2label=dict(enumerate(LABELS)),
        label2id={label: i for i, label in enumerate(LABELS)},
        ignore_mismatched_sizes=True,  # the base checkpoint carries a token-level head
        torch_dtype=half if args.lora else torch.float32,
        **extra,
    )
    if not args.load_4bit:
        model = model.to(device)
    model.config.pad_token_id = tokenizer.pad_token_id
    if args.load_4bit:
        from peft import prepare_model_for_kbit_training

        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    elif args.gradient_checkpointing:
        model.gradient_checkpointing_enable()
    if args.lora:
        from peft import LoraConfig, get_peft_model

        # Frozen base, rank-16 adapters on every linear layer, trainable classification head.
        model = get_peft_model(
            model,
            LoraConfig(
                task_type="SEQ_CLS",
                r=16,
                lora_alpha=32,
                lora_dropout=0.1,
                target_modules="all-linear",
            ),
        )
        for parameter in model.parameters():
            if parameter.requires_grad:
                parameter.data = parameter.data.float()
    positives = sum(labels)
    weights = torch.tensor(
        [len(labels) / (2 * (len(labels) - positives)), len(labels) / (2 * positives)],
        device=device,
    )
    if args.optimizer == "adafactor":
        from transformers.optimization import Adafactor

        # Factored second moments, no first moment: a 0.5B model fits an 8 GB GPU in fp32.
        optimizer = Adafactor(
            model.parameters(),
            lr=args.learning_rate,
            weight_decay=0.01,
            scale_parameter=False,
            relative_step=False,
            warmup_init=False,
        )
    else:
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    steps = args.epochs * ((len(texts) + args.batch_size - 1) // args.batch_size)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda step: min(1.0, (step + 1) / (0.1 * steps)) * max(0.0, 1 - step / steps)
    )
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)
    amp = Amp(device)
    model.train()
    started, step = time.time(), 0
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
            with amp.autocast():
                logits = model(**encoded).logits
            amp.step(loss_fn(logits.float(), target), model, optimizer)
            scheduler.step()
            optimizer.zero_grad()
            step += 1
            if step % 50 == 0:
                print(f"    step {step}/{steps}: {time.time() - started:.0f}s", flush=True)
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
        # A half-precision LoRA base needs autocast; full fine-tuning is evaluated in fp32.
        with Amp(device).autocast(enabled=args.lora):
            result.extend(model(**encoded).logits.argmax(-1).tolist())
    return result


def metrics(gold, predicted) -> dict:
    return {
        "precision": precision_score(gold, predicted, zero_division=0),
        "recall": recall_score(gold, predicted, zero_division=0),
        "f1": f1_score(gold, predicted, zero_division=0),
        "accuracy": float(np.mean(np.array(gold) == np.array(predicted))),
        "cohen_kappa_vs_dictionary": cohen_kappa_score(gold, predicted),
        "false_alarm_on_literal": float(
            np.mean([p for g, p in zip(gold, predicted, strict=True) if not g])
        ),
    }


def cross_validate(records, texts, labels, splits, args, device) -> dict:
    names = ["majority", "headword_prior", "char_ngram_logreg", "transformer"]
    predictions = {name: [0] * len(texts) for name in names}
    for fold, (train, test) in enumerate(splits):
        y = [labels[i] for i in train]
        # Share of metaphorical quotations of the same headword in training (0 if unseen).
        prior = {}
        for i in train:
            prior.setdefault(records[i]["headword"], []).append(labels[i])
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)
        ngram = LogisticRegression(class_weight="balanced", max_iter=3000, C=3.0).fit(
            vectorizer.fit_transform([texts[i] for i in train]), y
        )
        tokenizer, model = fit([texts[i] for i in train], y, args, device)
        outputs = {
            "majority": [0] * len(test),
            "headword_prior": [
                int(np.mean(prior.get(records[i]["headword"], [0])) > 0.5) for i in test
            ],
            "char_ngram_logreg": ngram.predict(
                vectorizer.transform([texts[i] for i in test])
            ).tolist(),
            "transformer": predict(tokenizer, model, [texts[i] for i in test], args, device),
        }
        for name, values in outputs.items():
            for i, value in zip(test, values, strict=True):
                predictions[name][i] = int(value)
        gold = [labels[i] for i in test]
        print(
            f"  fold {fold}: transformer F1 {f1_score(gold, outputs['transformer']):.3f}",
            flush=True,
        )
        del model
        torch.cuda.empty_cache()
    return {name: metrics(labels, values) for name, values in predictions.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="models/xlmr-kk-silver-pilot-v2")
    parser.add_argument("--output", default="models/kk-usage-xlmr-v1")
    parser.add_argument("--report", default="data/processed/kk_usage/usage_classifier.json")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--max-length", type=int, default=160)
    parser.add_argument("--window", type=int, default=150, help="characters on each side")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--optimizer",
        choices=["adamw", "adafactor"],
        default="adamw",
        help="adafactor for models whose AdamW states do not fit the GPU (Qwen 0.5B on 8 GB)",
    )
    parser.add_argument("--gradient-checkpointing", action="store_true")
    parser.add_argument(
        "--lora", action="store_true", help="LoRA adapters instead of full fine-tuning"
    )
    parser.add_argument(
        "--load-4bit",
        action="store_true",
        help="4-bit base (QLoRA, needs bitsandbytes and --lora) for 7-8B models",
    )
    parser.add_argument(
        "--unseen-only",
        action="store_true",
        help="only the unseen-word cross-validation, no final model (model comparisons)",
    )
    args = parser.parse_args()
    if args.load_4bit and not args.lora:
        parser.error("--load-4bit needs --lora")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    records = [json.loads(line) for line in SET.read_text(encoding="utf-8").splitlines()]
    texts = [window(r, args.window) for r in records]
    labels = [int(r["usage_type"] == "metaphorical") for r in records]
    groups = [r["headword"] for r in records]
    report = {
        "task": "Kazakh literal vs metaphorical usage of a marked word (dictionary «ауыс.»)",
        "quotations": len(records),
        "headwords": len(set(groups)),
        "metaphorical": sum(labels),
        "hyperparameters": {k: v for k, v in vars(args).items() if k not in {"output", "report"}},
    }
    print("unseen words (grouped by headword):", flush=True)
    unseen = StratifiedGroupKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
    report["unseen_words"] = cross_validate(
        records, texts, labels, unseen.split(texts, labels, groups), args, device
    )
    if args.unseen_only:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for name, r in report["unseen_words"].items():
            print(f"  {name:18} F1 {r['f1']:.2f} κ {r['cohen_kappa_vs_dictionary']:.2f}")
        return
    print("seen words (stratified by quotation):", flush=True)
    seen = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
    report["seen_words"] = cross_validate(
        records, texts, labels, seen.split(texts, labels), args, device
    )
    tokenizer, model = fit(texts, labels, args, device)
    output = Path(args.output)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    (output / "experiment.json").write_text(
        json.dumps(
            {
                k: report[k]
                for k in ("task", "quotations", "headwords", "metaphorical", "hyperparameters")
            }
            | {
                "cross_validation_unseen_words": report["unseen_words"]["transformer"],
                "status": "expert-sourced labels (dictionary), automatic extraction; "
                "research use only (copyrighted source)",
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
    for split in ("unseen_words", "seen_words"):
        print(split)
        for name, r in report[split].items():
            print(
                f"  {name:18} P {r['precision']:.2f} R {r['recall']:.2f} F1 {r['f1']:.2f} "
                f"κ {r['cohen_kappa_vs_dictionary']:.2f} FA {r['false_alarm_on_literal']:.2f}"
            )


if __name__ == "__main__":
    main()
