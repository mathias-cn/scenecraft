"""silence PostgREST log when Data API is disabled

Revision ID: 20260826_0018
Revises: 20260826_0017
Create Date: 2026-08-26

Bug conhecido do Supabase: com a Data API (PostgREST) desabilitada, o PostgREST
não desliga de verdade e tenta expor o schema `pg_pgrst_no_exposed_schemas`,
que não existe. Isso enche o log com
`schema "pg_pgrst_no_exposed_schemas" does not exist` sem afetar o app.

Workaround documentado em:
https://supabase.com/docs/guides/troubleshooting/schema-pg_pgrst_no_exposed_schemas-does-not-exist

Esta revision não altera tabelas do app — só a config da role `authenticator`.
Em Postgres sem essa role (teste local, não-Supabase), o bloco é um no-op.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260826_0018"
down_revision: Union[str, Sequence[str], None] = "20260826_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Role `authenticator` só existe no Supabase. Em Postgres local o DO é no-op.
    # NOTIFY fora do bloco: não é statement PL/pgSQL portátil; sem listener é inócuo.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN
                ALTER ROLE authenticator SET pgrst.db_schemas = '';
            END IF;
        END
        $$;
        """
    )
    op.execute("NOTIFY pgrst, 'reload config'")
    op.execute("NOTIFY pgrst, 'reload schema'")


def downgrade() -> None:
    # Correção de log, não de schema: reverter não é necessário.
    pass
