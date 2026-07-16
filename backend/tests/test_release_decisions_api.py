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
from llm_eval_lab.models import (
    ApplicationVersion,
    DeterministicCheckOutcome,
    DeterministicEvaluation,
    EvaluationRun,
    EvaluationSuite,
    HumanReviewItem,
    ReleaseRule,
    SemanticEvaluation,
)
from llm_eval_lab.models import (
    TestCase as EvaluationTestCase,
)
from llm_eval_lab.models import (
    TestCaseExecution as EvaluationTestCaseExecution,
)
from llm_eval_lab.release_decision_policy import evaluate_release


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_clean_completed_run() -> str:
    now = datetime.now(UTC)
    with SessionLocal() as session:
        baseline = ApplicationVersion(
            name="Release baseline",
            model_provider="fixture",
            model_name="deterministic",
            system_prompt="Answer from evidence.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        candidate = ApplicationVersion(
            name="Release candidate",
            model_provider="fixture",
            model_name="deterministic",
            system_prompt="Answer safely from evidence.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        test_case = EvaluationTestCase(
            key="clean-release-case",
            position=1,
            title="Keep a clean release eligible",
            user_input="Give the supported answer.",
            grounding_material=[],
            must_have_facts=["Supported fact."],
            forbidden_claims=["Unsafe claim."],
            test_type="normal",
            severity="normal",
            requires_human_review=False,
        )
        suite = EvaluationSuite(
            slug="release-decision-fixture",
            version=1,
            name="Release Decision Fixture",
            description="A minimal paired run for release policy tests.",
            test_cases=[test_case],
        )
        evaluation_run = EvaluationRun(
            baseline_version=baseline,
            candidate_version=candidate,
            evaluation_suite=suite,
            status="completed",
            started_at=now,
            completed_at=now,
        )
        for role, version, latency_ms, cost_usd in (
            ("baseline", baseline, 100, 0.01),
            ("candidate", candidate, 120, 0.02),
        ):
            execution = EvaluationTestCaseExecution(
                application_version=version,
                test_case=test_case,
                version_role=role,
                status="completed",
                prompt_context={"user_input": test_case.user_input},
                model_response="Supported fact.",
                usage={"total_tokens": 10, "cost_usd": cost_usd},
                latency_ms=latency_ms,
                started_at=now,
                completed_at=now,
                deterministic_evaluation=DeterministicEvaluation(
                    scorer_version="exact-phrase-v1",
                    passed=True,
                    regression_classification=None,
                    outcomes=[
                        DeterministicCheckOutcome(
                            check_type="must_have_fact",
                            position=1,
                            rule="Supported fact.",
                            passed=True,
                            matched_evidence="Supported fact.",
                        ),
                        DeterministicCheckOutcome(
                            check_type="forbidden_claim",
                            position=2,
                            rule="Unsafe claim.",
                            passed=True,
                            matched_evidence=None,
                        ),
                    ],
                ),
            )
            evaluation_run.executions.append(execution)
        session.add(evaluation_run)
        session.commit()
        return evaluation_run.id


def release_rule_payload() -> dict[str, object]:
    return {
        "slug": "default-local-release",
        "version": 1,
        "name": "Default local release rule",
        "blocking_severities": ["release_blocking"],
        "new_regression_severities": ["important", "release_blocking"],
        "require_resolved_reviews": True,
        "maximum_correctness_drop": 0.0,
        "minimum_candidate_safety_rate": 1.0,
        "maximum_candidate_average_latency_ms": 120,
        "maximum_candidate_total_cost_usd": 0.02,
    }


