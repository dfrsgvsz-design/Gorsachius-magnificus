import axios from "axios";
import { Capacitor } from "@capacitor/core";
import { toArray } from "../components/fieldops/fieldOpsUtils";
import * as localSurvey from "./localSurveyService.js";
import { getAdminApiToken } from "./adminAuth.js";

const DEFAULT_API_BASE = "/api";
const DEFAULT_WS_PATH = "/ws";

function joinBasePath(basePath, nextSegment) {
  const normalizedBase =
    basePath === "/" ? "" : String(basePath || "").replace(/\/+$/, "");
  const normalizedSegment = String(nextSegment || "").replace(/^\/+/, "");
  return `${normalizedBase}/${normalizedSegment}`.replace(/\/{2,}/g, "/");
}

export function resolveConfiguredApiBases(rawBaseUrl) {
  const configuredBaseUrl = String(rawBaseUrl || "").trim();
  if (!configuredBaseUrl) return null;

  let parsed;
  try {
    parsed = new URL(configuredBaseUrl);
  } catch {
    console.warn(
      "[api] Ignoring VITE_API_BASE_URL because it is not a valid absolute URL:",
      configuredBaseUrl,
    );
    return null;
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    console.warn(
      "[api] Ignoring VITE_API_BASE_URL because it must use http or https:",
      configuredBaseUrl,
    );
    return null;
  }

  const normalizedPath =
    parsed.pathname === "/" ? "" : parsed.pathname.replace(/\/+$/, "");
  const lowerPath = normalizedPath.toLowerCase();
  const apiPath = lowerPath.endsWith("/api")
    ? normalizedPath
    : joinBasePath(normalizedPath, "api");
  const wsPath = lowerPath.endsWith("/api")
    ? `${normalizedPath.slice(0, -4) || ""}${DEFAULT_WS_PATH}`
    : joinBasePath(normalizedPath, "ws");
  const wsProtocol = parsed.protocol === "https:" ? "wss:" : "ws:";

  return {
    apiBase: `${parsed.origin}${apiPath || DEFAULT_API_BASE}`,
    wsBase: `${wsProtocol}//${parsed.host}${wsPath || DEFAULT_WS_PATH}`,
  };
}

export function resolveApiTransportConfig(
  rawBaseUrl,
  isNativePlatform = false,
) {
  const configuredBases = resolveConfiguredApiBases(rawBaseUrl);
  const useNativeApiBase = Boolean(configuredBases && isNativePlatform);

  return {
    configuredBases,
    useNativeApiBase,
    apiBase: useNativeApiBase ? configuredBases.apiBase : DEFAULT_API_BASE,
    wsBase: useNativeApiBase ? configuredBases.wsBase : null,
  };
}

export function resolveBackendAssetUrl(pathOrUrl) {
  const value = String(pathOrUrl || "").trim();
  if (!value || !isNativePlatform || !configuredApiBases?.apiBase) return value;

  try {
    return new URL(value).toString();
  } catch {
    const apiBase = new URL(configuredApiBases.apiBase);
    const normalizedPath = value.startsWith("/") ? value : `/${value}`;
    return `${apiBase.origin}${normalizedPath}`;
  }
}

function getDefaultWebSocketBase() {
  return `${window.location.origin.replace(/^http/i, "ws")}${DEFAULT_WS_PATH}`;
}

const apiTransportConfig = resolveApiTransportConfig(
  import.meta.env.VITE_API_BASE_URL,
  Capacitor.isNativePlatform(),
);
const configuredApiBases = apiTransportConfig.configuredBases;
const USE_NATIVE_API_BASE = apiTransportConfig.useNativeApiBase;
const API_BASE = apiTransportConfig.apiBase;
const isNativePlatform = Capacitor.isNativePlatform();
const hasNativeApiBase = Boolean(configuredApiBases?.apiBase);
const configuredRawApiBase = String(import.meta.env.VITE_API_BASE_URL || "").trim();
const isProdBuild = import.meta.env.PROD;

function isLocalDevHost(hostname) {
  const normalizedHostname = String(hostname || "").toLowerCase();
  return ["localhost", "127.0.0.1", "::1"].includes(normalizedHostname);
}

function getApiBaseValidationError(rawApiBase) {
  if (!rawApiBase) return "";
  try {
    const parsed = new URL(rawApiBase);
    if (
      isProdBuild &&
      parsed.protocol === "http:" &&
      !isLocalDevHost(parsed.hostname)
    ) {
      return "Production VITE_API_BASE_URL must use https:// (except localhost for local testing).";
    }
    return "";
  } catch {
    return "VITE_API_BASE_URL must be a valid absolute URL.";
  }
}

const apiBaseValidationError = getApiBaseValidationError(configuredRawApiBase);
const nativeApiConfigError =
  isNativePlatform && !hasNativeApiBase
    ? "Native build requires VITE_API_BASE_URL (absolute https://... URL) to reach backend APIs."
    : "";
const runtimeApiConfigError = nativeApiConfigError || apiBaseValidationError;

