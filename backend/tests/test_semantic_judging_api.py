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
