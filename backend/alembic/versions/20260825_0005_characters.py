"""characters and character_assets

Revision ID: 20260825_0005
Revises: 20260825_0004
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0005"
down_revision: Union[str, None] = "20260825_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS: dict[str, tuple[str, ...]] = {
    "character_status": ("pending_approval", "approved", "rejected"),
    "character_asset_type": (
        "tpose_side",
        "tpose_back",
        "head_front",
        "head_side",
        "head_back",
        "sitting",
        "holding_mug",
        "smiling",
        "angry",
    ),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "characters",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("description_prompt", sa.Text(), nullable=False),
        sa.Column("style_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_image_url", sa.Text(), nullable=True),
        sa.Column("base_image_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum("character_status"),
            server_default=sa.text("'pending_approval'::character_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["style_id"], ["styles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_characters_style_id", "characters", ["style_id"])
    op.create_index("ix_characters_status", "characters", ["status"])

    op.create_table(
        "character_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("character_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_type", _enum("character_asset_type"), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "asset_type", name="uq_character_assets_character_type"),
    )
    op.create_index("ix_character_assets_character_id", "character_assets", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_character_assets_character_id", table_name="character_assets")
    op.drop_table("character_assets")
    op.drop_index("ix_characters_status", table_name="characters")
    op.drop_index("ix_characters_style_id", table_name="characters")
    op.drop_table("characters")
    bind = op.get_bind()
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
