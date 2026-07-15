# ruff: noqa: E402

import os
from collections import Counter
from pathlib import Path
from threading import Event, Thread

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select

load_dotenv(Path(__file__).parents[2] / ".env")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import llm_eval_lab.evaluation_runs as evaluation_runs_module
from llm_eval_lab.database import Base, SessionLocal, engine
from llm_eval_lab.evaluation_runs import reconcile_interrupted_evaluation_runs
from llm_eval_lab.main import app
from llm_eval_lab.model_provider import (
    ModelProviderFailure,
    ModelProviderRegistry,
    ModelRequest,
    ModelResponse,
    get_model_provider_registry,
)
from llm_eval_lab.models import ApplicationVersion, EvaluationRun
from llm_eval_lab.sample_suite import seed_sample_evaluation_suite
from llm_eval_lab.semantic_judging import (
    SemanticJudgeRequest,
    SemanticJudgeResult,
    get_semantic_judge,
)


class PromptAwareDeterministicAdapter:
    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content=f"{request.system_prompt} Answer from evidence.")


class OneCandidateFailureAdapter:
    def __init__(self) -> None:
        self.failed_once = False

    def generate(self, request: ModelRequest) -> ModelResponse:
        if request.system_prompt == "Candidate prompt." and not self.failed_once:
            self.failed_once = True
            raise ModelProviderFailure(
                "candidate_case_failed",
                "The deterministic candidate failure was preserved.",
            )
        return ModelResponse(content=f"{request.system_prompt} Answer from evidence.")


class BlockingDeterministicAdapter:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.entered.is_set():
            self.entered.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("The test did not release the blocking adapter.")
        return ModelResponse(content=f"{request.system_prompt} Answer from evidence.")


class DeterministicSemanticJudge:
    low_confidence_threshold = 0.7

    def configuration_snapshot(self):
        return {
            "judge_version": "structured-semantic-v1",
            "provider": "fixture-judge",
            "model": "deterministic-semantic-judge",
            "generation_parameters": {"temperature": 0},
            "low_confidence_threshold": 0.7,
        }

    def judge(self, request: SemanticJudgeRequest) -> SemanticJudgeResult:
        return SemanticJudgeResult(
            outcome="pass",
            rationale="Deterministic fixture judgment.",
            confidence=0.95,
        )


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides.clear()
    app.dependency_overrides[get_semantic_judge] = lambda: DeterministicSemanticJudge()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_run_inputs() -> tuple[str, str, str]:
    with SessionLocal() as session:
        suite = seed_sample_evaluation_suite(session)
        baseline = ApplicationVersion(
            name="Course prompt baseline",
            model_provider="ollama",
            model_name="course-demo-model",
            system_prompt="Baseline prompt.",
            generation_parameters={"temperature": 0},
            knowledge_config=None,
            tool_config=None,
        )
        candidate = ApplicationVersion(
            name="Safety prompt candidate",
            model_provider="ollama",
            model_name="course-demo-model",
            system_prompt="Candidate prompt.",
            generation_parameters={"temperature": 0},
            knowledge_config=None,
            tool_config=None,
        )
        session.add_all([baseline, candidate])
        session.commit()
        return baseline.id, candidate.id, suite.id


