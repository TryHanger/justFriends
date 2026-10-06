"""Local Transformers generation for open and fine-tuned models (Qwen-2.5, LLaMA-3.1, SozKZ).

Used to evaluate instruction-tuned checkpoints (hypothesis H1) on the same contract as the
API models. Unlike OpenAI/Claude/Ollama there is no constrained decoding here: an invalid
JSON answer fails the analysis instead of being repaired.
"""

import json
from pathlib import Path

from app.nlp.llm import LLMDetector


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
        **kwargs,
    ):
        super().__init__(model, **kwargs)
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(adapter or model)
        self.lm = AutoModelForCausalLM.from_pretrained(model, torch_dtype="auto")
        if adapter:
            from peft import PeftModel

            self.lm = PeftModel.from_pretrained(self.lm, adapter)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.lm.to(self.device).eval()
        self.adapter, self.max_new_tokens = adapter, max_new_tokens

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
                    "content": instructions + "\nJSON schema:\n" + json.dumps(schema),
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
        if len(generated) >= self.max_new_tokens:
            raise ValueError("Generation hit max_new_tokens; the JSON answer is incomplete")
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        return extract_json(text), do_sample
