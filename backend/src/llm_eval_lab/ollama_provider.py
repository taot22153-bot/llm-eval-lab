from __future__ import annotations

from typing import Any

import httpx2

from llm_eval_lab.model_provider import (
    ModelProviderFailure,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)


class OllamaModelAdapter:
    def __init__(self, client: httpx2.Client) -> None:
        self._client = client

    def generate(self, request: ModelRequest) -> ModelResponse:
        try:
            response = self._client.post(
                "/api/generate",
                json={
                    "model": request.model,
                    "system": request.system_prompt,
                    "prompt": request.user_prompt,
                    "options": request.generation_parameters,
                    "stream": False,
                },
            )
        except httpx2.ConnectError as error:
            base_url = str(self._client.base_url).rstrip("/")
            raise ModelProviderFailure(
                "provider_unavailable",
                f"Cannot reach Ollama at {base_url}. Start Ollama and verify OLLAMA_BASE_URL.",
            ) from error
        except httpx2.TimeoutException as error:
            base_url = str(self._client.base_url).rstrip("/")
            raise ModelProviderFailure(
                "provider_timeout",
                f"Ollama at {base_url} did not respond before the configured timeout. Verify "
                "the service and model, or adjust OLLAMA_TIMEOUT_SECONDS.",
            ) from error
        if response.status_code == 404:
            raise ModelProviderFailure(
                "model_unavailable",
                f"Ollama model '{request.model}' is unavailable. Install it locally or select "
                "an installed model.",
            )
        if response.is_error:
            raise ModelProviderFailure(
                "provider_request_failed",
                f"Ollama rejected the request with HTTP {response.status_code}. Check the "
                "configured model and generation parameters.",
            )
        payload: dict[str, Any] = response.json()
        content = payload.get("response")
        if not isinstance(content, str):
            raise ModelProviderFailure(
                "invalid_provider_response",
                "Ollama returned a response without generated text.",
            )

        prompt_tokens = payload.get("prompt_eval_count")
        completion_tokens = payload.get("eval_count")
        total_tokens = None
        if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
            total_tokens = prompt_tokens + completion_tokens

        return ModelResponse(
            content=content,
            usage=ModelUsage(
                prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
                completion_tokens=(
                    completion_tokens if isinstance(completion_tokens, int) else None
                ),
                total_tokens=total_tokens,
            ),
        )
