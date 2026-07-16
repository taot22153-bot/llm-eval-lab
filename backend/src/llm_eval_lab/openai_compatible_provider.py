from __future__ import annotations

from typing import Any

import httpx2

from llm_eval_lab.model_provider import (
    ModelProviderFailure,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)


def _token_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


class OpenAICompatibleAdapter:
    def __init__(
        self,
        client: httpx2.Client,
        *,
        input_cost_per_million_tokens: float | None = None,
        output_cost_per_million_tokens: float | None = None,
    ) -> None:
        self._client = client
        self._input_cost = input_cost_per_million_tokens
        self._output_cost = output_cost_per_million_tokens

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload = {
            **request.generation_parameters,
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "stream": False,
        }
        try:
            response = self._client.post("chat/completions", json=payload)
        except httpx2.ConnectError as error:
            raise ModelProviderFailure(
                "provider_unavailable",
                "Cannot reach the configured OpenAI-compatible endpoint. Verify "
                "OPENAI_COMPATIBLE_BASE_URL and local network access.",
            ) from error
        except httpx2.TimeoutException as error:
            raise ModelProviderFailure(
                "provider_timeout",
                "The OpenAI-compatible endpoint did not respond before the configured timeout. "
                "Verify the service or adjust OPENAI_COMPATIBLE_TIMEOUT_SECONDS.",
            ) from error

        if response.status_code == 429:
            raise ModelProviderFailure(
                "provider_rate_limited",
                "The OpenAI-compatible endpoint rate-limited the request. Retry later or verify "
                "the limits for OPENAI_COMPATIBLE_BASE_URL.",
            )
        if response.status_code in {401, 403}:
            raise ModelProviderFailure(
                "provider_authentication_failed",
                "The OpenAI-compatible endpoint rejected authentication. Verify the "
                "environment-only OPENAI_COMPATIBLE_API_KEY setting.",
            )
        if response.status_code == 404:
            raise ModelProviderFailure(
                "model_unavailable",
                f"OpenAI-compatible model '{request.model}' or the configured endpoint was not "
                "found. Verify the model name and OPENAI_COMPATIBLE_BASE_URL.",
            )
        if response.is_error:
            raise ModelProviderFailure(
                "provider_request_failed",
                f"The OpenAI-compatible endpoint rejected the request with HTTP "
                f"{response.status_code}. Verify the model and generation parameters.",
            )

        try:
            body: Any = response.json()
        except ValueError as error:
            raise ModelProviderFailure(
                "invalid_provider_response",
                "The OpenAI-compatible endpoint returned invalid JSON.",
            ) from error
        if not isinstance(body, dict):
            raise ModelProviderFailure(
                "invalid_provider_response",
                "The OpenAI-compatible endpoint returned an invalid response object.",
            )
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelProviderFailure(
                "invalid_provider_response",
                "The OpenAI-compatible endpoint returned no generated choice.",
            )
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ModelProviderFailure(
                "invalid_provider_response",
                "The OpenAI-compatible endpoint returned a choice without generated text.",
            )

        usage = body.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        prompt_tokens = _token_count(usage.get("prompt_tokens"))
        completion_tokens = _token_count(usage.get("completion_tokens"))
        total_tokens = _token_count(usage.get("total_tokens"))
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        cost_usd = None
        if (
            prompt_tokens is not None
            and completion_tokens is not None
            and self._input_cost is not None
            and self._output_cost is not None
        ):
            cost_usd = (
                prompt_tokens * self._input_cost
                + completion_tokens * self._output_cost
            ) / 1_000_000

        return ModelResponse(
            content=content,
            usage=ModelUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
            ),
        )
