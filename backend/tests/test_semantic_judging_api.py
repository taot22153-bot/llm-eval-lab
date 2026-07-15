# ruff: noqa: E402

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select

load_dotenv(Path(__file__).parents[2] / ".env")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from llm_eval_lab.database import Base, SessionLocal, engine
from llm_eval_lab.main import app
from llm_eval_lab.model_provider import (
    ModelProviderRegistry,
    ModelRequest,
    ModelResponse,
    get_model_provider_registry,
)
from llm_eval_lab.models import ApplicationVersion
from llm_eval_lab.models import TestCase as EvaluationTestCase
from llm_eval_lab.sample_suite import seed_sample_evaluation_suite
from llm_eval_lab.semantic_judging import (
    SemanticJudgeFailure,
    SemanticJudgeRequest,
    SemanticJudgeResult,
    get_semantic_judge,
)


class GroundedResponseAdapter:
    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content="The price is $79. The available colors are black and silver."
        )


class ConflictingSemanticJudge:
    low_confidence_threshold = 0.7

    def configuration_snapshot(self):
        return {
            "judge_version": "structured-semantic-v1",
            "provider": "fixture-judge",
            "model": "independent-judge-v1",
            "generation_parameters": {"temperature": 0},
            "low_confidence_threshold": 0.7,
        }

    def judge(self, request: SemanticJudgeRequest) -> SemanticJudgeResult:
        assert request.response == (
            "The price is $79. The available colors are black and silver."
        )
        return SemanticJudgeResult(
            outcome="fail",
            rationale="The response does not explain that the product includes a charging case.",
            confidence=0.91,
        )


class FailedSemanticJudge:
    low_confidence_threshold = 0.7

    def configuration_snapshot(self):
        return {
            "judge_version": "structured-semantic-v1",
            "provider": "ollama",
            "model": "missing-local-judge",
            "generation_parameters": {"temperature": 0},
            "low_confidence_threshold": 0.7,
        }

    def judge(self, request: SemanticJudgeRequest) -> SemanticJudgeResult:
        raise SemanticJudgeFailure(
            "provider_unavailable",
            "Cannot reach the configured local semantic judge.",
        )


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_execution_inputs() -> tuple[str, str]:
    with SessionLocal() as session:
        suite = seed_sample_evaluation_suite(session)
        test_case = session.scalar(
            select(EvaluationTestCase).where(
                EvaluationTestCase.suite_id == suite.id,
                EvaluationTestCase.key == "product-echo-bud-facts",
            )
        )
        application_version = ApplicationVersion(
            name="Evaluated application configuration",
            model_provider="ollama",
            model_name="course-demo-model",
            system_prompt="Answer only from supplied evidence.",
            generation_parameters={"temperature": 0},
            knowledge_config=None,
            tool_config=None,
        )
        session.add(application_version)
        session.commit()
        assert test_case is not None
        return application_version.id, test_case.id


def execute_and_reopen(semantic_judge) -> dict:
    application_version_id, test_case_id = seed_execution_inputs()
    registry = ModelProviderRegistry({"ollama": GroundedResponseAdapter()})
    app.dependency_overrides[get_model_provider_registry] = lambda: registry
    app.dependency_overrides[get_semantic_judge] = lambda: semantic_judge

    with TestClient(app) as client:
        created = client.post(
            "/api/test-case-executions",
            json={
                "application_version_id": application_version_id,
                "test_case_id": test_case_id,
            },
        )
        reopened = client.get(
            f"/api/test-case-executions/{created.json()['id']}"
        )

    assert created.status_code == 201
    assert reopened.status_code == 200
    return reopened.json()


