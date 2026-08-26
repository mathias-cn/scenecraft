"""better-auth jwks table for JWT plugin

Revision ID: 20260826_0016
Revises: 20260826_0015
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260826_0016"
down_revision: Union[str, Sequence[str], None] = "20260826_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE "jwks" (
            "id" TEXT PRIMARY KEY,
            "publicKey" TEXT NOT NULL,
            "privateKey" TEXT NOT NULL,
            "createdAt" TIMESTAMP NOT NULL,
            "expiresAt" TIMESTAMP,
            "alg" TEXT,
            "crv" TEXT
        )
        """
    )
    op.execute('ALTER TABLE "jwks" ENABLE ROW LEVEL SECURITY')
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON TABLE "jwks" FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON TABLE "jwks" FROM authenticated;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "jwks"')
