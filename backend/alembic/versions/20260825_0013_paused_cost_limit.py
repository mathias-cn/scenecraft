"""add paused_cost_limit to project_status

Revision ID: 20260825_0013
Revises: 20260825_0012
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260825_0013"
down_revision: Union[str, None] = "20260825_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE project_status ADD VALUE IF NOT EXISTS 'paused_cost_limit'")


def downgrade() -> None:
    op.execute(
        "UPDATE projects SET status = 'paused_for_review' WHERE status = 'paused_cost_limit'"
    )
