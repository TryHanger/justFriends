"""Anthropic Claude adapter (ТЗ п. 4, модуль A: Claude as one of the compared LLMs)."""

from app.nlp.llm import LLMDetector


class ClaudeDetector(LLMDetector):
    provider = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        client=None,
        effort: str | None = None,
        **kwargs,
    ):
        super().__init__(model, **kwargs)
        if client is None:
            import anthropic

            # Without an explicit key the SDK resolves ANTHROPIC_API_KEY or an `ant auth` profile.
            client = anthropic.Anthropic(**({"api_key": api_key} if api_key else {}), max_retries=2)
        self.client = client
        self.effort = effort

    def _complete(self, instructions, user, schema, sampling):
        request = dict(
            model=self.model,
            max_tokens=16000,
            system=instructions,
            messages=[{"role": "user", "content": user}],
            output_config={
                "format": {"type": "json_schema", "schema": schema},
                **({"effort": self.effort} if self.effort else {}),
            },
        )
        params = {k: v for k, v in sampling.items() if v is not None}
        applied = bool(params)
        try:
            response = self.client.messages.create(**request, **params)
        except Exception as exc:
            # Current Claude models reject temperature/top_p with HTTP 400; the comparison then
            # records provider-default decoding instead of silently claiming T=0.2/top-p=0.95.
            status = getattr(exc, "status_code", None)
            if not params or status != 400:
                raise
            response = self.client.messages.create(**request)
            applied = False
        if response.stop_reason == "refusal":
            raise ValueError("Claude declined the request")
        if response.stop_reason == "max_tokens":
            raise ValueError("Claude response is incomplete")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise ValueError("Claude returned no JSON text")
        return text, applied
