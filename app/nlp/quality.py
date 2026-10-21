"""Diagnostic quality metrics complementing the ТЗ targets in evaluation.py.

overlap_detection   one-to-one span matching by any character overlap: separates
                    "found the metaphor" from "drew the exact boundary".
char_detection      character-level P/R/F1 of metaphorical characters; boundary-tolerant
                    and independent of tokenizers.
document_detection  does the text contain a metaphor at all, plus false-alarm rate on
                    texts without metaphors (needs annotated negatives).
text_fields         tenor / ground / semantic label quality on matched spans: chrF
                    (character n-gram F-score, works for zh, kk and ru) and exact match.
tenor_localization  exact P/R/F1 of tenor offsets in the text.
calibration         ECE, Brier score and precision/coverage per confidence threshold;
                    used to choose which predictions experts must review.
by_genre            detection F1 per genre/era, exposing prose→poetry domain shift.
reliability         share of failed, truncated or omitted outputs and token usage.
"""

from collections import Counter, defaultdict

from app.schemas.taxonomy import METAPHOR_LABELS

TEXT_FIELDS = ("tenor", "ground", "semantic_label")
THRESHOLDS = (0.3, 0.5, 0.7, 0.9)


def _figurative(spans):
    return [s for s in spans if s.label in METAPHOR_LABELS]


def overlap_matches(gold, predicted) -> list[tuple]:
    """Greedy one-to-one pairs (gold, predicted) with any character overlap, largest first."""
    pairs = []
    for g in gold:
        for p in predicted:
            overlap = min(g.end, p.end) - max(g.start, p.start)
            if overlap > 0:
                pairs.append((overlap, g, p))
    used_g, used_p, matches = set(), set(), []
    for _, g, p in sorted(pairs, key=lambda item: -item[0]):
        if id(g) in used_g or id(p) in used_p:
            continue
        used_g.add(id(g))
        used_p.add(id(p))
        matches.append((g, p))
    return matches


def detection_counts(record, prediction) -> dict:
    gold, predicted = _figurative(record.spans), _figurative(prediction.metaphors)
    matched = len(overlap_matches(gold, predicted))
    gold_chars = {i for s in gold for i in range(s.start, s.end)}
    pred_chars = {i for s in predicted for i in range(s.start, s.end)}
    gold_doc, pred_doc = bool(gold), bool(predicted)
    return {
        "overlap_detection": (matched, len(predicted) - matched, len(gold) - matched),
        "char_detection": (
            len(gold_chars & pred_chars),
            len(pred_chars - gold_chars),
            len(gold_chars - pred_chars),
        ),
        "document_detection": (
            int(gold_doc and pred_doc),
            int(pred_doc and not gold_doc),
            int(gold_doc and not pred_doc),
        ),
        "negative_document": None if gold_doc else int(pred_doc),
    }


def chrf(hypothesis: str, reference: str, max_n: int = 6, beta: float = 2.0) -> float:
    """chrF (Popović, 2015): character n-gram F-beta averaged over n, whitespace ignored."""
    hyp, ref = "".join(hypothesis.split()).lower(), "".join(reference.split()).lower()
    if not hyp or not ref:
        return 0.0
    precisions, recalls = [], []
    for n in range(1, max_n + 1):
        h = Counter(hyp[i : i + n] for i in range(len(hyp) - n + 1))
        r = Counter(ref[i : i + n] for i in range(len(ref) - n + 1))
        if not h or not r:
            continue
        common = sum((h & r).values())
        precisions.append(common / sum(h.values()))
        recalls.append(common / sum(r.values()))
    if not precisions:
        return 0.0
    p, r = sum(precisions) / len(precisions), sum(recalls) / len(recalls)
    return (1 + beta**2) * p * r / (beta**2 * p + r) if p + r else 0.0


def text_field_scores(gold_records, predictions) -> dict:
    scores = {
        name: {"pairs": 0, "predicted": 0, "chrf_sum": 0.0, "exact": 0} for name in TEXT_FIELDS
    }
    tenor = [0, 0, 0]
    for record in gold_records:
        prediction = predictions[record.id]
        for g, p in overlap_matches(_figurative(record.spans), _figurative(prediction.metaphors)):
            for name in TEXT_FIELDS:
                reference = getattr(g, name)
                if not reference:
                    continue
                item = scores[name]
                item["pairs"] += 1
                hypothesis = getattr(p, name)
                if hypothesis:
                    item["predicted"] += 1
                    item["chrf_sum"] += chrf(hypothesis, reference)
                    item["exact"] += int(
                        " ".join(hypothesis.split()) == " ".join(reference.split())
                    )
        gold_tenors = {
            (s.tenor_start, s.tenor_end) for s in record.spans if s.tenor_start is not None
        }
        pred_tenors = {
            (s.tenor_start, s.tenor_end) for s in prediction.metaphors if s.tenor_start is not None
        }
        if gold_tenors or any(s.tenor for s in record.spans):
            tenor[0] += len(gold_tenors & pred_tenors)
            tenor[1] += len(pred_tenors - gold_tenors)
            tenor[2] += len(gold_tenors - pred_tenors)
    result = {}
    for name, item in scores.items():
        if item["pairs"]:
            result[name] = {
                "matched_spans_with_gold": item["pairs"],
                "coverage": item["predicted"] / item["pairs"],
                # Missing predictions score 0, so chrF is not inflated by abstentions.
                "chrf": item["chrf_sum"] / item["pairs"],
                "exact_match": item["exact"] / item["pairs"],
            }
    return result, (tenor if any(tenor) else None)


def calibration(gold_records, predictions, bins: int = 10) -> dict | None:
    points = []
    for record in gold_records:
        gold = _figurative(record.spans)
        predicted = _figurative(predictions[record.id].metaphors)
        hits = {id(p) for _, p in overlap_matches(gold, predicted)}
        points.extend((p.confidence, int(id(p) in hits)) for p in predicted)
    if not points:
        return None
    buckets = defaultdict(list)
    for confidence, correct in points:
        buckets[min(int(confidence * bins), bins - 1)].append((confidence, correct))
    ece = sum(
        len(items)
        / len(points)
        * abs(sum(c for c, _ in items) / len(items) - sum(k for _, k in items) / len(items))
        for items in buckets.values()
    )
    brier = sum((c - k) ** 2 for c, k in points) / len(points)
    curve = []
    for threshold in THRESHOLDS:
        kept = [k for c, k in points if c >= threshold]
        curve.append(
            {
                "threshold": threshold,
                "coverage": len(kept) / len(points),
                "precision": sum(kept) / len(kept) if kept else None,
            }
        )
    return {"predicted_spans": len(points), "ece": ece, "brier": brier, "by_threshold": curve}


def reliability(predictions: dict) -> dict:
    values = list(predictions.values())
    usage = [p.method.get("usage") for p in values if isinstance(p.method.get("usage"), dict)]
    report = {
        "documents": len(values),
        "failed": sum(p.model_version.startswith("failed:") for p in values),
        "with_omitted_spans": sum(any("omitted" in w for w in p.warnings) for p in values),
        "sampling_not_applied": sum(p.method.get("sampling_applied") is False for p in values),
    }
    if usage:
        report["mean_input_tokens"] = sum(u.get("input_tokens", 0) for u in usage) / len(usage)
        report["mean_output_tokens"] = sum(u.get("output_tokens", 0) for u in usage) / len(usage)
        report["total_tokens"] = sum(
            u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage
        )
    return report
