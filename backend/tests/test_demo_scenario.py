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
from llm_eval_lab.demo_provider import DeterministicDemoAdapter
from llm_eval_lab.demo_scenario import (
    DEMO_BASELINE_ID,
    DEMO_CANDIDATE_ID,
    reset_demo_scenario,
)
from llm_eval_lab.main import app
from llm_eval_lab.model_provider import ModelProviderRegistry, get_model_provider_registry
from llm_eval_lab.models import ApplicationVersion, EvaluationRun, ReleaseRule
from llm_eval_lab.sample_suite import seed_default_release_rule
from llm_eval_lab.semantic_judging import (
    ProviderBackedSemanticJudge,
    SemanticJudgeConfig,
    get_semantic_judge,
)

REPORT_PATH = Path(__file__).parent / "fixtures" / "agent-incident-validation-report.json"


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def demo_registry() -> ModelProviderRegistry:
    return ModelProviderRegistry({"demo-fixture": DeterministicDemoAdapter()})


def demo_judge(registry: ModelProviderRegistry) -> ProviderBackedSemanticJudge:
    return ProviderBackedSemanticJudge(
        registry,
        SemanticJudgeConfig(
            provider="demo-fixture",
            model="northstar-semantic-fixture-v1",
            low_confidence_threshold=0.7,
        ),
    )


def test_demo_reset_is_idempotent_and_preserves_unrelated_application_data():
    with SessionLocal() as session:
        unrelated = ApplicationVersion(
            name="User-owned version",
            model_provider="ollama",
            model_name="user-model",
            system_prompt="User-owned prompt.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        session.add(unrelated)
        session.commit()
        unrelated_id = unrelated.id

    with SessionLocal() as session:
        first = reset_demo_scenario(session)
        first_ids = (first.baseline.id, first.candidate.id, first.suite.id, first.rule.id)
        mixed_run = EvaluationRun(
            baseline_version_id=DEMO_BASELINE_ID,
            candidate_version_id=unrelated_id,
            evaluation_suite_id=first.suite.id,
            status="completed",
        )
        owned_run = EvaluationRun(
            baseline_version_id=DEMO_BASELINE_ID,
            candidate_version_id=DEMO_CANDIDATE_ID,
            evaluation_suite_id=first.suite.id,
            status="completed",
        )
        session.add_all([mixed_run, owned_run])
        session.commit()
        mixed_run_id = mixed_run.id
        owned_run_id = owned_run.id

    with SessionLocal() as session:
        second = reset_demo_scenario(session)
        second_ids = (
            second.baseline.id,
            second.candidate.id,
            second.suite.id,
            second.rule.id,
        )
        version_ids = set(session.scalars(select(ApplicationVersion.id)))
        run_ids = set(session.scalars(select(EvaluationRun.id)))

    assert first_ids == second_ids
    assert first_ids[:2] == (DEMO_BASELINE_ID, DEMO_CANDIDATE_ID)
    assert unrelated_id in version_ids
    assert {DEMO_BASELINE_ID, DEMO_CANDIDATE_ID} <= version_ids
    assert mixed_run_id in run_ids
    assert owned_run_id not in run_ids


def test_demo_reset_uses_one_commit_after_seed_data_exists(monkeypatch):
    with SessionLocal() as session:
        reset_demo_scenario(session)

    with SessionLocal() as session:
        real_commit = session.commit
        commit_calls = 0

        def counted_commit():
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls > 1:
                raise RuntimeError("Demo reset attempted a second commit.")
            real_commit()

        monkeypatch.setattr(session, "commit", counted_commit)
        reset_demo_scenario(session)

    assert commit_calls == 1


def test_demo_reset_rolls_back_run_deletion_when_commit_fails(monkeypatch):
    with SessionLocal() as session:
        scenario = reset_demo_scenario(session)
        owned_run = EvaluationRun(
            baseline_version_id=DEMO_BASELINE_ID,
            candidate_version_id=DEMO_CANDIDATE_ID,
            evaluation_suite_id=scenario.suite.id,
            status="completed",
        )
        session.add(owned_run)
        session.commit()
        owned_run_id = owned_run.id

    with SessionLocal() as session:
        def failed_commit():
            raise RuntimeError("Injected commit failure.")

        monkeypatch.setattr(session, "commit", failed_commit)
        with pytest.raises(RuntimeError, match="Injected commit failure"):
            reset_demo_scenario(session)

    with SessionLocal() as session:
        assert session.get(EvaluationRun, owned_run_id) is not None


def test_offline_demo_runs_a_regression_review_and_release_decision_end_to_end():
    with SessionLocal() as session:
        scenario = reset_demo_scenario(session)
        seed_default_release_rule(session)
        suite_id = scenario.suite.id
        rule_id = session.scalar(select(ReleaseRule.id))

    registry = demo_registry()
    app.dependency_overrides[get_model_provider_registry] = lambda: registry
    app.dependency_overrides[get_semantic_judge] = lambda: demo_judge(registry)

    with TestClient(app) as client:
        run_response = client.post(
            "/api/evaluation-runs",
            json={
                "baseline_version_id": DEMO_BASELINE_ID,
                "candidate_version_id": DEMO_CANDIDATE_ID,
                "evaluation_suite_id": suite_id,
            },
        )
        completed = client.get(
            f"/api/evaluation-runs/{run_response.json()['id']}"
        ).json()
        review_items = client.get("/api/human-review-items").json()
        assert len(review_items) == 1
        candidate_conflict = next(
            item
            for item in review_items
            if item["version_role"] == "candidate"
            and "automatic_conflict" in item["reasons"]
        )
        review_response = client.patch(
            f"/api/human-review-items/{candidate_conflict['id']}",
            json={
                "outcome": "fail",
                "rationale": "The Candidate exposed forbidden prompt-injection content.",
            },
        )
        evidence_response = client.post(
            f"/api/evaluation-runs/{completed['id']}/external-safety-evidence",
            content=REPORT_PATH.read_bytes(),
            headers={"Content-Type": "application/json"},
        )
        decision_response = client.post(
            "/api/release-decisions",
            json={
                "evaluation_run_id": completed["id"],
                "release_rule_id": rule_id,
            },
        )

    assert run_response.status_code == 201
    assert completed["status"] == "completed"
    assert len(completed["executions"]) == 2
    assert completed["deterministic_summary"]["new_regressions"] == 1
    assert completed["deterministic_summary"]["new_regressions_by_severity"][
        "release_blocking"
    ] == 1
    assert completed["deterministic_summary"]["baseline"]["safety"] == {
        "passed": 1,
        "failed": 0,
        "total": 1,
    }
    assert completed["deterministic_summary"]["candidate"]["safety"] == {
        "passed": 0,
        "failed": 1,
        "total": 1,
    }
    assert review_response.status_code == 200
    assert evidence_response.status_code == 201
    assert decision_response.status_code == 201
    decision = decision_response.json()
    assert decision["outcome"] == "fail"
    assert "release_blocking_failure" in {
        reason["code"] for reason in decision["reasons"]
    }
    assert "external_safety_evidence_ineffective" not in {
        reason["code"] for reason in decision["reasons"]
    }
    assert decision["metrics"]["external_safety"]["status"] == "pass"
