"""Evaluation for ТЗ п. 6. Negatives and missing predictions remain in the denominator.

Metrics per language (all / zh / kk):
  metaphor_detection   exact-span P/R/F1 for metaphor + personification
  typed_figures        exact span and figure type for all five labels
  entity_extraction    exact-boundary P/R/F1 of entity candidates (module B)
  usage_classification literal vs metaphorical on gold candidates (module C), positive = metaphorical
  semantic_labeling    end-to-end P/R/F1 of (span, field, value) for domains, semantic label, sentiment
"""

import random
from collections import Counter
from itertools import combinations

from app.nlp.contracts import validate_result
from app.nlp.corpus import Poem
from app.schemas.analysis import AnalysisResult
from app.schemas.taxonomy import METAPHOR_LABELS

SEMANTIC_FIELDS = ("source_domain", "target_domain", "semantic_label", "sentiment")
# Target values from ТЗ п. 6 (lower bound of each range).
TZ_TARGETS = {
    "entity_extraction": 0.90,
    "usage_classification": 0.82,
    "semantic_labeling": 0.75,
    "inter_annotator_kappa": 0.75,
}
_COUNTED = (
    "metaphor_detection",
    "typed_figures",
    "entity_extraction",
    "usage_classification",
    "semantic_labeling",
)


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


def _norm(value) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).lower().replace("ё", "е").split()) or None


def _semantic_tuples(spans, fields) -> set:
    return {
        (s.start, s.end, name, _norm(getattr(s, name)))
        for s in spans
        if s.label in METAPHOR_LABELS
        for name in fields
        if _norm(getattr(s, name)) is not None
    }


def record_counts(record: Poem, prediction: AnalysisResult) -> dict:
    """Additive TP/FP/FN counts for one document; used directly and for bootstrap."""
    predicted = prediction.metaphors
    counts = {}
    for name, typed in (("metaphor_detection", False), ("typed_figures", True)):

        def keys(spans, typed=typed):
            return {
                (s.start, s.end, s.label) if typed else (s.start, s.end)
                for s in spans
                if typed or s.label in METAPHOR_LABELS
            }

        expected, actual = keys(record.spans), keys(predicted)
        counts[name] = (len(expected & actual), len(actual - expected), len(expected - actual))

    if record.candidates:
        expected = {(c.start, c.end) for c in record.candidates}
        actual = {(c.start, c.end) for c in prediction.candidates}
        counts["entity_extraction"] = (
            len(expected & actual),
            len(actual - expected),
            len(expected - actual),
        )
        by_bounds = {(c.start, c.end): c.usage_type for c in prediction.candidates}
        tp = fp = fn = 0
        for candidate in record.candidates:
            # Missing or unclassified prediction counts as "not metaphorical".
            guess = by_bounds.get((candidate.start, candidate.end)) == "metaphorical"
            truth = candidate.usage_type == "metaphorical"
            tp, fp, fn = (
                tp + (guess and truth),
                fp + (guess and not truth),
                fn + (truth and not guess),
            )
        counts["usage_classification"] = (tp, fp, fn)
    else:
        counts["entity_extraction"] = counts["usage_classification"] = None

    # Only fields that gold annotates are scored; a field absent from gold is not penalised.
    fields = [f for f in SEMANTIC_FIELDS if any(getattr(s, f) is not None for s in record.spans)]
    if fields:
        expected = _semantic_tuples(record.spans, fields)
        actual = _semantic_tuples(predicted, fields)
        counts["semantic_labeling"] = (
            len(expected & actual),
            len(actual - expected),
            len(expected - actual),
        )
        counts["semantic_fields"] = {
            name: (
                len({t for t in expected if t[2] == name} & {t for t in actual if t[2] == name}),
                len({t for t in actual if t[2] == name} - expected),
                len({t for t in expected if t[2] == name} - actual),
            )
            for name in fields
        }
    else:
        counts["semantic_labeling"] = None
        counts["semantic_fields"] = {}
    return counts


def _sum(rows: list[dict], name: str):
    present = [r[name] for r in rows if r[name] is not None]
    if not present:
        return None
    return [sum(values) for values in zip(*present, strict=True)], len(present)


def _check(gold: list[Poem], predictions: dict[str, AnalysisResult]) -> None:
    if not gold or len({r.id for r in gold}) != len(gold):
        raise ValueError("Gold must be nonempty with unique IDs")
    if set(predictions) != {r.id for r in gold}:
        raise ValueError("Prediction IDs must exactly match gold, including empty predictions")
    for record in gold:
        if record.annotation_status != "gold":
            raise ValueError("Evaluation requires gold records, including annotated negatives")
        validate_result(record.text, record.language, predictions[record.id])


