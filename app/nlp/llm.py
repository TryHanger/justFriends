"""LLM adapters with one JSON contract and no provider calls at import time.

Every provider implements only `_complete(instructions, user, schema, sampling)`; prompt
strategies (ТЗ п. 2.2.2), soft-lexicon candidates (module B), output parsing and validation
(modules C/D) are shared so that methods are compared on identical post-processing.
"""

import json
import logging
import re
import threading
from urllib.request import Request, urlopen

from app.nlp.contracts import (
    NLPInputError,
    context_sentence,
    output_model,
    output_schema,
    resolve_language,
    validate_result,
)
from app.nlp.lexicon import CandidateExtractor, merge_candidates
from app.nlp.prompts import PromptStrategy, build_prompt
from app.schemas.analysis import AnalysisResult, EntityCandidate, MetaphorSpan

DEFAULT_STRATEGY = "few_shot+cot+rag+lexicon"
logger = logging.getLogger(__name__)
_MIP_KEYS = ("basic_meaning", "contextual_meaning", "contrast")


_KAZAKH_LETTERS = frozenset("әғқңөұүһіӘҒҚҢӨҰҮҺІ")


def _russian(value: str) -> bool:
    """Russian prose: Cyrillic must dominate and must not be Kazakh.

    Kazakh is Cyrillic too, so a Kazakh explanation must not pass as Russian. A Chinese
    explanation must not pass either just because our own Russian MIP labels
    ("базовое:", "контраст:") are appended to it. Quoted source words («жүрек», «心»)
    are ignored; a few unquoted source words inside Russian prose stay under the limits."""
    unquoted = re.sub(r"«[^»]*»|\"[^\"]*\"|“[^”]*”", "", value)
    letters = [char for char in unquoted if char.isalpha()]
    cyrillic = [char for char in letters if "Ѐ" <= char <= "ӿ"]
    if not cyrillic or len(cyrillic) / len(letters) < 0.7:
        return False
    return sum(char in _KAZAKH_LETTERS for char in cyrillic) / len(cyrillic) < 0.04


def _align(text: str, fragment: str, start: int, end: int) -> tuple[int, int] | None:
    if 0 <= start < end <= len(text) and text[start:end] == fragment:
        return start, end
    # Some LLM responses return UTF-8 byte offsets despite being asked for Python
    # character offsets. Repair only when the exact fragment occurs once.
    if not fragment:
        return None
    position = text.find(fragment)
    if position < 0 or text.find(fragment, position + 1) >= 0:
        return None
    return position, position + len(fragment)


def locate_tenor(text: str, tenor: str, start: int, end: int) -> tuple[int, int] | None:
    """Offsets of the tenor occurrence nearest to the image span, or None if implicit."""
    if not tenor:
        return None
    best, position = None, text.find(tenor)
    while position >= 0:
        distance = (
            0
            if position < end and position + len(tenor) > start
            else min(abs(position - end), abs(start - (position + len(tenor))))
        )
        if best is None or distance < best[0]:
            best = (distance, position)
        position = text.find(tenor, position + 1)
    return None if best is None else (best[1], best[1] + len(tenor))


