"""LoRA instruction tuning of open LLMs (Qwen-2.5, LLaMA-3.1, SozKZ) on the IFT dataset.

Loss is computed on assistant tokens only. Train and validation must come from disjoint
works. The adapter with the lowest validation loss is saved together with experiment.json;
quality is then measured with `predict --backend hf` and `evaluate` on the test split.
Requires the `finetune` extra (peft).
"""

import hashlib
import json
import math
import random
from pathlib import Path

from app.nlp.corpus import save_json
from app.nlp.hf_local import render_chat
from app.nlp.ift import read_ift


def encode_example(tokenizer, messages: list[dict], max_length: int) -> dict | None:
    prompt = render_chat(tokenizer, messages[:-1], add_generation_prompt=True)
    answer = messages[-1]["content"] + (tokenizer.eos_token or "")
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    answer_ids = tokenizer(answer, add_special_tokens=False)["input_ids"]
    if len(prompt_ids) + len(answer_ids) > max_length:
        return None  # never train on a truncated target answer
    return {
        "input_ids": prompt_ids + answer_ids,
        "labels": [-100] * len(prompt_ids) + answer_ids,
    }


def _batches(features, batch_size, pad_id, shuffle, rng):
    order = list(range(len(features)))
    if shuffle:
        rng.shuffle(order)
    for i in range(0, len(order), batch_size):
        chunk = [features[j] for j in order[i : i + batch_size]]
        width = max(len(f["input_ids"]) for f in chunk)
        yield {
            "input_ids": [f["input_ids"] + [pad_id] * (width - len(f["input_ids"])) for f in chunk],
            "labels": [f["labels"] + [-100] * (width - len(f["labels"])) for f in chunk],
            "attention_mask": [
                [1] * len(f["input_ids"]) + [0] * (width - len(f["input_ids"])) for f in chunk
            ],
        }


def finetune_lora(
    train_path,
    validation_path,
    output_dir,
    *,
    model_name: str,
    epochs: int = 3,
    batch_size: int = 2,
    gradient_accumulation: int = 8,
    learning_rate: float = 2e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    target_modules: list[str] | None = None,
    max_length: int = 4096,
    seed: int = 42,
    device: str | None = None,
):
    train, validation = read_ift(train_path), read_ift(validation_path)
    if {r["work_id"] for r in train} & {r["work_id"] for r in validation}:
        raise ValueError("Data leakage: the same work appears in IFT train and validation")
    if epochs < 1 or batch_size < 1 or gradient_accumulation < 1 or learning_rate <= 0:
        raise ValueError("Positive epochs, batch size, accumulation and learning rate required")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty to protect previous experiments")

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(seed)
    torch.manual_seed(seed)
    rng = random.Random(seed)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    pad_id = (
        tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    )
    if pad_id is None:
        raise ValueError("Tokenizer needs a pad or eos token")
    model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype="auto")
    config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=target_modules or "all-linear",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, config)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    def encode(rows):
        features, skipped = [], 0
        for row in rows:
            feature = encode_example(tokenizer, row["messages"], max_length)
            if feature is None:
                skipped += 1
            else:
                features.append(feature)
        return features, skipped

    train_features, train_skipped = encode(train)
    validation_features, validation_skipped = encode(validation)
    if not train_features or not validation_features:
        raise ValueError("No IFT examples fit max_length; increase it")

    identity = {
        "model": model_name,
        "train": hashlib.sha256(Path(train_path).read_bytes()).hexdigest(),
        "validation": hashlib.sha256(Path(validation_path).read_bytes()).hexdigest(),
        "seed": seed,
        "epochs": epochs,
        "batch_size": batch_size,
        "gradient_accumulation": gradient_accumulation,
        "learning_rate": learning_rate,
        "lora": {
            "r": lora_r,
            "alpha": lora_alpha,
            "dropout": lora_dropout,
            "target_modules": target_modules or "all-linear",
        },
        "max_length": max_length,
    }
    run_hash = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad), lr=learning_rate
    )
    steps_per_epoch = math.ceil(len(train_features) / batch_size / gradient_accumulation)
    total = max(1, steps_per_epoch * epochs)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda step: max(0.0, 1 - step / total)
    )

    def tensors(batch):
        return {k: torch.tensor(v, device=device) for k, v in batch.items()}

    history, best = [], math.inf
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        running, count = 0.0, 0
        for step, batch in enumerate(_batches(train_features, batch_size, pad_id, True, rng), 1):
            loss = model(**tensors(batch)).loss
            (loss / gradient_accumulation).backward()
            running, count = running + loss.item(), count + 1
            if step % gradient_accumulation == 0:
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
        if count % gradient_accumulation:
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
        model.eval()
        losses = []
        with torch.inference_mode():
            for batch in _batches(validation_features, batch_size, pad_id, False, rng):
                losses.append(model(**tensors(batch)).loss.item())
        validation_loss = sum(losses) / len(losses)
        history.append(
            {
                "epoch": epoch,
                "train_loss": running / max(1, count),
                "validation_loss": validation_loss,
            }
        )
        if validation_loss < best:
            best = validation_loss
            model.save_pretrained(output)
            tokenizer.save_pretrained(output)
    meta = {
        "kind": "lora-instruction-tuning",
        "model_version": f"ift-lora-{run_hash}",
        **identity,
        "train_examples": len(train_features),
        "train_skipped_too_long": train_skipped,
        "validation_examples": len(validation_features),
        "validation_skipped_too_long": validation_skipped,
        "best_validation_loss": best,
        "history": history,
    }
    save_json(output / "experiment.json", meta)
    return meta
