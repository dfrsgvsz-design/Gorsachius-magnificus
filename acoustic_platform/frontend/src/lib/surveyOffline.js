import {
  applyAttachmentContext,
  computeAttachmentChecksum,
  createAttachmentId,
  normalizeAttachmentContract,
  normalizeAttachmentIds,
} from "./attachmentContract";
import { normalizeSurveyTaxonomyPackage } from "./api";

const STORAGE_KEY = "bird-platform-field-survey-v1";
const DEVICE_KEY = "bird-platform-field-device-id";
const TILE_CACHE_PREFIX = "bird-platform-field-tiles";
const ATTACHMENT_DB_NAME = "bird-platform-field-attachments";
const ATTACHMENT_DB_VERSION = 1;
const ATTACHMENT_STORE = "attachments";
const WEB_ATTACHMENT_STORAGE_KIND = "indexeddb";
const DEFAULT_PROGRAM = "terrestrial_vertebrates";
const DEFAULT_JURISDICTION = "mainland_china";
const STATE_SCHEMA_VERSION = 2;
const JURISDICTION_ALIASES = {
  china_mainland: "mainland_china",
};
const ENTITY_TYPE_ALIASES = {
  protocol_definition: "protocol",
  taxonomy: "taxonomy_package",
  taxon_package: "taxonomy_package",
  designAsset: "design_asset",
  sampling_event: "event",
  export: "export_job",
};
const ENTITY_CONFIG = {
  project: {
    listKey: "projects",
    idField: "project_id",
    pullKeys: ["projects"],
  },
  site: { listKey: "sites", idField: "site_id", pullKeys: ["sites"] },
  route: { listKey: "routes", idField: "route_id", pullKeys: ["routes"] },
  observation: {
    listKey: "observations",
    idField: "observation_id",
    pullKeys: ["observations"],
  },
  track: { listKey: "tracks", idField: "track_id", pullKeys: ["tracks"] },
  map_package: {
    listKey: "mapPackages",
    idField: "package_id",
    pullKeys: ["map_packages", "mapPackages"],
  },
  protocol: {
    listKey: "protocols",
    idField: "protocol_id",
    alternateIdFields: ["protocol"],
    pullKeys: ["protocols", "protocol_definitions"],
    queueDefault: false,
  },
  taxonomy_package: {
    listKey: "taxonomyPackages",
    idField: "package_id",
    alternateIdFields: [
      "taxonomy_package_id",
      "asset_package_id",
      "taxonomy_release_id",
    ],
    pullKeys: ["taxonomy_packages", "taxonomyPackages", "taxon_packages"],
    queueDefault: false,
  },
  design_asset: {
    listKey: "designAssets",
    idField: "asset_id",
    alternateIdFields: ["design_asset_id"],
    pullKeys: ["design_assets", "designAssets"],
  },
  event: {
    listKey: "events",
    idField: "event_id",
    alternateIdFields: ["sampling_event_id"],
    pullKeys: ["events", "sampling_events"],
  },
  export_job: {
    listKey: "exportJobs",
    idField: "export_job_id",
    alternateIdFields: ["job_id"],
    pullKeys: ["export_jobs", "exportJobs"],
    queueDefault: false,
  },
};

const COLLECTION_KEYS = Array.from(
  new Set(Object.values(ENTITY_CONFIG).map((config) => config.listKey)),
);
const attachmentUrlCache = new Map();
let attachmentDbPromise = null;
let legacyAttachmentMigrationPromise = null;

function nowIso() {
  return new Date().toISOString();
}

function createId(prefix) {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return `${prefix}_${crypto.randomUUID().slice(0, 12)}`;
  }
  return `${prefix}_${Math.random().toString(16).slice(2, 14)}`;
}