def parse_output(
    raw: str, text: str, language: str, model_version: str, *, cot: bool = False
) -> AnalysisResult:
    output = output_model(cot).model_validate_json(raw)
    warnings = ["LLM preliminary annotation; confidence is self-reported and uncalibrated."]
    metaphors, candidates, omitted = [], [], 0
    for item in output.metaphors:
        bounds = _align(text, item.text, item.start, item.end)
        if bounds is None:
            # Never fabricate or guess a location: keep the rest of the analysis.
            omitted += 1
            continue
        start, end = bounds
        rationale = item.rationale
        if cot:
            steps = "; ".join(
                f"{name}: {getattr(item, key)}"
                for name, key in zip(("базовое", "контекстное", "контраст"), _MIP_KEYS, strict=True)
            )
            rationale = f"{rationale} (MIP — {steps})"
        entity = item.entity if item.entity and item.entity in item.text else None
        confidence = min(1.0, max(0.0, item.confidence))
        tenor = item.tenor.strip() or None
        tenor_bounds = locate_tenor(text, tenor, start, end) if tenor else None
        metaphors.append(
            MetaphorSpan(
                text=item.text,
                start=start,
                end=end,
                label=item.label,
                source_domain=item.source_domain,
                target_domain=item.target_domain,
                confidence=confidence,
                rationale=rationale,
                entity=entity,
                entity_type=item.entity_type,
                usage_type="metaphorical",
                context_sentence=context_sentence(text, start, end),
                semantic_label=item.semantic_label.strip() or None,
                sentiment=item.sentiment,
                tenor=tenor,
                tenor_start=tenor_bounds[0] if tenor_bounds else None,
                tenor_end=tenor_bounds[1] if tenor_bounds else None,
                ground=item.ground.strip() or None,
            )
        )
        if entity:
            offset = start + item.text.find(entity)
            candidates.append(
                EntityCandidate(
                    text=entity,
                    start=offset,
                    end=offset + len(entity),
                    entity_type=item.entity_type,
                    usage_type="metaphorical",
                    origin="model",
                    reasoning=item.semantic_label,
                )
            )
    taken = {(c.start, c.end) for c in candidates}
    covered = [(m.start, m.end) for m in metaphors]
    conflicts = 0
    for item in output.literal_candidates:
        bounds = _align(text, item.text, item.start, item.end)
        if bounds is None:
            omitted += 1
            continue
        if bounds in taken or any(bounds[0] < e and bounds[1] > s for s, e in covered):
            conflicts += 1
            continue
        taken.add(bounds)
        candidates.append(
            EntityCandidate(
                text=item.text,
                start=bounds[0],
                end=bounds[1],
                entity_type=item.entity_type,
                usage_type="literal",
                origin="model",
                reasoning=item.reasoning,
            )
        )
    if omitted:
        warnings.append(
            f"{omitted} item(s) omitted: the expression could not be aligned uniquely to the source text."
        )
    if conflicts:
        warnings.append(
            f"{conflicts} literal candidate(s) overlapped figurative spans and were dropped."
        )
    result = AnalysisResult(
        language=output.language,
        model_version=model_version,
        metaphors=sorted(metaphors, key=lambda s: s.start),
        needs_review=True,
        warnings=warnings,
        candidates=sorted(candidates, key=lambda c: (c.start, c.end)),
    )
    return validate_result(text, language, result)


def prompt_data(text: str, language: str) -> str:
    """Zero-shot request body; kept for callers that build prompts themselves."""
    return build_prompt(text, language, PromptStrategy.parse("zero_shot")).user


_TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
    "required": ["translations"],
    "additionalProperties": False,
}