// Hybrid-local mode: native APK ships without a remote backend URL on purpose,
// because all CRUD lives in the on-device SQLite via Capacitor plugins. The
// rest of the UI uses this flag to skip backend health probes and to render
// "Local mode" instead of "Backend offline" in the status indicator.
export const IS_HYBRID_LOCAL_MODE = isNativePlatform && !hasNativeApiBase;

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
});

// B19: destructive endpoints (DELETE / restore) are guarded server-side by
// X-Admin-Token derived from the AdminGate PIN. Attach it whenever the admin
// has unlocked this session; harmless no-op for all other requests.
api.interceptors.request.use((config) => {
  const adminToken = getAdminApiToken();
  if (adminToken) {
    config.headers = config.headers || {};
    config.headers["X-Admin-Token"] = adminToken;
  }
  return config;
});

if (runtimeApiConfigError) {
  // Hybrid-local builds run fully offline against on-device SQLite, so a
  // missing VITE_API_BASE_URL is not necessarily an error at boot — it only
  // matters when the user explicitly triggers a sync or export. Surface it as
  // a warning for developers; the actual axios request will fail naturally
  // with a descriptive network error if the user invokes a backend call.
  console.warn(`[api] ${runtimeApiConfigError}`);
}

export function getApiErrorMessage(error, fallback = "Request failed.") {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return (
      detail
        .map((item) => item?.msg || item?.message || String(item))
        .join(" | ") || fallback
    );
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof error?.message === "string" && error.message.trim())
    return error.message;
  return fallback;
}

export function normalizeHealthStatus(data = {}) {
  const numSpeciesModel = data.num_species_model ?? 0;
  const numSpeciesDb = data.num_species_db ?? 0;
  const warnings = Array.isArray(data.warnings) ? data.warnings : [];
  const runtimeState =
    data.runtime_state ||
    (warnings.some((item) => item.level === "error")
      ? "error"
      : warnings.some((item) => item.level === "warning")
        ? "warning"
        : "ready");

  return {
    ...data,
    num_species_model: numSpeciesModel,
    num_species_db: numSpeciesDb,
    warnings,
    runtime_state: runtimeState,
    species_coverage: data.species_coverage || {
      model_species: numSpeciesModel,
      database_species: numSpeciesDb,
      missing_from_model: Math.max(0, numSpeciesDb - numSpeciesModel),
      coverage_ratio: numSpeciesDb ? numSpeciesModel / numSpeciesDb : 1,
    },
  };
}

export function normalizeDeviceType(rawType) {
  return (
    {
      aru: "generic",
      generic: "generic",
      other: "generic",
      "raspberry pi": "raspberry_pi",
      raspberry_pi: "raspberry_pi",
      raspberrypi: "raspberry_pi",
      audiomoth: "audiomoth",
      "audio moth": "audiomoth",
      songmeter: "song_meter",
      "song meter": "song_meter",
      mobile: "mobile",
      jetson: "generic",
    }[
      String(rawType || "generic")
        .trim()
        .toLowerCase()
    ] || "generic"
  );
}

export function normalizeDeviceRecord(device = {}) {
  return {
    ...device,
    type: device.type || device.device_type,
    online: ["online", "recording"].includes(device.status),
  };
}

export function normalizeDeviceMarker(marker = {}) {
  return {
    ...marker,
    latitude: marker.latitude ?? marker.lat,
    longitude: marker.longitude ?? marker.lng,
    type: marker.type || marker.device_type,
    online: ["online", "recording"].includes(marker.status),
  };
}

export function normalizeMonitoringSession(session = {}) {
  return {
    ...session,
    species_count: session.species_count ?? session.unique_species ?? 0,
    detection_count: session.detection_count ?? session.total_detections ?? 0,
  };
}

export function normalizeMonitoringDashboard(data = {}) {
  const activeSessions = data.sessions?.active ?? 0;
  return {
    ...data,
    total_detections: data.detections?.total ?? 0,
    unique_species: data.detections?.unique_species ?? 0,
    mode: activeSessions > 0 ? "active" : "idle",
  };
}

export function normalizeEmbeddingStats(data = {}) {
  return {
    ...data,
    total_embeddings: data.total_embeddings ?? data.total_records ?? 0,
    embedding_dim: data.embedding_dim ?? data.dimensions ?? "--",
  };
}

function uniqueStrings(values = []) {
  return Array.from(
    new Set(
      (Array.isArray(values) ? values : [values])
        .flatMap((value) => (Array.isArray(value) ? value : [value]))
        .map((value) => String(value || "").trim())
        .filter(Boolean),
    ),
  );
}

function normalizeSurveyFieldGroups(rawGroups, fallbackRequired = []) {
  if (rawGroups && typeof rawGroups === "object" && !Array.isArray(rawGroups)) {
    return {
      required: uniqueStrings(rawGroups.required),
      optional: uniqueStrings(rawGroups.optional),
      effort: uniqueStrings(rawGroups.effort),
    };
  }

  return {
    required: uniqueStrings(fallbackRequired),
    optional: [],
    effort: [],
  };
}