function safeJsonParse(raw, fallback) {
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function isNonEmptyValue(value) {
  return value !== "" && value != null;
}

function resolveEntityType(entityType) {
  const key = String(entityType || "").trim();
  return ENTITY_CONFIG[key] ? key : ENTITY_TYPE_ALIASES[key] || key;
}

function getEntityConfig(entityTypeOrConfig) {
  if (
    entityTypeOrConfig &&
    typeof entityTypeOrConfig === "object" &&
    entityTypeOrConfig.idField
  ) {
    return entityTypeOrConfig;
  }
  return ENTITY_CONFIG[resolveEntityType(entityTypeOrConfig)] || null;
}

function getEntityId(record, entityTypeOrConfig) {
  const config = getEntityConfig(entityTypeOrConfig);
  if (!record || !config) return "";
  const candidates = [config.idField, ...(config.alternateIdFields || [])];
  for (const field of candidates) {
    if (isNonEmptyValue(record?.[field])) return record[field];
  }
  return "";
}

function normalizeEntityRecord(
  record,
  entityTypeOrConfig,
  fallbackSyncState = "synced",
) {
  const config = getEntityConfig(entityTypeOrConfig);
  if (!config || !record || typeof record !== "object") return null;
  const normalizedRecord =
    resolveEntityType(entityTypeOrConfig) === "taxonomy_package" ||
    config.listKey === "taxonomyPackages"
      ? normalizeSurveyTaxonomyPackage(record)
      : record;
  const entityId = getEntityId(normalizedRecord, config);
  if (!entityId) return null;
  return {
    ...normalizedRecord,
    [config.idField]: entityId,
    program: normalizedRecord.program || "",
    protocol: normalizedRecord.protocol || "",
    jurisdiction: normalizeJurisdiction(normalizedRecord.jurisdiction, ""),
    sync_state: normalizedRecord.sync_state || fallbackSyncState,
    server_updated_at:
      normalizedRecord.server_updated_at || normalizedRecord.updated_at || "",
  };
}

function getPullRecords(pullData, entityTypeOrConfig) {
  const config = getEntityConfig(entityTypeOrConfig);
  if (!config) return [];
  for (const key of config.pullKeys || []) {
    if (Array.isArray(pullData?.[key])) return pullData[key];
  }
  return [];
}

function mergeEntityCollection(
  baseRecords,
  incomingRecords,
  entityTypeOrConfig,
) {
  return mergeRecords(baseRecords, incomingRecords, entityTypeOrConfig);
}

function normalizeSelector(value, fallback = "") {
  return typeof value === "string" ? value : value || fallback;
}

function normalizeVertebrateSubmodule(value, fallback = "") {
  const normalized = String(value || "").trim();
  if (!normalized) return fallback;
  return ["birds", "mammals", "amphibians", "reptiles"].includes(normalized)
    ? normalized
    : fallback;
}

export function normalizeJurisdiction(value, fallback = DEFAULT_JURISDICTION) {
  const normalized = String(value || "").trim();
  if (!normalized) return fallback;
  return JURISDICTION_ALIASES[normalized] || normalized;
}

function isDataUrl(value) {
  return typeof value === "string" && value.startsWith("data:");
}

function hasDurableAttachmentReference(attachment) {
  return Boolean(
    attachment &&
    typeof attachment === "object" &&
    attachment.storage_kind === WEB_ATTACHMENT_STORAGE_KIND &&
    typeof attachment.storage_key === "string" &&
    attachment.storage_key,
  );
}

function normalizeStoredAttachment(
  attachment,
  { persistLocalUri = true } = {},
) {
  const normalized = normalizeAttachmentContract(attachment, {
    persistLocalUri,
    defaultStorageKind: WEB_ATTACHMENT_STORAGE_KIND,
  });
  if (!normalized) return null;
  if (!persistLocalUri && hasDurableAttachmentReference(normalized)) {
    delete normalized.local_uri;
  }
  return normalized;
}

function normalizeSurveyStateShape(
  state = {},
  { persistAttachmentUris = true } = {},
) {
  const base = {
    ...emptySurveyState(),
    ...(state || {}),
  };
  const normalized = {
    ...base,
    schema_version: Math.max(
      Number(base.schema_version || 0),
      STATE_SCHEMA_VERSION,
    ),
  };
  for (const key of COLLECTION_KEYS) {
    normalized[key] = Array.isArray(base[key]) ? base[key] : [];
  }
  normalized.taxonomyPackages = mergeEntityCollection(
    [],
    normalized.taxonomyPackages,
    "taxonomy_package",
  );
  normalized.mediaInbox = Array.isArray(base.mediaInbox)
    ? base.mediaInbox
        .map((attachment) =>
          normalizeStoredAttachment(attachment, {
            persistLocalUri: persistAttachmentUris,
          }),
        )
        .filter(Boolean)
    : [];
  normalized.activeDraftAttachmentIds = normalizeAttachmentIds(
    base.activeDraftAttachmentIds,
  );
  normalized.syncQueue = Array.isArray(base.syncQueue) ? base.syncQueue : [];
  normalized.conflicts = Array.isArray(base.conflicts) ? base.conflicts : [];
  normalized.activeProjectId = normalizeSelector(
    base.activeProjectId,
    normalized.projects[0]?.project_id || "",
  );
  normalized.activeSiteId = normalizeSelector(base.activeSiteId);
  normalized.activeRouteId = normalizeSelector(base.activeRouteId);
  normalized.activeProgram = normalizeSelector(
    base.activeProgram,
    DEFAULT_PROGRAM,
  );
  normalized.activeProtocol = normalizeSelector(base.activeProtocol);
  normalized.activeVertebrateSubmodule = normalizeVertebrateSubmodule(
    base.activeVertebrateSubmodule,
  );
  normalized.activeJurisdiction = normalizeJurisdiction(
    base.activeJurisdiction,
    DEFAULT_JURISDICTION,
  );
  normalized.activeDesignAssetId = normalizeSelector(base.activeDesignAssetId);
  normalized.activeEventId = normalizeSelector(base.activeEventId);
  normalized.mediaInbox = applyAttachmentContext(
    normalized.mediaInbox,
    normalized.activeDraftAttachmentIds,
    {
      owner_type: normalized.activeEventId ? "event" : "draft",
      owner_id:
        normalized.activeEventId ||
        normalized.activeDesignAssetId ||
        normalized.activeRouteId ||
        normalized.activeSiteId ||
        normalized.activeProjectId ||
        "",
      event_id: normalized.activeEventId || "",
      sync_state: "local_only",
    },
  );
  normalized.syncMeta = {
    ...emptySurveyState().syncMeta,
    ...(base.syncMeta || {}),
    deviceId: getDeviceId(),
  };
  return normalized;
}

export function getDeviceId() {
  if (typeof window === "undefined") return "field-device-web";
  const existing = window.localStorage.getItem(DEVICE_KEY);
  if (existing) return existing;
  const deviceId = createId("device");
  window.localStorage.setItem(DEVICE_KEY, deviceId);
  return deviceId;
}

export function emptySurveyState() {
  return {
    projects: [],
    sites: [],
    routes: [],
    observations: [],
    tracks: [],
    mapPackages: [],
    protocols: [],
    taxonomyPackages: [],
    designAssets: [],
    events: [],
    exportJobs: [],
    mediaInbox: [],
    activeDraftAttachmentIds: [],
    syncQueue: [],
    conflicts: [],
    activeProjectId: "",
    activeSiteId: "",
    activeRouteId: "",
    activeProgram: DEFAULT_PROGRAM,
    activeProtocol: "",
    activeVertebrateSubmodule: "",
    activeJurisdiction: DEFAULT_JURISDICTION,
    activeDesignAssetId: "",
    activeEventId: "",
    schema_version: STATE_SCHEMA_VERSION,
    syncMeta: {
      lastPulledAt: "",
      lastPushedAt: "",
      lastStatus: "idle",
      lastError: "",
      deviceId: getDeviceId(),
    },
  };
}

export function loadSurveyState() {
  if (typeof window === "undefined") return emptySurveyState();
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return emptySurveyState();
  const parsed = safeJsonParse(raw, emptySurveyState());
  const normalized = normalizeSurveyStateShape(parsed);
  if (
    normalized.mediaInbox.some(
      (attachment) =>
        isDataUrl(attachment?.local_uri) &&
        !hasDurableAttachmentReference(attachment),
    )
  ) {
    queueLegacyAttachmentMigration();
  }
  return normalized;
}

export function saveSurveyState(state) {
  if (typeof window === "undefined") return state;
  const normalized = normalizeSurveyStateShape(state, {
    persistAttachmentUris: false,
  });
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    // QuotaExceededError on mobile WebViews; state is still returned in memory.
  }
  if (
    normalized.mediaInbox.some(
      (attachment) =>
        isDataUrl(attachment?.local_uri) &&
        !hasDurableAttachmentReference(attachment),
    )
  ) {
    queueLegacyAttachmentMigration();
  }
  return normalized;
}

