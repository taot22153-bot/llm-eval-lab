from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    cors_origins: str = "http://localhost:5173"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = Field(default=120, gt=0)
    openai_compatible_base_url: str | None = None
    openai_compatible_api_key: SecretStr | None = None
    openai_compatible_timeout_seconds: float = Field(default=120, gt=0)
    openai_compatible_input_cost_per_million_tokens: float | None = Field(
        default=None,
        ge=0,
    )
    openai_compatible_output_cost_per_million_tokens: float | None = Field(
        default=None,
        ge=0,
    )
    semantic_judge_provider: str = "ollama"
    semantic_judge_model: str = "replace-with-an-installed-local-model"
    semantic_judge_low_confidence_threshold: float = 0.7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
