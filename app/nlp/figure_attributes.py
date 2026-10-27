"""Figure type, source and target domains for spans found by XLM-R.

The XLM-R detector only tags tokens as inside or outside a figure. Each span then gets a
type and two domains from linear heads over the detector's own hidden states (mean of the
span tokens in layers 6, 9 and 12, plus the mean of a context window), trained by
scripts/train_figure_attributes.py on Claude-annotated Chinese and Kazakh poems. An
explicit comparison marker (如/似/若…, -дай/-дей, сияқты…) makes the span a simile. The
explanation is assembled in Russian from these predictions.

Cross-validated by poem, the type is right 78% of the time, the source domain 46% and the
target domain 35%; below 0.4 probability a domain is right about one time in four, so it
is left unknown, and below 0.5 the explanation calls it tentative.
"""

import json
import re
from pathlib import Path

from app.schemas.analysis import AnalysisResult, MetaphorSpan

HEADS = ("label", "source_domain", "target_domain")
CONTEXT_CHARS = 80
UNKNOWN_BELOW = 0.4
TENTATIVE_BELOW = 0.5

LABEL_RU = {
    "metaphor": "метафора",
    "simile": "сравнение",
    "personification": "олицетворение",
    "metonymy": "метонимия",
    "idiom": "идиома",
}
DOMAIN_RU = {
    "nature": "природа",
    "water": "вода",
    "fire": "огонь",
    "light": "свет",
    "darkness": "тьма",
    "plant": "растение",
    "animal": "животное",
    "body": "тело",
    "person": "человек",
    "object": "предмет",
    "space": "пространство",
    "motion": "движение",
    "journey": "путь",
    "time": "время",
    "life": "жизнь",
    "death": "смерть",
    "emotion": "чувства",
    "love": "любовь",
    "mind": "разум",
    "society": "общество",
    "spirituality": "духовность",
    "other": "другое",
}

# Longest first, so that 如同 is reported rather than 如.
ZH_MARKERS = (
    "如同", "好像", "宛如", "犹如", "猶如", "恰似", "仿佛", "彷彿", "好似",
    "似", "如", "若", "犹", "猶", "像",
)  # fmt: skip
KK_SUFFIX = re.compile(r"[дт][ае]й(?:ын|ін|-ақ)?$", re.IGNORECASE)
KK_WORDS = ("сияқты", "секілді", "сықылды", "тәрізді", "іспетті", "бейне")
WORD = r"[^\W\d_]+(?:-[^\W\d_]+)?"


def simile_marker(text: str, start: int, end: int, language: str) -> str | None:
    """The comparison word inside the span or right next to it, if any.

    On the annotated poems a marker means a simile with precision 0.92, recall 0.86."""
    if language == "zh":
        window = text[max(0, start - 2) : end]
        return next((m for m in ZH_MARKERS if m in window), None)
    words = re.findall(WORD, text[start:end])
    for word in words:
        if len(word) > 4 and KK_SUFFIX.search(word):
            return word
    neighbours = re.findall(WORD, text[max(0, start - 12) : start])[-1:]
    neighbours += re.findall(WORD, text[end : end + 14])[:1]
    return next((w for w in words + neighbours if w.lower() in KK_WORDS), None)


def explanation(span: MetaphorSpan, marker: str | None, tentative: bool) -> str:
    source = DOMAIN_RU.get(span.source_domain)
    target = DOMAIN_RU.get(span.target_domain)
    head = f"«{span.text}» — {LABEL_RU[span.label]}"
    if span.label == "personification":
        text = f"{head}: свойства человека переносятся" + (
            f" на область «{target}»." if target else "."
        )
    elif span.label == "idiom":
        text = f"{head}: устойчивое образное выражение" + (
            f" об области «{target}»." if target else "."
        )
    elif source and target:
        text = f"{head}: образ из области «{source}» переносится на область «{target}»."
    elif source:
        text = f"{head}: образ из области «{source}»; на что он переносится, модель не определила."
    elif target:
        text = f"{head}: образное выражение об области «{target}»."
    else:
        text = f"{head}; области образа модель не определила."
    if marker:
        text += f" Сравнение выражено словом «{marker}»."
    if tentative:
        text += " Области определены предположительно."
    return text


