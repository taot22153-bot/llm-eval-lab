"""Create versioned Evaluation Suites and Test Cases.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_suites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", "version", name="uq_suite_slug_version"),
    )
    op.create_table(
        "test_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("grounding_material", sa.JSON(), nullable=False),
        sa.Column("must_have_facts", sa.JSON(), nullable=False),
        sa.Column("forbidden_claims", sa.JSON(), nullable=False),
        sa.Column("test_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "severity IN ('normal', 'important', 'release_blocking')",
            name="ck_test_case_severity",
        ),
        sa.CheckConstraint(
            "test_type IN ('normal', 'hallucination', 'prompt_injection', 'jailbreak')",
            name="ck_test_case_type",
        ),
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["evaluation_suites.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suite_id", "key", name="uq_test_case_suite_key"),
    )


def downgrade() -> None:
    op.drop_table("test_cases")
    op.drop_table("evaluation_suites")
