"""Create immutable External Safety Evidence.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_safety_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_product", sa.String(length=80), nullable=False),
        sa.Column("integration_contract", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("source_bundle_id", sa.String(length=160), nullable=False),
        sa.Column("source_pair_id", sa.String(length=80), nullable=False),
        sa.Column("baseline_agent_version_id", sa.String(length=160), nullable=False),
        sa.Column("candidate_agent_version_id", sa.String(length=160), nullable=False),
        sa.Column("baseline_evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("candidate_evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("baseline_verdict", sa.String(length=24), nullable=False),
        sa.Column("candidate_verdict", sa.String(length=24), nullable=False),
        sa.Column("divergence_summary", sa.Text(), nullable=False),
        sa.Column("canonical_json", mysql.LONGTEXT(), nullable=False),
        sa.Column("imported_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "baseline_verdict IN ('effective', 'ineffective', 'inconclusive')",
            name="ck_external_safety_evidence_baseline_verdict",
        ),
        sa.CheckConstraint(
            "candidate_verdict IN ('effective', 'ineffective', 'inconclusive')",
            name="ck_external_safety_evidence_candidate_verdict",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "source_digest",
            name="uq_external_safety_evidence_run_digest",
        ),
    )


def downgrade() -> None:
    op.drop_table("external_safety_evidence")
