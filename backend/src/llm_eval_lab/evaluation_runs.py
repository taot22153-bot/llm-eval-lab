from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from llm_eval_lab.database import SessionLocal, get_session
from llm_eval_lab.deterministic_scoring import classify_candidate_regression
from llm_eval_lab.model_provider import ModelProviderRegistry, get_model_provider_registry
from llm_eval_lab.models import (
    ApplicationVersion,
    DeterministicEvaluation,
    EvaluationRun,
    EvaluationSuite,
    ExternalSafetyEvidence,
    TestCaseExecution,
)
from llm_eval_lab.schemas import EvaluationRunCreate, EvaluationRunRead
from llm_eval_lab.semantic_judging import SemanticJudge, get_semantic_judge
from llm_eval_lab.test_case_executions import (
    new_test_case_execution,
    run_test_case_execution,
    serialize_test_case_execution,
)

router = APIRouter(prefix="/api/evaluation-runs", tags=["evaluation runs"])
DatabaseSession = Annotated[Session, Depends(get_session)]
ProviderRegistry = Annotated[ModelProviderRegistry, Depends(get_model_provider_registry)]
SemanticJudgeDependency = Annotated[SemanticJudge, Depends(get_semantic_judge)]


def _evaluation_run_statement():
    return select(EvaluationRun).options(
        selectinload(EvaluationRun.baseline_version),
        selectinload(EvaluationRun.candidate_version),
        selectinload(EvaluationRun.evaluation_suite),
        selectinload(EvaluationRun.executions).selectinload(
            TestCaseExecution.application_version
        ),
        selectinload(EvaluationRun.executions).selectinload(
            TestCaseExecution.test_case
        ),
        selectinload(EvaluationRun.executions)
        .selectinload(TestCaseExecution.deterministic_evaluation)
        .selectinload(DeterministicEvaluation.outcomes),
        selectinload(EvaluationRun.executions).selectinload(
            TestCaseExecution.semantic_evaluation
        ),
        selectinload(EvaluationRun.executions).selectinload(
            TestCaseExecution.human_review_item
        ),
    )


def load_evaluation_run(session: Session, run_id: str) -> EvaluationRun | None:
    statement = _evaluation_run_statement().where(EvaluationRun.id == run_id)
    return session.scalar(statement)


def load_evaluation_run_for_release(
    session: Session,
    run_id: str,
) -> EvaluationRun | None:
    statement = (
        _evaluation_run_statement()
        .options(
            selectinload(EvaluationRun.external_safety_evidence).defer(
                ExternalSafetyEvidence.canonical_json
            )
        )
        .where(EvaluationRun.id == run_id)
    )
    return session.scalar(statement)


def _progress(executions: list[TestCaseExecution]) -> dict[str, int]:
    counts = Counter(execution.status for execution in executions)
    return {
        "total": len(executions),
        "queued": counts["pending"],
        "running": counts["running"],
        "completed": counts["completed"],
        "failed": counts["failed"],
    }


def _rule_counts(
    executions: list[TestCaseExecution],
    check_type: str,
) -> dict[str, int]:
    outcomes = [
        outcome
        for execution in executions
        if execution.deterministic_evaluation is not None
        for outcome in execution.deterministic_evaluation.outcomes
        if outcome.check_type == check_type
    ]
    passed = sum(outcome.passed for outcome in outcomes)
    return {"passed": passed, "failed": len(outcomes) - passed, "total": len(outcomes)}


def _version_deterministic_summary(
    executions: list[TestCaseExecution],
) -> dict[str, Any]:
    scored = [
        execution
        for execution in executions
        if execution.deterministic_evaluation is not None
    ]
    passed = sum(
        execution.deterministic_evaluation.passed
        for execution in scored
        if execution.deterministic_evaluation is not None
    )
    severity_failures = {"normal": 0, "important": 0, "release_blocking": 0}
    for execution in scored:
        evaluation = execution.deterministic_evaluation
        if evaluation is not None and not evaluation.passed:
            severity_failures[execution.test_case.severity] += 1
    return {
        "scored_test_cases": len(scored),
        "passed_test_cases": passed,
        "failed_test_cases": len(scored) - passed,
        "correctness": _rule_counts(scored, "must_have_fact"),
        "safety": _rule_counts(scored, "forbidden_claim"),
        "severity_failures": severity_failures,
    }


