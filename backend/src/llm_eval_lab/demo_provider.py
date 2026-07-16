from __future__ import annotations

import json
from typing import Any

from llm_eval_lab.model_provider import (
    ModelProviderFailure,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from llm_eval_lab.sample_suite import SAMPLE_TEST_CASES

DEMO_PROVIDER_NAME = "demo-fixture"
DEMO_BASELINE_MODEL = "northstar-baseline-fixture-v1"
DEMO_CANDIDATE_MODEL = "northstar-candidate-fixture-v1"
DEMO_SEMANTIC_MODEL = "northstar-semantic-fixture-v1"
DEMO_REGRESSION_CASE_KEY = "prompt-injection-system-prompt"


def _case_for_prompt(user_prompt: str) -> dict[str, Any] | None:
    for test_case in SAMPLE_TEST_CASES:
        if f"User input:\n{test_case['user_input']}" in user_prompt:
            return test_case
    return None


class DeterministicDemoAdapter:
    """Explicitly labeled offline fixture for the interview demo, not an LLM."""

    def generate(self, request: ModelRequest) -> ModelResponse:
        if request.model == DEMO_SEMANTIC_MODEL:
            return self._semantic_response(request)
        if request.model not in {DEMO_BASELINE_MODEL, DEMO_CANDIDATE_MODEL}:
            raise ModelProviderFailure(
                "demo_model_unavailable",
                f"Demo fixture model '{request.model}' is not configured.",
            )

        test_case = _case_for_prompt(request.user_prompt)
        if test_case is None:
            raise ModelProviderFailure(
                "demo_case_unmatched",
                "The deterministic demo fixture received an unknown Test Case.",
            )
        response_parts = list(test_case["must_have_facts"])
        if (
            request.model == DEMO_CANDIDATE_MODEL
            and test_case["key"] == DEMO_REGRESSION_CASE_KEY
        ):
            response_parts.append(test_case["forbidden_claims"][0])
        content = " ".join(response_parts)
        return ModelResponse(
            content=content,
            usage=ModelUsage(
                prompt_tokens=len(request.user_prompt.split()),
                completion_tokens=len(content.split()),
                total_tokens=(
                    len(request.user_prompt.split()) + len(content.split())
                ),
                cost_usd=0.0,
            ),
        )

    def _semantic_response(self, request: ModelRequest) -> ModelResponse:
        try:
            payload = json.loads(request.user_prompt)
        except json.JSONDecodeError as error:
            raise ModelProviderFailure(
                "demo_judge_request_invalid",
                "The deterministic demo judge received invalid evidence JSON.",
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
            raise ModelProviderFailure(
                "demo_judge_request_invalid",
                "The deterministic demo judge requires a response evidence field.",
            )
        content = json.dumps(
            {
                "outcome": "pass",
                "rationale": (
                    "Deterministic demo judgment: the response is treated as semantically "
                    "supported so literal safety failures route to Human Review."
                ),
                "confidence": 0.95,
            }
        )
        return ModelResponse(content=content, usage=ModelUsage(cost_usd=0.0))
