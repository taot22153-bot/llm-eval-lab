# ruff: noqa: E402

import os
from datetime import UTC, datetime
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
    ModelProviderFailure,
    ModelProviderRegistry,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    get_model_provider_registry,
)
from llm_eval_lab.models import ApplicationVersion
from llm_eval_lab.models import TestCase as EvaluationTestCase
from llm_eval_lab.models import TestCaseExecution as EvaluationTestCaseExecution
from llm_eval_lab.sample_suite import seed_sample_evaluation_suite


class DeterministicModelAdapter:
    def generate(self, request: ModelRequest) -> ModelResponse:
        assert request.model == "course-demo-model"
        assert request.system_prompt == "Answer only from the supplied store policies."
        assert request.user_prompt == (
            "Grounding material:\n"
            "- EchoBud X1 product card: The fictional Northstar EchoBud X1 costs $79, "
            "is available in black or silver, and includes a USB-C charging case.\n\n"
            "User input:\n"
            "What colors does the EchoBud X1 come in, and what does it cost?"
        )
        assert request.generation_parameters == {"temperature": 0}
        return ModelResponse(
            content="The EchoBud X1 costs $79 and comes in black or silver.",
            usage=ModelUsage(prompt_tokens=51, completion_tokens=14, total_tokens=65),
        )


class UnavailableModelAdapter:
    def generate(self, request: ModelRequest) -> ModelResponse:
        raise ModelProviderFailure(
            "provider_unavailable",
            "Cannot reach the configured local model provider. Start it and retry.",
        )


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_evaluation_user_can_execute_one_test_case_and_reopen_the_result():
    with SessionLocal() as session:
        suite = seed_sample_evaluation_suite(session)
        test_case = session.scalar(
            select(EvaluationTestCase).where(
                EvaluationTestCase.suite_id == suite.id,
                EvaluationTestCase.key == "product-echo-bud-facts",
            )
        )
        application_version = ApplicationVersion(
            name="Course prompt baseline",
            model_provider="ollama",
            model_name="course-demo-model",
            system_prompt="Answer only from the supplied store policies.",
            generation_parameters={"temperature": 0},
            knowledge_config=None,
            tool_config=None,
        )
        session.add(application_version)
        session.commit()
        assert test_case is not None
        application_version_id = application_version.id
        test_case_id = test_case.id

    registry = ModelProviderRegistry({"ollama": DeterministicModelAdapter()})
    app.dependency_overrides[get_model_provider_registry] = lambda: registry

    with TestClient(app) as client:
        create_response = client.post(
            "/api/test-case-executions",
            json={
                "application_version_id": application_version_id,
                "test_case_id": test_case_id,
            },
        )
        created = create_response.json()
        detail_response = client.get(f"/api/test-case-executions/{created['id']}")

    assert create_response.status_code == 201
    assert created["status"] == "pending"
    assert detail_response.status_code == 200
    assert detail_response.json() == {
        "id": created["id"],
        "application_version_id": application_version_id,
        "application_version_name": "Course prompt baseline",
        "test_case_id": test_case_id,
        "test_case_key": "product-echo-bud-facts",
        "test_case_title": "Answer with supported product facts",
        "test_case_severity": "normal",
        "status": "completed",
        "prompt_context": {
            "model_provider": "ollama",
            "model_name": "course-demo-model",
            "system_prompt": "Answer only from the supplied store policies.",
            "generation_parameters": {"temperature": 0},
            "grounding_material": [
                {
                    "kind": "product",
                    "title": "EchoBud X1 product card",
                    "content": (
                        "The fictional Northstar EchoBud X1 costs $79, is available in black "
                        "or silver, and includes a USB-C charging case."
                    ),
                }
            ],
            "user_input": "What colors does the EchoBud X1 come in, and what does it cost?",
            "user_prompt": (
                "Grounding material:\n"
                "- EchoBud X1 product card: The fictional Northstar EchoBud X1 costs $79, "
                "is available in black or silver, and includes a USB-C charging case.\n\n"
                "User input:\n"
                "What colors does the EchoBud X1 come in, and what does it cost?"
            ),
        },
        "model_response": "The EchoBud X1 costs $79 and comes in black or silver.",
        "usage": {
            "prompt_tokens": 51,
            "completion_tokens": 14,
            "total_tokens": 65,
        },
        "latency_ms": detail_response.json()["latency_ms"],
        "error": None,
        "deterministic_evaluation": {
            "scorer_version": "exact-phrase-v1",
            "passed": False,
            "regression_classification": None,
            "outcomes": [
                {
                    "check_type": "must_have_fact",
                    "position": 1,
                    "rule": "The price is $79.",
                    "passed": False,
                    "matched_evidence": None,
                },
                {
                    "check_type": "must_have_fact",
                    "position": 2,
                    "rule": "The available colors are black and silver.",
                    "passed": False,
                    "matched_evidence": None,
                },
                {
                    "check_type": "forbidden_claim",
                    "position": 3,
                    "rule": "A color or price not present in the product card.",
                    "passed": True,
                    "matched_evidence": None,
                },
            ],
        },
        "created_at": created["created_at"],
        "started_at": detail_response.json()["started_at"],
        "completed_at": detail_response.json()["completed_at"],
    }
    assert detail_response.json()["latency_ms"] >= 0
    assert detail_response.json()["started_at"].endswith("Z")
    assert detail_response.json()["completed_at"].endswith("Z")