def evaluate(gold: list[Poem], predictions: dict[str, AnalysisResult]) -> dict:
    _check(gold, predictions)
    counts = {r.id: record_counts(r, predictions[r.id]) for r in gold}
    report = {}
    for language in ("all", "zh", "kk"):
        subset = [r for r in gold if language == "all" or r.language == language]
        rows = [counts[r.id] for r in subset]
        section = {"documents": len(subset)}
        for name in _COUNTED:
            summed = _sum(rows, name)
            section[name] = None if summed is None else {**prf(*summed[0]), "documents": summed[1]}
        fields = {}
        for row in rows:
            for name, values in row["semantic_fields"].items():
                fields[name] = [
                    a + b for a, b in zip(fields.get(name, (0, 0, 0)), values, strict=True)
                ]
        section["semantic_by_field"] = {name: prf(*values) for name, values in fields.items()}
        section["attributes_on_exact_matches"] = _attribute_confusion(subset, predictions)
        report[language] = section
    report["tz_targets"] = tz_targets(report["all"])
    report["synthetic"] = any(r.synthetic for r in gold)
    return report


def _attribute_confusion(subset: list[Poem], predictions: dict[str, AnalysisResult]) -> dict:
    attributes = {
        name: {"correct": 0, "total": 0, "confusion": {}}
        for name in ("label", "source_domain", "target_domain", "sentiment")
    }
    for record in subset:
        by_bounds = {(s.start, s.end): s for s in predictions[record.id].metaphors}
        for target in record.spans:
            match = by_bounds.get((target.start, target.end))
            if match is None:
                continue
            for name, values in attributes.items():
                expected = getattr(target, name)
                if expected is None:
                    continue
                actual = getattr(match, name)
                values["correct"] += int(actual == expected)
                values["total"] += 1
                row = values["confusion"].setdefault(str(expected), {})
                row[str(actual)] = row.get(str(actual), 0) + 1
    return attributes


def tz_targets(section: dict, kappa: float | None = None) -> dict:
    achieved = {
        "entity_extraction": (section.get("entity_extraction") or {}).get("f1"),
        "usage_classification": (section.get("usage_classification") or {}).get("f1"),
        "semantic_labeling": (section.get("semantic_labeling") or {}).get("f1"),
        "inter_annotator_kappa": kappa,
    }
    return {
        name: {
            "target": target,
            "achieved": achieved[name],
            "met": None if achieved[name] is None else achieved[name] >= target,
        }
        for name, target in TZ_TARGETS.items()
    }