def _deterministic_summary(executions: list[TestCaseExecution]) -> dict[str, Any]:
    baseline = [execution for execution in executions if execution.version_role == "baseline"]
    candidate = [execution for execution in executions if execution.version_role == "candidate"]
    candidate_evaluations = [
        execution.deterministic_evaluation
        for execution in candidate
        if execution.deterministic_evaluation is not None
    ]
    new_regressions_by_severity = {
        "normal": 0,
        "important": 0,
        "release_blocking": 0,
    }
    for execution in candidate:
        evaluation = execution.deterministic_evaluation
        if (
            evaluation is not None
            and evaluation.regression_classification == "new_regression"
        ):
            new_regressions_by_severity[execution.test_case.severity] += 1
    return {
        "baseline": _version_deterministic_summary(baseline),
        "candidate": _version_deterministic_summary(candidate),
        "new_regressions": sum(
            evaluation.regression_classification == "new_regression"
            for evaluation in candidate_evaluations
        ),
        "new_regressions_by_severity": new_regressions_by_severity,
        "existing_failures": sum(
            evaluation.regression_classification == "existing_failure"
            for evaluation in candidate_evaluations
        ),
    }


def _classify_regressions(evaluation_run: EvaluationRun) -> None:
    executions = {
        (execution.test_case_id, execution.version_role): execution
        for execution in evaluation_run.executions
    }
    for test_case_id in {execution.test_case_id for execution in evaluation_run.executions}:
        baseline = executions.get((test_case_id, "baseline"))
        candidate = executions.get((test_case_id, "candidate"))
        if (
            baseline is None
            or candidate is None
            or baseline.deterministic_evaluation is None
            or candidate.deterministic_evaluation is None
        ):
            continue
        candidate.deterministic_evaluation.regression_classification = (
            classify_candidate_regression(
                baseline.deterministic_evaluation.passed,
                candidate.deterministic_evaluation.passed,
            )
        )


def _evaluation_run_payload(evaluation_run: EvaluationRun) -> dict[str, Any]:
    ordered_executions = sorted(
        evaluation_run.executions,
        key=lambda execution: (
            0 if execution.version_role == "baseline" else 1,
            execution.test_case.position,
        ),
    )
    return {
        "id": evaluation_run.id,
        "baseline_version": {
            "id": evaluation_run.baseline_version.id,
            "name": evaluation_run.baseline_version.name,
        },
        "candidate_version": {
            "id": evaluation_run.candidate_version.id,
            "name": evaluation_run.candidate_version.name,
        },
        "evaluation_suite": {
            "id": evaluation_run.evaluation_suite.id,
            "slug": evaluation_run.evaluation_suite.slug,
            "version": evaluation_run.evaluation_suite.version,
            "name": evaluation_run.evaluation_suite.name,
        },
        "status": evaluation_run.status,
        "progress": _progress(ordered_executions),
        "deterministic_summary": _deterministic_summary(ordered_executions),
        "executions": [
            {
                **serialize_test_case_execution(execution),
                "version_role": execution.version_role,
            }
            for execution in ordered_executions
        ],
        "created_at": evaluation_run.created_at,
        "started_at": evaluation_run.started_at,
        "completed_at": evaluation_run.completed_at,
    }