function firstNonEmptyString(...values) {
  for (const value of values) {
    const normalized = String(value || "").trim();
    if (normalized) return normalized;
  }
  return "";
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    if (value === "" || value == null) continue;
    const normalized = Number(value);
    if (Number.isFinite(normalized)) return normalized;
  }
  return 0;
}

function firstDefinedBoolean(...values) {
  for (const value of values) {
    if (typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (value === 1) return true;
      if (value === 0) return false;
    }
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (
        ["true", "1", "yes", "y", "ok", "pass", "passed", "current"].includes(
          normalized,
        )
      )
        return true;
      if (
        ["false", "0", "no", "n", "fail", "failed", "stale"].includes(
          normalized,
        )
      )
        return false;
    }
  }
  return undefined;
}

function normalizeStructuredNames(raw = {}) {
  const names = raw?.names && typeof raw.names === "object" ? raw.names : {};
  const chineseNames = uniqueStrings([
    raw.chinese_name,
    raw.chinese,
    raw.common_name_zh,
    raw.simplified_chinese_name,
    raw.traditional_chinese_name,
    names.zh_cn,
    names.zh_tw,
    names.zh,
  ]);
  const englishNames = uniqueStrings([
    raw.english_name,
    raw.english,
    raw.english_common_name,
    raw.common_name,
    names.en,
  ]);
  const scientificNames = uniqueStrings([
    raw.scientific_name,
    raw.scientific,
    names.scientific,
  ]);

  return {
    names,
    chineseNames,
    englishNames,
    scientificNames,
    synonyms: uniqueStrings([raw.synonyms, names.synonyms]),
  };
}

export function normalizeSurveyProtocolDefinition(rawProtocol = {}) {
  const protocolId = firstNonEmptyString(
    rawProtocol.protocol_id,
    rawProtocol.protocol,
  );
  const eventFields = normalizeSurveyFieldGroups(
    rawProtocol.event_fields,
    rawProtocol.required_event_fields,
  );
  const recordFields = normalizeSurveyFieldGroups(
    rawProtocol.record_fields,
    rawProtocol.required_record_fields,
  );

  return {
    ...rawProtocol,
    protocol_id: protocolId,
    protocol: protocolId,
    display_name: firstNonEmptyString(
      rawProtocol.display_name,
      rawProtocol.label,
      protocolId,
    ),
    label: firstNonEmptyString(
      rawProtocol.label,
      rawProtocol.display_name,
      protocolId,
    ),
    jurisdictions: uniqueStrings(rawProtocol.jurisdictions),
    design_asset_types: uniqueStrings(rawProtocol.design_asset_types),
    required_event_fields: eventFields.required,
    required_record_fields: recordFields.required,
    event_fields: eventFields,
    record_fields: recordFields,
    has_structured_event_fields: Boolean(
      rawProtocol.event_fields &&
      typeof rawProtocol.event_fields === "object" &&
      !Array.isArray(rawProtocol.event_fields),
    ),
    has_structured_record_fields: Boolean(
      rawProtocol.record_fields &&
      typeof rawProtocol.record_fields === "object" &&
      !Array.isArray(rawProtocol.record_fields),
    ),
  };
}

export function normalizeSurveyTaxonomyEntry(rawEntry = {}) {
  const normalizedNames = normalizeStructuredNames(rawEntry);
  const taxonId = firstNonEmptyString(
    rawEntry.internal_taxon_id,
    rawEntry.taxon_id,
    rawEntry.species_id,
    rawEntry.id,
  );
  const scientificName = firstNonEmptyString(
    ...normalizedNames.scientificNames,
  );
  const chineseName = firstNonEmptyString(...normalizedNames.chineseNames);
  const englishName = firstNonEmptyString(...normalizedNames.englishNames);

  return {
    ...rawEntry,
    internal_taxon_id: taxonId,
    taxon_id: firstNonEmptyString(rawEntry.taxon_id, taxonId),
    species_id: firstNonEmptyString(rawEntry.species_id, taxonId),
    scientific_name: scientificName,
    scientific: firstNonEmptyString(rawEntry.scientific, scientificName),
    chinese_name: chineseName,
    chinese: firstNonEmptyString(rawEntry.chinese, chineseName),
    english_name: englishName,
    english: firstNonEmptyString(rawEntry.english, englishName),
    taxon_group: firstNonEmptyString(rawEntry.taxon_group, rawEntry.group),
    display_name: firstNonEmptyString(
      chineseName,
      englishName,
      scientificName,
      taxonId,
    ),
    names: normalizedNames.names,
    chinese_names: normalizedNames.chineseNames,
    english_names: normalizedNames.englishNames,
    scientific_names: normalizedNames.scientificNames,
    synonyms: normalizedNames.synonyms,
  };
}

