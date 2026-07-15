# ruff: noqa: E402

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

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
from llm_eval_lab.models import ApplicationVersion, EvaluationSuite
from llm_eval_lab.models import TestCase as EvaluationTestCase
from llm_eval_lab.semantic_judging import (
    SemanticJudgeRequest,
    SemanticJudgeResult,
    get_semantic_judge,
)


class RegressionFixtureAdapter:
    def generate(self, request: ModelRequest) -> ModelResponse:
        role = "baseline" if request.system_prompt == "Baseline prompt." else "candidate"
        if "quality-case" in request.user_prompt:
            content = "Supported fact."
        elif "existing-failure-case" in request.user_prompt:
            content = "Policy fact. Unsafe promise."
        elif role == "baseline":
            content = "Secure answer."
        else:
            content = "Secure answer. Leaked secret."
        return ModelResponse(content=content)


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


def seed_scoring_run_inputs() -> tuple[str, str, str]:
    with SessionLocal() as session:
        suite = EvaluationSuite(
            slug="deterministic-regression-fixture",
            version=1,
            name="Deterministic Regression Fixture",
            description="Small fixture for rule evidence and regression classification.",
            test_cases=[
                EvaluationTestCase(
                    key="quality-case",
                    position=1,
                    title="Pass supported quality evidence",
                    user_input="quality-case",
                    grounding_material=[],
                    must_have_facts=["Supported fact."],
                    forbidden_claims=["Invented fact."],
                    test_type="normal",
                    severity="normal",
                    requires_human_review=False,
                ),
                EvaluationTestCase(
                    key="existing-failure-case",
                    position=2,
                    title="Preserve an existing safety failure",
                    user_input="existing-failure-case",
                    grounding_material=[],
                    must_have_facts=["Policy fact."],
                    forbidden_claims=["Unsafe promise."],
                    test_type="hallucination",
                    severity="important",
                    requires_human_review=False,
                ),
                EvaluationTestCase(
                    key="new-regression-case",
                    position=3,
                    title="Surface a new release-blocking regression",
                    user_input="new-regression-case",
                    grounding_material=[],
                    must_have_facts=["Secure answer."],
                    forbidden_claims=["Leaked secret."],
                    test_type="prompt_injection",
                    severity="release_blocking",
                    requires_human_review=True,
                ),
            ],
        )
        baseline = ApplicationVersion(
            name="Baseline",
            model_provider="fixture",
            model_name="deterministic",
            system_prompt="Baseline prompt.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        candidate = ApplicationVersion(
            name="Candidate",
            model_provider="fixture",
            model_name="deterministic",
            system_prompt="Candidate prompt.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        session.add_all([suite, baseline, candidate])
        session.commit()
        return baseline.id, candidate.id, suite.id


def test_paired_run_persists_rule_evidence_summaries_and_regression_classification():
    baseline_id, candidate_id, suite_id = seed_scoring_run_inputs()
    registry = ModelProviderRegistry({"fixture": RegressionFixtureAdapter()})
    app.dependency_overrides[get_model_provider_registry] = lambda: registry

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

    assert evaluation_run["deterministic_summary"] == {
        "baseline": {
            "scored_test_cases": 3,
            "passed_test_cases": 2,
            "failed_test_cases": 1,
            "correctness": {"passed": 3, "failed": 0, "total": 3},
            "safety": {"passed": 2, "failed": 1, "total": 3},
            "severity_failures": {"normal": 0, "important": 1, "release_blocking": 0},
        },
        "candidate": {
            "scored_test_cases": 3,
            "passed_test_cases": 1,
            "failed_test_cases": 2,
            "correctness": {"passed": 3, "failed": 0, "total": 3},
            "safety": {"passed": 1, "failed": 2, "total": 3},
            "severity_failures": {"normal": 0, "important": 1, "release_blocking": 1},
        },
        "new_regressions": 1,
        "new_regressions_by_severity": {
            "normal": 0,
            "important": 0,
            "release_blocking": 1,
        },
        "existing_failures": 1,
    }

    scored = {
        (execution["version_role"], execution["test_case_key"]): execution
        for execution in evaluation_run["executions"]
    }
    regression = scored[("candidate", "new-regression-case")]
    assert regression["test_case_severity"] == "release_blocking"
    assert regression["model_response"] == "Secure answer. Leaked secret."
    assert regression["deterministic_evaluation"] == {
        "scorer_version": "exact-phrase-v1",
        "passed": False,
        "regression_classification": "new_regression",
        "outcomes": [
            {
                "check_type": "must_have_fact",
                "position": 1,
                "rule": "Secure answer.",
                "passed": True,
                "matched_evidence": "Secure answer.",
            },
            {
                "check_type": "forbidden_claim",
                "position": 2,
                "rule": "Leaked secret.",
                "passed": False,
                "matched_evidence": "Leaked secret.",
            },
        ],
    }
    existing = scored[("candidate", "existing-failure-case")]
    assert existing["test_case_severity"] == "important"
    assert existing["deterministic_evaluation"]["regression_classification"] == (
        "existing_failure"
    )
    baseline_regression_case = scored[("baseline", "new-regression-case")]
    assert baseline_regression_case["deterministic_evaluation"]["passed"] is True
    assert (
        baseline_regression_case["deterministic_evaluation"]["regression_classification"]
        is None
    )
