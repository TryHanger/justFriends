"""Hypothesis H1 (ТЗ п. 5): instruction fine-tuning (IFT) of an open model beats zero-shot
and few-shot prompting of the same model.

One open instruct model, the same held-out test items, three conditions:
* zero-shot — the instruction only;
* few-shot — the instruction plus k labelled examples from the training part;
* IFT — LoRA fine-tuning on the training part (loss on the answer tokens only).
The answer is chosen by the log-likelihood of each allowed label, identically in all
conditions, so the comparison measures what the model knows, not output formatting.

Tasks with expert-sourced labels
* kk: literal vs figurative use of the marked headword in dictionary quotations
  (data/processed/kk_usage/kk_usage_dictionary.jsonl); test = held-out headwords;
* zh: Zhu Xi's stanza type 賦 / 比 / 興 for the Shijing (data/processed/zhuxi/
  shijing_zhuxi_stanzas.jsonl); test = held-out poems.

    python -m scripts.h1_ift_vs_prompting --base-model Qwen/Qwen2.5-1.5B-Instruct
"""

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import cohen_kappa_score, f1_score
from sklearn.model_selection import GroupShuffleSplit
from transformers import AutoModelForCausalLM, AutoTokenizer

KK = Path("data/processed/kk_usage/kk_usage_dictionary.jsonl")
ZH = Path("data/processed/zhuxi/shijing_zhuxi_stanzas.jsonl")
TASKS = {
    "kk": {
        "labels": ["literal", "metaphorical"],
        "instruction": (
            "You judge Kazakh literary quotations. Decide whether the word marked with [[ ]] "
            "is used in its direct (literal) sense or in a figurative (metaphorical, "
            "transferred) sense in this context. Conventional figurative senses count as "
            "figurative. Answer with one word: literal or metaphorical."
        ),
    },
    "zh": {
        "labels": ["賦", "比", "興"],
        "instruction": (
            "You classify stanzas of the Shijing (詩經) as Zhu Xi did: 賦 — direct "
            "description of the matter; 比 — the whole stanza speaks of one thing to mean "
            "another; 興 — an image is evoked first to lead into the subject. Answer with "
            "one character: 賦, 比 or 興."
        ),
    },
}


def load(task: str) -> list[dict]:
    if task == "kk":
        rows = [json.loads(line) for line in KK.read_text(encoding="utf-8").splitlines()]
        return [
            {
                "input": r["text"][: r["start"]]
                + "[["
                + r["text"][r["start"] : r["end"]]
                + "]]"
                + r["text"][r["end"] :],
                "label": r["usage_type"],
                "group": r["headword"],
            }
            for r in rows
        ]
    rows = [json.loads(line) for line in ZH.read_text(encoding="utf-8").splitlines()]

    def reduce(label: str) -> str:
        return "比" if "比" in label else "興" if "興" in label else "賦"

    return [{"input": r["text"], "label": reduce(r["label"]), "group": r["poem_id"]} for r in rows]


def messages(task: str, item: dict, shots: list[dict]) -> list[dict]:
    result = [{"role": "system", "content": TASKS[task]["instruction"]}]
    for shot in shots:
        result += [
            {"role": "user", "content": shot["input"]},
            {"role": "assistant", "content": shot["label"]},
        ]
    return result + [{"role": "user", "content": item["input"]}]


def prompt_ids(tokenizer, msgs, max_length):
    text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    return ids[-max_length:]  # keep the end: the question is last


@torch.no_grad()
def predict(model, tokenizer, task, items, shots, args, device) -> list[str]:
    """Label with the highest log-likelihood of its tokens after the prompt."""
    model.eval()
    labels = TASKS[task]["labels"]
    label_ids = [tokenizer(label, add_special_tokens=False)["input_ids"] for label in labels]
    result = []
    for item in items:
        prompt = prompt_ids(tokenizer, messages(task, item, shots), args.max_length)
        scores = []
        for ids in label_ids:
            sequence = torch.tensor([prompt + ids], device=device)
            logits = model(input_ids=sequence).logits[0, len(prompt) - 1 : -1].float()
            logprobs = logits.log_softmax(-1).gather(1, torch.tensor(ids, device=device)[:, None])
            scores.append(float(logprobs.sum()))
        result.append(labels[int(np.argmax(scores))])
    return result


