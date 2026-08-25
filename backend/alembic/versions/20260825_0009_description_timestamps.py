"""add created_at/updated_at to descriptions

Revision ID: 20260825_0009
Revises: 20260825_0008
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0009"
down_revision: Union[str, None] = "20260825_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "descriptions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "descriptions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("descriptions", "updated_at")
    op.drop_column("descriptions", "created_at")