def run_evaluation_run(
    run_id: str,
    provider_registry: ModelProviderRegistry,
    semantic_judge: SemanticJudge,
) -> None:
    with SessionLocal() as session:
        evaluation_run = load_evaluation_run(session, run_id)
        if evaluation_run is None or evaluation_run.status != "pending":
            return
        evaluation_run.status = "running"
        evaluation_run.started_at = datetime.now(UTC)
        execution_ids = [execution.id for execution in evaluation_run.executions]
        session.commit()

    orchestration_failed = False
    for execution_id in execution_ids:
        try:
            run_test_case_execution(execution_id, provider_registry, semantic_judge)
        except Exception:
            orchestration_failed = True
            with SessionLocal() as session:
                execution = session.get(TestCaseExecution, execution_id)
                if execution is not None and execution.status in ("pending", "running"):
                    execution.status = "failed"
                    execution.error = {
                        "code": "execution_orchestration_failure",
                        "message": (
                            "The Evaluation Run could not orchestrate this execution. "
                            "The remaining Test Cases continued."
                        ),
                    }
                    execution.completed_at = datetime.now(UTC)
                    session.commit()

    with SessionLocal() as session:
        evaluation_run = load_evaluation_run(session, run_id)
        if evaluation_run is None:
            return
        _classify_regressions(evaluation_run)
        evaluation_run.status = "failed" if orchestration_failed else "completed"
        evaluation_run.completed_at = datetime.now(UTC)
        session.commit()


def reconcile_interrupted_evaluation_runs() -> None:
    with SessionLocal() as session:
        statement = select(EvaluationRun).where(
            EvaluationRun.status.in_(("pending", "running"))
        )
        interrupted = list(session.scalars(statement))
        if not interrupted:
            return

        completed_at = datetime.now(UTC)
        for evaluation_run in interrupted:
            evaluation_run.status = "failed"
            evaluation_run.completed_at = completed_at
        session.commit()


@router.post("", response_model=EvaluationRunRead, status_code=status.HTTP_201_CREATED)
def create_evaluation_run(
    payload: EvaluationRunCreate,
    background_tasks: BackgroundTasks,
    session: DatabaseSession,
    provider_registry: ProviderRegistry,
    semantic_judge: SemanticJudgeDependency,
) -> dict[str, Any]:
    if payload.baseline_version_id == payload.candidate_version_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Baseline and Candidate must be different Application Versions.",
        )

    baseline = session.get(ApplicationVersion, payload.baseline_version_id)
    candidate = session.get(ApplicationVersion, payload.candidate_version_id)
    suite_statement = (
        select(EvaluationSuite)
        .where(EvaluationSuite.id == payload.evaluation_suite_id)
        .options(selectinload(EvaluationSuite.test_cases))
    )
    suite = session.scalar(suite_statement)
    if baseline is None or candidate is None or suite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected Application Version or Evaluation Suite was not found.",
        )

    evaluation_run = EvaluationRun(
        baseline_version=baseline,
        candidate_version=candidate,
        evaluation_suite=suite,
        status="pending",
    )
    for test_case in suite.test_cases:
        evaluation_run.executions.extend(
            [
                new_test_case_execution(
                    baseline,
                    test_case,
                    version_role="baseline",
                ),
                new_test_case_execution(
                    candidate,
                    test_case,
                    version_role="candidate",
                ),
            ]
        )
    session.add(evaluation_run)
    session.commit()
    evaluation_run = load_evaluation_run(session, evaluation_run.id)
    if evaluation_run is None:
        raise RuntimeError("The Evaluation Run was not persisted.")

    response = _evaluation_run_payload(evaluation_run)
    background_tasks.add_task(
        run_evaluation_run,
        evaluation_run.id,
        provider_registry,
        semantic_judge,
    )
    return response


@router.get("", response_model=list[EvaluationRunRead])
def list_evaluation_runs(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    statement = _evaluation_run_statement().order_by(EvaluationRun.created_at.desc()).limit(limit)
    return [
        _evaluation_run_payload(evaluation_run)
        for evaluation_run in session.scalars(statement)
    ]


@router.get("/{run_id}", response_model=EvaluationRunRead)
def get_evaluation_run(run_id: str, session: DatabaseSession) -> dict[str, Any]:
    evaluation_run = load_evaluation_run(session, run_id)
    if evaluation_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation Run {run_id} was not found.",
        )
    return _evaluation_run_payload(evaluation_run)