def test_evidence_fingerprint_is_stable_when_test_case_positions_tie():
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        evaluation_run = session.get(EvaluationRun, run_id)
        assert evaluation_run is not None
        release_rule = ReleaseRule(**release_rule_payload())
        session.add(release_rule)
        session.flush()
        for execution in evaluation_run.executions:
            execution.version_role = "candidate"

        first_fingerprint = evaluate_release(
            evaluation_run,
            release_rule,
        ).evidence_fingerprint
        evaluation_run.executions.reverse()
        reversed_fingerprint = evaluate_release(
            evaluation_run,
            release_rule,
        ).evidence_fingerprint

    assert reversed_fingerprint == first_fingerprint


def test_clean_run_at_threshold_boundaries_produces_one_reproducible_pass_decision():
    run_id = seed_clean_completed_run()

    with TestClient(app) as client:
        rule_response = client.post("/api/release-rules", json=release_rule_payload())
        rule = rule_response.json()
        decision_response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )
        repeated_response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert rule_response.status_code == 201
    assert decision_response.status_code == 201
    decision = decision_response.json()
    assert decision["outcome"] == "pass"
    assert decision["reasons"] == [
        {
            "code": "all_release_conditions_passed",
            "message": "All configured release conditions passed.",
            "execution_ids": [],
            "observed": None,
            "threshold": None,
        }
    ]
    assert decision["metrics"] == {
        "correctness": {
            "baseline_rate": 1.0,
            "candidate_rate": 1.0,
            "delta": 0.0,
            "maximum_drop": 0.0,
            "status": "pass",
        },
        "safety": {
            "baseline_rate": 1.0,
            "candidate_rate": 1.0,
            "minimum_candidate_rate": 1.0,
            "status": "pass",
        },
        "latency": {
            "baseline_average_ms": 100.0,
            "candidate_average_ms": 120.0,
            "maximum_candidate_average_ms": 120,
            "status": "pass",
        },
        "cost": {
            "baseline_total_usd": 0.01,
            "candidate_total_usd": 0.02,
            "maximum_candidate_total_usd": 0.02,
            "status": "pass",
        },
    }
    assert len(decision["evidence_fingerprint"]) == 64
    assert repeated_response.status_code == 200
    assert repeated_response.json() == decision


@pytest.mark.parametrize(
    ("severity", "expected_reason"),
    [
        ("release_blocking", "release_blocking_failure"),
        ("important", "new_important_regression"),
    ],
)
def test_decisive_candidate_failures_block_release_with_direct_execution_evidence(
    severity: str,
    expected_reason: str,
):
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        candidate.test_case.severity = severity
        evaluation = candidate.deterministic_evaluation
        assert evaluation is not None
        evaluation.passed = False
        evaluation.regression_classification = "new_regression"
        evaluation.outcomes[1].passed = False
        evaluation.outcomes[1].matched_evidence = "Unsafe claim."
        candidate_id = candidate.id
        session.commit()

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "fail"
    reason = next(
        reason for reason in decision["reasons"] if reason["code"] == expected_reason
    )
    assert reason["execution_ids"] == [candidate_id]
    assert reason["observed"] == severity
    assert reason["threshold"] in (
        ["release_blocking"],
        ["important", "release_blocking"],
    )


@pytest.mark.parametrize(
    ("severity", "expected_reason"),
    [
        ("release_blocking", "release_blocking_failure"),
        ("important", "new_important_regression"),
    ],
)
def test_decisive_automatic_failure_precedes_an_unresolved_review(
    severity: str,
    expected_reason: str,
):
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        candidate.test_case.severity = severity
        evaluation = candidate.deterministic_evaluation
        assert evaluation is not None
        evaluation.passed = False
        evaluation.regression_classification = "new_regression"
        evaluation.outcomes[1].passed = False
        evaluation.outcomes[1].matched_evidence = "Unsafe claim."
        session.add(
            HumanReviewItem(
                execution=candidate,
                status="pending",
                reasons=["automatic_conflict"],
            )
        )
        session.commit()

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "fail"
    assert expected_reason in {reason["code"] for reason in decision["reasons"]}


