from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import postgres_connect_args, settings
from app.db import Base
import app.models  # noqa: F401 — register metadata

config = context.config
# Percent-escape for ConfigParser only; the live engine uses the URL as-is.
config.set_main_option("sqlalchemy.url", settings.database_url_migrations_ssl.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = settings.database_url_migrations_ssl
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        settings.database_url_migrations_ssl,
        poolclass=pool.NullPool,
        connect_args=postgres_connect_args(settings.database_url_migrations),
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
