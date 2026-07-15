from __future__ import annotations

import pytest

from llm_eval_lab.model_provider import (
    ModelProviderFailure,
    ModelProviderRegistry,
    ModelRequest,
    ModelResponse,
)
from llm_eval_lab.semantic_judging import (
    ProviderBackedSemanticJudge,
    SemanticJudgeConfig,
    SemanticJudgeFailure,
    SemanticJudgeRequest,
    human_review_reasons,
)


class StaticJudgeAdapter:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(content=self.content)


class FailedJudgeAdapter:
    def generate(self, request: ModelRequest) -> ModelResponse:
        raise ModelProviderFailure(
            "provider_unavailable",
            "The configured local semantic judge is unavailable.",
        )


def judge_request() -> SemanticJudgeRequest:
    return SemanticJudgeRequest(
        user_input="What is the return window?",
        grounding_material=[
            {
                "kind": "return",
                "title": "Return policy",
                "content": "Unopened products may be returned within 30 days.",
            }
        ],
        must_have_facts=["The return window is 30 days."],
        forbidden_claims=["Opened earbuds can always be returned."],
        response="Unopened products may be returned within 30 days.",
    )


def judge_config() -> SemanticJudgeConfig:
    return SemanticJudgeConfig(
        provider="ollama",
        model="local-judge-model",
        low_confidence_threshold=0.7,
    )


def test_high_confidence_agreement_does_not_require_human_review():
    adapter = StaticJudgeAdapter(
        '{"outcome":"pass","rationale":"The answer is grounded.","confidence":0.94}'
    )
    judge = ProviderBackedSemanticJudge(
        ModelProviderRegistry({"ollama": adapter}),
        judge_config(),
    )

    result = judge.judge(judge_request())

    assert result.outcome == "pass"
    assert result.rationale == "The answer is grounded."
    assert result.confidence == 0.94
    assert human_review_reasons(
        deterministic_passed=True,
        semantic_result=result,
        semantic_failure=None,
        requires_human_review=False,
        low_confidence_threshold=0.7,
    ) == ()
    assert adapter.requests[0].model == "local-judge-model"
    assert adapter.requests[0].generation_parameters == {"temperature": 0}


def test_conflicting_automatic_scores_route_to_human_review():
    adapter = StaticJudgeAdapter(
        '{"outcome":"fail","rationale":"A required condition is missing.","confidence":0.91}'
    )
    judge = ProviderBackedSemanticJudge(
        ModelProviderRegistry({"ollama": adapter}),
        judge_config(),
    )

    result = judge.judge(judge_request())

    assert human_review_reasons(
        deterministic_passed=True,
        semantic_result=result,
        semantic_failure=None,
        requires_human_review=False,
        low_confidence_threshold=0.7,
    ) == ("automatic_conflict",)


def test_low_confidence_result_routes_to_human_review():
    adapter = StaticJudgeAdapter(
        '{"outcome":"pass","rationale":"The answer is probably grounded.","confidence":0.69}'
    )
    judge = ProviderBackedSemanticJudge(
        ModelProviderRegistry({"ollama": adapter}),
        judge_config(),
    )

    result = judge.judge(judge_request())

    assert human_review_reasons(
        deterministic_passed=True,
        semantic_result=result,
        semantic_failure=None,
        requires_human_review=False,
        low_confidence_threshold=0.7,
    ) == ("low_confidence",)


def test_insufficient_evidence_routes_to_human_review():
    adapter = StaticJudgeAdapter(
        '{"outcome":"insufficient_evidence","rationale":"The policy is ambiguous.",'
        '"confidence":0.88}'
    )
    judge = ProviderBackedSemanticJudge(
        ModelProviderRegistry({"ollama": adapter}),
        judge_config(),
    )

    result = judge.judge(judge_request())

    assert human_review_reasons(
        deterministic_passed=True,
        semantic_result=result,
        semantic_failure=None,
        requires_human_review=False,
        low_confidence_threshold=0.7,
    ) == ("insufficient_evidence",)


def test_malformed_judge_output_is_an_inspectable_failure():
    adapter = StaticJudgeAdapter("The answer passes.")
    judge = ProviderBackedSemanticJudge(
        ModelProviderRegistry({"ollama": adapter}),
        judge_config(),
    )

    with pytest.raises(SemanticJudgeFailure) as raised:
        judge.judge(judge_request())

    assert raised.value.code == "malformed_judge_output"
    assert "JSON" in raised.value.message


def test_provider_failure_is_an_inspectable_judge_failure():
    judge = ProviderBackedSemanticJudge(
        ModelProviderRegistry({"ollama": FailedJudgeAdapter()}),
        judge_config(),
    )

    with pytest.raises(SemanticJudgeFailure) as raised:
        judge.judge(judge_request())

    assert raised.value.code == "provider_unavailable"
    assert raised.value.message == "The configured local semantic judge is unavailable."


def test_explicit_review_requirement_is_preserved_even_when_scores_agree():
    adapter = StaticJudgeAdapter(
        '{"outcome":"pass","rationale":"The answer is grounded.","confidence":0.94}'
    )
    judge = ProviderBackedSemanticJudge(
        ModelProviderRegistry({"ollama": adapter}),
        judge_config(),
    )
    result = judge.judge(judge_request())

    assert human_review_reasons(
        deterministic_passed=True,
        semantic_result=result,
        semantic_failure=None,
        requires_human_review=True,
        low_confidence_threshold=0.7,
    ) == ("test_case_requires_review",)