function chooseLatest(existing, incoming) {
  if (!existing) return incoming;
  const existingUpdated =
    existing.updated_at || existing.server_updated_at || "";
  const incomingUpdated =
    incoming.updated_at || incoming.server_updated_at || "";
  return incomingUpdated >= existingUpdated
    ? { ...existing, ...incoming }
    : { ...incoming, ...existing };
}

export function mergeRecords(existingRecords, incomingRecords, idField) {
  const config = getEntityConfig(idField) || { idField };
  const merged = new Map();
  for (const record of existingRecords || []) {
    const normalized = normalizeEntityRecord(
      record,
      config,
      record?.sync_state || "synced",
    );
    if (!normalized) continue;
    merged.set(normalized[config.idField], normalized);
  }
  for (const record of incomingRecords || []) {
    const normalized = normalizeEntityRecord(record, config, "synced");
    if (!normalized) continue;
    const mergedRecord = chooseLatest(
      merged.get(normalized[config.idField]),
      normalized,
    );
    merged.set(normalized[config.idField], mergedRecord);
  }
  return Array.from(merged.values());
}

export function mergeStoredSurveyState(currentState, incomingState) {
  if (!incomingState || typeof incomingState !== "object") return currentState;
  const base = normalizeSurveyStateShape(currentState || emptySurveyState());
  const incoming = normalizeSurveyStateShape(incomingState);
  const next = {
    ...base,
    ...incoming,
    syncQueue: Array.isArray(incoming.syncQueue)
      ? incoming.syncQueue
      : base.syncQueue,
    conflicts: Array.isArray(incoming.conflicts)
      ? incoming.conflicts
      : base.conflicts,
    mediaInbox: Array.isArray(incoming.mediaInbox)
      ? incoming.mediaInbox
      : base.mediaInbox,
    activeDraftAttachmentIds: normalizeAttachmentIds(
      Array.isArray(incoming.activeDraftAttachmentIds)
        ? incoming.activeDraftAttachmentIds
        : base.activeDraftAttachmentIds,
    ),
  };
  for (const [entityType, config] of Object.entries(ENTITY_CONFIG)) {
    next[config.listKey] = mergeEntityCollection(
      base[config.listKey],
      incoming[config.listKey],
      entityType,
    );
  }
  next.activeProjectId =
    incoming.activeProjectId ||
    base.activeProjectId ||
    next.projects[0]?.project_id ||
    "";
  next.activeSiteId = incoming.activeSiteId || base.activeSiteId || "";
  next.activeRouteId = incoming.activeRouteId || base.activeRouteId || "";
  next.activeProgram =
    incoming.activeProgram || base.activeProgram || DEFAULT_PROGRAM;
  next.activeProtocol = incoming.activeProtocol || base.activeProtocol || "";
  next.activeVertebrateSubmodule = normalizeVertebrateSubmodule(
    incoming.activeVertebrateSubmodule || base.activeVertebrateSubmodule || "",
    "",
  );
  next.activeJurisdiction = normalizeJurisdiction(
    incoming.activeJurisdiction ||
      base.activeJurisdiction ||
      DEFAULT_JURISDICTION,
    DEFAULT_JURISDICTION,
  );
  next.activeDesignAssetId =
    incoming.activeDesignAssetId || base.activeDesignAssetId || "";
  next.activeEventId = incoming.activeEventId || base.activeEventId || "";
  next.syncMeta = {
    ...emptySurveyState().syncMeta,
    ...(base.syncMeta || {}),
    ...(incoming.syncMeta || {}),
    deviceId: getDeviceId(),
  };
  return normalizeSurveyStateShape(next);
}

export function upsertLocalEntity(state, entityType, record, options = {}) {
  const resolvedType = resolveEntityType(entityType);
  const config = ENTITY_CONFIG[resolvedType];
  if (!config) return state;
  const idField = config.idField;
  const listKey = config.listKey;
  const idValue =
    getEntityId(record, config) || createId(idField.replace("_id", ""));
  const prepared = {
    ...record,
    [idField]: idValue,
    jurisdiction: normalizeJurisdiction(record.jurisdiction, ""),
    updated_at: record.updated_at || nowIso(),
    sync_state: options.syncState || record.sync_state || "queued",
  };
  const current = normalizeSurveyStateShape(state || emptySurveyState());
  const next = mergeEntityCollection(
    current[listKey],
    [prepared],
    resolvedType,
  );
  const nextState = { ...current, [listKey]: next };
  const shouldSelect = options.select === true;
  const shouldQueue = options.queue ?? config.queueDefault ?? true;
  if (shouldQueue !== false) {
    nextState.syncQueue = [
      ...(current.syncQueue || []),
      {
        op_id: createId("op"),
        entity_type: resolvedType,
        operation: options.operation || "upsert",
        entity_id: idValue,
        payload: {
          ...prepared,
          server_updated_at:
            record.server_updated_at || prepared.server_updated_at || "",
        },
        queued_at: nowIso(),
      },
    ];
  }
  nextState.activeProgram =
    prepared.program || nextState.activeProgram || DEFAULT_PROGRAM;
  nextState.activeProtocol =
    prepared.protocol || nextState.activeProtocol || "";
  const preparedSubmodule = normalizeVertebrateSubmodule(
    prepared.submodule || prepared.extra?.submodule || "",
    "",
  );
  if (
    prepared.program === "terrestrial_vertebrates" &&
    preparedSubmodule &&
    (shouldSelect || !nextState.activeVertebrateSubmodule)
  ) {
    nextState.activeVertebrateSubmodule = preparedSubmodule;
  }
  nextState.activeJurisdiction = normalizeJurisdiction(
    prepared.jurisdiction ||
      nextState.activeJurisdiction ||
      DEFAULT_JURISDICTION,
    DEFAULT_JURISDICTION,
  );
  if (
    (shouldSelect || !nextState.activeProjectId) &&
    resolvedType === "project"
  ) {
    nextState.activeProjectId = idValue;
  }
  if ((shouldSelect || !nextState.activeSiteId) && resolvedType === "site") {
    nextState.activeSiteId = idValue;
  }
  if ((shouldSelect || !nextState.activeRouteId) && resolvedType === "route") {
    nextState.activeRouteId = idValue;
  }
  if (
    (shouldSelect || !nextState.activeDesignAssetId) &&
    resolvedType === "design_asset"
  ) {
    nextState.activeDesignAssetId = idValue;
  }
  if ((shouldSelect || !nextState.activeEventId) && resolvedType === "event") {
    nextState.activeEventId = idValue;
  }
  return normalizeSurveyStateShape(nextState);
}

