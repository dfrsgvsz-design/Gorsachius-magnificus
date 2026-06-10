import { App } from "@capacitor/app";
import { Capacitor } from "@capacitor/core";
import { Camera, CameraResultType, CameraSource } from "@capacitor/camera";
import { Directory, Filesystem } from "@capacitor/filesystem";
import { Geolocation } from "@capacitor/geolocation";
import { Haptics, ImpactStyle } from "@capacitor/haptics";
import {
  applyAttachmentContext,
  computeAttachmentChecksum,
  computeAttachmentChecksumFromBase64,
  createAttachmentId,
  normalizeAttachmentContract,
  normalizeAttachmentIds,
} from "./attachmentContract";
import { normalizeSurveyTaxonomyPackage } from "./api";

const SURVEY_STATE_FILE = "field-survey-state.json";
const SURVEY_STATE_BACKUP_FILE = "field-survey-state.backup.json";
const SURVEY_STATE_META_FILE = "field-survey-state.meta.json";
const MEDIA_DIRECTORY = "field-survey-media";
const NATIVE_ATTACHMENT_STORAGE_KIND = "capacitor-filesystem";
const NATIVE_SURVEY_STATE_VERSION = 2;
const DEFAULT_JURISDICTION = "mainland_china";
const JURISDICTION_ALIASES = {
  china_mainland: "mainland_china",
};

let cachedState = null;
let latestSerializedState = "";
let backgroundFlushBound = false;

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

function safeJsonParse(raw, fallback = null) {
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function normalizeJurisdiction(value, fallback = DEFAULT_JURISDICTION) {
  const normalized = String(value || "").trim();
  if (!normalized) return fallback;
  return JURISDICTION_ALIASES[normalized] || normalized;
}

function hasNativeAttachmentReference(attachment) {
  return Boolean(
    attachment &&
    typeof attachment === "object" &&
    attachment.storage_kind === NATIVE_ATTACHMENT_STORAGE_KIND &&
    ((typeof attachment.storage_path === "string" && attachment.storage_path) ||
      (typeof attachment.native_path === "string" && attachment.native_path)),
  );
}

function normalizeStoredAttachment(
  attachment,
  { persistLocalUri = true } = {},
) {
  const normalized = normalizeAttachmentContract(attachment, {
    persistLocalUri,
    defaultStorageKind: NATIVE_ATTACHMENT_STORAGE_KIND,
  });
  if (!normalized) return null;
  if (!persistLocalUri && hasNativeAttachmentReference(normalized)) {
    delete normalized.local_uri;
  }
  return normalized;
}

function normalizeTaxonomyPackages(packages = []) {
  return Array.isArray(packages)
    ? packages
        .map((item) => normalizeSurveyTaxonomyPackage(item))
        .filter((item) => Boolean(item?.package_id))
    : [];
}

function normalizeNativeSurveyState(
  state,
  { persistAttachmentUris = true } = {},
) {
  if (!state || typeof state !== "object") return null;
  const normalized = {
    ...state,
    schema_version: Math.max(
      Number(state.schema_version || 0),
      NATIVE_SURVEY_STATE_VERSION,
    ),
    projects: Array.isArray(state.projects) ? state.projects : [],
    sites: Array.isArray(state.sites) ? state.sites : [],
    routes: Array.isArray(state.routes) ? state.routes : [],
    observations: Array.isArray(state.observations) ? state.observations : [],
    tracks: Array.isArray(state.tracks) ? state.tracks : [],
    mapPackages: Array.isArray(state.mapPackages) ? state.mapPackages : [],
    protocols: Array.isArray(state.protocols) ? state.protocols : [],
    taxonomyPackages: normalizeTaxonomyPackages(state.taxonomyPackages),
    designAssets: Array.isArray(state.designAssets) ? state.designAssets : [],
    events: Array.isArray(state.events) ? state.events : [],
    exportJobs: Array.isArray(state.exportJobs) ? state.exportJobs : [],
    mediaInbox: Array.isArray(state.mediaInbox)
      ? state.mediaInbox
          .map((attachment) =>
            normalizeStoredAttachment(attachment, {
              persistLocalUri: persistAttachmentUris,
            }),
          )
          .filter(Boolean)
      : [],
    activeDraftAttachmentIds: normalizeAttachmentIds(
      state.activeDraftAttachmentIds,
    ),
    syncQueue: Array.isArray(state.syncQueue) ? state.syncQueue : [],
    conflicts: Array.isArray(state.conflicts) ? state.conflicts : [],
    activeProjectId:
      typeof state.activeProjectId === "string" ? state.activeProjectId : "",
    activeSiteId:
      typeof state.activeSiteId === "string" ? state.activeSiteId : "",
    activeRouteId:
      typeof state.activeRouteId === "string" ? state.activeRouteId : "",
    activeProgram:
      typeof state.activeProgram === "string" && state.activeProgram
        ? state.activeProgram
        : "terrestrial_vertebrates",
    activeProtocol:
      typeof state.activeProtocol === "string" ? state.activeProtocol : "",
    activeVertebrateSubmodule:
      typeof state.activeVertebrateSubmodule === "string"
        ? state.activeVertebrateSubmodule
        : "",
    activeJurisdiction: normalizeJurisdiction(
      state.activeJurisdiction,
      DEFAULT_JURISDICTION,
    ),
    activeDesignAssetId:
      typeof state.activeDesignAssetId === "string"
        ? state.activeDesignAssetId
        : "",
    activeEventId:
      typeof state.activeEventId === "string" ? state.activeEventId : "",
    syncMeta: {
      lastPulledAt: state.syncMeta?.lastPulledAt || "",
      lastPushedAt: state.syncMeta?.lastPushedAt || "",
      lastStatus: state.syncMeta?.lastStatus || "idle",
      lastError: state.syncMeta?.lastError || "",
      deviceId: state.syncMeta?.deviceId || "",
      removedQueueIds: Array.isArray(state.syncMeta?.removedQueueIds)
        ? state.syncMeta.removedQueueIds
        : [],
    },
  };
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
  return normalized;
}

async function readTextFile(path) {
  const result = await Filesystem.readFile({
    path,
    directory: Directory.Data,
    encoding: "utf8",
  });
  return typeof result.data === "string" ? result.data : "";
}

async function writeTextFile(path, data) {
  await Filesystem.writeFile({
    path,
    data,
    directory: Directory.Data,
    encoding: "utf8",
    recursive: true,
  });
}

async function statTimestamp(path) {
  try {
    const stat = await Filesystem.stat({ path, directory: Directory.Data });
    return Date.parse(stat.mtime || stat.ctime || "") || 0;
  } catch {
    return 0;
  }
}

async function readStateCandidate(path) {
  try {
    const raw = await readTextFile(path);
    const parsed = normalizeNativeSurveyState(safeJsonParse(raw, null));
    if (!parsed || typeof parsed !== "object") return null;
    return {
      path,
      raw,
      parsed,
      timestamp: await statTimestamp(path),
    };
  } catch {
    return null;
  }
}

function chooseNewestCandidate(...candidates) {
  return (
    candidates
      .filter(Boolean)
      .sort(
        (left, right) => (right.timestamp || 0) - (left.timestamp || 0),
      )[0] || null
  );
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () =>
      reject(reader.error || new Error("Unable to read blob"));
    reader.readAsDataURL(blob);
  });
}