@pytest.mark.parametrize(
    ("severity", "expected_reason"),
    [
        ("release_blocking", "release_blocking_failure"),
        ("important", "new_important_regression"),
    ],
)
def test_human_pass_cannot_override_a_nonnegotiable_automatic_failure(
    severity: str,
    expected_reason: str,
):
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        candidate.test_case.severity = severity
        evaluation = candidate.deterministic_evaluation
        assert evaluation is not None
        evaluation.passed = False
        evaluation.regression_classification = "new_regression"
        evaluation.outcomes[1].passed = False
        evaluation.outcomes[1].matched_evidence = "Unsafe claim."
        session.add(
            HumanReviewItem(
                execution=candidate,
                status="resolved",
                reasons=["automatic_conflict"],
                outcome="pass",
                rationale="The reviewer accepts the response as a whole.",
                resolved_at=datetime.now(UTC),
            )
        )
        session.commit()

    payload = release_rule_payload()
    payload["maximum_correctness_drop"] = 1.0
    payload["minimum_candidate_safety_rate"] = 0.0
    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=payload).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "fail"
    assert expected_reason in {reason["code"] for reason in decision["reasons"]}


def test_unresolved_review_requires_manual_decision_and_resolution_creates_new_snapshot():
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        review = HumanReviewItem(
            execution=candidate,
            status="pending",
            reasons=["test_case_requires_review"],
        )
        session.add(review)
        session.commit()
        review_id = review.id
        candidate_id = candidate.id

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        manual_response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )
        resolved_response = client.patch(
            f"/api/human-review-items/{review_id}",
            json={
                "outcome": "pass",
                "rationale": "The complete evidence supports this response.",
            },
        )
        pass_response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )
        history_response = client.get(
            f"/api/release-decisions?evaluation_run_id={run_id}"
        )

    assert manual_response.status_code == 201
    manual = manual_response.json()
    assert manual["outcome"] == "manual_review_required"
    assert manual["reasons"] == [
        {
            "code": "unresolved_human_review",
            "message": "Keep a clean release eligible requires Human Review.",
            "execution_ids": [candidate_id],
            "observed": "pending",
            "threshold": "resolved",
        }
    ]
    assert resolved_response.status_code == 200
    assert pass_response.status_code == 201
    passed = pass_response.json()
    assert passed["outcome"] == "pass"
    assert passed["id"] != manual["id"]
    assert passed["evidence_fingerprint"] != manual["evidence_fingerprint"]
    assert history_response.status_code == 200
    assert [decision["id"] for decision in history_response.json()] == [
        passed["id"],
        manual["id"],
    ]


def test_unresolved_baseline_review_does_not_gate_a_clean_candidate():
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        baseline = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "baseline",
            )
        )
        assert baseline is not None
        session.add(
            HumanReviewItem(
                execution=baseline,
                status="pending",
                reasons=["automatic_conflict"],
            )
        )
        session.commit()

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "pass"
    assert decision["reasons"][0]["code"] == "all_release_conditions_passed"


@pytest.mark.parametrize(
    ("failed_condition", "expected_reason", "expected_observed", "expected_threshold"),
    [
        ("correctness", "correctness_drop_exceeded", 1.0, 0.0),
        ("safety", "candidate_safety_below_minimum", 0.0, 1.0),
        ("latency", "latency_budget_exceeded", 121.0, 120),
        ("cost", "cost_budget_exceeded", 0.021, 0.02),
    ],
)
def test_quality_safety_latency_and_cost_threshold_failures_are_explained(
    failed_condition: str,
    expected_reason: str,
    expected_observed: float,
    expected_threshold: float,
):
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        evaluation = candidate.deterministic_evaluation
        assert evaluation is not None
        if failed_condition == "correctness":
            evaluation.passed = False
            evaluation.outcomes[0].passed = False
            evaluation.outcomes[0].matched_evidence = None
        elif failed_condition == "safety":
            evaluation.passed = False
            evaluation.outcomes[1].passed = False
            evaluation.outcomes[1].matched_evidence = "Unsafe claim."
        elif failed_condition == "latency":
            candidate.latency_ms = 121
        else:
            candidate.usage = {"total_tokens": 10, "cost_usd": 0.021}
        session.commit()

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "fail"
    assert decision["metrics"][failed_condition]["status"] == "fail"
    reason = next(
        reason for reason in decision["reasons"] if reason["code"] == expected_reason
    )
    assert reason["observed"] == expected_observed
    assert reason["threshold"] == expected_threshold


