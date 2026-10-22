"""Shijing stanza type 賦 / 比 / 興 by a classifier trained on Zhu Xi's labels.

Training and input conventions: scripts/train_stanza_classifier.py. The model reads one
stanza in traditional script; quality (5-fold CV, grouped by poem) is macro-F1 0.55 and
κ 0.43 with Zhu Xi, with 比 weak, so results are suggestions shown with probabilities.
"""

import importlib.util
import re
from functools import lru_cache
from pathlib import Path

from app.schemas.analysis import StanzaLabel

# A blank line (possibly holding spaces, \r or full-width spaces) separates stanzas.
_BLANK_LINE = re.compile(r"\n[^\S\n]*\n")


def split_stanzas(text: str) -> list[tuple[int, int]]:
    """[start, end) of each stanza without surrounding whitespace; no blank line = one."""
    spans, position = [], 0
    for separator in [*_BLANK_LINE.finditer(text), None]:
        stop = separator.start() if separator else len(text)
        segment = text[position:stop]
        if segment.strip():
            start = position + len(segment) - len(segment.lstrip())
            spans.append((start, position + len(segment.rstrip())))
        if separator:
            position = separator.end()
    return spans


_HAN = re.compile(r"[一-鿿]")
_VERSE_BREAK = re.compile(r"[，。；！？、,.;!?\n]")
# The shortest stanzas the classifier was trained on: 8 characters in 2 verses
# ("盧令令、其人美且仁。"). A shorter fragment (an idiom, a single line) is not a stanza
# and its 賦/比/興 label would be meaningless.
MIN_HAN, MIN_VERSES = 8, 2


def is_stanza(segment: str) -> bool:
    verses = [v for v in _VERSE_BREAK.split(segment) if len(_HAN.findall(v)) >= 2]
    return len(_HAN.findall(segment)) >= MIN_HAN and len(verses) >= MIN_VERSES


@lru_cache(maxsize=1)
def _converters():
    from opencc import OpenCC

    return OpenCC("s2t"), OpenCC("t2s")


def to_traditional(text: str) -> str:
    """Simplified text is converted; text already holding traditional forms is kept as is,
    because s2t is not an identity on traditional script (e.g. one-to-many characters)."""
    s2t, t2s = _converters()
    return text if t2s.convert(text) != text else s2t.convert(text)


class StanzaClassifier:
    def __init__(self, model_path, max_length: int = 128):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path).eval()
        config = self.model.config
        self.labels = [config.id2label[i] for i in range(config.num_labels)]
        self.max_length = max_length
        self.version = Path(model_path).name

    def probabilities(self, texts: list[str]) -> list[list[float]]:
        result = []
        with self.torch.no_grad():
            for start in range(0, len(texts), 64):  # batches as in the training script
                encoded = self.tokenizer(
                    texts[start : start + 64],
                    truncation=True,
                    max_length=self.max_length,
                    padding=True,
                    return_tensors="pt",
                )
                result.extend(self.model(**encoded).logits.softmax(-1).tolist())
        return result

    def classify(self, text: str) -> list[StanzaLabel]:
        spans = [(s, e) for s, e in split_stanzas(text) if is_stanza(text[s:e])]
        if not spans:
            return []
        inputs = [to_traditional(text[start:end]) for start, end in spans]
        result = []
        for (start, end), row in zip(spans, self.probabilities(inputs), strict=True):
            best = max(range(len(row)), key=row.__getitem__)
            rounded = [round(p, 4) for p in row]
            result.append(
                StanzaLabel(
                    text=text[start:end],
                    start=start,
                    end=end,
                    label=self.labels[best],
                    probabilities=dict(zip(self.labels, rounded, strict=True)),
                )
            )
        return result


def stanza_model_ready(model_path: str | None) -> bool:
    """Like _local_model_ready in the API: weights plus the libraries to run them."""
    return (
        bool(model_path)
        and Path(model_path).is_dir()
        and all(
            importlib.util.find_spec(name) is not None
            for name in ("torch", "transformers", "opencc")
        )
    )


@lru_cache(maxsize=2)
def load_stanza_classifier(model_path: str | None) -> StanzaClassifier | None:
    """Shared by all pipeline profiles; None when the model or its libraries are absent."""
    return StanzaClassifier(model_path) if stanza_model_ready(model_path) else None