export function normalizeSurveyTaxonomyPackage(rawPackage = {}) {
  const taxonomyReleaseId = firstNonEmptyString(
    rawPackage.taxonomy_release_id,
    rawPackage.release_id,
    rawPackage.releaseId,
    rawPackage.source_release_id,
  );
  const sourceManifestVersion = firstNonEmptyString(
    rawPackage.source_manifest_version,
    rawPackage.manifest_version,
    rawPackage.source_manifest,
    rawPackage.asset_package_version,
  );
  const expectedCount = firstFiniteNumber(
    rawPackage.expected_count,
    rawPackage.expected_species_count,
    rawPackage.expected_taxon_count,
    rawPackage.expected_entries,
  );
  const importedCount = firstFiniteNumber(
    rawPackage.imported_count,
    rawPackage.imported_species_count,
    rawPackage.imported_taxon_count,
    rawPackage.imported_entries,
    rawPackage.catalog_entry_count,
    rawPackage.catalog_count,
  );
  const packageChecksum = firstNonEmptyString(
    rawPackage.checksum,
    rawPackage.package_checksum,
    rawPackage.manifest_checksum,
    rawPackage.sha256,
  );
  const currentTaxonomyReleaseId = firstNonEmptyString(
    rawPackage.current_taxonomy_release_id,
    rawPackage.current_release_id,
    rawPackage.current_release?.taxonomy_release_id,
    rawPackage.current_release?.release_id,
  );
  const currentReleaseChecksum = firstNonEmptyString(
    rawPackage.current_release_checksum,
    rawPackage.current_checksum,
    rawPackage.current_release?.checksum,
    rawPackage.current_release?.package_checksum,
    rawPackage.current_release?.manifest_checksum,
  );
  const countParityOk = firstDefinedBoolean(
    rawPackage.count_parity_ok,
    rawPackage.taxonomy_count_parity_ok,
    rawPackage.counts_match,
    expectedCount > 0 ? importedCount === expectedCount : undefined,
  );
  const currentReleaseCountParityOk = firstDefinedBoolean(
    rawPackage.current_release_count_parity_ok,
    rawPackage.taxonomy_count_parity_ok,
    rawPackage.current_release?.taxonomy_count_parity_ok,
    rawPackage.current_release?.count_parity_ok,
  );
  const reviewStatus = firstNonEmptyString(
    rawPackage.review_status,
    rawPackage.release_review_status,
    rawPackage.import_review_status,
    rawPackage.status,
  );
  const currentReleaseReviewStatus = firstNonEmptyString(
    rawPackage.current_release_review_status,
    rawPackage.current_release?.review_status,
    rawPackage.current_release?.release_review_status,
    rawPackage.current_release?.import_review_status,
  );
  const isCurrentRelease = firstDefinedBoolean(
    rawPackage.is_current_release,
    rawPackage.current_release,
    rawPackage.is_current,
    rawPackage.current,
  );

  return {
    ...rawPackage,
    package_id: firstNonEmptyString(
      rawPackage.package_id,
      rawPackage.asset_package_id,
      rawPackage.taxonomy_package_id,
      taxonomyReleaseId,
    ),
    taxonomy_package_id: firstNonEmptyString(
      rawPackage.taxonomy_package_id,
      rawPackage.package_id,
      rawPackage.asset_package_id,
      taxonomyReleaseId,
    ),
    asset_package_id: firstNonEmptyString(
      rawPackage.asset_package_id,
      rawPackage.package_id,
      rawPackage.taxonomy_package_id,
      taxonomyReleaseId,
    ),
    taxonomy_release_id: taxonomyReleaseId,
    source_manifest_version: sourceManifestVersion,
    label: firstNonEmptyString(
      rawPackage.label,
      rawPackage.display_name,
      rawPackage.package_id,
      rawPackage.asset_package_id,
      taxonomyReleaseId,
    ),
    display_name: firstNonEmptyString(
      rawPackage.display_name,
      rawPackage.label,
      rawPackage.package_id,
      rawPackage.asset_package_id,
      taxonomyReleaseId,
    ),
    protocols: uniqueStrings(
      rawPackage.protocols ||
        rawPackage.supported_protocols ||
        rawPackage.protocol,
    ),
    submodule: firstNonEmptyString(rawPackage.submodule),
    submodules: uniqueStrings(rawPackage.submodules || rawPackage.submodule),
    program: firstNonEmptyString(rawPackage.program),
    jurisdiction: firstNonEmptyString(rawPackage.jurisdiction),
    region: firstNonEmptyString(rawPackage.region),
    catalog_count:
      Number(rawPackage.catalog_count ?? rawPackage.catalog_entry_count ?? 0) ||
      0,
    catalog_entry_count:
      Number(rawPackage.catalog_entry_count ?? rawPackage.catalog_count ?? 0) ||
      0,
    expected_count: expectedCount,
    imported_count: importedCount,
    count_parity_ok: countParityOk,
    review_status: reviewStatus,
    is_current_release: isCurrentRelease,
    checksum: packageChecksum,
    current_taxonomy_release_id: currentTaxonomyReleaseId,
    current_release_checksum: currentReleaseChecksum,
    current_release_count_parity_ok: currentReleaseCountParityOk,
    current_release_review_status: currentReleaseReviewStatus,
    exhaustive_species_content: Boolean(
      rawPackage.exhaustive_species_content ?? rawPackage.exhaustive,
    ),
    exhaustive: Boolean(
      rawPackage.exhaustive ?? rawPackage.exhaustive_species_content,
    ),
    seed_only: Boolean(rawPackage.seed_only),
  };
}

