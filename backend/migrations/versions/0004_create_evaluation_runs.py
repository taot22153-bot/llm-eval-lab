"""Create paired Evaluation Runs.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("baseline_version_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_version_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_suite_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_evaluation_run_status",
        ),
        sa.CheckConstraint(
            "baseline_version_id <> candidate_version_id",
            name="ck_evaluation_run_distinct_versions",
        ),
        sa.ForeignKeyConstraint(
            ["baseline_version_id"],
            ["application_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_version_id"],
            ["application_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_suite_id"],
            ["evaluation_suites.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "test_case_executions",
        sa.Column("evaluation_run_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "test_case_executions",
        sa.Column("version_role", sa.String(length=24), nullable=True),
    )
    op.create_foreign_key(
        "fk_test_case_execution_evaluation_run",
        "test_case_executions",
        "evaluation_runs",
        ["evaluation_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_test_case_execution_version_role",
        "test_case_executions",
        "version_role IS NULL OR version_role IN ('baseline', 'candidate')",
    )
    op.create_check_constraint(
        "ck_test_case_execution_run_role_pair",
        "test_case_executions",
        "(evaluation_run_id IS NULL AND version_role IS NULL) OR "
        "(evaluation_run_id IS NOT NULL AND version_role IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_test_case_execution_run_role_pair",
        "test_case_executions",
        type_="check",
    )
    op.drop_constraint(
        "ck_test_case_execution_version_role",
        "test_case_executions",
        type_="check",
    )
    op.drop_constraint(
        "fk_test_case_execution_evaluation_run",
        "test_case_executions",
        type_="foreignkey",
    )
    op.drop_column("test_case_executions", "version_role")
    op.drop_column("test_case_executions", "evaluation_run_id")
    op.drop_table("evaluation_runs")