export function mergeSyncPull(state, pullData) {
  const current = normalizeSurveyStateShape(state || emptySurveyState());
  const next = { ...current };
  for (const [entityType, config] of Object.entries(ENTITY_CONFIG)) {
    next[config.listKey] = mergeEntityCollection(
      current[config.listKey],
      getPullRecords(pullData, entityType),
      entityType,
    );
  }
  next.conflicts = pullData.conflicts || current.conflicts || [];
  next.activeProgram =
    pullData.active_program || current.activeProgram || DEFAULT_PROGRAM;
  next.activeProtocol =
    pullData.active_protocol || current.activeProtocol || "";
  next.activeVertebrateSubmodule = normalizeVertebrateSubmodule(
    pullData.active_vertebrate_submodule ||
      pullData.active_submodule ||
      current.activeVertebrateSubmodule ||
      "",
    "",
  );
  next.activeJurisdiction = normalizeJurisdiction(
    pullData.active_jurisdiction ||
      current.activeJurisdiction ||
      DEFAULT_JURISDICTION,
    DEFAULT_JURISDICTION,
  );
  next.syncMeta = {
    ...(current.syncMeta || {}),
    lastPulledAt: pullData.pulled_at || nowIso(),
    lastStatus: next.conflicts.length > 0 ? "conflict" : "synced",
    lastError: "",
  };
  return normalizeSurveyStateShape(next);
}

function buildAppliedKeySet(syncJob) {
  const keys = new Set();
  for (const item of syncJob?.applied || []) {
    if (!item?.entity_type || !item?.record) continue;
    const resolvedType = resolveEntityType(item.entity_type);
    const config = ENTITY_CONFIG[resolvedType];
    if (!config) continue;
    const entityId = getEntityId(item.record, config);
    if (entityId) keys.add(`${resolvedType}:${entityId}`);
  }
  for (const item of syncJob?.deleted || []) {
    const resolvedType = resolveEntityType(item?.entity_type);
    if (resolvedType && item?.entity_id)
      keys.add(`${resolvedType}:${item.entity_id}`);
  }
  return keys;
}

function buildConflictKeySet(syncJob) {
  const keys = new Set();
  for (const conflict of syncJob?.conflicts || []) {
    const resolvedType = resolveEntityType(conflict?.entity_type);
    if (resolvedType && conflict?.entity_id)
      keys.add(`${resolvedType}:${conflict.entity_id}`);
  }
  return keys;
}

export function applySyncResult(state, syncJob) {
  let next = normalizeSurveyStateShape(state || emptySurveyState());
  const applied = syncJob?.applied || [];
  for (const item of applied) {
    if (!item?.entity_type || !item?.record) continue;
    const resolvedType = resolveEntityType(item.entity_type);
    const config = ENTITY_CONFIG[resolvedType];
    if (!config) continue;
    next = {
      ...next,
      [config.listKey]: mergeEntityCollection(
        next[config.listKey],
        [
          {
            ...item.record,
            sync_state: "synced",
            server_updated_at: item.record.updated_at,
          },
        ],
        resolvedType,
      ),
    };
  }
  const appliedKeys = buildAppliedKeySet(syncJob);
  const conflictKeys = buildConflictKeySet(syncJob);
  next.syncQueue = (next.syncQueue || [])
    .filter((operation) => {
      const opKey = `${resolveEntityType(operation.entity_type)}:${operation.entity_id}`;
      return !appliedKeys.has(opKey);
    })
    .map((operation) => {
      const opKey = `${resolveEntityType(operation.entity_type)}:${operation.entity_id}`;
      return conflictKeys.has(opKey)
        ? { ...operation, queue_status: "conflict" }
        : operation;
    });
  next.conflicts = syncJob?.conflicts || [];
  next.syncMeta = {
    ...(next.syncMeta || {}),
    lastPushedAt: syncJob?.updated_at || nowIso(),
    lastStatus: (syncJob?.conflicts || []).length > 0 ? "conflict" : "synced",
    lastError: "",
    removedQueueIds: Array.from(appliedKeys),
  };
  return normalizeSurveyStateShape(next);
}

function parseGeoJsonText(text) {
  const data = JSON.parse(text);
  if (data?.type === "FeatureCollection") {
    const feature = (data.features || []).find((item) =>
      item?.geometry?.type?.includes("Line"),
    );
    if (!feature) throw new Error("GeoJSON file does not contain a route line");
    return normalizeLineGeometry(feature.geometry);
  }
  if (data?.type === "Feature")
    return normalizeLineGeometry(data.geometry || {});
  return normalizeLineGeometry(data);
}

function normalizeLineGeometry(geometry) {
  if (!geometry || typeof geometry !== "object")
    throw new Error("Missing geometry");
  if (geometry.type === "LineString")
    return { type: "LineString", coordinates: geometry.coordinates || [] };
  if (geometry.type === "MultiLineString") {
    const merged = [];
    for (const part of geometry.coordinates || []) merged.push(...part);
    return { type: "LineString", coordinates: merged };
  }
  throw new Error("Only LineString and MultiLineString are supported");
}

function parseGpxText(text) {
  const parser = new DOMParser();
  const xml = parser.parseFromString(text, "application/xml");
  const parserErrors = xml.getElementsByTagName("parsererror");
  if (parserErrors.length > 0) throw new Error("Invalid GPX file");
  const points = Array.from(xml.querySelectorAll("trkpt, rtept")).map(
    (node) => {
      const lon = Number(node.getAttribute("lon"));
      const lat = Number(node.getAttribute("lat"));
      const ele = node.querySelector("ele")?.textContent;
      const coords = [lon, lat];
      if (ele) coords.push(Number(ele));
      return coords;
    },
  );
  if (points.length === 0) throw new Error("GPX file has no route points");
  const pointTimes = Array.from(
    xml.querySelectorAll("trkpt time, rtept time"),
  ).map((node) => node.textContent || "");
  return { geometry: { type: "LineString", coordinates: points }, pointTimes };
}

