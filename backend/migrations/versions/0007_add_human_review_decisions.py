"""Add auditable Human Review decisions.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "human_review_items",
        sa.Column("outcome", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "human_review_items",
        sa.Column("rationale", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_human_review_item_outcome",
        "human_review_items",
        "outcome IS NULL OR outcome IN ('pass', 'fail')",
    )
    op.create_check_constraint(
        "ck_human_review_item_decision_state",
        "human_review_items",
        "(status = 'pending' AND outcome IS NULL AND rationale IS NULL "
        "AND resolved_at IS NULL) OR "
        "(status = 'resolved' AND outcome IS NOT NULL AND rationale IS NOT NULL "
        "AND resolved_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_human_review_item_decision_state",
        "human_review_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_human_review_item_outcome",
        "human_review_items",
        type_="check",
    )
    op.drop_column("human_review_items", "rationale")
    op.drop_column("human_review_items", "outcome")
