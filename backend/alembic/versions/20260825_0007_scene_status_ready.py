"""add ready to scene_status

Revision ID: 20260825_0007
Revises: 20260825_0006
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260825_0007"
down_revision: Union[str, None] = "20260825_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE scene_status ADD VALUE IF NOT EXISTS 'ready'")


def downgrade() -> None:
    # Postgres não remove valores de enum com segurança.
    return