function haversineMeters(a, b) {
  const r = 6371000;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLon = toRad(b[0] - a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const sinLat = Math.sin(dLat / 2);
  const sinLon = Math.sin(dLon / 2);
  const base =
    sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLon * sinLon;
  return 2 * r * Math.atan2(Math.sqrt(base), Math.sqrt(Math.max(0, 1 - base)));
}

export function lineDistanceMeters(coordinates = []) {
  let total = 0;
  for (let i = 1; i < coordinates.length; i += 1)
    total += haversineMeters(coordinates[i - 1], coordinates[i]);
  return Number(total.toFixed(2));
}

export async function parseRouteFile(file) {
  const text = await file.text();
  const lowerName = (file.name || "").toLowerCase();
  const parsed = lowerName.endsWith(".gpx")
    ? parseGpxText(text)
    : { ...parseGeoJsonText(text), pointTimes: [] };
  return {
    name: file.name.replace(/\.[^.]+$/, ""),
    geometry: parsed.geometry || parsed,
    point_times: parsed.pointTimes || parsed.point_times || [],
    length_m: lineDistanceMeters((parsed.geometry || parsed).coordinates || []),
    source: "imported",
    imported_format: lowerName.endsWith(".gpx") ? "gpx" : "geojson",
    original_filename: file.name,
  };
}

export function buildFeatureCollection(record) {
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: record.geometry || { type: "LineString", coordinates: [] },
        properties: {
          id: record.route_id || record.track_id,
          name: record.name || "",
          route_type: record.route_type || "",
          source: record.source || "",
          length_m: record.length_m || record.distance_m || 0,
        },
      },
    ],
  };
}

export function buildGpx(record) {
  const coords = record?.geometry?.coordinates || [];
  const pointTimes = record?.point_times || [];
  const doc = document.implementation.createDocument(
    "http://www.topografix.com/GPX/1/1",
    "gpx",
  );
  const gpx = doc.documentElement;
  gpx.setAttribute("version", "1.1");
  gpx.setAttribute("creator", "Biodiversity Field Survey Platform");
  const trk = doc.createElement("trk");
  const name = doc.createElement("name");
  name.textContent = record?.name || "track";
  trk.appendChild(name);
  const seg = doc.createElement("trkseg");
  coords.forEach((point, index) => {
    const trkpt = doc.createElement("trkpt");
    trkpt.setAttribute("lon", String(point[0]));
    trkpt.setAttribute("lat", String(point[1]));
    if (point.length > 2) {
      const ele = doc.createElement("ele");
      ele.textContent = String(point[2]);
      trkpt.appendChild(ele);
    }
    if (pointTimes[index]) {
      const time = doc.createElement("time");
      time.textContent = pointTimes[index];
      trkpt.appendChild(time);
    }
    seg.appendChild(trkpt);
  });
  trk.appendChild(seg);
  gpx.appendChild(trk);
  return `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(doc)}`;
}

export function downloadTextFile(
  filename,
  content,
  mimeType = "text/plain;charset=utf-8",
) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function projectXY(point, originLat) {
  const metersPerLon = 111320 * Math.cos((originLat * Math.PI) / 180);
  const metersPerLat = 110540;
  return [point[0] * metersPerLon, point[1] * metersPerLat];
}

function pointToSegmentMeters(point, start, end) {
  const originLat = point[1];
  const [px, py] = projectXY(point, originLat);
  const [ax, ay] = projectXY(start, originLat);
  const [bx, by] = projectXY(end, originLat);
  const dx = bx - ax;
  const dy = by - ay;
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay);
  const t = Math.max(
    0,
    Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)),
  );
  const nearestX = ax + t * dx;
  const nearestY = ay + t * dy;
  return Math.hypot(px - nearestX, py - nearestY);
}

export function snapObservationToRoutes(observationPoint, routes = []) {
  if (!observationPoint || observationPoint.length < 2)
    return { snapped_route_id: "", snapped_distance_m: 0 };
  let nearest = { snapped_route_id: "", snapped_distance_m: Infinity };
  for (const route of routes) {
    const coords = route?.geometry?.coordinates || [];
    for (let idx = 1; idx < coords.length; idx += 1) {
      const distance = pointToSegmentMeters(
        observationPoint,
        coords[idx - 1],
        coords[idx],
      );
      if (distance < nearest.snapped_distance_m) {
        nearest = {
          snapped_route_id: route.route_id || "",
          snapped_distance_m: Number(distance.toFixed(2)),
        };
      }
    }
  }
  if (!Number.isFinite(nearest.snapped_distance_m))
    return { snapped_route_id: "", snapped_distance_m: 0 };
  return nearest;
}

function tileXY(lon, lat, zoom) {
  const cappedLat = Math.max(Math.min(lat, 85.05112878), -85.05112878);
  const latRad = (cappedLat * Math.PI) / 180;
  const n = 2 ** zoom;
  const x = Math.floor(((lon + 180) / 360) * n);
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n,
  );
  return [x, y];
}

function buildTileUrls(tileUrlTemplate, bbox, minZoom, maxZoom) {
  const urls = [];
  if (!tileUrlTemplate || !bbox) return urls;
  for (let zoom = minZoom; zoom <= maxZoom; zoom += 1) {
    const [minX, maxY] = tileXY(bbox.min_lon, bbox.min_lat, zoom);
    const [maxX, minY] = tileXY(bbox.max_lon, bbox.max_lat, zoom);
    for (let x = minX; x <= maxX; x += 1) {
      for (let y = minY; y <= maxY; y += 1) {
        const subdomain = ["a", "b", "c"][(x + y) % 3];
        urls.push(
          tileUrlTemplate
            .replace("{s}", subdomain)
            .replace("{z}", String(zoom))
            .replace("{x}", String(x))
            .replace("{y}", String(y)),
        );
      }
    }
  }
  return urls;
}

