"""Layer-wise probing for hypothesis H3 (ТЗ п. 5): where is metaphor information encoded?

For every gold entity candidate the hidden states of each layer are mean-pooled over the
tokens that overlap the candidate. A logistic-regression probe predicts literal vs
metaphorical. Two measures per layer:
  * macro-F1 with grouped cross-validation by work_id (no work in both train and test);
  * online-code MDL (Voita & Titov, 2020): codelength in bits and compression relative to a
    uniform code. Higher compression = information is more easily extractable.
"""

import math
import random

from app.nlp.corpus import Poem

BLOCKS = (0.1, 0.2, 0.4, 0.8, 1.0)


def probing_items(records: list[Poem]) -> list[dict]:
    items = []
    for record in records:
        for c in record.candidates:
            if c.usage_type is None:
                raise ValueError(f"{record.id}: candidate without usage decision")
            items.append(
                {
                    "record": record,
                    "start": c.start,
                    "end": c.end,
                    "label": int(c.usage_type == "metaphorical"),
                    "group": record.work_id,
                }
            )
    labels = {i["label"] for i in items}
    if labels != {0, 1}:
        raise ValueError("Probing needs both literal and metaphorical gold candidates")
    return items


def layer_features(
    model_name: str, items: list[dict], max_length: int = 512, device=None, loader=None
):
    """Return features[layer][item] as lists of floats (layer 0 = embeddings)."""
    import torch

    if loader is None:
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        model = AutoModel.from_pretrained(model_name)
    else:
        tokenizer, model = loader(model_name)
    if not tokenizer.is_fast:
        raise ValueError("Probing needs a fast tokenizer with offset mapping")
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    per_layer: list[list[list[float]]] | None = None
    for item in items:
        text = item["record"].text
        # Center a window on the candidate when the poem exceeds the model limit.
        encoded = tokenizer(text, return_offsets_mapping=True, add_special_tokens=False)
        offsets = encoded["offset_mapping"]
        inside = [i for i, (s, e) in enumerate(offsets) if s < item["end"] and e > item["start"]]
        if not inside:
            raise ValueError("Candidate boundary does not align with any model token")
        budget = max_length - 2
        first = max(0, min(inside[0] - budget // 2, len(offsets) - budget))
        window = list(range(first, min(len(offsets), first + budget)))
        ids = [encoded["input_ids"][i] for i in window]
        if tokenizer.bos_token_id is not None or tokenizer.cls_token_id is not None:
            start_id = (
                tokenizer.cls_token_id
                if tokenizer.cls_token_id is not None
                else tokenizer.bos_token_id
            )
            ids, shift = [start_id] + ids, 1
        else:
            shift = 0
        positions = [window.index(i) + shift for i in inside if i in window]
        with torch.inference_mode():
            output = model(input_ids=torch.tensor([ids], device=device), output_hidden_states=True)
        states = output.hidden_states
        if per_layer is None:
            per_layer = [[] for _ in states]
        for layer, hidden in enumerate(states):
            per_layer[layer].append(hidden[0, positions].float().mean(0).cpu().tolist())
    return per_layer


def _probe():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))


def grouped_f1(features, labels, groups, folds: int = 5) -> float:
    from sklearn.metrics import f1_score
    from sklearn.model_selection import GroupKFold

    folds = min(folds, len(set(groups)))
    if folds < 2:
        raise ValueError("Grouped cross-validation needs at least two works")
    predicted = [0] * len(labels)
    for train, test in GroupKFold(n_splits=folds).split(features, labels, groups):
        y = [labels[i] for i in train]
        if len(set(y)) < 2:
            majority = y[0]
            for i in test:
                predicted[i] = majority
            continue
        model = _probe().fit([features[i] for i in train], y)
        for i, value in zip(test, model.predict([features[i] for i in test]), strict=True):
            predicted[i] = int(value)
    return float(f1_score(labels, predicted, average="macro"))


def online_codelength(features, labels, seed: int = 42, blocks=BLOCKS) -> dict:
    order = list(range(len(labels)))
    random.Random(seed).shuffle(order)
    n = len(order)
    cuts = sorted({max(2, int(round(fraction * n))) for fraction in blocks} | {n})
    bits = cuts[0] * 1.0  # first block transmitted with a uniform code over two classes
    for previous, current in zip(cuts, cuts[1:], strict=False):
        train, block = order[:previous], order[previous:current]
        y = [labels[i] for i in train]
        if len(set(y)) < 2:
            share = (y.count(1) + 1) / (len(y) + 2)
            probabilities = [[1 - share, share] for _ in block]
        else:
            model = _probe().fit([features[i] for i in train], y)
            probabilities = model.predict_proba([features[i] for i in block])
        for i, p in zip(block, probabilities, strict=True):
            bits -= math.log2(max(float(p[labels[i]]), 1e-12))
    uniform = float(n)
    return {"codelength_bits": bits, "uniform_bits": uniform, "compression": uniform / bits}


def probe_layers(
    model_name: str,
    records: list[Poem],
    *,
    max_length: int = 512,
    seed: int = 42,
    folds: int = 5,
    device=None,
    loader=None,
) -> dict:
    items = probing_items(records)
    layers = layer_features(model_name, items, max_length, device, loader)
    labels = [i["label"] for i in items]
    groups = [i["group"] for i in items]
    results = []
    for index, features in enumerate(layers):
        results.append(
            {
                "layer": index,
                "macro_f1": grouped_f1(features, labels, groups, folds),
                **online_codelength(features, labels, seed),
            }
        )
    best = max(results, key=lambda r: r["compression"])
    count = len(results) - 1
    return {
        "model": model_name,
        "items": len(items),
        "metaphorical": sum(labels),
        "works": len(set(groups)),
        "layers": results,
        "best_layer_by_mdl": best["layer"],
        "best_layer_relative_depth": best["layer"] / count if count else 0.0,
        "note": "H3 is supported when the best layers lie in the middle third of the network "
        "consistently across models and seeds, not by a single run.",
    }
