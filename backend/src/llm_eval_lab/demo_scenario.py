from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from llm_eval_lab.database import SessionLocal
from llm_eval_lab.demo_provider import (
    DEMO_BASELINE_MODEL,
    DEMO_CANDIDATE_MODEL,
    DEMO_PROVIDER_NAME,
)
from llm_eval_lab.models import (
    ApplicationVersion,
    EvaluationRun,
    EvaluationSuite,
    ReleaseRule,
    TestCase,
)
from llm_eval_lab.sample_suite import (
    SAMPLE_TEST_CASES,
    seed_default_release_rule,
)

DEMO_BASELINE_ID = "00000000-0000-4000-8000-000000000011"
DEMO_CANDIDATE_ID = "00000000-0000-4000-8000-000000000012"
DEMO_VERSION_IDS = (DEMO_BASELINE_ID, DEMO_CANDIDATE_ID)
DEMO_SUITE_ID = "00000000-0000-4000-8000-000000000021"
DEMO_SUITE_SLUG = "demo-northstar-interview"
DEMO_SUITE_VERSION = 1


@dataclass(frozen=True)
class DemoScenario:
    baseline: ApplicationVersion
    candidate: ApplicationVersion
    suite: EvaluationSuite
    rule: ReleaseRule


def _new_demo_versions() -> tuple[ApplicationVersion, ApplicationVersion]:
    baseline = ApplicationVersion(
        id=DEMO_BASELINE_ID,
        name="Northstar demo Baseline (deterministic fixture)",
        model_provider=DEMO_PROVIDER_NAME,
        model_name=DEMO_BASELINE_MODEL,
        system_prompt=(
            "DEMO FIXTURE: answer only with the supplied Northstar policy evidence."
        ),
        generation_parameters={"temperature": 0},
        knowledge_config={"source": "northstar-electronics-support-v1"},
        tool_config=None,
    )
    candidate = ApplicationVersion(
        id=DEMO_CANDIDATE_ID,
        name="Northstar demo Candidate (known safety regression)",
        model_provider=DEMO_PROVIDER_NAME,
        model_name=DEMO_CANDIDATE_MODEL,
        system_prompt=(
            "DEMO FIXTURE: candidate prompt with one intentional prompt-injection "
            "safety regression."
        ),
        generation_parameters={"temperature": 0},
        knowledge_config={"source": "northstar-electronics-support-v1"},
        tool_config=None,
    )
    return baseline, candidate


def seed_demo_evaluation_suite(session: Session) -> EvaluationSuite:
    existing = session.get(EvaluationSuite, DEMO_SUITE_ID)
    if existing is not None:
        return existing

    regression_case = next(
        test_case
        for test_case in SAMPLE_TEST_CASES
        if test_case["key"] == "prompt-injection-system-prompt"
    )
    suite = EvaluationSuite(
        id=DEMO_SUITE_ID,
        slug=DEMO_SUITE_SLUG,
        version=DEMO_SUITE_VERSION,
        name="Northstar Interview Demo",
        description=(
            "One deterministic release-blocking regression for the five-minute demo."
        ),
        test_cases=[
            TestCase(
                **{
                    **regression_case,
                    "position": 1,
                    "requires_human_review": False,
                }
            )
        ],
    )
    session.add(suite)
    session.commit()
    session.refresh(suite)
    return suite


def reset_demo_scenario(session: Session) -> DemoScenario:
    """Reset only run evidence owned by the exact fixed demo-version pair."""

    suite = seed_demo_evaluation_suite(session)
    rule = seed_default_release_rule(session)

    session.execute(
        delete(EvaluationRun).where(
            EvaluationRun.baseline_version_id == DEMO_BASELINE_ID,
            EvaluationRun.candidate_version_id == DEMO_CANDIDATE_ID,
        )
    )
    versions = {
        version.id: version
        for version in session.scalars(
            select(ApplicationVersion).where(ApplicationVersion.id.in_(DEMO_VERSION_IDS))
        )
    }
    new_baseline, new_candidate = _new_demo_versions()
    baseline = versions.get(DEMO_BASELINE_ID, new_baseline)
    candidate = versions.get(DEMO_CANDIDATE_ID, new_candidate)
    if baseline is new_baseline:
        session.add(baseline)
    if candidate is new_candidate:
        session.add(candidate)
    session.commit()
    return DemoScenario(
        baseline=baseline,
        candidate=candidate,
        suite=suite,
        rule=rule,
    )


def load_demo_scenario(session: Session) -> DemoScenario | None:
    versions = {
        version.id: version
        for version in session.scalars(
            select(ApplicationVersion).where(ApplicationVersion.id.in_(DEMO_VERSION_IDS))
        )
    }
    if set(versions) != set(DEMO_VERSION_IDS):
        return None
    suite = seed_demo_evaluation_suite(session)
    rule = seed_default_release_rule(session)
    return DemoScenario(
        baseline=versions[DEMO_BASELINE_ID],
        candidate=versions[DEMO_CANDIDATE_ID],
        suite=suite,
        rule=rule,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the reserved offline demo scenario.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Ensure the fixed-ID demo versions and clear run evidence where that exact "
            "version pair is used together."
        ),
    )
    args = parser.parse_args()
    with SessionLocal() as session:
        scenario = (
            reset_demo_scenario(session)
            if args.reset
            else load_demo_scenario(session) or reset_demo_scenario(session)
        )
        print("Offline deterministic demo scenario ready.")
        print(f"Baseline: {scenario.baseline.name}")
        print(f"Candidate: {scenario.candidate.name}")
        print(f"Evaluation Suite: {scenario.suite.name} v{scenario.suite.version}")
        print(f"Release Rule: {scenario.rule.name} v{scenario.rule.version}")


if __name__ == "__main__":
    main()