export async function prefetchMapTiles({
  tileUrl,
  bbox,
  minZoom,
  maxZoom,
  cacheKey = "default",
  maxTiles = 600,
}) {
  if (typeof caches === "undefined") {
    return { downloaded: 0, total: 0, capped: false };
  }
  const urls = buildTileUrls(tileUrl, bbox, minZoom, maxZoom);
  const selected = urls.slice(0, maxTiles);
  const cache = await caches.open(`${TILE_CACHE_PREFIX}-${cacheKey}`);
  let downloaded = 0;
  for (const url of selected) {
    const request = new Request(url, { mode: "no-cors" });
    const existing = await cache.match(request);
    if (existing) continue;
    try {
      const response = await fetch(request);
      if (response) {
        await cache.put(request, response.clone());
        downloaded += 1;
      }
    } catch {
      // Ignore individual tile failures so partial offline packages still work.
    }
  }
  return {
    downloaded,
    total: urls.length,
    capped: urls.length > selected.length,
  };
}

export function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function createDefaultProject(platformConfig) {
  const resolvedRegionName =
    platformConfig?.study_region?.name_zh ||
    platformConfig?.study_region?.name ||
    "Field Survey Region";
  return {
    project_id: createId("proj"),
    name: `${resolvedRegionName} Field Survey`,
    team_members: [],
    target_taxa: [
      "birds",
      "mammals",
      "amphibians",
      "reptiles",
      "plants",
      "insects",
      "traces",
    ],
    program: DEFAULT_PROGRAM,
    protocol: "",
    jurisdiction: DEFAULT_JURISDICTION,
    region: resolvedRegionName,
    survey_window: {},
    notes: "",
    created_at: nowIso(),
    updated_at: nowIso(),
    sync_state: "queued",
  };
}

export function filterByProject(records, projectId) {
  if (!projectId) return records || [];
  return (records || []).filter((record) => record.project_id === projectId);
}

export function filterBySite(records, siteId) {
  if (!siteId) return records || [];
  return (records || []).filter((record) => record.site_id === siteId);
}

export function filterByProgram(records, program) {
  if (!program) return records || [];
  return (records || []).filter((record) => (record.program || "") === program);
}

export function filterByProtocol(records, protocol) {
  if (!protocol) return records || [];
  return (records || []).filter(
    (record) => (record.protocol || "") === protocol,
  );
}

export function filterByJurisdiction(records, jurisdiction) {
  if (!jurisdiction) return records || [];
  const targetJurisdiction = normalizeJurisdiction(jurisdiction, "");
  return (records || []).filter(
    (record) =>
      normalizeJurisdiction(record.jurisdiction, "") === targetJurisdiction,
  );
}

export function filterSurveyRecords(records, filters = {}) {
  let filtered = records || [];
  if (filters.projectId)
    filtered = filterByProject(filtered, filters.projectId);
  if (filters.siteId) filtered = filterBySite(filtered, filters.siteId);
  if (filters.program) filtered = filterByProgram(filtered, filters.program);
  if (filters.protocol) filtered = filterByProtocol(filtered, filters.protocol);
  if (filters.jurisdiction)
    filtered = filterByJurisdiction(filtered, filters.jurisdiction);
  if (filters.eventId)
    filtered = filtered.filter(
      (record) => (record.event_id || "") === filters.eventId,
    );
  if (filters.designAssetId) {
    filtered = filtered.filter(
      (record) =>
        (record.asset_id || record.design_asset_id || "") ===
        filters.designAssetId,
    );
  }
  return filtered;
}

