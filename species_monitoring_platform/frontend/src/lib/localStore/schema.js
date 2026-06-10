// localStore/schema.js — SQLite schema mirror of backend/survey_store.py.
//
// Mirrors the 9 business tables defined in `_DDL` (`survey_projects`,
// `survey_sites`, `survey_routes`, `survey_observations`, `survey_tracks`,
// `survey_map_packages`, `survey_design_assets`, `survey_events`,
// `survey_export_jobs`). The two server-only operational tables
// (`survey_sync_jobs` / `survey_sync_conflicts`) are intentionally omitted —
// the frontend tracks pending mutations via the in-memory `syncQueue`
// in `surveyOffline.js`.
//
// Every row carries `deleted_at TEXT NOT NULL DEFAULT ''` from day one so the
// soft-delete behaviour from B18 is available without a migration step.
//
// v2 (B24): adds `survey_sync_outbox` — a durable queue of local mutations
// awaiting push to the backend. The in-memory `syncQueue` in surveyOffline.js
// remains the UI-facing view, but the outbox survives localStorage quota
// failures and app restarts, and captures mutations made by components that
// never touch the FieldOps React state (e.g. ProjectManagementPanel).

export const SCHEMA_VERSION = 2;

export const TABLE_NAMES = [
  "survey_projects",
  "survey_sites",
  "survey_routes",
  "survey_observations",
  "survey_tracks",
  "survey_map_packages",
  "survey_design_assets",
  "survey_events",
  "survey_export_jobs",
];

const TABLE_DEFS = [
  `CREATE TABLE IF NOT EXISTS survey_projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_sites (
    site_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_routes (
    route_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    site_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    route_type TEXT NOT NULL DEFAULT 'transect',
    length_m REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_observations (
    observation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    site_id TEXT NOT NULL DEFAULT '',
    route_id TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    program TEXT NOT NULL DEFAULT '',
    submodule TEXT NOT NULL DEFAULT '',
    protocol TEXT NOT NULL DEFAULT '',
    jurisdiction TEXT NOT NULL DEFAULT '',
    snapped_route_id TEXT NOT NULL DEFAULT '',
    scientific_name TEXT NOT NULL DEFAULT '',
    chinese_name TEXT NOT NULL DEFAULT '',
    english_name TEXT NOT NULL DEFAULT '',
    taxon_id TEXT NOT NULL DEFAULT '',
    taxon_group TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_tracks (
    track_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    site_id TEXT NOT NULL DEFAULT '',
    route_id TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    program TEXT NOT NULL DEFAULT '',
    submodule TEXT NOT NULL DEFAULT '',
    protocol TEXT NOT NULL DEFAULT '',
    jurisdiction TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'recorded',
    distance_m REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_map_packages (
    package_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    min_zoom INTEGER NOT NULL DEFAULT 8,
    max_zoom INTEGER NOT NULL DEFAULT 14,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_design_assets (
    asset_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    site_id TEXT NOT NULL DEFAULT '',
    asset_type TEXT NOT NULL DEFAULT 'route',
    program TEXT NOT NULL DEFAULT '',
    submodule TEXT NOT NULL DEFAULT '',
    protocol TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_events (
    event_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    site_id TEXT NOT NULL DEFAULT '',
    design_asset_id TEXT NOT NULL DEFAULT '',
    route_id TEXT NOT NULL DEFAULT '',
    program TEXT NOT NULL DEFAULT '',
    submodule TEXT NOT NULL DEFAULT '',
    protocol TEXT NOT NULL DEFAULT '',
    jurisdiction TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    ended_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_export_jobs (
    export_job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    jurisdiction TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS survey_sync_outbox (
    op_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    operation TEXT NOT NULL DEFAULT 'upsert',
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    queued_at TEXT NOT NULL,
    queue_status TEXT NOT NULL DEFAULT 'pending'
  )`,
];

const INDEX_DEFS = [
  // sites
  `CREATE INDEX IF NOT EXISTS idx_survey_sites_project ON survey_sites(project_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_sites_deleted ON survey_sites(deleted_at)`,
  // routes
  `CREATE INDEX IF NOT EXISTS idx_survey_routes_project ON survey_routes(project_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_routes_site ON survey_routes(site_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_routes_deleted ON survey_routes(deleted_at)`,
  // observations
  `CREATE INDEX IF NOT EXISTS idx_survey_observations_project ON survey_observations(project_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_observations_site ON survey_observations(site_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_observations_route ON survey_observations(route_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_observations_event ON survey_observations(event_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_observations_deleted ON survey_observations(deleted_at)`,
  // tracks
  `CREATE INDEX IF NOT EXISTS idx_survey_tracks_project ON survey_tracks(project_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_tracks_site ON survey_tracks(site_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_tracks_route ON survey_tracks(route_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_tracks_event ON survey_tracks(event_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_tracks_deleted ON survey_tracks(deleted_at)`,
  // map_packages
  `CREATE INDEX IF NOT EXISTS idx_survey_map_packages_project ON survey_map_packages(project_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_map_packages_deleted ON survey_map_packages(deleted_at)`,
  // design_assets
  `CREATE INDEX IF NOT EXISTS idx_survey_design_assets_project ON survey_design_assets(project_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_design_assets_site ON survey_design_assets(site_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_design_assets_program ON survey_design_assets(program)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_design_assets_protocol ON survey_design_assets(protocol)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_design_assets_type ON survey_design_assets(asset_type)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_design_assets_deleted ON survey_design_assets(deleted_at)`,
  // events
  `CREATE INDEX IF NOT EXISTS idx_survey_events_project ON survey_events(project_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_events_site ON survey_events(site_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_events_asset ON survey_events(design_asset_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_events_route ON survey_events(route_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_events_program ON survey_events(program)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_events_protocol ON survey_events(protocol)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_events_deleted ON survey_events(deleted_at)`,
  // export_jobs
  `CREATE INDEX IF NOT EXISTS idx_survey_export_jobs_project ON survey_export_jobs(project_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_export_jobs_jurisdiction ON survey_export_jobs(jurisdiction)`,
  // sync outbox
  `CREATE INDEX IF NOT EXISTS idx_survey_sync_outbox_entity ON survey_sync_outbox(entity_type, entity_id)`,
  `CREATE INDEX IF NOT EXISTS idx_survey_sync_outbox_queued ON survey_sync_outbox(queued_at)`,
];

/** Bootstrap script — run once on first open. Subsequent runs are no-ops
 *  thanks to `IF NOT EXISTS`. */
export const SCHEMA_BOOTSTRAP_SQL = [
  ...TABLE_DEFS,
  ...INDEX_DEFS,
  `INSERT OR IGNORE INTO survey_meta (key, value) VALUES ('schema_version', '${SCHEMA_VERSION}')`,
]
  .map((stmt) => `${stmt};`)
  .join("\n");
