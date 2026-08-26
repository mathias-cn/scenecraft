"""add completed to project_stage

Revision ID: 20260825_0010
Revises: 20260825_0009
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260825_0010"
down_revision: Union[str, None] = "20260825_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE project_stage ADD VALUE IF NOT EXISTS 'completed'")


def downgrade() -> None:
    # Postgres não remove valor de enum; projetos em 'completed' devem ser
    # migrados para 'published' antes de um downgrade completo.
    op.execute(
        "UPDATE projects SET current_stage = 'published' WHERE current_stage = 'completed'"
    )
    op.execute("UPDATE jobs SET stage = 'published' WHERE stage = 'completed'")
