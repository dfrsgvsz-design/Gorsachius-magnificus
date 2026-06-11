"""survey_store baseline · captures the post-Batch C schema state

Revision ID: 0001_survey_store_baseline
Revises:
Create Date: 2026-06-11 00:00:00 +0000

This is the **state-of-the-art baseline** for the survey_store SQLite
database as of P0 W2 (Batch C + W2 conflict-resolution PR). Everything
that ``SurveyStore._init_schema`` produces on a fresh empty database is
materialized here. Future schema changes belong in a follow-up alembic
revision, not by extending this file.

For pre-alembic databases (deployed before this PR), the helper
``apply_survey_store_migrations`` in
``shared.backend.stores.migrations_runtime`` detects the existing
``survey_projects`` table and stamps the database at this revision
without re-running the CREATEs.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0001_survey_store_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES_DDL: tuple[str, ...] = (
    """
    CREATE TABLE survey_projects (
        project_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        region TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        deleted_at TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE survey_sites (
        site_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        name TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        deleted_at TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE survey_routes (
        route_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        name TEXT NOT NULL,
        route_type TEXT DEFAULT 'transect',
        length_m REAL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        deleted_at TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE survey_observations (
        observation_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        route_id TEXT DEFAULT '',
        event_id TEXT DEFAULT '',
        program TEXT DEFAULT '',
        submodule TEXT DEFAULT '',
        protocol TEXT DEFAULT '',
        jurisdiction TEXT DEFAULT '',
        snapped_route_id TEXT DEFAULT '',
        scientific_name TEXT DEFAULT '',
        chinese_name TEXT DEFAULT '',
        english_name TEXT DEFAULT '',
        taxon_id TEXT DEFAULT '',
        taxon_group TEXT DEFAULT '',
        observed_at TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        deleted_at TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE survey_tracks (
        track_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        route_id TEXT DEFAULT '',
        event_id TEXT DEFAULT '',
        program TEXT DEFAULT '',
        submodule TEXT DEFAULT '',
        protocol TEXT DEFAULT '',
        jurisdiction TEXT DEFAULT '',
        name TEXT NOT NULL,
        source TEXT DEFAULT 'recorded',
        distance_m REAL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        deleted_at TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE survey_map_packages (
        package_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        name TEXT NOT NULL,
        min_zoom INTEGER DEFAULT 8,
        max_zoom INTEGER DEFAULT 14,
        status TEXT DEFAULT 'draft',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        deleted_at TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE survey_design_assets (
        asset_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        asset_type TEXT DEFAULT 'route',
        program TEXT DEFAULT '',
        submodule TEXT DEFAULT '',
        protocol TEXT DEFAULT '',
        name TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        deleted_at TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE survey_events (
        event_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        design_asset_id TEXT DEFAULT '',
        route_id TEXT DEFAULT '',
        program TEXT DEFAULT '',
        submodule TEXT DEFAULT '',
        protocol TEXT DEFAULT '',
        jurisdiction TEXT DEFAULT '',
        started_at TEXT DEFAULT '',
        ended_at TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        deleted_at TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE survey_export_jobs (
        export_job_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        jurisdiction TEXT DEFAULT '',
        status TEXT DEFAULT 'ready',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE survey_sync_jobs (
        sync_job_id TEXT PRIMARY KEY,
        device_id TEXT DEFAULT '',
        user_id TEXT DEFAULT '',
        status TEXT DEFAULT 'applied',
        operation_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        operations_json TEXT NOT NULL,
        conflicts_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE survey_sync_conflicts (
        conflict_id TEXT PRIMARY KEY,
        sync_job_id TEXT DEFAULT '',
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        fields_json TEXT NOT NULL,
        incoming_json TEXT NOT NULL,
        server_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE survey_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        device_id TEXT DEFAULT '',
        user_id TEXT DEFAULT '',
        op TEXT NOT NULL,
        entity_type TEXT DEFAULT '',
        entity_id TEXT DEFAULT '',
        method TEXT DEFAULT '',
        path TEXT DEFAULT '',
        ip TEXT DEFAULT '',
        status_code INTEGER DEFAULT 0,
        request_id TEXT DEFAULT ''
    )
    """,
)

_INDEXES_DDL: tuple[str, ...] = (
    # survey_sites
    "CREATE INDEX idx_survey_sites_project ON survey_sites(project_id)",
    # survey_routes
    "CREATE INDEX idx_survey_routes_project ON survey_routes(project_id)",
    "CREATE INDEX idx_survey_routes_site ON survey_routes(site_id)",
    # survey_observations
    "CREATE INDEX idx_survey_observations_project ON survey_observations(project_id)",
    "CREATE INDEX idx_survey_observations_site ON survey_observations(site_id)",
    "CREATE INDEX idx_survey_observations_route ON survey_observations(route_id)",
    "CREATE INDEX idx_survey_observations_event ON survey_observations(event_id)",
    "CREATE INDEX idx_survey_observations_program ON survey_observations(program)",
    "CREATE INDEX idx_survey_observations_submodule ON survey_observations(submodule)",
    "CREATE INDEX idx_survey_observations_protocol ON survey_observations(protocol)",
    "CREATE INDEX idx_survey_observations_jurisdiction ON survey_observations(jurisdiction)",
    "CREATE INDEX idx_survey_observations_snapped_route ON survey_observations(snapped_route_id)",
    # survey_tracks
    "CREATE INDEX idx_survey_tracks_project ON survey_tracks(project_id)",
    "CREATE INDEX idx_survey_tracks_site ON survey_tracks(site_id)",
    "CREATE INDEX idx_survey_tracks_route ON survey_tracks(route_id)",
    "CREATE INDEX idx_survey_tracks_event ON survey_tracks(event_id)",
    "CREATE INDEX idx_survey_tracks_program ON survey_tracks(program)",
    "CREATE INDEX idx_survey_tracks_submodule ON survey_tracks(submodule)",
    "CREATE INDEX idx_survey_tracks_protocol ON survey_tracks(protocol)",
    "CREATE INDEX idx_survey_tracks_jurisdiction ON survey_tracks(jurisdiction)",
    # survey_map_packages
    "CREATE INDEX idx_survey_map_packages_project ON survey_map_packages(project_id)",
    # survey_design_assets
    "CREATE INDEX idx_survey_design_assets_project ON survey_design_assets(project_id)",
    "CREATE INDEX idx_survey_design_assets_site ON survey_design_assets(site_id)",
    "CREATE INDEX idx_survey_design_assets_program ON survey_design_assets(program)",
    "CREATE INDEX idx_survey_design_assets_protocol ON survey_design_assets(protocol)",
    "CREATE INDEX idx_survey_design_assets_submodule ON survey_design_assets(submodule)",
    "CREATE INDEX idx_survey_design_assets_type ON survey_design_assets(asset_type)",
    # survey_events
    "CREATE INDEX idx_survey_events_project ON survey_events(project_id)",
    "CREATE INDEX idx_survey_events_site ON survey_events(site_id)",
    "CREATE INDEX idx_survey_events_asset ON survey_events(design_asset_id)",
    "CREATE INDEX idx_survey_events_program ON survey_events(program)",
    "CREATE INDEX idx_survey_events_protocol ON survey_events(protocol)",
    "CREATE INDEX idx_survey_events_submodule ON survey_events(submodule)",
    # survey_export_jobs
    "CREATE INDEX idx_survey_export_jobs_project ON survey_export_jobs(project_id)",
    "CREATE INDEX idx_survey_export_jobs_jurisdiction ON survey_export_jobs(jurisdiction)",
    # survey_sync_conflicts
    "CREATE INDEX idx_survey_sync_conflicts_job ON survey_sync_conflicts(sync_job_id)",
    # survey_audit_log
    "CREATE INDEX idx_survey_audit_log_ts ON survey_audit_log(timestamp)",
    "CREATE INDEX idx_survey_audit_log_entity ON survey_audit_log(entity_type, entity_id)",
    # soft-delete deleted_at indexes
    "CREATE INDEX idx_survey_projects_deleted_at ON survey_projects(deleted_at)",
    "CREATE INDEX idx_survey_sites_deleted_at ON survey_sites(deleted_at)",
    "CREATE INDEX idx_survey_routes_deleted_at ON survey_routes(deleted_at)",
    "CREATE INDEX idx_survey_observations_deleted_at ON survey_observations(deleted_at)",
    "CREATE INDEX idx_survey_tracks_deleted_at ON survey_tracks(deleted_at)",
    "CREATE INDEX idx_survey_map_packages_deleted_at ON survey_map_packages(deleted_at)",
    "CREATE INDEX idx_survey_design_assets_deleted_at ON survey_design_assets(deleted_at)",
    "CREATE INDEX idx_survey_events_deleted_at ON survey_events(deleted_at)",
)


def upgrade() -> None:
    for ddl in _TABLES_DDL:
        op.execute(ddl)
    for ddl in _INDEXES_DDL:
        op.execute(ddl)


def downgrade() -> None:
    # Reverse order for safety even though SQLite doesn't enforce FK
    # dependencies between these tables.
    for ddl in reversed(_INDEXES_DDL):
        # `IF EXISTS` makes downgrade tolerant of partial baselines.
        name = ddl.split()[2]
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for ddl in reversed(_TABLES_DDL):
        # Crude but robust extraction: "CREATE TABLE <name> (" → grab <name>.
        head, _, _ = ddl.strip().partition("(")
        parts = head.split()
        if len(parts) >= 3 and parts[0].upper() == "CREATE":
            op.execute(f"DROP TABLE IF EXISTS {parts[2]}")
