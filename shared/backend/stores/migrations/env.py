"""Alembic environment for the survey_store SQLite database.

This module is invoked by `alembic` (CLI or programmatic) and only runs
in online (live-connection) mode. The runtime helper supplies the database
URL through ``config.attributes['connection']`` when called programmatically;
direct CLI invocations fall back to ``sqlalchemy.url`` in alembic.ini (which
must be overridden via ``-x url=...`` to point at a real database).
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool


config = context.config
target_metadata = None  # we use raw SQL migrations, not autogenerate


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite needs batch ops for any future ALTER
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # When the runtime helper calls us, it pre-attaches the live SQLAlchemy
    # connection so we share the same transaction; otherwise spin one up.
    injected_connection = config.attributes.get("connection")
    if injected_connection is not None:
        context.configure(
            connection=injected_connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