function normalizeTaxonomyReviewStatus(value) {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function isTaxonomyReviewStatusProblem(status) {
  return [
    "needs_review",
    "pending",
    "rejected",
    "failed",
    "error",
    "stale",
    "mismatch",
  ].includes(status);
}

function isTaxonomyReviewStatusApproved(status) {
  return [
    "approved",
    "ready",
    "released",
    "pass",
    "passed",
    "ok",
    "complete",
    "completed",
  ].includes(status);
}

function compareNumbersDescending(left, right) {
  if (left === right) return 0;
  return left > right ? -1 : 1;
}

function compareStringsDescending(left, right) {
  if (left === right) return 0;
  return left > right ? -1 : 1;
}

function compareSurveyTaxonomyPackages(left, right) {
  const leftReview = normalizeTaxonomyReviewStatus(
    left?.review_status || left?.current_release_review_status,
  );
  const rightReview = normalizeTaxonomyReviewStatus(
    right?.review_status || right?.current_release_review_status,
  );
  const comparisons = [
    compareNumbersDescending(
      left?.is_current_release === true ? 1 : 0,
      right?.is_current_release === true ? 1 : 0,
    ),
    compareNumbersDescending(
      left?.taxonomy_release_id &&
        left?.current_taxonomy_release_id &&
        left.taxonomy_release_id === left.current_taxonomy_release_id
        ? 1
        : 0,
      right?.taxonomy_release_id &&
        right?.current_taxonomy_release_id &&
        right.taxonomy_release_id === right.current_taxonomy_release_id
        ? 1
        : 0,
    ),
    compareNumbersDescending(
      isTaxonomyReviewStatusApproved(leftReview) ? 1 : 0,
      isTaxonomyReviewStatusApproved(rightReview) ? 1 : 0,
    ),
    compareNumbersDescending(
      isTaxonomyReviewStatusProblem(leftReview) ? 0 : 1,
      isTaxonomyReviewStatusProblem(rightReview) ? 0 : 1,
    ),
    compareNumbersDescending(
      left?.count_parity_ok === true ? 1 : 0,
      right?.count_parity_ok === true ? 1 : 0,
    ),
    compareNumbersDescending(left?.checksum ? 1 : 0, right?.checksum ? 1 : 0),
    compareNumbersDescending(
      Number(left?.imported_count || left?.catalog_entry_count || 0),
      Number(right?.imported_count || right?.catalog_entry_count || 0),
    ),
    compareStringsDescending(
      String(left?.server_updated_at || left?.updated_at || ""),
      String(right?.server_updated_at || right?.updated_at || ""),
    ),
    compareStringsDescending(
      String(left?.package_id || left?.taxonomy_release_id || ""),
      String(right?.package_id || right?.taxonomy_release_id || ""),
    ),
  ];
  return comparisons.find((value) => value !== 0) || 0;
}

function uniqueNonEmptyStrings(values = []) {
  return Array.from(
    new Set(
      (values || []).map((value) => String(value || "").trim()).filter(Boolean),
    ),
  );
}

export function deriveSurveyTaxonomyPackageStatus(packages = []) {
  const normalizedPackages = (packages || [])
    .map((item) => normalizeSurveyTaxonomyPackage(item))
    .filter((item) => item && (item.package_id || item.taxonomy_release_id))
    .sort(compareSurveyTaxonomyPackages);
  const activePackage = normalizedPackages[0] || null;
  const currentPackage =
    normalizedPackages.find((item) => item.is_current_release === true) || null;
  const activeReleaseId = String(
    activePackage?.taxonomy_release_id || "",
  ).trim();
  const currentReleaseId = String(
    activePackage?.current_taxonomy_release_id ||
      currentPackage?.taxonomy_release_id ||
      "",
  ).trim();
  const activeChecksum = String(activePackage?.checksum || "").trim();
  const currentReleaseChecksum = String(
    activePackage?.current_release_checksum || currentPackage?.checksum || "",
  ).trim();
  const activeReleaseChecksums = activeReleaseId
    ? uniqueNonEmptyStrings(
        normalizedPackages
          .filter(
            (item) =>
              String(item?.taxonomy_release_id || "").trim() ===
              activeReleaseId,
          )
          .map((item) => item?.checksum),
      )
    : [];
  const hasReleaseMismatch = Boolean(
    activePackage &&
    activeReleaseId &&
    currentReleaseId &&
    activeReleaseId !== currentReleaseId,
  );
  const hasChecksumMismatch = Boolean(
    activePackage &&
    (activeReleaseChecksums.length > 1 ||
      (activeChecksum &&
        currentReleaseChecksum &&
        activeChecksum !== currentReleaseChecksum)),
  );
  const hasCurrentReleaseIssue = Boolean(
    activePackage &&
    (activePackage.is_current_release === false || hasReleaseMismatch),
  );
  const hasParityIssue = Boolean(
    activePackage &&
    (activePackage.count_parity_ok === false ||
      activePackage.current_release_count_parity_ok === false),
  );
  const reviewStatus = normalizeTaxonomyReviewStatus(
    activePackage?.review_status ||
      activePackage?.current_release_review_status,
  );
  const hasReviewIssue = Boolean(
    activePackage && isTaxonomyReviewStatusProblem(reviewStatus),
  );
  const hasGateMetadata = Boolean(
    activePackage &&
    (activePackage.taxonomy_release_id ||
      activePackage.checksum ||
      activePackage.review_status ||
      activePackage.current_taxonomy_release_id ||
      activePackage.current_release_checksum ||
      typeof activePackage.count_parity_ok === "boolean" ||
      typeof activePackage.is_current_release === "boolean" ||
      typeof activePackage.current_release_count_parity_ok === "boolean"),
  );
  const hasRequiredGateMetadata = Boolean(
    activePackage &&
    activeReleaseId &&
    activeChecksum &&
    currentReleaseId &&
    currentReleaseChecksum &&
    (typeof activePackage.count_parity_ok === "boolean" ||
      typeof activePackage.current_release_count_parity_ok === "boolean" ||
      typeof currentPackage?.count_parity_ok === "boolean") &&
    Boolean(
      reviewStatus ||
      normalizeTaxonomyReviewStatus(
        currentPackage?.review_status ||
          currentPackage?.current_release_review_status,
      ),
    ),
  );
  const reasonCodes = [];
  if (!activePackage) {
    reasonCodes.push("missing_package");
  } else {
    if (!hasRequiredGateMetadata) reasonCodes.push("missing_gate_metadata");
    if (hasCurrentReleaseIssue) reasonCodes.push("stale_release");
    if (hasChecksumMismatch) reasonCodes.push("checksum_mismatch");
    if (hasParityIssue) reasonCodes.push("count_parity");
    if (hasReviewIssue) reasonCodes.push("review_status");
  }

  return {
    packages: normalizedPackages,
    activePackage,
    currentPackage,
    currentReleaseId,
    currentReleaseChecksum,
    activeReleaseChecksums,
    hasGateMetadata,
    hasRequiredGateMetadata,
    isCurrentRelease: Boolean(
      activePackage &&
      (activePackage.is_current_release === true ||
        (activeReleaseId &&
          currentReleaseId &&
          activeReleaseId === currentReleaseId) ||
        (!currentReleaseId &&
          currentPackage &&
          activeReleaseId &&
          activeReleaseId ===
            String(currentPackage.taxonomy_release_id || "").trim())),
    ),
    hasCurrentReleaseIssue,
    hasReleaseMismatch,
    hasChecksumMismatch,
    hasParityIssue,
    reviewStatus,
    hasReviewIssue,
    reasonCodes,
    isBlocked: reasonCodes.length > 0,
  };
}

export function replaceEntity(
  state,
  entityType,
  record,
  { select = false } = {},
) {
  const resolvedType = resolveEntityType(entityType);
  const config = ENTITY_CONFIG[resolvedType];
  const normalized = normalizeEntityRecord(
    record,
    config,
    record?.sync_state || "synced",
  );
  if (!config || !normalized) return state;
  const current = normalizeSurveyStateShape(state || emptySurveyState());
  const next = {
    ...current,
    [config.listKey]: mergeEntityCollection(
      current[config.listKey] || [],
      [
        {
          ...normalized,
          sync_state: normalized.sync_state || "synced",
          server_updated_at:
            normalized.updated_at || normalized.server_updated_at || "",
        },
      ],
      resolvedType,
    ),
  };
  next.activeProgram =
    normalized.program || next.activeProgram || DEFAULT_PROGRAM;
  next.activeProtocol = normalized.protocol || next.activeProtocol || "";
  const normalizedSubmodule = normalizeVertebrateSubmodule(
    normalized.submodule || normalized.extra?.submodule || "",
    "",
  );
  if (
    normalized.program === "terrestrial_vertebrates" &&
    normalizedSubmodule &&
    (select || !next.activeVertebrateSubmodule)
  ) {
    next.activeVertebrateSubmodule = normalizedSubmodule;
  }
  next.activeJurisdiction = normalizeJurisdiction(
    normalized.jurisdiction || next.activeJurisdiction || DEFAULT_JURISDICTION,
    DEFAULT_JURISDICTION,
  );
  if (select && resolvedType === "project")
    next.activeProjectId = normalized[config.idField];
  if (select && resolvedType === "site")
    next.activeSiteId = normalized[config.idField];
  if (select && resolvedType === "route")
    next.activeRouteId = normalized[config.idField];
  if (select && resolvedType === "design_asset")
    next.activeDesignAssetId = normalized[config.idField];
  if (select && resolvedType === "event")
    next.activeEventId = normalized[config.idField];
  return normalizeSurveyStateShape(next);
}

export async function serializeAttachment(file) {
  const attachmentId = createAttachmentId();
  const checksum = await computeAttachmentChecksum(file);
  await writeAttachmentRecord(attachmentId, file);
  return normalizeStoredAttachment({
    attachment_id: attachmentId,
    filename: file.name,
    mime_type: file.type || "application/octet-stream",
    byte_size: file.size,
    local_uri: createAttachmentObjectUrl(attachmentId, file),
    storage_kind: WEB_ATTACHMENT_STORAGE_KIND,
    storage_key: attachmentId,
    checksum,
    sync_state: "local_only",
    added_at: nowIso(),
  });
}

function getIndexedDb() {
  if (typeof indexedDB !== "undefined") return indexedDB;
  if (typeof window !== "undefined" && window.indexedDB)
    return window.indexedDB;
  return null;
}

function openAttachmentDb() {
  if (attachmentDbPromise) return attachmentDbPromise;
  const dbApi = getIndexedDb();
  if (!dbApi) {
    return Promise.reject(
      new Error("IndexedDB is unavailable in this browser."),
    );
  }
  attachmentDbPromise = new Promise((resolve, reject) => {
    const request = dbApi.open(ATTACHMENT_DB_NAME, ATTACHMENT_DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ATTACHMENT_STORE)) {
        db.createObjectStore(ATTACHMENT_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error || new Error("Unable to open attachment storage."));
  }).catch((error) => {
    attachmentDbPromise = null;
    throw error;
  });
  return attachmentDbPromise;
}

async function runAttachmentStore(mode, handler) {
  const db = await openAttachmentDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(ATTACHMENT_STORE, mode);
    const store = transaction.objectStore(ATTACHMENT_STORE);
    const request = handler(store);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error || new Error("Attachment storage request failed."));
  });
}

