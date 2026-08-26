"""better-auth tables for Next.js Google login

Revision ID: 20260826_0015
Revises: 20260825_0014
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260826_0015"
down_revision: Union[str, None] = "20260825_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_TABLES = ("user", "session", "account", "verification")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE "user" (
            "id" TEXT PRIMARY KEY,
            "name" TEXT NOT NULL,
            "email" TEXT NOT NULL UNIQUE,
            "emailVerified" BOOLEAN NOT NULL,
            "image" TEXT,
            "createdAt" TIMESTAMP NOT NULL,
            "updatedAt" TIMESTAMP NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE "session" (
            "id" TEXT PRIMARY KEY,
            "expiresAt" TIMESTAMP NOT NULL,
            "token" TEXT NOT NULL UNIQUE,
            "createdAt" TIMESTAMP NOT NULL,
            "updatedAt" TIMESTAMP NOT NULL,
            "ipAddress" TEXT,
            "userAgent" TEXT,
            "userId" TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE
        )
        """
    )
    op.execute('CREATE INDEX "session_userId_idx" ON "session" ("userId")')
    op.execute(
        """
        CREATE TABLE "account" (
            "id" TEXT PRIMARY KEY,
            "issuer" TEXT NOT NULL,
            "accountId" TEXT NOT NULL,
            "providerId" TEXT NOT NULL,
            "userId" TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
            "accessToken" TEXT,
            "refreshToken" TEXT,
            "idToken" TEXT,
            "accessTokenExpiresAt" TIMESTAMP,
            "refreshTokenExpiresAt" TIMESTAMP,
            "scope" TEXT,
            "password" TEXT,
            "createdAt" TIMESTAMP NOT NULL,
            "updatedAt" TIMESTAMP NOT NULL
        )
        """
    )
    op.execute(
        'CREATE UNIQUE INDEX "account_issuer_accountId_key" ON "account" ("issuer", "accountId")'
    )
    op.execute('CREATE INDEX "account_userId_idx" ON "account" ("userId")')
    op.execute(
        """
        CREATE TABLE "verification" (
            "id" TEXT PRIMARY KEY,
            "identifier" TEXT NOT NULL,
            "value" TEXT NOT NULL,
            "expiresAt" TIMESTAMP NOT NULL,
            "createdAt" TIMESTAMP NOT NULL,
            "updatedAt" TIMESTAMP NOT NULL
        )
        """
    )
    op.execute('CREATE INDEX "verification_identifier_idx" ON "verification" ("identifier")')

    for table in AUTH_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    REVOKE ALL ON TABLE "{table}" FROM anon;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    REVOKE ALL ON TABLE "{table}" FROM authenticated;
                END IF;
            END
            $$
            """
        )


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "verification"')
    op.execute('DROP TABLE IF EXISTS "account"')
    op.execute('DROP TABLE IF EXISTS "session"')
    op.execute('DROP TABLE IF EXISTS "user"')
