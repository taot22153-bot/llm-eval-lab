from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from llm_eval_lab.models import (
    EvaluationRun,
    ExternalSafetyEvidence,
    ReleaseRule,
    TestCaseExecution,
)


@dataclass(frozen=True)
class ReleaseDecisionResult:
    outcome: str
    reasons: list[dict[str, Any]]
    metrics: dict[str, Any]
    evidence_fingerprint: str


def _executions(evaluation_run: EvaluationRun, role: str) -> list[TestCaseExecution]:
    return [
        execution
        for execution in evaluation_run.executions
        if execution.version_role == role
    ]


def _deterministic_rule_rate(
    executions: list[TestCaseExecution],
    check_type: str,
) -> float:
    outcomes: list[bool] = []
    for execution in executions:
        evaluation = execution.deterministic_evaluation
        if evaluation is None:
            continue
        for outcome in evaluation.outcomes:
            if outcome.check_type != check_type:
                continue
            outcomes.append(outcome.passed)
    if not outcomes:
        return 1.0
    return sum(outcomes) / len(outcomes)


def _average_latency(executions: list[TestCaseExecution]) -> float | None:
    values = [execution.latency_ms for execution in executions]
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None) / len(values)


def _total_cost(executions: list[TestCaseExecution]) -> float | None:
    values = [
        execution.usage.get("cost_usd") if execution.usage is not None else None
        for execution in executions
    ]
    if not values or any(not isinstance(value, (int, float)) for value in values):
        return None
    return round(sum(float(value) for value in values), 6)


def _status(observed: float | None, threshold: float | int | None, passes: bool) -> str:
    if threshold is None:
        return "not_configured"
    if observed is None:
        return "unavailable"
    return "pass" if passes else "fail"


def _external_safety_record(evidence: ExternalSafetyEvidence) -> dict[str, Any]:
    return {
        "id": evidence.id,
        "source_product": evidence.source_product,
        "integration_contract": evidence.integration_contract,
        "schema_version": evidence.schema_version,
        "source_digest": evidence.source_digest,
        "source_bundle_id": evidence.source_bundle_id,
        "source_pair_id": evidence.source_pair_id,
        "baseline_agent_version_id": evidence.baseline_agent_version_id,
        "candidate_agent_version_id": evidence.candidate_agent_version_id,
        "baseline_evidence_fingerprint": evidence.baseline_evidence_fingerprint,
        "candidate_evidence_fingerprint": evidence.candidate_evidence_fingerprint,
        "baseline_verdict": evidence.baseline_verdict,
        "candidate_verdict": evidence.candidate_verdict,
        "divergence_summary": evidence.divergence_summary,
    }


def _external_safety_metric(evaluation_run: EvaluationRun) -> dict[str, Any]:
    records = [
        _external_safety_record(evidence)
        for evidence in sorted(
            evaluation_run.external_safety_evidence,
            key=lambda item: (item.source_digest, item.id),
        )
    ]
    verdicts = {record["candidate_verdict"] for record in records}
    if "ineffective" in verdicts:
        metric_status = "fail"
    elif "inconclusive" in verdicts:
        metric_status = "manual_review_required"
    elif records:
        metric_status = "pass"
    else:
        metric_status = "not_present"
    return {
        "status": metric_status,
        "record_count": len(records),
        "records": records,
    }


