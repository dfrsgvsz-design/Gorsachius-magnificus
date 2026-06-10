// localStore/entityMeta.js — entity table/column registry + cascade rules.
//
// Mirror of `_ENTITY_META` in backend/survey_store.py. The cascade map is
// extracted from `_delete_entity_locked` so that frontend soft-delete obeys
// the same family tree as the server.
//
// Restoration is intentionally non-cascading (matches server `_restore_entity_locked`):
// the user must restore each level explicitly. This keeps the trash UI
// predictable and prevents accidentally resurrecting a child of a tombstoned
// parent.

export const ENTITY_META = {
  project: {
    table: "survey_projects",
    idField: "project_id",
    defaultPrefix: "proj",
    columns: ["project_id", "name", "region", "created_at", "updated_at", "deleted_at", "payload_json"],
    indexedColumns: ["name", "region"],
  },
  site: {
    table: "survey_sites",
    idField: "site_id",
    defaultPrefix: "site",
    columns: ["site_id", "project_id", "name", "latitude", "longitude", "created_at", "updated_at", "deleted_at", "payload_json"],
    indexedColumns: ["project_id", "name", "latitude", "longitude"],
  },
  route: {
    table: "survey_routes",
    idField: "route_id",
    defaultPrefix: "route",
    columns: ["route_id", "project_id", "site_id", "name", "route_type", "length_m", "created_at", "updated_at", "deleted_at", "payload_json"],
    indexedColumns: ["project_id", "site_id", "name", "route_type", "length_m"],
  },
  observation: {
    table: "survey_observations",
    idField: "observation_id",
    defaultPrefix: "obs",
    columns: [
      "observation_id", "project_id", "site_id", "route_id", "event_id",
      "program", "submodule", "protocol", "jurisdiction", "snapped_route_id",
      "scientific_name", "chinese_name", "english_name", "taxon_id", "taxon_group",
      "observed_at", "created_at", "updated_at", "deleted_at", "payload_json",
    ],
    indexedColumns: [
      "project_id", "site_id", "route_id", "event_id", "program", "submodule",
      "protocol", "jurisdiction", "snapped_route_id", "scientific_name",
      "chinese_name", "english_name", "taxon_id", "taxon_group", "observed_at",
    ],
  },
  track: {
    table: "survey_tracks",
    idField: "track_id",
    defaultPrefix: "track",
    columns: [
      "track_id", "project_id", "site_id", "route_id", "event_id",
      "program", "submodule", "protocol", "jurisdiction",
      "name", "source", "distance_m", "created_at", "updated_at", "deleted_at", "payload_json",
    ],
    indexedColumns: [
      "project_id", "site_id", "route_id", "event_id", "program", "submodule",
      "protocol", "jurisdiction", "name", "source", "distance_m",
    ],
  },
  map_package: {
    table: "survey_map_packages",
    idField: "package_id",
    defaultPrefix: "mp",
    columns: ["package_id", "project_id", "name", "min_zoom", "max_zoom", "status", "created_at", "updated_at", "deleted_at", "payload_json"],
    indexedColumns: ["project_id", "name", "min_zoom", "max_zoom", "status"],
  },
  design_asset: {
    table: "survey_design_assets",
    idField: "asset_id",
    defaultPrefix: "asset",
    columns: ["asset_id", "project_id", "site_id", "asset_type", "program", "submodule", "protocol", "name", "status", "created_at", "updated_at", "deleted_at", "payload_json"],
    indexedColumns: ["project_id", "site_id", "asset_type", "program", "submodule", "protocol", "name", "status"],
  },
  event: {
    table: "survey_events",
    idField: "event_id",
    defaultPrefix: "evt",
    columns: ["event_id", "project_id", "site_id", "design_asset_id", "route_id", "program", "submodule", "protocol", "jurisdiction", "started_at", "ended_at", "created_at", "updated_at", "deleted_at", "payload_json"],
    indexedColumns: ["project_id", "site_id", "design_asset_id", "route_id", "program", "submodule", "protocol", "jurisdiction", "started_at", "ended_at"],
  },
  export_job: {
    table: "survey_export_jobs",
    idField: "export_job_id",
    defaultPrefix: "expjob",
    columns: ["export_job_id", "project_id", "jurisdiction", "status", "created_at", "updated_at", "deleted_at", "payload_json"],
    indexedColumns: ["project_id", "jurisdiction", "status"],
  },
};