class LLMDetector:
    """Shared analysis flow; subclasses implement one provider call."""

    provider = "llm"

    def __init__(
        self,
        model: str,
        *,
        strategy: str = DEFAULT_STRATEGY,
        temperature: float | None = 0.2,
        top_p: float | None = 0.95,
        extractor: CandidateExtractor | None = None,
        knowledge=None,
        rag_k: int = 4,
    ):
        if not model:
            raise ValueError("Set a model name")
        self.model = model
        self.strategy = PromptStrategy.parse(strategy)
        self.temperature, self.top_p = temperature, top_p
        self.extractor = extractor or CandidateExtractor()
        self.knowledge, self.rag_k = knowledge, rag_k
        # Per-thread token counter: background jobs may share one detector instance.
        self._local = threading.local()

    def _record_usage(self, input_tokens, output_tokens) -> None:
        usage = getattr(self._local, "usage", None)
        if usage is None:
            return
        usage["requests"] += 1
        usage["input_tokens"] += int(input_tokens or 0)
        usage["output_tokens"] += int(output_tokens or 0)

    # Provider hook: return the raw JSON text and whether sampling parameters were applied.
    def _complete(
        self, instructions: str, user: str, schema: dict, sampling: dict
    ) -> tuple[str, bool]:
        raise NotImplementedError

    @property
    def model_version(self) -> str:
        return f"{self.provider}:{self.model}"

    def analyze(self, text: str, language: str = "auto") -> AnalysisResult:
        try:
            known = resolve_language(text, language)
        except NLPInputError:
            if language != "auto":
                raise
            known = None  # let the model detect the language; skip language-specific resources
        lexicon_candidates = self.extractor.extract(text, known) if known else []
        prompt = build_prompt(
            text,
            known or language,
            self.strategy,
            candidates=lexicon_candidates if known else None,
            knowledge=self.knowledge,
            rag_k=self.rag_k,
        )
        cot = "cot" in self.strategy
        sampling = {"temperature": self.temperature, "top_p": self.top_p}
        self._local.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
        raw, applied = self._complete(
            prompt.instructions, prompt.user, output_schema(cot), sampling
        )
        result = parse_output(raw, text, language, self.model_version, cot=cot)
        result = self._ensure_russian(result)
        method = {
            **prompt.record,
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature if applied else None,
            "top_p": self.top_p if applied else None,
            "sampling_applied": applied,
            # Includes the optional Russian translation pass; reported by the provider.
            "usage": dict(self._local.usage),
        }
        warnings = list(result.warnings)
        if not applied and (self.temperature is not None or self.top_p is not None):
            warnings.append("Provider rejected temperature/top_p; its default decoding was used.")
        if known:
            method["lexicon"] = self.extractor.version(result.language)
        candidates = merge_candidates(
            result.candidates, lexicon_candidates if "lexicon" in self.strategy else []
        )
        result = result.model_copy(
            update={"candidates": candidates, "method": method, "warnings": warnings}
        )
        return validate_result(text, language, result)

    def _ensure_russian(self, result: AnalysisResult) -> AnalysisResult:
        """Translate Russian-only fields in a narrowly scoped pass when the model ignored the rule.

        Covers the figures' explanations and the candidates' readings and reasoning: the
        interface is Russian-only, while the poem-language fields (tenor, ground) stay."""
        items = {
            "metaphors": (list(result.metaphors), ("rationale", "semantic_label")),
            "candidates": (list(result.candidates), ("lexicon_meaning", "reasoning")),
        }
        fields = [
            (group, index, name)
            for group, (objects, names) in items.items()
            for index, obj in enumerate(objects)
            for name in names
            if getattr(obj, name) and not _russian(getattr(obj, name))
        ]
        # Models tend to "translate" Kazakh by returning Kazakh: one more pass for leftovers.
        for attempt in range(2):
            if not fields:
                break
            translations = self._translate(
                [
                    {
                        "expression": items[group][0][i].text,
                        "value": getattr(items[group][0][i], name),
                    }
                    for group, i, name in fields
                ],
                # Deterministic first; a retry at temperature 0 would repeat the same answer.
                temperature=0.0 if attempt == 0 else None,
            )
            leftover = []
            for (group, index, name), value in zip(fields, translations, strict=True):
                objects = items[group][0]
                if value.strip() and _russian(value):
                    objects[index] = objects[index].model_copy(update={name: value})
                else:
                    leftover.append((group, index, name))
                    logger.warning("Rejected Russian translation of %s: %r", name, value[:160])
            fields = leftover
        # A failed translation of one explanation must not discard the whole analysis:
        # keep the original text and flag it for the reviewer instead.
        untranslated = len(fields)
        warnings = list(result.warnings)
        if untranslated:
            warnings.append(f"{untranslated} explanation(s) could not be translated into Russian.")
        return result.model_copy(
            update={
                "metaphors": items["metaphors"][0],
                "candidates": items["candidates"][0],
                "warnings": warnings,
            }
        )

    def _translate(self, items: list[dict], temperature: float | None) -> list[str]:
        raw, _ = self._complete(
            "Translate each value from Chinese or Kazakh into clear, concise Russian. "
            "The answer must be Russian: Kazakh is not Russian, so never return text with the "
            "letters ә, ғ, қ, ң, ө, ұ, ү, һ, і and never return the value unchanged or "
            "wrapped in quotes. Single source words such as 舟 or жүрек may stay inside the "
            "Russian sentence. Preserve meaning and do not add claims. Return exactly one "
            "translated string per input item, in the same order.",
            json.dumps({"items": items}, ensure_ascii=False),
            _TRANSLATION_SCHEMA,
            {"temperature": temperature, "top_p": None},
        )
        translations = json.loads(raw)["translations"]
        if len(translations) != len(items):
            # Cannot tell which translation belongs to which item: keep the originals, so
            # they are retried and, failing that, flagged instead of failing the analysis.
            logger.warning("Translation returned %d items for %d", len(translations), len(items))
            return [item["value"] for item in items]
        return translations


