from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Metaphor Analyzer API"
    environment: str = "local"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./metaphors.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    max_upload_mb: int = 20
    nlp_backend: Literal[
        "openai", "anthropic", "ollama", "hf", "baseline", "xlmr", "hybrid"
    ] = "openai"
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
    attribute_model_path: str | None = None
    hybrid_llm_backend: Literal["openai", "anthropic", "ollama", "hf"] = "openai"
    nlp_review_threshold: float = Field(default=0.8, ge=0, le=1)
    nlp_max_length: int = Field(default=256, ge=4, le=512)
    nlp_stride: int = Field(default=64, ge=0)
    embedding_model: str = "intfloat/multilingual-e5-base"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
