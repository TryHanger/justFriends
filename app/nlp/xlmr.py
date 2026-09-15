"""XLM-R BIO detection with complete-text sliding windows and original character offsets."""

from pathlib import Path

from app.nlp.contracts import resolve_language, validate_result
from app.schemas.analysis import AnalysisResult, MetaphorSpan
from app.schemas.taxonomy import BIO_LABELS, METAPHOR_LABELS

LABEL2ID = {label: i for i, label in enumerate(BIO_LABELS)}


def align_labels(text, offsets, spans):
    """Reject unrepresentable boundaries instead of silently changing the gold annotation."""
    positives = [s for s in spans if s.label in METAPHOR_LABELS]
    labels, seen, covered = [], set(), {}
    for start, end in offsets:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        hits = [i for i, s in enumerate(positives) if start < s.end and end > s.start]
        if start == end or not hits:
            labels.append(0)
            continue
        if len(hits) != 1:
            raise ValueError("Tokenizer merges different gold spans; review annotation boundaries")
        i = hits[0]
        span = positives[i]
        if start < span.start or end > span.end:
            raise ValueError("Gold boundary cuts a tokenizer token; review annotation boundaries")
        labels.append(2 if i in seen else 1)
        seen.add(i)
        covered.setdefault(i, []).append((start, end))
    for i, span in enumerate(positives):
        parts = covered.get(i, [])
        if (
            not parts
            or min(a for a, _ in parts) != span.start
            or max(b for _, b in parts) != span.end
        ):
            raise ValueError("Gold span cannot be represented by tokenizer offsets")
    return labels


def token_windows(ids, offsets, tokenizer, max_length=256, stride=64, labels=None):
    capacity = max_length - 2
    if not 4 <= max_length <= 512 or not 0 <= stride < capacity:
        raise ValueError("Use max_length 4..512 and stride < max_length-2")
    if tokenizer.bos_token_id is None or tokenizer.eos_token_id is None:
        raise ValueError("XLM-R tokenizer requires BOS/EOS tokens")
    if len(ids) != len(offsets) or labels is not None and len(labels) != len(ids):
        raise ValueError("Token, offset and label lengths must match")
    for start in range(0, len(ids), capacity - stride):
        end = min(start + capacity, len(ids))
        feature = {
            "input_ids": [tokenizer.bos_token_id, *ids[start:end], tokenizer.eos_token_id],
            "attention_mask": [1] * (end - start + 2),
        }
        if labels is not None:
            feature["labels"] = [-100, *labels[start:end], -100]
        yield start, end, feature
        if end == len(ids):
            break


def decode_bio(text, offsets, tags, confidences):
    if not len(offsets) == len(tags) == len(confidences):
        raise ValueError("Mismatched BIO arrays")
    spans, current = [], None

    def finish():
        if current:
            start, end, scores = current
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            if start < end:
                spans.append(
                    MetaphorSpan(
                        text=text[start:end],
                        start=start,
                        end=end,
                        label="metaphor",
                        source_domain="unknown",
                        target_domain="unknown",
                        confidence=sum(scores) / len(scores),
                        rationale="XLM-R detected a metaphor; type and domains need classification.",
                    )
                )

    for (start, end), tag, confidence in zip(offsets, tags, confidences):
        if tag not in BIO_LABELS:
            raise ValueError(f"Unexpected BIO label {tag}")
        if start == end:
            continue
        # SentencePiece byte fallback may produce multiple tokens with overlapping offsets.
        if current and start < current[1]:
            current[1] = max(end, current[1])
            current[2].append(confidence)
            continue
        if tag == "O":
            finish()
            current = None
        elif tag == "B-METAPHOR" or current is None:
            finish()
            current = [start, end, [confidence]]
        else:
            current[1] = end
            current[2].append(confidence)
    finish()
    return spans


class XLMRDetector:
    def __init__(self, model_path: str, max_length=256, stride=64, device=None):
        if not Path(model_path).is_dir():
            raise ValueError("XLMR_MODEL_PATH must point to a locally fine-tuned checkpoint")
        if not 4 <= max_length <= 512 or not 0 <= stride < max_length - 2:
            raise ValueError("Use max_length 4..512 and stride < max_length-2")

        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, use_fast=True, local_files_only=True
        )
        self.model = AutoModelForTokenClassification.from_pretrained(
            model_path, local_files_only=True
        )
        if self.model.config.model_type != "xlm-roberta" or not self.tokenizer.is_fast:
            raise ValueError("Expected XLM-R and a fast tokenizer")
        if self.model.config.id2label != dict(enumerate(BIO_LABELS)):
            raise ValueError("Checkpoint must be trained with O, B-METAPHOR, I-METAPHOR")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device).eval()
        self.max_length, self.stride = max_length, stride
        self.version = getattr(
            self.model.config, "nlp_model_version", f"xlmr:{Path(model_path).name}"
        )

    def analyze(self, text: str, language: str = "auto") -> AnalysisResult:
        import torch

        language = resolve_language(text, language)
        encoded = self.tokenizer(
            text, add_special_tokens=False, return_offsets_mapping=True, verbose=False
        )
        ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
        sums = torch.zeros(len(ids), 3)
        counts = torch.zeros(len(ids), 1)
        with torch.inference_mode():
            for start, end, feature in token_windows(
                ids, offsets, self.tokenizer, self.max_length, self.stride
            ):
                tensors = {k: torch.tensor([v], device=self.device) for k, v in feature.items()}
                probs = self.model(**tensors).logits[0, 1:-1].softmax(-1).cpu()
                sums[start:end] += probs
                counts[start:end] += 1
        if ids:
            scores, labels = (sums / counts).max(-1)
            spans = decode_bio(
                text, offsets, [BIO_LABELS[i] for i in labels.tolist()], scores.tolist()
            )
        else:
            spans = []
        result = AnalysisResult(
            language=language,
            model_version=self.version,
            metaphors=spans,
            needs_review=True,
            warnings=["Token probabilities are uncalibrated; domains unknown."],
        )
        return validate_result(text, language, result)