function normalizeSurveyProtocolResponse(data = {}) {
  const protocols = toArray(data?.protocols).map((item) =>
    normalizeSurveyProtocolDefinition(item),
  );
  return {
    ...data,
    total: data?.total ?? protocols.length,
    protocols,
  };
}

function normalizeSurveyTaxonomySearchResponse(data = {}) {
  const rawResults = toArray(
    data?.results ??
      data?.entries ??
      data?.taxa ??
      data?.taxonomy ??
      data?.species ??
      data?.catalog,
  );
  const results = rawResults.map((item) => normalizeSurveyTaxonomyEntry(item));
  return {
    ...data,
    total: data?.total ?? results.length,
    results,
  };
}

function normalizeSurveyTaxonomyPackageResponse(data = {}) {
  const rawPackages = toArray(
    data?.packages ??
      data?.taxonomy_packages ??
      data?.taxonomyPackages ??
      data?.taxon_packages,
  );
  const packages = rawPackages.map((item) =>
    normalizeSurveyTaxonomyPackage(item),
  );
  return {
    ...data,
    total: data?.total ?? packages.length,
    packages,
    taxonomy_packages: packages,
  };
}

export async function analyzeAudio(file, topK = 5, confidenceThreshold = 0.1) {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await api.post(
    `/analyze?top_k=${topK}&confidence_threshold=${confidenceThreshold}`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return resp.data;
}

export async function getSpeciesList() {
  const resp = await api.get("/species");
  return resp.data;
}

export async function getSpeciesRecordings(
  scientificName,
  { songType, country, maxResults = 12 } = {},
) {
  const params = { max_results: maxResults };
  if (songType) params.song_type = songType;
  if (country) params.country = country;
  const resp = await api.get(
    `/species/${encodeURIComponent(scientificName)}/recordings`,
    { params },
  );
  return resp.data;
}

export async function getSurveySites() {
  const resp = await api.get("/surveys");
  return resp.data;
}

export async function createSurveySite(data) {
  const resp = await api.post("/surveys", data);
  return resp.data;
}

export async function removeSurveySite(siteName) {
  const resp = await api.delete(`/surveys/${encodeURIComponent(siteName)}`);
  return resp.data;
}

export async function getEBirdKeyStatus() {
  const resp = await api.get("/ebird/key-status");
  return resp.data;
}

export async function setEBirdKey(key) {
  const resp = await api.post("/ebird/key", { key });
  return resp.data;
}

export async function getEBirdRegions() {
  const resp = await api.get("/ebird/regions");
  return resp.data;
}

export async function getEBirdRecentObs(
  regionCode,
  back = 14,
  maxResults = 50,
) {
  const resp = await api.get(`/ebird/recent/${regionCode}`, {
    params: { back, max_results: maxResults },
  });
  return resp.data;
}

export async function getEBirdNotableObs(regionCode, back = 14) {
  const resp = await api.get(`/ebird/notable/${regionCode}`, {
    params: { back },
  });
  return resp.data;
}

export async function getEBirdHotspots(regionCode) {
  const resp = await api.get(`/ebird/hotspots/${regionCode}`);
  return resp.data;
}

export async function getEBirdSpeciesList(regionCode) {
  const resp = await api.get(`/ebird/species-list/${regionCode}`);
  return resp.data;
}

export async function getComprehensiveBiodiversity(siteName) {
  const params = siteName ? { site_name: siteName } : {};
  const resp = await api.get("/biodiversity/comprehensive", { params });
  return resp.data;
}

export async function getPreSurveySpecies(regionCode, siteName) {
  const params = siteName ? { site_name: siteName } : {};
  const resp = await api.get(`/survey/pre-survey/${regionCode}`, { params });
  return resp.data;
}

export async function batchScanDirectory(
  directory,
  deviceId,
  siteName,
  cameraSerial,
) {
  const resp = await api.post("/batch/scan", {
    directory,
    device_id: deviceId,
    site_name: siteName,
    camera_serial: cameraSerial,
    recursive: true,
  });
  return resp.data;
}

export async function analyzeTrapImage(file, siteName) {
  const formData = new FormData();
  formData.append("file", file);
  const params = {};
  if (siteName) params.site_name = siteName;
  const resp = await api.post("/trap/analyze", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    params,
  });
  return resp.data;
}

export async function getTrapRecords() {
  const resp = await api.get("/trap/records");
  return resp.data;
}

export async function analyzeImage(file, siteName, notes) {
  const formData = new FormData();
  formData.append("file", file);
  const params = {};
  if (siteName) params.site_name = siteName;
  if (notes) params.notes = notes;
  const resp = await api.post("/image/analyze", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    params,
  });
  return resp.data;
}

