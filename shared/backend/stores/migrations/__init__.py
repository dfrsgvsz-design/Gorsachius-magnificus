"""Alembic-managed schema migrations for the `survey_store` SQLite database.

P0 W3 first-cut integration. See `shared.backend.stores.migrations_runtime`
for the helper that callers invoke at startup (it knows how to stamp an
existing pre-alembic database at baseline before running any new migrations).

Only the survey_store database is alembic-managed today. The taxonomy
catalog regenerates from seed JSON every boot and the detection store is a
single-table append-only log, so neither earns the alembic operating cost
yet. Revisit when either store gains schema branches that need rollback.
"""