@pytest.mark.parametrize(
    ("missing_metric", "expected_reason", "expected_threshold"),
    [
        ("latency", "latency_metric_unavailable", 120),
        ("cost", "cost_metric_unavailable", 0.02),
    ],
)
def test_configured_budgets_without_evidence_require_manual_review(
    missing_metric: str,
    expected_reason: str,
    expected_threshold: float,
):
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        if missing_metric == "latency":
            candidate.latency_ms = None
        else:
            candidate.usage = {"total_tokens": 10}
        session.commit()

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "manual_review_required"
    assert decision["metrics"][missing_metric]["status"] == "unavailable"
    reason = next(
        reason for reason in decision["reasons"] if reason["code"] == expected_reason
    )
    assert reason["observed"] is None
    assert reason["threshold"] == expected_threshold


def test_failed_or_unscored_execution_cannot_silently_pass_a_release():
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        candidate.status = "failed"
        candidate.error = {
            "code": "provider_unavailable",
            "message": "The local model provider was unavailable.",
        }
        candidate.deterministic_evaluation = None
        candidate_id = candidate.id
        session.commit()

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "manual_review_required"
    reason = next(
        reason
        for reason in decision["reasons"]
        if reason["code"] == "evaluation_evidence_unavailable"
    )
    assert reason["execution_ids"] == [candidate_id]
    assert reason["observed"] == "failed"
    assert reason["threshold"] == "completed_and_scored"


def test_resolved_human_failure_overrides_deterministic_pass_for_blocking_case():
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        candidate.test_case.severity = "release_blocking"
        review = HumanReviewItem(
            execution=candidate,
            status="pending",
            reasons=["automatic_conflict"],
        )
        session.add(review)
        session.commit()
        review_id = review.id
        candidate_id = candidate.id

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        review_response = client.patch(
            f"/api/human-review-items/{review_id}",
            json={
                "outcome": "fail",
                "rationale": "The response violates the blocking safety requirement.",
            },
        )
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert review_response.status_code == 200
    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "fail"
    reason = next(
        reason
        for reason in decision["reasons"]
        if reason["code"] == "release_blocking_failure"
    )
    assert reason["execution_ids"] == [candidate_id]


def test_resolved_candidate_human_failure_is_a_release_gate_without_rewriting_metrics():
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        review = HumanReviewItem(
            execution=candidate,
            status="resolved",
            reasons=["automatic_conflict"],
            outcome="fail",
            rationale="The candidate response is not acceptable as a whole.",
            resolved_at=datetime.now(UTC),
        )
        session.add(review)
        session.commit()
        candidate_id = candidate.id

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "fail"
    assert decision["metrics"]["correctness"]["candidate_rate"] == 1.0
    assert decision["metrics"]["safety"]["candidate_rate"] == 1.0
    reason = next(
        reason
        for reason in decision["reasons"]
        if reason["code"] == "human_review_failure"
    )
    assert reason["execution_ids"] == [candidate_id]
    assert reason["observed"] == "fail"
    assert reason["threshold"] == "pass"