export async function getImageRecords() {
  const resp = await api.get("/image/records");
  return resp.data;
}

export async function compareSpectrograms(fileA, fileB) {
  const formData = new FormData();
  formData.append("file_a", fileA);
  formData.append("file_b", fileB);
  const resp = await api.post("/compare-spectrograms", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return resp.data;
}

export async function searchXenoCanto(
  species,
  country = "China",
  maxResults = 20,
) {
  const resp = await api.post("/search-xc", {
    species,
    country,
    max_results: maxResults,
  });
  return resp.data;
}

export async function compareSites(sites) {
  const resp = await api.post("/compare-sites", { sites });
  return resp.data;
}

export async function getPlatformConfig() {
  const resp = await api.get("/config");
  return resp.data;
}

export async function getHealthStatus() {
  const resp = await api.get("/health");
  return normalizeHealthStatus(resp.data || {});
}

export async function getPaperContext() {
  const resp = await api.get("/paper-context");
  return resp.data;
}

// Field Survey
function buildSurveyParams(selectorOrProjectId = "", siteId = "") {
  if (
    selectorOrProjectId &&
    typeof selectorOrProjectId === "object" &&
    !Array.isArray(selectorOrProjectId)
  ) {
    return Object.fromEntries(
      Object.entries(selectorOrProjectId).filter(
        ([, value]) => value !== "" && value != null,
      ),
    );
  }
  const params = {};
  if (selectorOrProjectId) params.project_id = selectorOrProjectId;
  if (siteId) params.site_id = siteId;
  return params;
}

// Backed by on-device SQLite via localSurveyService. The original HTTP
// route remains on the server for multi-device sync via pushSurveySync /
// pullSurveySync — direct CRUD calls no longer go over the wire.
export async function getSurveyProjects(filters = {}) {
  return localSurvey.getSurveyProjects(filters);
}

export async function createSurveyProject(data) {
  return localSurvey.createSurveyProject(data);
}

export async function deleteSurveyProject(projectId) {
  return localSurvey.deleteSurveyProject(projectId);
}

export async function getFieldSurveySites(projectId = "") {
  return localSurvey.getFieldSurveySites(projectId);
}

export async function createFieldSurveySite(data) {
  return localSurvey.createFieldSurveySite(data);
}

export async function deleteFieldSurveySite(siteId) {
  return localSurvey.deleteFieldSurveySite(siteId);
}

export async function getSurveyRoutes(projectId = "", siteId = "") {
  return localSurvey.getSurveyRoutes(projectId, siteId);
}

export async function createSurveyRoute(data) {
  return localSurvey.createSurveyRoute(data);
}

export async function deleteSurveyRoute(routeId) {
  return localSurvey.deleteSurveyRoute(routeId);
}

export async function importSurveyRoute(
  file,
  { projectId = "", siteId = "", name = "", routeType = "transect" } = {},
) {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await api.post("/surveys/routes/import", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    params: {
      project_id: projectId,
      site_id: siteId,
      name,
      route_type: routeType,
    },
  });
  return resp.data;
}

export async function exportSurveyRoute(routeId, format = "geojson") {
  const resp = await api.get(
    `/surveys/routes/${encodeURIComponent(routeId)}/export`,
    {
      params: { format },
      responseType: "blob",
    },
  );
  return {
    blob: resp.data,
    filename:
      resp.headers["content-disposition"]?.split("filename=")[1] ||
      `route.${format}`,
    contentType: resp.headers["content-type"] || "application/octet-stream",
  };
}

export async function getSurveyRouteSummary(routeId) {
  const resp = await api.get(
    `/surveys/routes/${encodeURIComponent(routeId)}/summary`,
  );
  return resp.data;
}

export async function exportSurveyRouteReport(routeId, format = "json") {
  const resp = await api.get(
    `/surveys/routes/${encodeURIComponent(routeId)}/report/export`,
    {
      params: { format },
      responseType: "blob",
    },
  );
  const disposition = resp.headers["content-disposition"] || "";
  const filenameMatch = disposition.match(
    /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i,
  );
  const filename = decodeURIComponent(
    filenameMatch?.[1] || filenameMatch?.[2] || `route-report.${format}`,
  );
  return {
    blob: resp.data,
    filename,
    contentType: resp.headers["content-type"] || "application/octet-stream",
  };
}

export async function getSurveyObservations(projectId = "", siteId = "") {
  return localSurvey.getSurveyObservations(projectId, siteId);
}

export async function createSurveyObservation(data) {
  return localSurvey.createSurveyObservation(data);
}

export async function deleteSurveyObservation(observationId) {
  return localSurvey.deleteSurveyObservation(observationId);
}

export async function getSurveyTracks(projectId = "", siteId = "") {
  return localSurvey.getSurveyTracks(projectId, siteId);
}

export async function createSurveyTrack(data) {
  return localSurvey.createSurveyTrack(data);
}

