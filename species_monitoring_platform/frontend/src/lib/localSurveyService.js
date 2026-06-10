// localSurveyService.js — on-device equivalent of surveyApi.* in api.js.
//
// Each export here is signature-compatible with the matching `api.*Survey*`
// HTTP function so the upstream call sites can be switched to local mode
// without touching their callers. Response shapes match what the FastAPI
// routes return on a successful request:
//
//   list-style:   { projects: [...], total: N }
//   create-style: { project: {...} }
//   delete-style: { deleted: id }
//
// Anything that genuinely needs the server (CNN inference, multi-device
// sync, taxonomy search, etc.) stays in api.js — this module never falls
// back to HTTP. The hybrid wiring lives in api.js and useSyncEngine.js.

import {
  enqueueOutbox,
  ensureSchema,
  getById,
  getEntityMeta,
  listEntities,
  listTrash as listTrashRows,
  restore as restoreRow,
  softDelete as softDeleteRow,
  upsert,
} from "./localStore/index.js";

// ── B24: durable sync outbox ──────────────────────────────────────
//
// Every mutation below records itself in `survey_sync_outbox` so that
// useSyncEngine can replay it against the backend the next time the device
// is online. Outbox failure must never fail the local write the user just
// made — the entity row is already committed; we only lose the *automatic*
// replay (the next full push still reconciles via pull merge).

async function recordOutbox(entityType, operation, entityId, payload = {}) {
  try {
    await enqueueOutbox(entityType, operation, entityId, payload);
  } catch (err) {
    console.warn(
      `[localSurveyService] outbox enqueue failed (${operation} ${entityType})`,
      err,
    );
  }
}

function deletePayload(entityType, entityId) {
  const meta = getEntityMeta(entityType);
  return meta ? { [meta.idField]: String(entityId) } : {};
}

// ── Filter helpers ────────────────────────────────────────────────

function normalizeFilters(input = "", maybeSiteId = "") {
  if (
    input &&
    typeof input === "object" &&
    !Array.isArray(input)
  ) {
    const out = {};
    for (const [k, v] of Object.entries(input)) {
      if (v === undefined || v === null || v === "") continue;
      out[k] = v;
    }
    return out;
  }
  const out = {};
  if (input) out.project_id = String(input);
  if (maybeSiteId) out.site_id = String(maybeSiteId);
  return out;
}

async function ensureReady() {
  await ensureSchema();
}

// ── Projects ──────────────────────────────────────────────────────

export async function getSurveyProjects(filters = {}) {
  await ensureReady();
  const projects = await listEntities("project", {
    filters: normalizeFilters(filters),
  });
  return { projects, total: projects.length };
}

export async function createSurveyProject(data = {}) {
  await ensureReady();
  const project = await upsert("project", data);
  await recordOutbox("project", "upsert", project.project_id, project);
  return { project };
}

export async function deleteSurveyProject(projectId) {
  await ensureReady();
  const ok = await softDeleteRow("project", projectId);
  if (ok) {
    await recordOutbox(
      "project",
      "delete",
      projectId,
      deletePayload("project", projectId),
    );
  }
  return { deleted: ok ? String(projectId) : "" };
}

// ── Sites ─────────────────────────────────────────────────────────

export async function getFieldSurveySites(projectId = "") {
  await ensureReady();
  const sites = await listEntities("site", {
    filters: normalizeFilters(projectId),
  });
  return { sites, total: sites.length };
}

export async function createFieldSurveySite(data = {}) {
  await ensureReady();
  const site = await upsert("site", data);
  await recordOutbox("site", "upsert", site.site_id, site);
  return { site };
}

export async function deleteFieldSurveySite(siteId) {
  await ensureReady();
  const ok = await softDeleteRow("site", siteId);
  if (ok) {
    await recordOutbox("site", "delete", siteId, deletePayload("site", siteId));
  }
  return { deleted: ok ? String(siteId) : "" };
}

// ── Routes ────────────────────────────────────────────────────────

export async function getSurveyRoutes(projectId = "", siteId = "") {
  await ensureReady();
  const routes = await listEntities("route", {
    filters: normalizeFilters(projectId, siteId),
  });
  return { routes, total: routes.length };
}

export async function createSurveyRoute(data = {}) {
  await ensureReady();
  const route = await upsert("route", data);
  await recordOutbox("route", "upsert", route.route_id, route);
  return { route };
}

export async function deleteSurveyRoute(routeId) {
  await ensureReady();
  const ok = await softDeleteRow("route", routeId);
  if (ok) {
    await recordOutbox(
      "route",
      "delete",
      routeId,
      deletePayload("route", routeId),
    );
  }
  return { deleted: ok ? String(routeId) : "" };
}

// ── Observations ──────────────────────────────────────────────────

export async function getSurveyObservations(projectId = "", siteId = "") {
  await ensureReady();
  const observations = await listEntities("observation", {
    filters: normalizeFilters(projectId, siteId),
  });
  return { observations, total: observations.length };
}

export async function createSurveyObservation(data = {}) {
  await ensureReady();
  const observation = await upsert("observation", data);
  await recordOutbox(
    "observation",
    "upsert",
    observation.observation_id,
    observation,
  );
  return { observation };
}

export async function deleteSurveyObservation(observationId) {
  await ensureReady();
  const ok = await softDeleteRow("observation", observationId);
  if (ok) {
    await recordOutbox(
      "observation",
      "delete",
      observationId,
      deletePayload("observation", observationId),
    );
  }
  return { deleted: ok ? String(observationId) : "" };
}

// ── Tracks ────────────────────────────────────────────────────────