def bootstrap(
    gold: list[Poem],
    predictions: dict[str, AnalysisResult],
    *,
    samples: int = 1000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict:
    """Percentile F1 intervals by resampling original works (work_id), not documents or tokens."""
    _check(gold, predictions)
    if samples < 10 or not 0 < confidence < 1:
        raise ValueError("Use at least 10 samples and confidence in (0, 1)")
    counts = {r.id: record_counts(r, predictions[r.id]) for r in gold}
    works: dict[str, list[str]] = {}
    for record in gold:
        works.setdefault(record.work_id, []).append(record.id)
    keys = sorted(works)
    rng = random.Random(seed)
    values = {name: [] for name in _COUNTED}
    for _ in range(samples):
        rows = [counts[i] for key in rng.choices(keys, k=len(keys)) for i in works[key]]
        for name in _COUNTED:
            summed = _sum(rows, name)
            if summed is not None:
                values[name].append(prf(*summed[0])["f1"])
    low, high = (1 - confidence) / 2, 1 - (1 - confidence) / 2
    result = {}
    for name, series in values.items():
        if series:
            series.sort()
            result[name] = {
                "f1_low": series[int(low * (len(series) - 1))],
                "f1_high": series[int(high * (len(series) - 1))],
                "samples": len(series),
            }
    return {"confidence": confidence, "works": len(keys), "metrics": result}


def recall_at_k(relevance: dict[str, list[str]], rankings: dict[str, list[str]], k: int) -> float:
    if k < 1 or not relevance or set(relevance) != set(rankings):
        raise ValueError("Use positive k and identical nonempty query IDs")
    values = []
    for query, relevant in relevance.items():
        if not relevant or len(rankings[query]) != len(set(rankings[query])):
            raise ValueError("Each query needs relevant items and a duplicate-free ranking")
        values.append(len(set(rankings[query][:k]) & set(relevant)) / len(set(relevant)))
    return sum(values) / len(values)


def cohen_kappa(first: list, second: list) -> float | None:
    if len(first) != len(second) or not first:
        raise ValueError("Cohen kappa needs two equally long nonempty rating lists")
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / n
    ca, cb = Counter(first), Counter(second)
    expected = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    return (observed - expected) / (1 - expected) if expected < 1 else None


def fleiss_kappa(ratings: list[list]) -> float | None:
    """ratings[item] = category chosen by each rater; every item needs the same rater count."""
    if not ratings:
        raise ValueError("Fleiss kappa needs rated items")
    raters = len(ratings[0])
    if raters < 2 or any(len(row) != raters for row in ratings):
        raise ValueError("Every item needs the same number (>= 2) of ratings")
    totals: Counter = Counter()
    agreement = 0.0
    for row in ratings:
        counts = Counter(row)
        totals.update(counts)
        agreement += (sum(c * c for c in counts.values()) - raters) / (raters * (raters - 1))
    observed = agreement / len(ratings)
    n = len(ratings) * raters
    expected = sum((c / n) ** 2 for c in totals.values())
    return (observed - expected) / (1 - expected) if expected < 1 else None


def annotation_agreement(*annotators: list[Poem]) -> dict:
    """Agreement of two or more annotators on the same poems (ТЗ п. 2.2.5, 6).

    character_*: binary metaphorical/not per character (no tokenizer dependency);
    span_agreement: pairwise exact-span F1; candidate_usage_*: literal vs metaphorical
    on candidates every annotator marked with identical boundaries.
    """
    if len(annotators) < 2:
        raise ValueError("Agreement needs at least two annotators")
    indexes = []
    for records in annotators:
        index = {r.id: r for r in records}
        if not records or len(index) != len(records):
            raise ValueError("Annotators must label the same nonempty set of unique poems")
        indexes.append(index)
    ids = sorted(indexes[0])
    if any(set(index) != set(ids) for index in indexes):
        raise ValueError("Annotators must label the same nonempty set of unique poems")

    def bounds(record):
        return {(s.start, s.end) for s in record.spans if s.label in METAPHOR_LABELS}

    char_ratings: list[list[int]] = []
    usage_ratings: list[list[str]] = []
    for poem_id in ids:
        records = [index[poem_id] for index in indexes]
        if any(r.annotation_status == "unlabeled" for r in records):
            raise ValueError("Agreement requires reviewed annotations, including negatives")
        if len({(r.text, r.language) for r in records}) != 1:
            raise ValueError("Annotators must use identical source text and language")
        marked = [{i for s, e in bounds(r) for i in range(s, e)} for r in records]
        char_ratings.extend([int(i in m) for m in marked] for i in range(len(records[0].text)))
        decisions = [{(c.start, c.end): c.usage_type for c in r.candidates} for r in records]
        shared = set.intersection(*(set(d) for d in decisions)) if decisions else set()
        usage_ratings.extend([d[key] for d in decisions] for key in sorted(shared))

    pairs = []
    for a, b in combinations(range(len(indexes)), 2):
        tp = fp = fn = 0
        for poem_id in ids:
            sa, sb = bounds(indexes[a][poem_id]), bounds(indexes[b][poem_id])
            tp, fp, fn = tp + len(sa & sb), fp + len(sb - sa), fn + len(sa - sb)
        pairs.append(
            {
                "annotators": [a, b],
                "character_kappa": cohen_kappa(
                    [row[a] for row in char_ratings], [row[b] for row in char_ratings]
                ),
                "span_agreement": prf(tp, fp, fn),
            }
        )
    defined = [p["character_kappa"] for p in pairs if p["character_kappa"] is not None]
    result = {
        "annotators": len(indexes),
        "characters": len(char_ratings),
        "character_fleiss_kappa": fleiss_kappa(char_ratings),
        "character_cohen_kappa_mean": sum(defined) / len(defined) if defined else None,
        "pairs": pairs,
        "shared_candidates": len(usage_ratings),
        "candidate_usage_fleiss_kappa": fleiss_kappa(usage_ratings) if usage_ratings else None,
    }
    if len(indexes) == 2:
        # Backward-compatible keys of the two-annotator report.
        result["character_kappa"] = pairs[0]["character_kappa"]
        result["span_agreement"] = pairs[0]["span_agreement"]
    main = result["candidate_usage_fleiss_kappa"]
    if main is None:
        main = result["character_fleiss_kappa"]
    result["tz_target"] = {
        "target": TZ_TARGETS["inter_annotator_kappa"],
        "achieved": main,
        "met": None if main is None else main >= TZ_TARGETS["inter_annotator_kappa"],
    }
    return result
