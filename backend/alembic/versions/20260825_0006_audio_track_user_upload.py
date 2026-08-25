"""add user_upload to audio_track_source

Revision ID: 20260825_0006
Revises: 20260825_0005
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260825_0006"
down_revision: Union[str, None] = "20260825_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audio_track_source ADD VALUE IF NOT EXISTS 'user_upload'")


def downgrade() -> None:
    # Postgres não remove valores de enum com segurança; faixas user_upload devem ser apagadas antes.
    return