class FigureAttributes:
    """Linear heads stored as JSON next to the detector checkpoint (no pickle)."""

    def __init__(self, heads: dict, layers: list[int], report: dict | None = None):
        import numpy as np

        self.layers = layers
        self.report = report or {}
        self.heads = {
            name: (
                np.asarray(head["coef"], dtype="float32"),
                np.asarray(head["intercept"], dtype="float32"),
                head["classes"],
                np.asarray(head["mean"], dtype="float32"),
                np.asarray(head["scale"], dtype="float32"),
            )
            for name, head in heads.items()
        }

    @classmethod
    def load(cls, path: str | Path) -> "FigureAttributes | None":
        path = Path(path)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["heads"], data["layers"], data.get("report"))

    def predict(self, features) -> dict[str, tuple[str, float]]:
        """Most probable class and its probability per head."""
        import numpy as np

        result = {}
        for name, (coef, intercept, classes, mean, scale) in self.heads.items():
            logits = coef @ ((features - mean) / scale) + intercept
            probs = np.exp(logits - logits.max())
            probs /= probs.sum()
            best = int(probs.argmax())
            result[name] = (classes[best], float(probs[best]))
        return result

    def features(self, model, tokenizer, device, text: str, start: int, end: int):
        """Hidden states of the span in its context window; None if no token covers it."""
        import torch

        left = max(0, start - CONTEXT_CHARS)
        window = text[left : min(len(text), end + CONTEXT_CHARS)]
        encoded = tokenizer(
            window,
            return_offsets_mapping=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        offsets = encoded.pop("offset_mapping")[0].tolist()
        with torch.inference_mode():
            hidden = model(
                **{k: v.to(device) for k, v in encoded.items()}, output_hidden_states=True
            ).hidden_states
        start, end = start - left, end - left
        inside = [i for i, (a, b) in enumerate(offsets) if b > a and a < end and b > start]
        if not inside:
            return None
        real = [i for i, (a, b) in enumerate(offsets) if b > a]
        parts = [hidden[layer][0, inside].mean(0) for layer in self.layers]
        parts.append(hidden[self.layers[-1]][0, real].mean(0))
        return torch.cat(parts).float().cpu().numpy()

    def apply(self, text: str, result: AnalysisResult, model, tokenizer, device) -> AnalysisResult:
        spans = []
        for span in result.metaphors:
            vector = self.features(model, tokenizer, device, text, span.start, span.end)
            if vector is None:
                spans.append(span)
                continue
            marker = simile_marker(text, span.start, span.end, result.language)
            spans.append(annotate(span, self.predict(vector), marker))
        method = {
            **result.method,
            "attributes": {
                "method": "linear heads over XLM-R hidden states; comparison markers",
                "source": self.report.get("source"),
                "cv_accuracy": {
                    head: values.get("accuracy")
                    for head, values in self.report.get("cv", {}).items()
                },
            },
        }
        return result.model_copy(update={"metaphors": spans, "method": method})


def annotate(
    span: MetaphorSpan, predicted: dict[str, tuple[str, float]], marker: str | None
) -> MetaphorSpan:
    """Type and domains from the heads (a comparison marker overrides the type)."""
    domains = {}
    tentative = False
    for head in ("source_domain", "target_domain"):
        value, probability = predicted[head]
        domains[head] = value if probability >= UNKNOWN_BELOW else "unknown"
        tentative |= UNKNOWN_BELOW <= probability < TENTATIVE_BELOW
    updated = span.model_copy(
        update={"label": "simile" if marker else predicted["label"][0], **domains}
    )
    return updated.model_copy(update={"rationale": explanation(updated, marker, tentative)})
