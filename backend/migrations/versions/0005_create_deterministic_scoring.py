"""Create versioned deterministic scoring evidence.

Revision ID: 0005
Revises: 0004
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _matched_evidence(response: str, rule: str) -> str | None:
    match = re.search(re.escape(rule), response, flags=re.IGNORECASE)
    return match.group(0) if match is not None else None


def _backfill_existing_scores() -> None:
    connection = op.get_bind()
    executions = sa.table(
        "test_case_executions",
        sa.column("id", sa.String(length=36)),
        sa.column("test_case_id", sa.String(length=36)),
        sa.column("evaluation_run_id", sa.String(length=36)),
        sa.column("version_role", sa.String(length=24)),
        sa.column("status", sa.String(length=24)),
        sa.column("model_response", sa.Text()),
        sa.column("completed_at", sa.DateTime(timezone=True)),
    )
    test_cases = sa.table(
        "test_cases",
        sa.column("id", sa.String(length=36)),
        sa.column("must_have_facts", sa.JSON()),
        sa.column("forbidden_claims", sa.JSON()),
    )
    evaluations = sa.table(
        "deterministic_evaluations",
        sa.column("id", sa.String(length=36)),
        sa.column("test_case_execution_id", sa.String(length=36)),
        sa.column("scorer_version", sa.String(length=80)),
        sa.column("passed", sa.Boolean()),
        sa.column("regression_classification", sa.String(length=40)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    outcomes = sa.table(
        "deterministic_check_outcomes",
        sa.column("id", sa.String(length=36)),
        sa.column("deterministic_evaluation_id", sa.String(length=36)),
        sa.column("check_type", sa.String(length=40)),
        sa.column("position", sa.Integer()),
        sa.column("rule", sa.Text()),
        sa.column("passed", sa.Boolean()),
        sa.column("matched_evidence", sa.Text()),
    )
    rows = list(
        connection.execute(
            sa.select(
                executions.c.id.label("execution_id"),
                executions.c.test_case_id,
                executions.c.evaluation_run_id,
                executions.c.version_role,
                executions.c.model_response,
                executions.c.completed_at,
                test_cases.c.must_have_facts,
                test_cases.c.forbidden_claims,
            )
            .join(test_cases, test_cases.c.id == executions.c.test_case_id)
            .where(
                executions.c.status == "completed",
                executions.c.model_response.is_not(None),
            )
        ).mappings()
    )

    scores_by_execution: dict[str, tuple[str, bool]] = {}
    paired_executions: dict[tuple[str, str, str], str] = {}
    for row in rows:
        execution_id = row["execution_id"]
        response = row["model_response"]
        evaluation_id = str(uuid4())
        outcome_values: list[dict[str, object]] = []
        rules = [
            ("must_have_fact", rule)
            for rule in list(row["must_have_facts"] or [])
        ] + [
            ("forbidden_claim", rule)
            for rule in list(row["forbidden_claims"] or [])
        ]
        for position, (check_type, rule) in enumerate(rules, start=1):
            evidence = _matched_evidence(response, rule)
            passed = (
                evidence is not None
                if check_type == "must_have_fact"
                else evidence is None
            )
            outcome_values.append(
                {
                    "id": str(uuid4()),
                    "deterministic_evaluation_id": evaluation_id,
                    "check_type": check_type,
                    "position": position,
                    "rule": rule,
                    "passed": passed,
                    "matched_evidence": evidence,
                }
            )
        score_passed = all(outcome["passed"] for outcome in outcome_values)
        connection.execute(
            evaluations.insert().values(
                id=evaluation_id,
                test_case_execution_id=execution_id,
                scorer_version="exact-phrase-v1",
                passed=score_passed,
                regression_classification=None,
                created_at=row["completed_at"] or datetime.now(UTC),
            )
        )
        if outcome_values:
            connection.execute(outcomes.insert(), outcome_values)
        scores_by_execution[execution_id] = (evaluation_id, score_passed)
        if row["evaluation_run_id"] is not None and row["version_role"] is not None:
            paired_executions[
                (
                    row["evaluation_run_id"],
                    row["test_case_id"],
                    row["version_role"],
                )
            ] = execution_id

    for (run_id, test_case_id, role), candidate_execution_id in paired_executions.items():
        if role != "candidate":
            continue
        baseline_execution_id = paired_executions.get(
            (run_id, test_case_id, "baseline")
        )
        if baseline_execution_id is None:
            continue
        candidate_evaluation_id, candidate_passed = scores_by_execution[
            candidate_execution_id
        ]
        _, baseline_passed = scores_by_execution[baseline_execution_id]
        if candidate_passed:
            continue
        classification = "new_regression" if baseline_passed else "existing_failure"
        connection.execute(
            evaluations.update()
            .where(evaluations.c.id == candidate_evaluation_id)
            .values(regression_classification=classification)
        )


def upgrade() -> None:
    op.create_table(
        "deterministic_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("test_case_execution_id", sa.String(length=36), nullable=False),
        sa.Column("scorer_version", sa.String(length=80), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("regression_classification", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "regression_classification IS NULL OR "
            "regression_classification IN ('new_regression', 'existing_failure')",
            name="ck_deterministic_evaluation_regression",
        ),
        sa.ForeignKeyConstraint(
            ["test_case_execution_id"],
            ["test_case_executions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "test_case_execution_id",
            name="uq_deterministic_evaluation_execution",
        ),
    )
    op.create_table(
        "deterministic_check_outcomes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deterministic_evaluation_id", sa.String(length=36), nullable=False),
        sa.Column("check_type", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("matched_evidence", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "check_type IN ('must_have_fact', 'forbidden_claim')",
            name="ck_deterministic_outcome_type",
        ),
        sa.ForeignKeyConstraint(
            ["deterministic_evaluation_id"],
            ["deterministic_evaluations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "deterministic_evaluation_id",
            "position",
            name="uq_deterministic_outcome_position",
        ),
    )
    _backfill_existing_scores()


def downgrade() -> None:
    op.drop_table("deterministic_check_outcomes")
    op.drop_table("deterministic_evaluations")