class OpenAIDetector(LLMDetector):
    provider = "openai"
    # A typical answer is under 1k tokens. Without a cap, a rare degenerate repetition
    # runs to the model maximum and the analysis hangs for minutes before failing.
    max_output_tokens = 6000

    def __init__(self, model: str, api_key: str, client=None, **kwargs):
        super().__init__(model, **kwargs)
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, timeout=120.0, max_retries=2)
        self.client = client

    def _complete(self, instructions, user, schema, sampling):
        request = dict(
            model=self.model,
            instructions=instructions,
            input=user,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "metaphor_analysis",
                    "strict": True,
                    "schema": schema,
                }
            },
            max_output_tokens=self.max_output_tokens,
        )
        params = {k: v for k, v in sampling.items() if v is not None}
        applied = bool(params)
        try:
            response = self.client.responses.create(**request, **params)
        except Exception as exc:
            # Reasoning models reject sampling parameters; retry once with provider defaults.
            message = str(exc).lower()
            if not params or not any(key in message for key in params):
                raise
            params = {}
            response = self.client.responses.create(**request)
            applied = False
        if response.status == "incomplete":
            # Usually a one-off repetition loop that hit the cap: sample once more.
            response = self.client.responses.create(**request, **params)
        if response.status != "completed":
            raise ValueError("LLM response is incomplete")
        usage = getattr(response, "usage", None)
        self._record_usage(getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0))
        return response.output_text, applied


class OllamaDetector(LLMDetector):
    """Local open models (Qwen-2.5, LLaMA-3.1, fine-tuned GGUF exports) through Ollama."""

    provider = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout: int = 180,
        context_window: int = 16384,
        **kwargs,
    ):
        if not model:
            raise ValueError("Set an installed Ollama model name")
        super().__init__(model, **kwargs)
        self.base_url, self.timeout = base_url.rstrip("/"), timeout
        if context_window < 4096:
            raise ValueError("Ollama context window must be at least 4096")
        self.context_window = context_window

    def _complete(self, instructions, user, schema, sampling):
        # Conservative token estimate from UTF-8 bytes (half a token per byte: 1.5 per Han
        # character, 1 per Cyrillic letter, 0.5 per ASCII character — above real BPE rates).
        # Reserve space for output and chat-template overhead, preventing default
        # server-side prompt truncation.
        budget = len((instructions + user + json.dumps(schema)).encode("utf-8")) // 2
        if budget + 2048 + 512 > self.context_window:
            raise ValueError(
                "Poem exceeds conservative Ollama context budget; "
                "increase OLLAMA_CONTEXT_WINDOW or submit shorter context"
            )
        options = {"num_ctx": self.context_window, "num_predict": 2048}
        options.update({k: v for k, v in sampling.items() if v is not None})
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": options,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user},
            ],
        }
        request = Request(
            self.base_url + "/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)
        if not payload.get("done") or payload.get("done_reason") == "length":
            raise ValueError("Ollama response is incomplete")
        self._record_usage(payload.get("prompt_eval_count"), payload.get("eval_count"))
        return payload["message"]["content"], any(v is not None for v in sampling.values())
