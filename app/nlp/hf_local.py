"""Local Transformers generation for open and fine-tuned models (Qwen-2.5, LLaMA-3.1, SozKZ).

Used to evaluate instruction-tuned checkpoints (hypothesis H1) on the same contract as the
API models. Unlike OpenAI/Claude/Ollama there is no constrained decoding here: an invalid
JSON answer fails the analysis. With `lenient`, values outside a schema enum are replaced
by its "other"/"unknown" member (or the array item is dropped) instead, so the content of
an answer can be inspected even when the model ignores the closed lists.
"""

import json
from pathlib import Path

from app.nlp.llm import LLMDetector

_DROP = object()
FORMAT_NOTE = (
    "\nAnswer with one JSON object that follows this JSON Schema. Fill in the values; "
    "never repeat the schema itself.\nJSON Schema:\n"
)


def coerce_enums(value, schema: dict, defs: dict | None = None) -> tuple[object, int]:
    """Value with out-of-enum strings replaced; returns it and the number of repairs."""
    defs = schema.get("$defs", {}) if defs is None else defs
    if "$ref" in schema:
        schema = defs[schema["$ref"].rsplit("/", 1)[-1]]
    if "anyOf" in schema:
        if value is None:
            return value, 0
        schema = next(s for s in schema["anyOf"] if s.get("type") != "null")
    if "enum" in schema and isinstance(value, str) and value not in schema["enum"]:
        fallback = next((v for v in ("other", "unknown") if v in schema["enum"]), _DROP)
        return fallback, 1
    if isinstance(value, dict) and "properties" in schema:
        repairs, out = 0, {}
        for key, item in value.items():
            if key not in schema["properties"]:
                out[key] = item
                continue
            fixed, count = coerce_enums(item, schema["properties"][key], defs)
            if fixed is _DROP:
                return _DROP, repairs + count
            out[key], repairs = fixed, repairs + count
        return out, repairs
    if isinstance(value, list) and "items" in schema:
        repairs, out = 0, []
        for item in value:
            fixed, count = coerce_enums(item, schema["items"], defs)
            repairs += count
            if fixed is not _DROP:
                out.append(fixed)
        return out, repairs
    return value, 0


def render_chat(tokenizer, messages: list[dict], add_generation_prompt: bool) -> str:
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=add_generation_prompt
        )
    # Base checkpoints (e.g. small SozKZ models) may lack a chat template.
    text = "".join(f"<|{m['role']}|>\n{m['content']}\n" for m in messages)
    return text + ("<|assistant|>\n" if add_generation_prompt else "")


def extract_json(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("Model output contains no JSON object")
    try:
        _, end = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise ValueError("Model output JSON is invalid or incomplete") from exc
    return text[start:end]


class TransformersDetector(LLMDetector):
    provider = "hf"

    def __init__(
        self,
        model: str,
        adapter: str | None = None,
        max_new_tokens: int = 2048,
        device: str | None = None,
        load_4bit: bool = False,
        lenient: bool = False,
        **kwargs,
    ):
        super().__init__(model, **kwargs)
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(adapter or model)
        if load_4bit and self.device == "cuda":
            # 7-8B models (KazLLM, Qwen-7B) fit an 8 GB GPU only with a 4-bit base.
            from transformers import BitsAndBytesConfig

            from app.nlp.amp import amp_dtype

            quantization = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=amp_dtype(torch.device("cuda")),
            )
            self.lm = AutoModelForCausalLM.from_pretrained(
                model, quantization_config=quantization, device_map={"": 0}
            )
        else:
            self.lm = AutoModelForCausalLM.from_pretrained(model, torch_dtype="auto")
            self.lm.to(self.device)
        if adapter:
            from peft import PeftModel

            self.lm = PeftModel.from_pretrained(self.lm, adapter)
        self.lm.eval()
        self.adapter, self.max_new_tokens = adapter, max_new_tokens
        self.lenient = lenient
        # Raw text and enum repairs of every answer, for inspecting what the model said.
        self.outputs: list[dict] = []

    @property
    def model_version(self) -> str:
        suffix = f"+{Path(self.adapter).name}" if self.adapter else ""
        return f"hf:{self.model}{suffix}"

    def _complete(self, instructions, user, schema, sampling):
        import torch

        prompt = render_chat(
            self.tokenizer,
            [
                {
                    "role": "system",
                    "content": instructions
                    + (FORMAT_NOTE if self.lenient else "\nJSON schema:\n")
                    + json.dumps(schema),
                },
                {"role": "user", "content": user},
            ],
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        temperature, top_p = sampling.get("temperature"), sampling.get("top_p")
        do_sample = bool(temperature)
        kwargs = {"do_sample": do_sample, "max_new_tokens": self.max_new_tokens}
        if do_sample:
            kwargs.update(temperature=temperature, top_p=top_p or 1.0)
        with torch.inference_mode():
            output = self.lm.generate(**inputs, **kwargs)
        generated = output[0, inputs["input_ids"].shape[1] :]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        self.outputs.append({"text": text, "repairs": 0})
        if len(generated) >= self.max_new_tokens:
            raise ValueError("Generation hit max_new_tokens; the JSON answer is incomplete")
        self._record_usage(inputs["input_ids"].shape[1], len(generated))
        try:
            answer = extract_json(text)
        except ValueError as exc:
            raise ValueError(f"{exc}. Model output starts with: {text[:400]!r}") from exc
        if self.lenient:
            fixed, self.outputs[-1]["repairs"] = coerce_enums(json.loads(answer), schema)
            if fixed is not _DROP:
                answer = json.dumps(fixed, ensure_ascii=False)
        return answer, do_sample