export const ENTITY_TYPES = Object.freeze(Object.keys(ENTITY_META));

/** Cascade rules for soft-delete. Order matters: deeper descendants first
 *  so each child's own cascade fires before its parent stamps `deleted_at`.
 *
 *  `kind` semantics:
 *    - "recursive": invoke softDelete(childType, childId) for each match —
 *      lets the child run its own cascade rules.
 *    - "stamp":     bulk UPDATE deleted_at on rows matching `where`. Used for
 *      leaf tables (observations / tracks / map_packages) that have no
 *      further descendants of their own.
 *    - "purge":     hard DELETE. Reserved for operational artefacts
 *      (export_jobs) that the server explicitly hard-deletes.
 */
export const CASCADE_RULES = {
  project: [
    { kind: "recursive", childType: "site", where: "project_id=? AND deleted_at=''" },
    { kind: "recursive", childType: "route", where: "project_id=? AND deleted_at=''" },
    { kind: "recursive", childType: "design_asset", where: "project_id=? AND deleted_at=''" },
    { kind: "recursive", childType: "event", where: "project_id=? AND deleted_at=''" },
    { kind: "stamp", table: "survey_observations", where: "project_id=? AND deleted_at=''" },
    { kind: "stamp", table: "survey_tracks", where: "project_id=? AND deleted_at=''" },
    { kind: "stamp", table: "survey_map_packages", where: "project_id=? AND deleted_at=''" },
    { kind: "purge", table: "survey_export_jobs", where: "project_id=?" },
  ],
  site: [
    { kind: "recursive", childType: "route", where: "site_id=? AND deleted_at=''" },
    { kind: "recursive", childType: "design_asset", where: "site_id=? AND deleted_at=''" },
    { kind: "recursive", childType: "event", where: "site_id=? AND deleted_at=''" },
    { kind: "stamp", table: "survey_observations", where: "site_id=? AND deleted_at=''" },
    { kind: "stamp", table: "survey_tracks", where: "site_id=? AND deleted_at=''" },
  ],
  route: [
    // Server walks design_assets via JSON payload (`route_id` lives inside
    // payload_json). The frontend mirrors this with a payload-aware filter
    // implemented in cascade.js.
    { kind: "recursive_payload", childType: "design_asset", payloadKey: "route_id" },
    { kind: "recursive", childType: "event", where: "route_id=? AND deleted_at=''" },
    // Observations match either route_id or snapped_route_id. Two stamps
    // is simpler than a single OR clause (and keeps indexes hot).
    { kind: "stamp", table: "survey_observations", where: "route_id=? AND deleted_at=''" },
    { kind: "stamp", table: "survey_observations", where: "snapped_route_id=? AND deleted_at=''" },
    { kind: "stamp", table: "survey_tracks", where: "route_id=? AND deleted_at=''" },
  ],
  design_asset: [
    // Parent_asset_id lives inside payload_json on the server too.
    { kind: "recursive_payload", childType: "design_asset", payloadKey: "parent_asset_id" },
    { kind: "recursive", childType: "event", where: "design_asset_id=? AND deleted_at=''" },
  ],
  event: [
    { kind: "stamp", table: "survey_observations", where: "event_id=? AND deleted_at=''" },
    { kind: "stamp", table: "survey_tracks", where: "event_id=? AND deleted_at=''" },
  ],
  // Leaf entities — no descendants.
  observation: [],
  track: [],
  map_package: [],
  export_job: [],
};

/** Server-side aliases (e.g. "sampling_event" -> "event"). Mirrors
 *  `ENTITY_TYPE_ALIASES` in surveyOffline.js so we accept either form. */
export const ENTITY_TYPE_ALIASES = Object.freeze({
  protocol_definition: "protocol",
  taxonomy: "taxonomy_package",
  taxon_package: "taxonomy_package",
  designAsset: "design_asset",
  sampling_event: "event",
  export: "export_job",
});

export function resolveEntityType(rawType) {
  const key = String(rawType || "").trim();
  if (ENTITY_META[key]) return key;
  const alias = ENTITY_TYPE_ALIASES[key];
  return alias && ENTITY_META[alias] ? alias : "";
}

export function getEntityMeta(entityType) {
  const resolved = resolveEntityType(entityType);
  return resolved ? ENTITY_META[resolved] : null;
}