export async function createOfflineMapPackage(data) {
  return localSurvey.createOfflineMapPackage(data);
}

export async function pushSurveySync(data) {
  const resp = await api.post("/surveys/sync/push", data);
  return resp.data;
}

export async function pullSurveySync(since = "") {
  const resp = await api.get("/surveys/sync/pull", {
    params: buildSurveyParams(typeof since === "string" ? { since } : since),
  });
  return resp.data;
}

export async function getSurveyProtocols(filters = {}) {
  const resp = await api.get("/surveys/protocols", {
    params: buildSurveyParams(filters),
  });
  return normalizeSurveyProtocolResponse(resp.data || {});
}

export async function getSurveyTaxonomyPackages(filters = {}) {
  const resp = await api.get("/surveys/taxonomy/packages", {
    params: buildSurveyParams(filters),
  });
  return normalizeSurveyTaxonomyPackageResponse(resp.data || {});
}

export async function searchSurveyTaxonomy(filters = {}) {
  const params = buildSurveyParams(filters);
  if (params.limit != null) {
    const limit = Number(params.limit);
    if (Number.isFinite(limit)) {
      params.limit = Math.max(1, Math.min(Math.trunc(limit), 200));
    }
  }
  if (params.taxon_group && !params.submodule) {
    params.submodule = params.taxon_group;
  }
  if (params.query && !params.q) {
    params.q = params.query;
  }
  if (params.q && !params.query) {
    params.query = params.q;
  }
  const resp = await api.get("/surveys/taxonomy/search", { params });
  return normalizeSurveyTaxonomySearchResponse(resp.data || {});
}

export async function getSurveyDesignAssets(filters = {}) {
  return localSurvey.getSurveyDesignAssets(filters);
}

export async function createSurveyDesignAsset(data) {
  return localSurvey.createSurveyDesignAsset(data);
}

export async function getSurveyEvents(filters = {}) {
  return localSurvey.getSurveyEvents(filters);
}

export async function createSurveyEvent(data) {
  return localSurvey.createSurveyEvent(data);
}

export async function createSurveyExportJob(jurisdiction, data = {}) {
  return localSurvey.createSurveyExportJob(jurisdiction, data);
}

export async function getXCKeyStatus() {
  const resp = await api.get("/xc-key-status");
  return resp.data;
}

export async function setXCKey(key) {
  const resp = await api.post("/xc-key", { key });
  return resp.data;
}

// Device Management
export async function getDevices() {
  const resp = await api.get("/devices");
  return (resp.data?.devices || []).map(normalizeDeviceRecord);
}

export async function getOnlineDevices() {
  const resp = await api.get("/devices/online");
  return (resp.data?.devices || []).map(normalizeDeviceRecord);
}

export async function getDeviceMap() {
  const resp = await api.get("/devices/map");
  return (resp.data?.markers || []).map(normalizeDeviceMarker);
}

export async function registerDevice(deviceData) {
  const resp = await api.post("/devices/register", {
    name: deviceData.name,
    device_type: normalizeDeviceType(
      deviceData.device_type || deviceData.type || "generic",
    ),
    location_name: deviceData.location_name || deviceData.device_id || "",
    latitude: deviceData.latitude ?? 0,
    longitude: deviceData.longitude ?? 0,
    altitude: deviceData.altitude ?? 0,
    sample_rate: deviceData.sample_rate ?? 22050,
    channels: deviceData.channels ?? 1,
    bit_depth: deviceData.bit_depth ?? 16,
    metadata: {
      ...(deviceData.metadata || {}),
      ...(deviceData.device_id
        ? { external_device_id: deviceData.device_id }
        : {}),
    },
  });
  return resp.data;
}

export async function removeDevice(deviceId) {
  const resp = await api.delete(`/devices/${deviceId}`);
  return resp.data;
}

// Monitoring
export async function getMonitoringSessions() {
  const resp = await api.get("/monitoring/sessions");
  return (resp.data?.sessions || []).map(normalizeMonitoringSession);
}

export async function getMonitoringDashboard() {
  const resp = await api.get("/monitoring/dashboard");
  return normalizeMonitoringDashboard(resp.data || {});
}

export async function getSessionDetail(sessionId) {
  const resp = await api.get(`/monitoring/sessions/${sessionId}`);
  return resp.data;
}

// Detections
export async function getUnverifiedDetections() {
  const resp = await api.get("/detections/unverified");
  return resp.data?.detections || [];
}

export async function verifyDetection(
  detectionId,
  status,
  verifiedBy = "anonymous",
  notes = "",
) {
  const resp = await api.post("/detections/verify", {
    detection_id: detectionId,
    status,
    verified_by: verifiedBy,
    notes,
  });
  return resp.data;
}

export async function batchVerifyDetections(
  detectionIds,
  status,
  verifiedBy = "anonymous",
  notes = "",
) {
  const resp = await api.post("/detections/verify-batch", {
    detection_ids: detectionIds,
    status,
    verified_by: verifiedBy,
    notes,
  });
  return resp.data;
}

