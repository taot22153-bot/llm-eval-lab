from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelRequest:
    model: str
    system_prompt: str
    user_prompt: str
    generation_parameters: dict[str, Any]


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class ModelResponse:
    content: str
    usage: ModelUsage = ModelUsage()


class ModelProviderFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ModelProvider(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse: ...


class ModelProviderRegistry:
    def __init__(self, providers: dict[str, ModelProvider]) -> None:
        self._providers = providers

    def get(self, provider_name: str) -> ModelProvider:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ModelProviderFailure(
                "unsupported_provider",
                f"Model provider '{provider_name}' is not configured.",
            )
        return provider


@lru_cache
def get_model_provider_registry() -> ModelProviderRegistry:
    import httpx2

    from llm_eval_lab.config import get_settings
    from llm_eval_lab.ollama_provider import OllamaModelAdapter

    settings = get_settings()
    ollama_client = httpx2.Client(
        base_url=settings.ollama_base_url.rstrip("/"),
        timeout=settings.ollama_timeout_seconds,
        trust_env=False,
    )
    return ModelProviderRegistry({"ollama": OllamaModelAdapter(ollama_client)})
