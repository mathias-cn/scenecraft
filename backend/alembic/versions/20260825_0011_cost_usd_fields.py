"""add cost_usd on audio/descriptions/thumbnails and project llm_cost_usd

Revision ID: 20260825_0011
Revises: 20260825_0010
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0011"
down_revision: Union[str, None] = "20260825_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COST = sa.Numeric(precision=12, scale=6)


def upgrade() -> None:
    op.add_column("audio_tracks", sa.Column("cost_usd", _COST, nullable=True))
    op.add_column("descriptions", sa.Column("cost_usd", _COST, nullable=True))
    op.add_column("thumbnails", sa.Column("cost_usd", _COST, nullable=True))
    op.add_column("projects", sa.Column("llm_cost_usd", _COST, nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "llm_cost_usd")
    op.drop_column("thumbnails", "cost_usd")
    op.drop_column("descriptions", "cost_usd")
    op.drop_column("audio_tracks", "cost_usd")
