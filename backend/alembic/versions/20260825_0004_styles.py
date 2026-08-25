"""styles table and seed of scene visual styles

Revision ID: 20260825_0004
Revises: 20260825_0003
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0004"
down_revision: Union[str, None] = "20260825_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_STYLES: tuple[tuple[str, str], ...] = (
    ("Fotorrealista", "fotorrealista"),
    ("Ilustração digital", "ilustracao-digital"),
    ("Anime", "anime"),
)


def upgrade() -> None:
    op.create_table(
        "styles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_styles_slug"),
    )
    styles = sa.table(
        "styles",
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        styles,
        [{"name": name, "slug": slug, "active": True} for name, slug in SEED_STYLES],
    )


def downgrade() -> None:
    op.drop_table("styles")
