from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Metaphor Analyzer API"
    environment: str = "local"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./metaphors.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    max_upload_mb: int = 20
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