export async function getSurveyTracks(projectId = "", siteId = "") {
  await ensureReady();
  const tracks = await listEntities("track", {
    filters: normalizeFilters(projectId, siteId),
  });
  return { tracks, total: tracks.length };
}

export async function createSurveyTrack(data = {}) {
  await ensureReady();
  const track = await upsert("track", data);
  await recordOutbox("track", "upsert", track.track_id, track);
  return { track };
}

// Tracks have no soft-delete endpoint on the server. Keep parity by exposing
// one anyway so the unified Trash UI can invoke it.
export async function deleteSurveyTrack(trackId) {
  await ensureReady();
  const ok = await softDeleteRow("track", trackId);
  if (ok) {
    await recordOutbox(
      "track",
      "delete",
      trackId,
      deletePayload("track", trackId),
    );
  }
  return { deleted: ok ? String(trackId) : "" };
}

// ── Map packages ──────────────────────────────────────────────────

export async function createOfflineMapPackage(data = {}) {
  await ensureReady();
  const package_ = await upsert("map_package", data);
  await recordOutbox("map_package", "upsert", package_.package_id, package_);
  return { package: package_ };
}

export async function deleteOfflineMapPackage(packageId) {
  await ensureReady();
  const ok = await softDeleteRow("map_package", packageId);
  if (ok) {
    await recordOutbox(
      "map_package",
      "delete",
      packageId,
      deletePayload("map_package", packageId),
    );
  }
  return { deleted: ok ? String(packageId) : "" };
}

// ── Design assets ─────────────────────────────────────────────────

export async function getSurveyDesignAssets(filters = {}) {
  await ensureReady();
  const design_assets = await listEntities("design_asset", {
    filters: normalizeFilters(filters),
  });
  return { design_assets, total: design_assets.length };
}

export async function createSurveyDesignAsset(data = {}) {
  await ensureReady();
  const design_asset = await upsert("design_asset", data);
  await recordOutbox(
    "design_asset",
    "upsert",
    design_asset.asset_id,
    design_asset,
  );
  return { design_asset };
}

export async function deleteSurveyDesignAsset(assetId) {
  await ensureReady();
  const ok = await softDeleteRow("design_asset", assetId);
  if (ok) {
    await recordOutbox(
      "design_asset",
      "delete",
      assetId,
      deletePayload("design_asset", assetId),
    );
  }
  return { deleted: ok ? String(assetId) : "" };
}

// ── Events ────────────────────────────────────────────────────────

export async function getSurveyEvents(filters = {}) {
  await ensureReady();
  const events = await listEntities("event", {
    filters: normalizeFilters(filters),
  });
  return { events, total: events.length };
}

export async function createSurveyEvent(data = {}) {
  await ensureReady();
  const event = await upsert("event", data);
  await recordOutbox("event", "upsert", event.event_id, event);
  return { event };
}

export async function deleteSurveyEvent(eventId) {
  await ensureReady();
  const ok = await softDeleteRow("event", eventId);
  if (ok) {
    await recordOutbox(
      "event",
      "delete",
      eventId,
      deletePayload("event", eventId),
    );
  }
  return { deleted: ok ? String(eventId) : "" };
}

// ── Export jobs ───────────────────────────────────────────────────

export async function createSurveyExportJob(jurisdiction, data = {}) {
  await ensureReady();
  const payload = {
    ...data,
    jurisdiction: jurisdiction || data.jurisdiction || "",
  };
  const export_job = await upsert("export_job", payload);
  return { export_job };
}

// ── Trash + restore (B18 endpoints, frontend-only equivalent) ─────

export async function getSurveyTrash(entityType = "") {
  await ensureReady();
  const items = await listTrashRows(entityType);
  return { items, total: items.length };
}

const SYNCABLE_ENTITY_TYPES = new Set([
  "project",
  "site",
  "route",
  "observation",
  "track",
  "map_package",
  "design_asset",
  "event",
]);

export async function restoreSurveyEntity(entityType, entityId) {
  await ensureReady();
  const ok = await restoreRow(entityType, entityId);
  if (ok && SYNCABLE_ENTITY_TYPES.has(String(entityType))) {
    // Resurrect on the server by replaying the live record as an upsert —
    // sync push has no "restore" verb.
    const record = await getById(entityType, entityId);
    if (record) {
      await recordOutbox(entityType, "upsert", entityId, record);
    }
  }
  return { restored: ok ? String(entityId) : "" };
}

// ── Single-row reads (used by the Trash UI to show full payload) ──

export async function getSurveyEntityById(entityType, entityId, options = {}) {
  await ensureReady();
  return getById(entityType, entityId, options);
}

// ── Aggregate "pull" snapshot for syncEngine bootstrap ────────────

/**
 * Build a snapshot in the shape that `pullSurveySync` returns, but sourced
 * entirely from the local SQLite store. Lets useSyncEngine bootstrap the
 * in-memory state without an HTTP round-trip when the device is offline.
 */
export async function buildLocalPullSnapshot() {
  await ensureReady();
  const [projects, sites, routes, observations, tracks, mapPackages, designAssets, events, exportJobs] = await Promise.all([
    listEntities("project"),
    listEntities("site"),
    listEntities("route"),
    listEntities("observation"),
    listEntities("track"),
    listEntities("map_package"),
    listEntities("design_asset"),
    listEntities("event"),
    listEntities("export_job"),
  ]);
  return {
    pulled_at: new Date().toISOString(),
    projects,
    sites,
    routes,
    observations,
    tracks,
    map_packages: mapPackages,
    design_assets: designAssets,
    events,
    export_jobs: exportJobs,
    conflicts: [],
  };
}

export const __localServiceInternals = { normalizeFilters };
