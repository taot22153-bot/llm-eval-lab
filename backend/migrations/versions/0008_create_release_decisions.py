"""Create versioned Release Rules and reproducible Release Decisions.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "release_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("blocking_severities", sa.JSON(), nullable=False),
        sa.Column("new_regression_severities", sa.JSON(), nullable=False),
        sa.Column("require_resolved_reviews", sa.Boolean(), nullable=False),
        sa.Column("maximum_correctness_drop", sa.Float(), nullable=False),
        sa.Column("minimum_candidate_safety_rate", sa.Float(), nullable=False),
        sa.Column(
            "maximum_candidate_average_latency_ms",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "maximum_candidate_total_cost_usd",
            sa.Float(),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_release_rule_version"),
        sa.CheckConstraint(
            "maximum_correctness_drop >= 0 AND maximum_correctness_drop <= 1",
            name="ck_release_rule_correctness_drop",
        ),
        sa.CheckConstraint(
            "minimum_candidate_safety_rate >= 0 "
            "AND minimum_candidate_safety_rate <= 1",
            name="ck_release_rule_safety_rate",
        ),
        sa.CheckConstraint(
            "maximum_candidate_average_latency_ms IS NULL "
            "OR maximum_candidate_average_latency_ms >= 0",
            name="ck_release_rule_latency_budget",
        ),
        sa.CheckConstraint(
            "maximum_candidate_total_cost_usd IS NULL "
            "OR maximum_candidate_total_cost_usd >= 0",
            name="ck_release_rule_cost_budget",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "slug",
            "version",
            name="uq_release_rule_slug_version",
        ),
    )
    op.create_table(
        "release_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_run_id", sa.String(length=36), nullable=False),
        sa.Column("release_rule_id", sa.String(length=36), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('pass', 'fail', 'manual_review_required')",
            name="ck_release_decision_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["release_rule_id"],
            ["release_rules.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "release_rule_id",
            "evidence_fingerprint",
            name="uq_release_decision_evidence",
        ),
    )


def downgrade() -> None:
    op.drop_table("release_decisions")
    op.drop_table("release_rules")