def test_conflict_persists_semantic_evidence_without_overwriting_deterministic_evidence():
    execution = execute_and_reopen(ConflictingSemanticJudge())

    with TestClient(app) as client:
        queue_response = client.get("/api/human-review-items?status=pending")

    assert execution["status"] == "completed"
    assert execution["deterministic_evaluation"]["passed"] is True
    semantic = execution["semantic_evaluation"]
    assert semantic["judge_version"] == "structured-semantic-v1"
    assert semantic["outcome"] == "fail"
    assert semantic["rationale"] == (
        "The response does not explain that the product includes a charging case."
    )
    assert semantic["confidence"] == 0.91
    assert semantic["judge_configuration"] == {
        "judge_version": "structured-semantic-v1",
        "provider": "fixture-judge",
        "model": "independent-judge-v1",
        "generation_parameters": {"temperature": 0},
        "low_confidence_threshold": 0.7,
    }
    assert semantic["error"] is None
    assert semantic["created_at"].endswith("Z")
    assert execution["human_review_item"]["status"] == "pending"
    assert execution["human_review_item"]["reasons"] == ["automatic_conflict"]
    assert execution["human_review_item"]["created_at"].endswith("Z")
    assert queue_response.status_code == 200
    assert queue_response.json() == [
        {
            "id": execution["human_review_item"]["id"],
            "test_case_execution_id": execution["id"],
            "test_case_title": "Answer with supported product facts",
            "application_version_name": "Evaluated application configuration",
            "evaluation_run_id": None,
            "version_role": None,
            "status": "pending",
            "reasons": ["automatic_conflict"],
            "outcome": None,
            "rationale": None,
            "created_at": execution["human_review_item"]["created_at"],
            "resolved_at": None,
        }
    ]


def test_judge_failure_cannot_silently_become_a_passing_score():
    execution = execute_and_reopen(FailedSemanticJudge())

    assert execution["status"] == "completed"
    assert execution["deterministic_evaluation"]["passed"] is True
    semantic = execution["semantic_evaluation"]
    assert semantic["outcome"] is None
    assert semantic["rationale"] is None
    assert semantic["confidence"] is None
    assert semantic["error"] == {
        "code": "provider_unavailable",
        "message": "Cannot reach the configured local semantic judge.",
    }
    assert execution["human_review_item"]["reasons"] == ["judge_failure"]


def test_reviewer_can_inspect_resolve_and_reopen_a_human_review_without_overwriting_scores():
    execution = execute_and_reopen(ConflictingSemanticJudge())
    review_id = execution["human_review_item"]["id"]

    with TestClient(app) as client:
        detail_response = client.get(f"/api/human-review-items/{review_id}")
        invalid_response = client.patch(
            f"/api/human-review-items/{review_id}",
            json={"outcome": "pass", "rationale": ""},
        )
        resolved_response = client.patch(
            f"/api/human-review-items/{review_id}",
            json={
                "outcome": "pass",
                "rationale": "The answer is supported when judged by meaning, not exact phrasing.",
            },
        )
        duplicate_response = client.patch(
            f"/api/human-review-items/{review_id}",
            json={
                "outcome": "fail",
                "rationale": "A later request must not rewrite the completed review.",
            },
        )
        pending_response = client.get("/api/human-review-items?status=pending")
        resolved_history_response = client.get(
            "/api/human-review-items?status=resolved"
        )
        execution_response = client.get(
            f"/api/test-case-executions/{execution['id']}"
        )

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["reasons"] == ["automatic_conflict"]
    assert detail["outcome"] is None
    assert detail["rationale"] is None
    assert detail["execution"]["prompt_context"]["user_input"] == (
        "What colors does the EchoBud X1 come in, and what does it cost?"
    )
    assert detail["execution"]["prompt_context"]["grounding_material"]
    assert detail["execution"]["model_response"] == (
        "The price is $79. The available colors are black and silver."
    )
    assert detail["execution"]["deterministic_evaluation"]["passed"] is True
    assert detail["execution"]["semantic_evaluation"]["outcome"] == "fail"

    assert invalid_response.status_code == 422
    assert resolved_response.status_code == 200
    resolved = resolved_response.json()
    assert resolved["status"] == "resolved"
    assert resolved["outcome"] == "pass"
    assert resolved["rationale"] == (
        "The answer is supported when judged by meaning, not exact phrasing."
    )
    assert resolved["resolved_at"].endswith("Z")
    assert duplicate_response.status_code == 409
    assert pending_response.json() == []
    assert resolved_history_response.status_code == 200
    assert resolved_history_response.json()[0]["id"] == review_id
    assert resolved_history_response.json()[0]["outcome"] == "pass"

    persisted_execution = execution_response.json()
    assert persisted_execution["deterministic_evaluation"] == execution[
        "deterministic_evaluation"
    ]
    assert persisted_execution["semantic_evaluation"] == execution[
        "semantic_evaluation"
    ]
    assert persisted_execution["human_review_item"]["outcome"] == "pass"
    assert persisted_execution["human_review_item"]["rationale"] == resolved[
        "rationale"
    ]


def test_human_review_patch_is_allowed_from_the_local_web_console():
    with TestClient(app) as client:
        response = client.options(
            "/api/human-review-items/review-id",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]
