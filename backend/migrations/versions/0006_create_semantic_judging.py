"""Create semantic judgments and Human Review queue items.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("test_case_execution_id", sa.String(length=36), nullable=False),
        sa.Column("judge_version", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("judge_configuration", sa.JSON(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('pass', 'fail', 'insufficient_evidence')",
            name="ck_semantic_evaluation_outcome",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_semantic_evaluation_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["test_case_execution_id"],
            ["test_case_executions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "test_case_execution_id",
            name="uq_semantic_evaluation_execution",
        ),
    )
    op.create_table(
        "human_review_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("test_case_execution_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'resolved')",
            name="ck_human_review_item_status",
        ),
        sa.ForeignKeyConstraint(
            ["test_case_execution_id"],
            ["test_case_executions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "test_case_execution_id",
            name="uq_human_review_item_execution",
        ),
    )


def downgrade() -> None:
    op.drop_table("human_review_items")
    op.drop_table("semantic_evaluations")