def ift(model, tokenizer, task, train, args, device):
    from peft import LoraConfig, get_peft_model

    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.lora_r,
            lora_alpha=2 * args.lora_r,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
            task_type="CAUSAL_LM",
        ),
    )
    if args.balance:
        # Oversample minority labels to the majority count: with 19% figurative quotations
        # the unbalanced run learned to answer "literal" for everything.
        by_label = {}
        for item in train:
            by_label.setdefault(item["label"], []).append(item)
        target = max(len(v) for v in by_label.values())
        rng = random.Random(args.seed)
        train = [
            item
            for items in by_label.values()
            for item in items + [rng.choice(items) for _ in range(target - len(items))]
        ]
    examples = []
    for item in train:
        prompt = prompt_ids(tokenizer, messages(task, item, []), args.max_length)
        answer = tokenizer(item["label"] + (tokenizer.eos_token or ""), add_special_tokens=False)[
            "input_ids"
        ]
        examples.append((prompt + answer, [-100] * len(prompt) + answer))
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=args.learning_rate
    )
    model.train()
    step = 0
    for _ in range(args.epochs):
        random.shuffle(examples)
        for ids, labels in examples:
            out = model(
                input_ids=torch.tensor([ids], device=device),
                labels=torch.tensor([labels], device=device),
            )
            (out.loss / args.accumulation).backward()
            step += 1
            if step % args.accumulation == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad()
    return model


def scores(task, gold, predicted) -> dict:
    if task == "kk":
        g = [x == "metaphorical" for x in gold]
        p = [x == "metaphorical" for x in predicted]
        return {
            "f1_metaphorical": f1_score(g, p, zero_division=0),
            "kappa": cohen_kappa_score(g, p),
        }
    return {
        "macro_f1": f1_score(gold, predicted, average="macro", zero_division=0),
        "kappa": cohen_kappa_score(gold, predicted),
        "accuracy": float(np.mean(np.array(gold) == np.array(predicted))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--tasks", nargs="+", default=["kk", "zh"])
    parser.add_argument("--test-share", type=float, default=0.25)
    parser.add_argument("--shots", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--accumulation", type=int, default=8)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=384)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--balance", action="store_true", help="oversample minority labels for IFT")
    parser.add_argument("--report", default="data/processed/h1/h1_ift_vs_prompting.json")
    args = parser.parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    report = {"base_model": args.base_model, "hyperparameters": vars(args), "tasks": {}}
    for task in args.tasks:
        items = load(task)
        split = GroupShuffleSplit(n_splits=1, test_size=args.test_share, random_state=args.seed)
        train_idx, test_idx = next(split.split(items, groups=[i["group"] for i in items]))
        train, test = [items[i] for i in train_idx], [items[i] for i in test_idx]
        gold = [i["label"] for i in test]
        # Few-shot examples: balanced across labels, from the training part only.
        rng = random.Random(args.seed)
        per_label = max(1, args.shots // len(TASKS[task]["labels"]))
        shots = [
            s
            for label in TASKS[task]["labels"]
            for s in rng.sample([t for t in train if t["label"] == label], per_label)
        ]
        rng.shuffle(shots)
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model, torch_dtype=torch.bfloat16
        ).to(device)
        result = {
            "train": len(train),
            "test": len(test),
            "test_labels": {lab: gold.count(lab) for lab in TASKS[task]["labels"]},
        }
        result["zero_shot"] = scores(
            task, gold, predict(model, tokenizer, task, test, [], args, device)
        )
        print(task, "zero-shot", result["zero_shot"], flush=True)
        result["few_shot"] = scores(
            task, gold, predict(model, tokenizer, task, test, shots, args, device)
        )
        print(task, "few-shot", result["few_shot"], flush=True)
        model = ift(model, tokenizer, task, train, args, device)
        result["ift_lora"] = scores(
            task, gold, predict(model, tokenizer, task, test, [], args, device)
        )
        print(task, "IFT", result["ift_lora"], flush=True)
        report["tasks"][task] = result
        del model
        torch.cuda.empty_cache()
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