def test_human_review_does_not_rewrite_automatic_quality_metrics():
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        baseline = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "baseline",
            )
        )
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert baseline is not None
        assert candidate is not None
        session.add(
            HumanReviewItem(
                execution=baseline,
                status="resolved",
                reasons=["automatic_conflict"],
                outcome="fail",
                rationale="The baseline response is unacceptable as a whole.",
                resolved_at=datetime.now(UTC),
            )
        )
        evaluation = candidate.deterministic_evaluation
        assert evaluation is not None
        evaluation.passed = False
        evaluation.outcomes[0].passed = False
        evaluation.outcomes[0].matched_evidence = None
        session.commit()

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert response.status_code == 201
    decision = response.json()
    assert decision["outcome"] == "fail"
    assert decision["metrics"]["correctness"] == {
        "baseline_rate": 1.0,
        "candidate_rate": 0.0,
        "delta": -1.0,
        "maximum_drop": 0.0,
        "status": "fail",
    }
    assert "correctness_drop_exceeded" in {
        reason["code"] for reason in decision["reasons"]
    }


def test_semantic_evidence_change_creates_a_new_fingerprinted_snapshot():
    run_id = seed_clean_completed_run()
    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        candidate.semantic_evaluation = SemanticEvaluation(
            judge_version="structured-semantic-v1",
            outcome="pass",
            rationale="Initial independent semantic evidence.",
            confidence=0.8,
            judge_configuration={"provider": "fixture", "model": "judge-v1"},
            error=None,
        )
        session.commit()

    with TestClient(app) as client:
        rule = client.post("/api/release-rules", json=release_rule_payload()).json()
        initial_response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    with SessionLocal() as session:
        candidate = session.scalar(
            select(EvaluationTestCaseExecution).where(
                EvaluationTestCaseExecution.evaluation_run_id == run_id,
                EvaluationTestCaseExecution.version_role == "candidate",
            )
        )
        assert candidate is not None
        assert candidate.semantic_evaluation is not None
        candidate.semantic_evaluation.rationale = "Revised independent semantic evidence."
        candidate.semantic_evaluation.confidence = 0.95
        session.commit()

    with TestClient(app) as client:
        revised_response = client.post(
            "/api/release-decisions",
            json={"evaluation_run_id": run_id, "release_rule_id": rule["id"]},
        )

    assert initial_response.status_code == 201
    assert revised_response.status_code == 201
    initial = initial_response.json()
    revised = revised_response.json()
    assert revised["id"] != initial["id"]
    assert revised["evidence_fingerprint"] != initial["evidence_fingerprint"]


def test_release_rules_are_versioned_api_inputs_and_incomplete_runs_are_rejected():
    run_id = seed_clean_completed_run()

    with TestClient(app) as client:
        created_response = client.post(
            "/api/release-rules",
            json=release_rule_payload(),
        )
        duplicate_response = client.post(
            "/api/release-rules",
            json=release_rule_payload(),
        )
        list_response = client.get("/api/release-rules")
        patch_response = client.patch(
            f"/api/release-rules/{created_response.json()['id']}",
            json={"name": "Mutated rule"},
        )

    with SessionLocal() as session:
        evaluation_run = session.get(EvaluationRun, run_id)
        assert evaluation_run is not None
        evaluation_run.status = "running"
        evaluation_run.completed_at = None
        session.commit()

    with TestClient(app) as client:
        decision_response = client.post(
            "/api/release-decisions",
            json={
                "evaluation_run_id": run_id,
                "release_rule_id": created_response.json()["id"],
            },
        )

    assert created_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert list_response.status_code == 200
    assert list_response.json() == [created_response.json()]
    assert patch_response.status_code == 404
    assert decision_response.status_code == 409


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("blocking_severities", ["normal"]),
        ("new_regression_severities", ["normal"]),
    ],
)
def test_release_rules_cannot_disable_nonnegotiable_failure_gates(
    field: str,
    unsafe_value: list[str],
):
    payload = release_rule_payload()
    payload[field] = unsafe_value

    with TestClient(app) as client:
        response = client.post("/api/release-rules", json=payload)

    assert response.status_code == 422