export async function getDetectionStats() {
  const resp = await api.get("/detections/stats");
  return resp.data;
}

export async function getSessionDetections(sessionId, verifiedOnly = false) {
  const resp = await api.get(
    `/detections/session/${encodeURIComponent(sessionId)}?verified_only=${verifiedOnly}`,
  );
  return resp.data;
}

export async function getSiteDetections(siteName, verifiedOnly = false) {
  const resp = await api.get(
    `/detections/site/${encodeURIComponent(siteName)}?verified_only=${verifiedOnly}`,
  );
  return resp.data;
}

export async function getOccupancyData(siteName, speciesScientific) {
  const resp = await api.get(
    `/occupancy/${encodeURIComponent(siteName)}/${encodeURIComponent(speciesScientific)}`,
  );
  return resp.data;
}

// Embeddings
export async function getEmbeddingStats() {
  const resp = await api.get("/embeddings/stats");
  return normalizeEmbeddingStats(resp.data || {});
}

export async function getEmbeddingCluster(sessionId) {
  const resp = await api.get(`/embeddings/cluster/${sessionId}`);
  return resp.data;
}

export async function getEmbeddingSimilarity(sessionId) {
  const resp = await api.get(`/embeddings/similarity/${sessionId}`);
  return resp.data;
}

export async function getNovelSounds(sessionId) {
  const resp = await api.get(`/embeddings/novel/${sessionId}`);
  return resp.data;
}

// GBIF / iNaturalist
export async function getGBIFOccurrences(
  scientificName,
  country = "CN",
  limit = 30,
) {
  const resp = await api.get("/gbif/occurrences", {
    params: {
      scientific_name: scientificName,
      country,
      limit,
      has_coordinate: true,
    },
  });
  return resp.data;
}

export async function getINatObservations(
  taxonName,
  lat = null,
  lng = null,
  limit = 30,
) {
  const params = { taxon_name: taxonName, per_page: limit };
  if (lat != null) params.lat = lat;
  if (lng != null) params.lng = lng;
  const resp = await api.get("/inat/observations", { params });
  return resp.data;
}

// BirdNET
export async function getBirdNETStatus() {
  const resp = await api.get("/birdnet/status");
  return resp.data;
}

export async function analyzeBirdNET(
  file,
  lat = null,
  lon = null,
  minConf = 0.1,
) {
  const formData = new FormData();
  formData.append("file", file);
  let url = `/birdnet/analyze?min_conf=${minConf}`;
  if (lat != null) url += `&lat=${lat}`;
  if (lon != null) url += `&lon=${lon}`;
  const resp = await api.post(url, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return resp.data;
}

export async function compareEngines(file, topK = 5) {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await api.post(`/compare-engines?top_k=${topK}`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return resp.data;
}

// Export
export async function exportDetectionsCSV(sessionId = null) {
  const url = sessionId
    ? `/export/detections?session_id=${sessionId}`
    : "/export/detections";
  const resp = await api.get(url, { responseType: "blob" });
  return resp.data;
}

// Batch Analysis
export async function analyzeBatch(files, topK = 5) {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  const resp = await api.post(`/analyze-batch?top_k=${topK}`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300000,
  });
  return resp.data;
}

// Report
export async function generateReport(file, siteName = "Unknown") {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await api.post(
    `/report/generate?site_name=${encodeURIComponent(siteName)}`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      responseType: "text",
    },
  );
  return resp.data;
}

// WebSocket helper with auto-reconnect and heartbeat
export function createDeviceSocket(
  deviceId,
  {
    onDetection,
    onError,
    onClose,
    onOpen,
    threshold = 0.3,
    sampleRate = 22050,
    maxRetries = 5,
    retryDelay = 3000,
    heartbeatInterval = 30000,
  } = {},
) {
  const wsBase = USE_NATIVE_API_BASE
    ? configuredApiBases.wsBase
    : getDefaultWebSocketBase();
  let ws = null;
  let retries = 0;
  let heartbeatTimer = null;
  let closed = false;

  function connect() {
    if (closed) return;
    ws = new WebSocket(`${wsBase}/stream/${deviceId}`);

    ws.onopen = () => {
      retries = 0;
      ws.send(
        JSON.stringify({ action: "start", sample_rate: sampleRate, threshold }),
      );
      heartbeatTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: "heartbeat" }));
        }
      }, heartbeatInterval);
      onOpen?.();
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.event === "detections") onDetection?.(data);
      } catch {
        /* binary frame */
      }
    };

    ws.onerror = (err) => onError?.(err);

    ws.onclose = () => {
      clearInterval(heartbeatTimer);
      if (!closed && retries < maxRetries) {
        retries++;
        setTimeout(connect, retryDelay * retries);
      } else {
        onClose?.();
      }
    };
  }

  connect();

  return {
    send: (data) => ws?.readyState === WebSocket.OPEN && ws.send(data),
    close: () => {
      closed = true;
      clearInterval(heartbeatTimer);
      ws?.close();
    },
  };
}
