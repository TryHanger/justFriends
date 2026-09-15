"""Exact character-span scores; negatives and missing predictions remain in the denominator."""

from app.nlp.contracts import validate_result
from app.nlp.corpus import Poem
from app.schemas.analysis import AnalysisResult
from app.schemas.taxonomy import METAPHOR_LABELS


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if p + r else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def evaluate(gold: list[Poem], predictions: dict[str, AnalysisResult]) -> dict:
    if not gold or len({r.id for r in gold}) != len(gold):
        raise ValueError("Gold must be nonempty with unique IDs")
    if set(predictions) != {r.id for r in gold}:
        raise ValueError("Prediction IDs must exactly match gold, including empty predictions")
    for record in gold:
        if record.annotation_status != "gold":
            raise ValueError("Evaluation requires gold records, including annotated negatives")
        validate_result(record.text, record.language, predictions[record.id])
    report = {}
    for language in ("all", "zh", "kk"):
        subset = [r for r in gold if language == "all" or r.language == language]
        counts = {"metaphor_detection": [0, 0, 0], "typed_figures": [0, 0, 0]}
        attributes = {
            name: {"correct": 0, "total": 0, "confusion": {}}
            for name in ("label", "source_domain", "target_domain")
        }
        for record in subset:
            predicted = predictions[record.id].metaphors
            for name, typed in (("metaphor_detection", False), ("typed_figures", True)):

                def keys(spans):
                    return {
                        (s.start, s.end, s.label) if typed else (s.start, s.end)
                        for s in spans
                        if typed or s.label in METAPHOR_LABELS
                    }

                expected, actual = keys(record.spans), keys(predicted)
                delta = (len(expected & actual), len(actual - expected), len(expected - actual))
                counts[name] = [a + b for a, b in zip(counts[name], delta)]
            by_bounds = {(s.start, s.end): s for s in predicted}
            for target in record.spans:
                match = by_bounds.get((target.start, target.end))
                if match is None:
                    continue
                for name, values in attributes.items():
                    actual, expected = getattr(match, name), getattr(target, name)
                    values["correct"] += int(actual == expected)
                    values["total"] += 1
                    row = values["confusion"].setdefault(expected, {})
                    row[actual] = row.get(actual, 0) + 1
        report[language] = {
            "documents": len(subset),
            **{k: prf(*v) for k, v in counts.items()},
            "attributes_on_exact_matches": attributes,
        }
    report["synthetic"] = any(r.synthetic for r in gold)
    return report


def recall_at_k(relevance: dict[str, list[str]], rankings: dict[str, list[str]], k: int) -> float:
    if k < 1 or not relevance or set(relevance) != set(rankings):
        raise ValueError("Use positive k and identical nonempty query IDs")
    values = []
    for query, relevant in relevance.items():
        if not relevant or len(rankings[query]) != len(set(rankings[query])):
            raise ValueError("Each query needs relevant items and a duplicate-free ranking")
        values.append(len(set(rankings[query][:k]) & set(relevant)) / len(set(relevant)))
    return sum(values) / len(values)


def annotation_agreement(first: list[Poem], second: list[Poem]) -> dict:
    """Character binary Cohen kappa + exact-span F1; no tokenization dependency."""
    other = {r.id: r for r in second}
    if (
        not first
        or len(other) != len(second)
        or len({r.id for r in first}) != len(first)
        or {r.id for r in first} != set(other)
    ):
        raise ValueError("Annotators must label the same nonempty set of unique poems")
    n = agree = positives_a = positives_b = tp = fp = fn = 0
    for a in first:
        b = other[a.id]
        if a.annotation_status == "unlabeled" or b.annotation_status == "unlabeled":
            raise ValueError("Agreement requires reviewed annotations, including negatives")
        if a.text != b.text or a.language != b.language:
            raise ValueError("Annotators must use identical source text and language")

        def bounds(record):
            return {(s.start, s.end) for s in record.spans if s.label in METAPHOR_LABELS}

        sa, sb = bounds(a), bounds(b)
        ca = {i for start, end in sa for i in range(start, end)}
        cb = {i for start, end in sb for i in range(start, end)}
        n += len(a.text)
        agree += len(a.text) - len(ca ^ cb)
        positives_a += len(ca)
        positives_b += len(cb)
        tp, fp, fn = tp + len(sa & sb), fp + len(sb - sa), fn + len(sa - sb)
    pa, pb = positives_a / n, positives_b / n
    chance = pa * pb + (1 - pa) * (1 - pb)
    return {
        "character_kappa": (agree / n - chance) / (1 - chance) if chance < 1 else None,
        "span_agreement": prf(tp, fp, fn),
        "characters": n,
    }