def test_evaluation_user_can_run_and_reopen_a_paired_evaluation_run():
    baseline_id, candidate_id, suite_id = seed_run_inputs()

    registry = ModelProviderRegistry({"ollama": PromptAwareDeterministicAdapter()})
    app.dependency_overrides[get_model_provider_registry] = lambda: registry

    with TestClient(app) as client:
        create_response = client.post(
            "/api/evaluation-runs",
            json={
                "baseline_version_id": baseline_id,
                "candidate_version_id": candidate_id,
                "evaluation_suite_id": suite_id,
            },
        )
        created = create_response.json()
        reopened_response = client.get(f"/api/evaluation-runs/{created['id']}")
        history_response = client.get("/api/evaluation-runs")

    assert create_response.status_code == 201
    assert created["status"] == "pending"
    assert created["progress"] == {
        "total": 16,
        "queued": 16,
        "running": 0,
        "completed": 0,
        "failed": 0,
    }

    assert reopened_response.status_code == 200
    reopened = reopened_response.json()
    assert reopened["id"] == created["id"]
    assert reopened["baseline_version"] == {
        "id": baseline_id,
        "name": "Course prompt baseline",
    }
    assert reopened["candidate_version"] == {
        "id": candidate_id,
        "name": "Safety prompt candidate",
    }
    assert reopened["evaluation_suite"] == {
        "id": suite_id,
        "slug": "northstar-electronics-support",
        "version": 1,
        "name": "Northstar Electronics Support",
    }
    assert reopened["status"] == "completed"
    assert reopened["progress"] == {
        "total": 16,
        "queued": 0,
        "running": 0,
        "completed": 16,
        "failed": 0,
    }
    assert len(reopened["executions"]) == 16
    assert Counter(execution["version_role"] for execution in reopened["executions"]) == {
        "baseline": 8,
        "candidate": 8,
    }
    assert Counter(execution["test_case_key"] for execution in reopened["executions"]) == {
        "product-echo-bud-facts": 2,
        "shipping-standard-window": 2,
        "return-opened-earbuds": 2,
        "warranty-water-damage": 2,
        "hallucination-unannounced-product": 2,
        "hallucination-same-day-delivery": 2,
        "prompt-injection-system-prompt": 2,
        "jailbreak-fabricated-warranty": 2,
    }
    assert {
        execution["model_response"]
        for execution in reopened["executions"]
    } == {
        "Baseline prompt. Answer from evidence.",
        "Candidate prompt. Answer from evidence.",
    }
    assert history_response.status_code == 200
    assert [evaluation_run["id"] for evaluation_run in history_response.json()] == [
        created["id"]
    ]


def test_evaluation_run_rejects_using_the_same_version_on_both_sides():
    baseline_id, _, suite_id = seed_run_inputs()

    with TestClient(app) as client:
        response = client.post(
            "/api/evaluation-runs",
            json={
                "baseline_version_id": baseline_id,
                "candidate_version_id": baseline_id,
                "evaluation_suite_id": suite_id,
            },
        )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Baseline and Candidate must be different Application Versions."
    }


@pytest.mark.parametrize(
    ("field", "missing_id"),
    [
        ("baseline_version_id", "missing-baseline"),
        ("candidate_version_id", "missing-candidate"),
        ("evaluation_suite_id", "missing-suite"),
    ],
)
def test_evaluation_run_rejects_an_invalid_reference(field: str, missing_id: str):
    baseline_id, candidate_id, suite_id = seed_run_inputs()
    payload = {
        "baseline_version_id": baseline_id,
        "candidate_version_id": candidate_id,
        "evaluation_suite_id": suite_id,
    }
    payload[field] = missing_id

    with TestClient(app) as client:
        response = client.post("/api/evaluation-runs", json=payload)

    assert response.status_code == 404


def test_one_failed_case_does_not_hide_or_stop_the_other_results():
    baseline_id, candidate_id, suite_id = seed_run_inputs()
    registry = ModelProviderRegistry({"ollama": OneCandidateFailureAdapter()})
    app.dependency_overrides[get_model_provider_registry] = lambda: registry

    with TestClient(app) as client:
        response = client.post(
            "/api/evaluation-runs",
            json={
                "baseline_version_id": baseline_id,
                "candidate_version_id": candidate_id,
                "evaluation_suite_id": suite_id,
            },
        )
        evaluation_run = client.get(
            f"/api/evaluation-runs/{response.json()['id']}"
        ).json()

    assert evaluation_run["status"] == "completed"
    assert evaluation_run["progress"] == {
        "total": 16,
        "queued": 0,
        "running": 0,
        "completed": 15,
        "failed": 1,
    }
    failed = [
        execution
        for execution in evaluation_run["executions"]
        if execution["status"] == "failed"
    ]
    assert len(failed) == 1
    assert failed[0]["version_role"] == "candidate"
    assert failed[0]["error"] == {
        "code": "candidate_case_failed",
        "message": "The deterministic candidate failure was preserved.",
    }


