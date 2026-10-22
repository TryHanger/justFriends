from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Metaphor Analyzer API"
    environment: str = "local"
    quality_runner_enabled: bool = False
    quality_frontend_worker_enabled: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./metaphors.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    max_upload_mb: int = 20
    nlp_backend: Literal["openai", "anthropic", "ollama", "hf", "baseline", "xlmr", "hybrid"] = (
        "openai"
    )
    # Prompt strategy (ТЗ п. 2.2.2): '+'-joined few_shot, cot, rag, lexicon; or zero_shot.
    llm_prompt_strategy: str = "few_shot+cot+rag+lexicon"
    # Decoding parameters from ТЗ п. 4.1; empty value in .env means provider default.
    llm_temperature: float | None = Field(default=0.2, ge=0, le=2)
    llm_top_p: float | None = Field(default=0.95, gt=0, le=1)
    rag_top_k: int = Field(default=4, ge=0, le=20)
    lexicon_dir: str | None = None
    knowledge_dir: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    hf_model: str = ""
    hf_adapter: str | None = None
    ollama_model: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_context_window: int = Field(default=16384, ge=4096)
    xlmr_model_path: str = "models/xlmr"
    experimental_kk_xlmr_model_path: str = "models/xlmr-zh-kk-expert-v2"
    chinese_gold_xlmr_model_path: str = "models/cmdag-xlmr-mps-full-v2"
    attribute_model_path: str | None = None
    # Shijing stanza classifier 賦/比/興 (Zhu Xi labels); skipped when absent. Empty disables.
    stanza_model_path: str | None = "models/zhuxi-stanza-sikuroberta-v1"
    hybrid_llm_backend: Literal["openai", "anthropic", "ollama", "hf"] = "openai"
    # Two-stage analysis (docs/NLP.md): for these languages (comma-separated, empty = off)
    # every candidate of an LLM backend is judged again by a direct usage question.
    nlp_two_stage_languages: str = "kk"
    nlp_usage_backend: Literal["openai", "anthropic", "ollama"] = "openai"
    nlp_usage_model: str = "gpt-4o"
    # Stage 2 also questions every Kazakh content word no stage-1 candidate covers.
    nlp_usage_all_words: bool = True
    # Classical Chinese poetry mode (app/nlp/allegory.py): images read in the commentary
    # tradition for zh texts that look like classical verse. False disables it.
    nlp_classical_zh: bool = True
    nlp_allegory_model: str = "gpt-4o-mini"
    nlp_review_threshold: float = Field(default=0.8, ge=0, le=1)
    nlp_max_length: int = Field(default=256, ge=4, le=512)
    nlp_stride: int = Field(default=64, ge=0)
    embedding_model: str = "intfloat/multilingual-e5-base"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
