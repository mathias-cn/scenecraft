"""add text_script to source_type

Revision ID: 20260826_0019
Revises: 20260826_0018
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260826_0019"
down_revision: Union[str, Sequence[str], None] = "20260826_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'text_script'")


def downgrade() -> None:
    # Postgres não remove valores de enum com segurança.
    return