function dataUrlToBase64(dataUrl) {
  const parts = String(dataUrl || "").split(",", 2);
  return parts[1] || "";
}

async function fetchBlob(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Unable to read captured media: ${response.status}`);
  }
  return response.blob();
}

async function persistMediaBlob(blob, preferredExtension = "bin") {
  const extension =
    String(preferredExtension || "bin")
      .replace(/[^a-z0-9]/gi, "")
      .toLowerCase() || "bin";
  const filename = `${MEDIA_DIRECTORY}/${createId("media")}.${extension}`;
  const dataUrl = await blobToDataUrl(blob);
  await Filesystem.writeFile({
    path: filename,
    data: dataUrlToBase64(dataUrl),
    directory: Directory.Data,
    recursive: true,
  });
  return filename;
}

async function persistMediaFileReference(
  sourcePath,
  preferredExtension = "bin",
) {
  const extension =
    String(preferredExtension || "bin")
      .replace(/[^a-z0-9]/gi, "")
      .toLowerCase() || "bin";
  const filename = `${MEDIA_DIRECTORY}/${createId("media")}.${extension}`;
  if (sourcePath) {
    try {
      const copied = await Filesystem.copy({
        from: sourcePath,
        to: filename,
        toDirectory: Directory.Data,
      });
      return { filename, nativeUri: copied.uri };
    } catch {
      try {
        const existing = await Filesystem.readFile({ path: sourcePath });
        const written = await Filesystem.writeFile({
          path: filename,
          data: existing.data,
          directory: Directory.Data,
          recursive: true,
        });
        return { filename, nativeUri: written.uri };
      } catch {
        // Fall back to blob persistence when direct file operations are unavailable.
      }
    }
  }
  return null;
}

async function resolveStoredMediaUri(storagePath, nativePath = "") {
  if (storagePath) {
    const resolved = await Filesystem.getUri({
      path: storagePath,
      directory: Directory.Data,
    });
    return {
      nativeUri: resolved.uri,
      localUri: Capacitor.convertFileSrc(resolved.uri),
    };
  }
  if (nativePath) {
    return {
      nativeUri: nativePath,
      localUri: Capacitor.convertFileSrc(nativePath),
    };
  }
  return { nativeUri: "", localUri: "" };
}

async function persistStateSnapshot(state, { includeBackup = true } = {}) {
  const normalized =
    normalizeNativeSurveyState(state, { persistAttachmentUris: false }) ||
    state;
  const serialized = JSON.stringify(normalized);
  if (includeBackup) {
    try {
      const existing = await readTextFile(SURVEY_STATE_FILE);
      if (existing && existing !== serialized) {
        await writeTextFile(SURVEY_STATE_BACKUP_FILE, existing);
      }
    } catch {
      // Ignore missing or unreadable primary snapshots.
    }
  }
  await writeTextFile(SURVEY_STATE_FILE, serialized);
  await writeTextFile(
    SURVEY_STATE_META_FILE,
    JSON.stringify({
      saved_at: nowIso(),
      bytes: serialized.length,
      platform: Capacitor.getPlatform(),
      schema_version: normalized?.schema_version || NATIVE_SURVEY_STATE_VERSION,
    }),
  );
  cachedState = normalized;
  latestSerializedState = serialized;
  return normalized;
}

function ensureBackgroundFlushBinding() {
  if (!isNativeMobile() || backgroundFlushBound) return;
  backgroundFlushBound = true;
  App.addListener("appStateChange", ({ isActive }) => {
    if (isActive || !cachedState) return;
    persistStateSnapshot(cachedState, { includeBackup: false }).catch(() => {});
  });
}

async function ensureLocationPermission() {
  const current = await Geolocation.checkPermissions();
  const state = current.location || current.coarseLocation || "prompt";
  if (state === "granted") return current;
  const requested = await Geolocation.requestPermissions({
    permissions: ["location", "coarseLocation"],
  });
  const nextState = requested.location || requested.coarseLocation || "denied";
  if (nextState !== "granted") {
    throw new Error("Location permission was not granted.");
  }
  return requested;
}

async function ensureCameraPermission(source) {
  const current = await Camera.checkPermissions();
  const wantsPhotos = source !== CameraSource.Camera;
  const cameraState = current.camera || "prompt";
  const photosState = current.photos || "prompt";

  if (
    cameraState === "granted" &&
    (!wantsPhotos || photosState === "granted")
  ) {
    return current;
  }

  const requested = await Camera.requestPermissions({
    permissions: wantsPhotos ? ["camera", "photos"] : ["camera"],
  });
  const nextCameraState = requested.camera || "denied";
  const nextPhotosState = requested.photos || "granted";

  if (
    nextCameraState !== "granted" ||
    (wantsPhotos && nextPhotosState !== "granted")
  ) {
    throw new Error("Camera permission was not granted.");
  }

  return requested;
}

export function isNativeMobile() {
  return Capacitor.isNativePlatform();
}

export async function loadNativeSurveyState() {
  if (!isNativeMobile()) return null;
  ensureBackgroundFlushBinding();
  if (cachedState) return cachedState;

  const primary = await readStateCandidate(SURVEY_STATE_FILE);
  const backup = await readStateCandidate(SURVEY_STATE_BACKUP_FILE);
  const next = chooseNewestCandidate(primary, backup);

  if (!next) return null;

  cachedState = next.parsed;
  latestSerializedState = next.raw;
  return cachedState;
}

export async function saveNativeSurveyState(state) {
  if (!isNativeMobile()) return state;
  ensureBackgroundFlushBinding();
  return persistStateSnapshot(state);
}

export async function requestNativeCurrentPosition() {
  if (!isNativeMobile()) return null;
  ensureBackgroundFlushBinding();
  await ensureLocationPermission();

  try {
    const position = await Geolocation.getCurrentPosition({
      enableHighAccuracy: true,
      timeout: 12000,
      maximumAge: 15000,
    });
    return {
      lat: position.coords.latitude,
      lon: position.coords.longitude,
      accuracy: position.coords.accuracy,
      timestamp: position.timestamp || Date.now(),
    };
  } catch {
    const fallback = await Geolocation.getCurrentPosition({
      enableHighAccuracy: false,
      timeout: 18000,
      maximumAge: 120000,
    });
    return {
      lat: fallback.coords.latitude,
      lon: fallback.coords.longitude,
      accuracy: fallback.coords.accuracy,
      timestamp: fallback.timestamp || Date.now(),
    };
  }
}

export async function startNativePositionWatch(onPosition, onError = () => {}) {
  if (!isNativeMobile()) return null;
  ensureBackgroundFlushBinding();
  await ensureLocationPermission();

  const watchId = await Geolocation.watchPosition(
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
    },
    (position, error) => {
      if (error) {
        onError(error);
        return;
      }
      if (!position?.coords) return;
      onPosition({
        lat: position.coords.latitude,
        lon: position.coords.longitude,
        accuracy: position.coords.accuracy,
        timestamp: position.timestamp || Date.now(),
      });
    },
  );

  return watchId;
}

export async function stopNativePositionWatch(watchId) {
  if (!isNativeMobile() || !watchId) return;
  try {
    await Geolocation.clearWatch({ id: watchId });
  } catch {
    // Ignore watch cleanup failures.
  }
}

export async function capturePhotoAttachment(source = CameraSource.Camera) {
  if (!isNativeMobile()) return null;
  ensureBackgroundFlushBinding();
  await ensureCameraPermission(source);

  const photo = await Camera.getPhoto({
    quality: 80,
    resultType: CameraResultType.Uri,
    source,
    saveToGallery: source === CameraSource.Camera,
    correctOrientation: true,
    presentationStyle: "fullscreen",
  });

  const format = (photo.format || "jpeg").toLowerCase();
  const extension = format === "jpeg" ? "jpg" : format;
  const type = `image/${format === "jpg" ? "jpeg" : format}`;
  const sourcePath = photo.webPath || photo.path;

  if (!sourcePath) {
    throw new Error("Captured photo is missing a readable path.");
  }

  let persistedPath;
  let nativeUri;
  let size;
  let checksum = "";

  const copied = await persistMediaFileReference(photo.path || "", extension);
  if (copied) {
    persistedPath = copied.filename;
    nativeUri = copied.nativeUri;
    try {
      const stat = await Filesystem.stat({
        path: persistedPath,
        directory: Directory.Data,
      });
      size = Number(stat.size || 0);
    } catch {
      size = 0;
    }
    try {
      const stored = await Filesystem.readFile({
        path: persistedPath,
        directory: Directory.Data,
      });
      if (typeof stored.data === "string") {
        checksum = await computeAttachmentChecksumFromBase64(stored.data);
      }
    } catch {
      checksum = "";
    }
  } else {
    const blob = await fetchBlob(sourcePath);
    persistedPath = await persistMediaBlob(blob, extension);
    const resolved = await resolveStoredMediaUri(persistedPath);
    nativeUri = resolved.nativeUri;
    size = blob.size || 0;
    checksum = await computeAttachmentChecksum(blob);
  }

  const resolvedUris = await resolveStoredMediaUri(persistedPath, nativeUri);

  return normalizeStoredAttachment({
    attachment_id: createAttachmentId(),
    filename: `field-photo-${Date.now()}.${extension}`,
    mime_type: type,
    byte_size: size,
    local_uri: resolvedUris.localUri,
    added_at: nowIso(),
    storage_kind: NATIVE_ATTACHMENT_STORAGE_KIND,
    native_path: resolvedUris.nativeUri,
    storage_path: persistedPath,
    storage_key: persistedPath,
    checksum,
    sync_state: "local_only",
  });
}

export async function restoreDraftAttachment(attachment) {
  const normalized = normalizeStoredAttachment(attachment);
  if (!normalized || !hasNativeAttachmentReference(normalized))
    return normalized;
  const resolved = await resolveStoredMediaUri(
    normalized.storage_path || "",
    normalized.native_path || "",
  );
  return {
    ...normalized,
    native_path: resolved.nativeUri || normalized.native_path || "",
    local_uri: resolved.localUri,
  };
}

export async function restoreDraftAttachments(attachments = []) {
  return Promise.all(
    (attachments || []).map((attachment) => restoreDraftAttachment(attachment)),
  );
}

export async function pulseFeedback(style = ImpactStyle.Medium) {
  if (!isNativeMobile()) return;
  try {
    await Haptics.impact({ style });
  } catch {
    // Ignore haptic failures on unsupported devices.
  }
}

export { CameraSource, ImpactStyle };