def test_provider_failure_is_persisted_without_corrupting_the_execution_record():
    with SessionLocal() as session:
        suite = seed_sample_evaluation_suite(session)
        test_case = session.scalar(
            select(EvaluationTestCase).where(EvaluationTestCase.suite_id == suite.id)
        )
        application_version = ApplicationVersion(
            name="Unavailable local model",
            model_provider="ollama",
            model_name="missing-model",
            system_prompt="Use supplied evidence only.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        session.add(application_version)
        session.commit()
        assert test_case is not None
        application_version_id = application_version.id
        test_case_id = test_case.id

    registry = ModelProviderRegistry({"ollama": UnavailableModelAdapter()})
    app.dependency_overrides[get_model_provider_registry] = lambda: registry

    with TestClient(app) as client:
        create_response = client.post(
            "/api/test-case-executions",
            json={
                "application_version_id": application_version_id,
                "test_case_id": test_case_id,
            },
        )
        failed_response = client.get(
            f"/api/test-case-executions/{create_response.json()['id']}"
        )

    assert create_response.status_code == 201
    assert create_response.json()["status"] == "pending"
    failed = failed_response.json()
    assert failed["status"] == "failed"
    assert failed["model_response"] is None
    assert failed["usage"] is None
    assert failed["deterministic_evaluation"] is None
    assert failed["error"] == {
        "code": "provider_unavailable",
        "message": "Cannot reach the configured local model provider. Start it and retry.",
    }
    assert failed["started_at"].endswith("Z")
    assert failed["completed_at"].endswith("Z")


def test_process_restart_marks_an_in_flight_execution_as_failed_evidence():
    with SessionLocal() as session:
        suite = seed_sample_evaluation_suite(session)
        test_case = session.scalar(
            select(EvaluationTestCase).where(EvaluationTestCase.suite_id == suite.id)
        )
        application_version = ApplicationVersion(
            name="Interrupted prompt experiment",
            model_provider="ollama",
            model_name="course-demo-model",
            system_prompt="Use supplied evidence only.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        assert test_case is not None
        execution = EvaluationTestCaseExecution(
            application_version=application_version,
            test_case=test_case,
            status="running",
            prompt_context={"user_prompt": "Previously assembled prompt"},
            started_at=datetime.now(UTC),
        )
        session.add(execution)
        session.commit()
        execution_id = execution.id

    with TestClient(app) as client:
        response = client.get(f"/api/test-case-executions/{execution_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == {
        "code": "execution_interrupted",
        "message": "Execution was interrupted by an application restart. Run the Test Case again.",
    }
    assert response.json()["completed_at"].endswith("Z")