async function writeAttachmentRecord(id, blob) {
  return runAttachmentStore("readwrite", (store) =>
    store.put({
      id,
      blob,
      size: blob?.size || 0,
      type: blob?.type || "application/octet-stream",
      saved_at: nowIso(),
    }),
  );
}

async function readAttachmentRecord(id) {
  return runAttachmentStore("readonly", (store) => store.get(id));
}

function createAttachmentObjectUrl(id, blob) {
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function")
    return "";
  const existing = attachmentUrlCache.get(id);
  if (existing) {
    try {
      URL.revokeObjectURL(existing);
    } catch {
      // Ignore stale object URL cleanup failures.
    }
  }
  const next = URL.createObjectURL(blob);
  attachmentUrlCache.set(id, next);
  return next;
}

function dataUrlToBlob(dataUrl) {
  const match = String(dataUrl || "").match(/^data:(.*?);base64,(.*)$/);
  if (!match) throw new Error("Unsupported legacy attachment encoding.");
  const mimeType = match[1] || "application/octet-stream";
  const binary = atob(match[2] || "");
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mimeType });
}

async function migrateAttachmentToIndexedDb(attachment) {
  const normalized = normalizeStoredAttachment(attachment);
  if (!normalized) return null;
  if (hasDurableAttachmentReference(normalized)) {
    return normalizeStoredAttachment(normalized, { persistLocalUri: false });
  }
  const localUri = normalized.local_uri || "";
  if (!isDataUrl(localUri)) return normalized;
  const mediaId =
    normalized.attachment_id || normalized.media_id || createAttachmentId();
  const blob = dataUrlToBlob(localUri);
  const checksum =
    normalized.checksum || (await computeAttachmentChecksum(blob));
  await writeAttachmentRecord(mediaId, blob);
  return normalizeStoredAttachment(
    {
      ...normalized,
      attachment_id: mediaId,
      mime_type:
        normalized.mime_type ||
        normalized.type ||
        blob.type ||
        "application/octet-stream",
      byte_size: normalized.byte_size || normalized.size || blob.size || 0,
      storage_kind: WEB_ATTACHMENT_STORAGE_KIND,
      storage_key: mediaId,
      checksum,
    },
    { persistLocalUri: false },
  );
}

function queueLegacyAttachmentMigration() {
  if (typeof window === "undefined") return;
  if (legacyAttachmentMigrationPromise) return;
  legacyAttachmentMigrationPromise = Promise.resolve()
    .then(async () => {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const current = normalizeSurveyStateShape(
        safeJsonParse(raw, emptySurveyState()),
      );
      if (
        !current.mediaInbox.some(
          (attachment) =>
            isDataUrl(attachment?.local_uri) &&
            !hasDurableAttachmentReference(attachment),
        )
      ) {
        return;
      }
      const migratedInbox = [];
      for (const attachment of current.mediaInbox) {
        migratedInbox.push(await migrateAttachmentToIndexedDb(attachment));
      }
      const migrated = normalizeSurveyStateShape(
        {
          ...current,
          mediaInbox: migratedInbox.filter(Boolean),
        },
        { persistAttachmentUris: false },
      );
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated));
    })
    .catch(() => {
      // Ignore background migration failures and leave legacy data in place.
    })
    .finally(() => {
      legacyAttachmentMigrationPromise = null;
    });
}

export async function restoreDraftAttachment(attachment) {
  const normalized = normalizeStoredAttachment(attachment);
  if (!normalized || !hasDurableAttachmentReference(normalized))
    return normalized;
  const cachedUrl = attachmentUrlCache.get(normalized.storage_key);
  if (cachedUrl) {
    return { ...normalized, local_uri: cachedUrl };
  }
  const record = await readAttachmentRecord(normalized.storage_key);
  if (!record?.blob) {
    return { ...normalized, local_uri: "" };
  }
  return {
    ...normalized,
    local_uri: createAttachmentObjectUrl(normalized.storage_key, record.blob),
  };
}

export async function restoreDraftAttachments(attachments = []) {
  return Promise.all(
    (attachments || []).map((attachment) => restoreDraftAttachment(attachment)),
  );
}
