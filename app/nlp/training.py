"""Explicit train/validation inputs; test data is never used during fitting."""

import hashlib
import json
import random
from pathlib import Path

from app.nlp.corpus import (
    assert_disjoint,
    manifest,
    read_corpus,
    require_gold,
    require_silver_pilot,
    save_json,
)
from app.nlp.evaluation import evaluate
from app.nlp.xlmr import LABEL2ID, XLMRDetector, align_labels, token_windows
from app.schemas.taxonomy import BIO_LABELS, TAXONOMY_VERSION


def train_xlmr(
    train_path,
    validation_path,
    output_dir,
    *,
    model_name="FacebookAI/xlm-roberta-base",
    epochs=3,
    batch_size=4,
    learning_rate=2e-5,
    max_length=256,
    stride=64,
    seed=42,
    allow_synthetic=False,
    allow_silver_pilot=False,
    kazakh_sampling_weight=1.0,
    device=None,
):
    train, validation = read_corpus(train_path), read_corpus(validation_path)
    if allow_silver_pilot:
        require_silver_pilot(train)
        require_silver_pilot(validation)
    else:
        require_gold(train, allow_synthetic)
        require_gold(validation, allow_synthetic)
    assert_disjoint(train, validation)
    if epochs < 1 or batch_size < 1 or learning_rate <= 0 or kazakh_sampling_weight < 1:
        raise ValueError("Positive epochs, batch size, learning rate and Kazakh sampling weight required")
    if not any(s.label in {"metaphor", "personification"} for r in train for s in r.spans):
        raise ValueError("Training set needs positive metaphor examples")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty to protect previous experiments")
    if not 4 <= max_length <= 512 or not 0 <= stride < max_length - 2:
        raise ValueError("Use max_length 4..512 and stride < max_length-2")

    import torch
    import transformers
    from torch.utils.data import DataLoader
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
    )

    random.seed(seed)
    torch.manual_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=3,
        id2label=dict(enumerate(BIO_LABELS)),
        label2id=LABEL2ID,
    )
    if not tokenizer.is_fast or model.config.model_type != "xlm-roberta":
        raise ValueError("Expected XLM-R and a fast tokenizer")
    identity = {
        "train": manifest(train)["sha256"],
        "validation": manifest(validation)["sha256"],
        "model": model_name,
        "seed": seed,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "max_length": max_length,
        "stride": stride,
        "taxonomy_version": TAXONOMY_VERSION,
    }
    run_hash = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
    model.config.nlp_model_version = f"xlmr-v1-{run_hash}"
    features, sample_weights = [], []
    for record in train:
        encoded = tokenizer(
            record.text, add_special_tokens=False, return_offsets_mapping=True, verbose=False
        )
        labels = align_labels(record.text, encoded["offset_mapping"], record.spans)
        windows = list(
            token_windows(
                encoded["input_ids"],
                encoded["offset_mapping"],
                tokenizer,
                max_length,
                stride,
                labels,
            )
        )
        features.extend(feature for _, _, feature in windows)
        sample_weights.extend(
            [kazakh_sampling_weight if record.language == "kk" else 1.0] * len(windows)
        )
    if device is None:
        device = (
            "cuda"
            if torch.cuda.is_available()
            else "mps"
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
            else "cpu"
        )
    model.to(device)
    collator = DataCollatorForTokenClassification(tokenizer)
    sampler = None
    if kazakh_sampling_weight > 1:
        sampler = torch.utils.data.WeightedRandomSampler(
            sample_weights, num_samples=len(features), replacement=True, generator=torch.Generator().manual_seed(seed)
        )
    loader = DataLoader(
        features,
        batch_size=batch_size,
        shuffle=sampler is None,
        sampler=sampler,
        collate_fn=collator,
        generator=torch.Generator().manual_seed(seed),
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    history = []
    best_f1 = -1.0
    for epoch in range(epochs):
        model.train()
        losses = []
        total_steps = len(loader)
        for step, batch in enumerate(loader, 1):
            optimizer.zero_grad(set_to_none=True)
            loss = model(**{k: v.to(device) for k, v in batch.items()}).loss
            if not torch.isfinite(loss):
                raise ValueError("Non-finite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            losses.append(loss.item())
            if step % 10 == 0 or step == total_steps:
                print(
                    f"epoch={epoch + 1} step={step}/{total_steps} "
                    f"mean_loss={sum(losses) / len(losses):.4f}",
                    flush=True,
                )
        # Use the very same decoder as production inference without reloading weights.
        detector = XLMRDetector.__new__(XLMRDetector)
        detector.tokenizer, detector.model, detector.device = tokenizer, model.eval(), device
        detector.max_length, detector.stride, detector.version = max_length, stride, "training"
        detector.attributes = None  # validation scores spans only
        predictions = {r.id: detector.analyze(r.text, r.language) for r in validation}
        scores = evaluate(validation, predictions, allow_non_gold=allow_silver_pilot)
        f1 = scores["all"]["metaphor_detection"]["f1"]
        history.append(
            {"epoch": epoch + 1, "loss": sum(losses) / len(losses), "validation": scores}
        )
        if f1 > best_f1:
            best_f1 = f1
            model.save_pretrained(output, safe_serialization=True)
            tokenizer.save_pretrained(output)
        print(
            f"epoch={epoch + 1} loss={history[-1]['loss']:.4f} validation_span_f1={f1:.4f}",
            flush=True,
        )
    metadata = {
        "base_model": model_name,
        "taxonomy_version": TAXONOMY_VERSION,
        "seed": seed,
        "max_length": max_length,
        "stride": stride,
        "kazakh_sampling_weight": kazakh_sampling_weight,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "epochs": epochs,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "model_version": model.config.nlp_model_version,
        "synthetic_smoke_test": any(r.synthetic for r in train + validation),
        "supervision": "silver-pilot" if allow_silver_pilot else "gold",
        "warning": (
            "Weakly supervised pilot only: metrics on model-consensus control are not Gold metrics."
            if allow_silver_pilot
            else None
        ),
        "train": manifest(train),
        "validation": manifest(validation),
        "history": history,
    }
    save_json(output / "experiment.json", metadata)
    return metadata