def test_restart_marks_an_in_flight_evaluation_run_as_failed():
    baseline_id, candidate_id, suite_id = seed_run_inputs()
    with SessionLocal() as session:
        evaluation_run = EvaluationRun(
            baseline_version_id=baseline_id,
            candidate_version_id=candidate_id,
            evaluation_suite_id=suite_id,
            status="running",
        )
        session.add(evaluation_run)
        session.commit()
        run_id = evaluation_run.id

    reconcile_interrupted_evaluation_runs()

    with SessionLocal() as session:
        recovered = session.get(EvaluationRun, run_id)
        assert recovered is not None
        assert recovered.status == "failed"
        assert recovered.completed_at is not None


def test_progress_reports_one_running_execution_while_the_rest_remain_queued():
    baseline_id, candidate_id, suite_id = seed_run_inputs()
    adapter = BlockingDeterministicAdapter()
    registry = ModelProviderRegistry({"ollama": adapter})
    app.dependency_overrides[get_model_provider_registry] = lambda: registry
    responses = []

    with TestClient(app) as client:
        thread = Thread(
            target=lambda: responses.append(
                client.post(
                    "/api/evaluation-runs",
                    json={
                        "baseline_version_id": baseline_id,
                        "candidate_version_id": candidate_id,
                        "evaluation_suite_id": suite_id,
                    },
                )
            ),
            daemon=True,
        )
        thread.start()
        try:
            assert adapter.entered.wait(timeout=5)
            with SessionLocal() as session:
                run_id = session.scalar(select(EvaluationRun.id))
            assert run_id is not None
            in_progress = client.get(f"/api/evaluation-runs/{run_id}").json()
        finally:
            adapter.release.set()
            thread.join(timeout=5)

        assert not thread.is_alive()
        terminal = client.get(f"/api/evaluation-runs/{run_id}").json()

    assert in_progress["status"] == "running"
    assert in_progress["progress"] == {
        "total": 16,
        "queued": 15,
        "running": 1,
        "completed": 0,
        "failed": 0,
    }
    assert responses[0].status_code == 201
    assert terminal["status"] == "completed"
    assert terminal["progress"]["completed"] == 16


def test_orchestration_failure_is_recorded_and_remaining_cases_continue(monkeypatch):
    baseline_id, candidate_id, suite_id = seed_run_inputs()
    registry = ModelProviderRegistry({"ollama": PromptAwareDeterministicAdapter()})
    app.dependency_overrides[get_model_provider_registry] = lambda: registry
    real_run_execution = evaluation_runs_module.run_test_case_execution
    calls = 0

    def fail_first_execution(
        execution_id: str,
        provider_registry: ModelProviderRegistry,
        semantic_judge,
    ):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("deterministic orchestration failure")
        real_run_execution(execution_id, provider_registry, semantic_judge)

    monkeypatch.setattr(
        evaluation_runs_module,
        "run_test_case_execution",
        fail_first_execution,
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/evaluation-runs",
            json={
                "baseline_version_id": baseline_id,
                "candidate_version_id": candidate_id,
                "evaluation_suite_id": suite_id,
            },
        ).json()
        evaluation_run = client.get(f"/api/evaluation-runs/{created['id']}").json()

    assert evaluation_run["status"] == "failed"
    assert evaluation_run["progress"] == {
        "total": 16,
        "queued": 0,
        "running": 0,
        "completed": 15,
        "failed": 1,
    }
    failed = [
        execution
        for execution in evaluation_run["executions"]
        if execution["status"] == "failed"
    ]
    assert failed[0]["error"]["code"] == "execution_orchestration_failure"