def _evidence_fingerprint(evaluation_run: EvaluationRun, release_rule: ReleaseRule) -> str:
    snapshot = {
        "evaluation_run_id": evaluation_run.id,
        "evaluation_run_status": evaluation_run.status,
        "release_rule": {
            "id": release_rule.id,
            "slug": release_rule.slug,
            "version": release_rule.version,
            "name": release_rule.name,
            "blocking_severities": release_rule.blocking_severities,
            "new_regression_severities": release_rule.new_regression_severities,
            "require_resolved_reviews": release_rule.require_resolved_reviews,
            "maximum_correctness_drop": release_rule.maximum_correctness_drop,
            "minimum_candidate_safety_rate": release_rule.minimum_candidate_safety_rate,
            "maximum_candidate_average_latency_ms": (
                release_rule.maximum_candidate_average_latency_ms
            ),
            "maximum_candidate_total_cost_usd": (
                release_rule.maximum_candidate_total_cost_usd
            ),
        },
        "executions": [
            {
                "id": execution.id,
                "role": execution.version_role,
                "status": execution.status,
                "test_case": {
                    "id": execution.test_case.id,
                    "key": execution.test_case.key,
                    "title": execution.test_case.title,
                    "severity": execution.test_case.severity,
                },
                "model_response": execution.model_response,
                "latency_ms": execution.latency_ms,
                "error": execution.error,
                "cost_usd": (
                    execution.usage.get("cost_usd")
                    if execution.usage is not None
                    else None
                ),
                "deterministic": (
                    {
                        "scorer_version": (
                            execution.deterministic_evaluation.scorer_version
                        ),
                        "passed": execution.deterministic_evaluation.passed,
                        "regression_classification": (
                            execution.deterministic_evaluation.regression_classification
                        ),
                        "outcomes": [
                            {
                                "type": outcome.check_type,
                                "position": outcome.position,
                                "rule": outcome.rule,
                                "passed": outcome.passed,
                                "matched_evidence": outcome.matched_evidence,
                            }
                            for outcome in execution.deterministic_evaluation.outcomes
                        ],
                    }
                    if execution.deterministic_evaluation is not None
                    else None
                ),
                "semantic": (
                    {
                        "judge_version": execution.semantic_evaluation.judge_version,
                        "outcome": execution.semantic_evaluation.outcome,
                        "rationale": execution.semantic_evaluation.rationale,
                        "confidence": execution.semantic_evaluation.confidence,
                        "judge_configuration": (
                            execution.semantic_evaluation.judge_configuration
                        ),
                        "error": execution.semantic_evaluation.error,
                    }
                    if execution.semantic_evaluation is not None
                    else None
                ),
                "human_review": (
                    {
                        "status": execution.human_review_item.status,
                        "reasons": execution.human_review_item.reasons,
                        "outcome": execution.human_review_item.outcome,
                        "rationale": execution.human_review_item.rationale,
                    }
                    if execution.human_review_item is not None
                    else None
                ),
            }
            for execution in sorted(
                evaluation_run.executions,
                key=lambda item: (
                    item.version_role or "",
                    item.test_case.position,
                    item.id,
                ),
            )
        ],
    }
    external_safety = _external_safety_metric(evaluation_run)
    if external_safety["records"]:
        snapshot["external_safety"] = external_safety
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def evaluate_release(
    evaluation_run: EvaluationRun,
    release_rule: ReleaseRule,
) -> ReleaseDecisionResult:
    baseline = _executions(evaluation_run, "baseline")
    candidate = _executions(evaluation_run, "candidate")
    baseline_correctness = _deterministic_rule_rate(baseline, "must_have_fact")
    candidate_correctness = _deterministic_rule_rate(candidate, "must_have_fact")
    correctness_delta = candidate_correctness - baseline_correctness
    baseline_safety = _deterministic_rule_rate(baseline, "forbidden_claim")
    candidate_safety = _deterministic_rule_rate(candidate, "forbidden_claim")
    baseline_latency = _average_latency(baseline)
    candidate_latency = _average_latency(candidate)
    baseline_cost = _total_cost(baseline)
    candidate_cost = _total_cost(candidate)

    metrics = {
        "correctness": {
            "baseline_rate": baseline_correctness,
            "candidate_rate": candidate_correctness,
            "delta": correctness_delta,
            "maximum_drop": release_rule.maximum_correctness_drop,
            "status": (
                "pass"
                if correctness_delta >= -release_rule.maximum_correctness_drop
                else "fail"
            ),
        },
        "safety": {
            "baseline_rate": baseline_safety,
            "candidate_rate": candidate_safety,
            "minimum_candidate_rate": release_rule.minimum_candidate_safety_rate,
            "status": (
                "pass"
                if candidate_safety >= release_rule.minimum_candidate_safety_rate
                else "fail"
            ),
        },
        "latency": {
            "baseline_average_ms": baseline_latency,
            "candidate_average_ms": candidate_latency,
            "maximum_candidate_average_ms": (
                release_rule.maximum_candidate_average_latency_ms
            ),
            "status": _status(
                candidate_latency,
                release_rule.maximum_candidate_average_latency_ms,
                release_rule.maximum_candidate_average_latency_ms is None
                or (
                    candidate_latency is not None
                    and candidate_latency
                    <= release_rule.maximum_candidate_average_latency_ms
                ),
            ),
        },
        "cost": {
            "baseline_total_usd": baseline_cost,
            "candidate_total_usd": candidate_cost,
            "maximum_candidate_total_usd": (
                release_rule.maximum_candidate_total_cost_usd
            ),
            "status": _status(
                candidate_cost,
                release_rule.maximum_candidate_total_cost_usd,
                release_rule.maximum_candidate_total_cost_usd is None
                or (
                    candidate_cost is not None
                    and candidate_cost <= release_rule.maximum_candidate_total_cost_usd
                ),
            ),
        },
        "external_safety": _external_safety_metric(evaluation_run),
    }
    ineffective_evidence_ids = [
        record["id"]
        for record in metrics["external_safety"]["records"]
        if record["candidate_verdict"] == "ineffective"
    ]
    failure_reasons: list[dict[str, Any]] = []
    if ineffective_evidence_ids:
        failure_reasons.append(
            {
                "code": "external_safety_evidence_ineffective",
                "message": "External Safety Evidence found an ineffective Candidate.",
                "execution_ids": [],
                "observed": ineffective_evidence_ids,
                "threshold": "effective",
            }
        )
    for execution in candidate:
        severity = execution.test_case.severity
        review = execution.human_review_item
        review_failed = (
            review is not None
            and review.status == "resolved"
            and review.outcome == "fail"
        )
        if review_failed:
            failure_reasons.append(
                {
                    "code": "human_review_failure",
                    "message": (
                        f"{execution.test_case.title} failed Human Review."
                    ),
                    "execution_ids": [execution.id],
                    "observed": "fail",
                    "threshold": "pass",
                }
            )
        evaluation = execution.deterministic_evaluation
        deterministic_failed = evaluation is not None and not evaluation.passed
        if (deterministic_failed or review_failed) and (
            severity == "release_blocking"
            or severity in release_rule.blocking_severities
        ):
            failure_reasons.append(
                {
                    "code": "release_blocking_failure",
                    "message": (
                        f"{execution.test_case.title} failed at a blocking severity."
                    ),
                    "execution_ids": [execution.id],
                    "observed": severity,
                    "threshold": release_rule.blocking_severities,
                }
            )
        if (
            deterministic_failed
            and evaluation is not None
            and evaluation.regression_classification == "new_regression"
            and (
                severity == "important"
                or severity in release_rule.new_regression_severities
            )
        ):
            failure_reasons.append(
                {
                    "code": "new_important_regression",
                    "message": (
                        f"{execution.test_case.title} is a new {severity} regression."
                    ),
                    "execution_ids": [execution.id],
                    "observed": severity,
                    "threshold": release_rule.new_regression_severities,
                }
            )
    if failure_reasons:
        return ReleaseDecisionResult(
            outcome="fail",
            reasons=failure_reasons,
            metrics=metrics,
            evidence_fingerprint=_evidence_fingerprint(evaluation_run, release_rule),
        )
    candidate_execution_ids = [execution.id for execution in candidate]
    budget_failure_reasons: list[dict[str, Any]] = []
    if metrics["latency"]["status"] == "fail":
        budget_failure_reasons.append(
            {
                "code": "latency_budget_exceeded",
                "message": "Candidate average latency exceeds the configured budget.",
                "execution_ids": candidate_execution_ids,
                "observed": candidate_latency,
                "threshold": release_rule.maximum_candidate_average_latency_ms,
            }
        )
    if metrics["cost"]["status"] == "fail":
        budget_failure_reasons.append(
            {
                "code": "cost_budget_exceeded",
                "message": "Candidate total cost exceeds the configured budget.",
                "execution_ids": candidate_execution_ids,
                "observed": candidate_cost,
                "threshold": release_rule.maximum_candidate_total_cost_usd,
            }
        )
    if budget_failure_reasons:
        return ReleaseDecisionResult(
            outcome="fail",
            reasons=budget_failure_reasons,
            metrics=metrics,
            evidence_fingerprint=_evidence_fingerprint(evaluation_run, release_rule),
        )
    manual_review_reasons: list[dict[str, Any]] = []
    inconclusive_evidence_ids = [
        record["id"]
        for record in metrics["external_safety"]["records"]
        if record["candidate_verdict"] == "inconclusive"
    ]
    if inconclusive_evidence_ids:
        manual_review_reasons.append(
            {
                "code": "external_safety_evidence_inconclusive",
                "message": "External Safety Evidence is inconclusive.",
                "execution_ids": [],
                "observed": inconclusive_evidence_ids,
                "threshold": "effective",
            }
        )
    for execution in evaluation_run.executions:
        if (
            execution.status == "completed"
            and execution.deterministic_evaluation is not None
        ):
            continue
        manual_review_reasons.append(
            {
                "code": "evaluation_evidence_unavailable",
                "message": (
                    f"{execution.test_case.title} has no completed, scored "
                    f"{execution.version_role} evidence."
                ),
                "execution_ids": [execution.id],
                "observed": (
                    execution.status
                    if execution.status != "completed"
                    else "unscored"
                ),
                "threshold": "completed_and_scored",
            }
        )
    if metrics["latency"]["status"] == "unavailable":
        manual_review_reasons.append(
            {
                "code": "latency_metric_unavailable",
                "message": "Candidate latency evidence is unavailable.",
                "execution_ids": candidate_execution_ids,
                "observed": None,
                "threshold": release_rule.maximum_candidate_average_latency_ms,
            }
        )
    if metrics["cost"]["status"] == "unavailable":
        manual_review_reasons.append(
            {
                "code": "cost_metric_unavailable",
                "message": "Candidate cost evidence is unavailable.",
                "execution_ids": candidate_execution_ids,
                "observed": None,
                "threshold": release_rule.maximum_candidate_total_cost_usd,
            }
        )
    if release_rule.require_resolved_reviews:
        manual_review_reasons.extend(
            {
                "code": "unresolved_human_review",
                "message": (
                    f"{execution.test_case.title} requires Human Review."
                ),
                "execution_ids": [execution.id],
                "observed": "pending",
                "threshold": "resolved",
            }
            for execution in candidate
            if execution.human_review_item is not None
            and execution.human_review_item.status == "pending"
        )
    if manual_review_reasons:
        return ReleaseDecisionResult(
            outcome="manual_review_required",
            reasons=manual_review_reasons,
            metrics=metrics,
            evidence_fingerprint=_evidence_fingerprint(
                evaluation_run,
                release_rule,
            ),
        )
    quality_failure_reasons: list[dict[str, Any]] = []
    if metrics["correctness"]["status"] == "fail":
        quality_failure_reasons.append(
            {
                "code": "correctness_drop_exceeded",
                "message": "Candidate correctness drop exceeds the configured limit.",
                "execution_ids": candidate_execution_ids,
                "observed": baseline_correctness - candidate_correctness,
                "threshold": release_rule.maximum_correctness_drop,
            }
        )
    if metrics["safety"]["status"] == "fail":
        quality_failure_reasons.append(
            {
                "code": "candidate_safety_below_minimum",
                "message": "Candidate safety rate is below the configured minimum.",
                "execution_ids": candidate_execution_ids,
                "observed": candidate_safety,
                "threshold": release_rule.minimum_candidate_safety_rate,
            }
        )
    if quality_failure_reasons:
        return ReleaseDecisionResult(
            outcome="fail",
            reasons=quality_failure_reasons,
            metrics=metrics,
            evidence_fingerprint=_evidence_fingerprint(evaluation_run, release_rule),
        )
    return ReleaseDecisionResult(
        outcome="pass",
        reasons=[
            {
                "code": "all_release_conditions_passed",
                "message": "All configured release conditions passed.",
                "execution_ids": [],
                "observed": None,
                "threshold": None,
            }
        ],
        metrics=metrics,
        evidence_fingerprint=_evidence_fingerprint(evaluation_run, release_rule),
    )
