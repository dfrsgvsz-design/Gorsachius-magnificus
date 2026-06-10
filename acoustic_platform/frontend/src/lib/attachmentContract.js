const DEFAULT_ATTACHMENT_SYNC_STATE = "local_only";

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

function pickFirstNonEmpty(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function pickNumeric(...values) {
  for (const value of values) {
    const normalized = Number(value);
    if (Number.isFinite(normalized) && normalized >= 0) return normalized;
  }
  return 0;
}

function normalizeOwnerType(value, fallback = "draft") {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (!normalized) return fallback;
  return normalized;
}

function base64ToBytes(base64) {
  const normalized = String(base64 || "").trim();
  if (!normalized) return new Uint8Array();
  if (typeof atob === "function") {
    const binary = atob(normalized);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }
  if (typeof globalThis.Buffer !== "undefined") {
    return new Uint8Array(globalThis.Buffer.from(normalized, "base64"));
  }
  return new Uint8Array();
}

async function digestBytes(bytes) {
  if (!bytes || typeof bytes.length !== "number" || bytes.length === 0)
    return "";
  const subtle = globalThis.crypto?.subtle;
  if (typeof subtle?.digest !== "function") return "";
  const hash = await subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

export function createAttachmentId(prefix = "att") {
  return createId(prefix);
}

export function getAttachmentLookupId(attachmentOrId) {
  if (typeof attachmentOrId === "string") return attachmentOrId;
  if (!attachmentOrId || typeof attachmentOrId !== "object") return "";
  return pickFirstNonEmpty(
    attachmentOrId.attachment_id,
    attachmentOrId.media_id,
    attachmentOrId.storage_key,
    attachmentOrId.storage_path,
  );
}

export function normalizeAttachmentContract(
  attachment,
  { persistLocalUri = true, defaultStorageKind = "", context = {} } = {},
) {
  if (!attachment || typeof attachment !== "object") return null;

  const attachmentId =
    getAttachmentLookupId(attachment) || createAttachmentId();
  const ownerType = normalizeOwnerType(
    attachment.owner_type ||
      context.owner_type ||
      (attachment.event_id || context.event_id ? "event" : "draft"),
  );
  const eventId = pickFirstNonEmpty(
    attachment.event_id,
    context.event_id,
    ownerType === "event" ? attachment.owner_id : "",
    ownerType === "event" ? context.owner_id : "",
  );
  const ownerId = pickFirstNonEmpty(
    attachment.owner_id,
    context.owner_id,
    ownerType === "event" ? eventId : "",
  );
  const mimeType = pickFirstNonEmpty(
    attachment.mime_type,
    attachment.type,
    "application/octet-stream",
  );
  const filename = pickFirstNonEmpty(
    attachment.filename,
    attachment.name,
    "attachment",
  );
  const byteSize = pickNumeric(attachment.byte_size, attachment.size);
  const hasStorageReference = Boolean(
    pickFirstNonEmpty(
      attachment.storage_key,
      attachment.storage_path,
      attachment.native_path,
      attachment.storage_kind,
    ),
  );
  const storageKind = pickFirstNonEmpty(
    attachment.storage_kind,
    hasStorageReference ? defaultStorageKind : "",
  );
  const storageKey = pickFirstNonEmpty(
    attachment.storage_key,
    attachment.storage_path,
    attachment.media_id,
    attachment.attachment_id,
    attachmentId,
  );
  const localUri =
    typeof attachment.local_uri === "string" ? attachment.local_uri : "";
  const normalized = {
    ...attachment,
    attachment_id: attachmentId,
    event_id: eventId,
    owner_type: ownerType,
    owner_id: ownerId,
    mime_type: mimeType,
    filename,
    byte_size: byteSize,
    storage_key: storageKey,
    checksum: pickFirstNonEmpty(attachment.checksum),
    sync_state: pickFirstNonEmpty(
      attachment.sync_state,
      context.sync_state,
      DEFAULT_ATTACHMENT_SYNC_STATE,
    ),
    media_id: attachmentId,
    name: filename,
    type: mimeType,
    size: byteSize,
    added_at: pickFirstNonEmpty(attachment.added_at) || nowIso(),
  };

  if (storageKind) normalized.storage_kind = storageKind;
  if (typeof attachment.storage_path === "string" && attachment.storage_path)
    normalized.storage_path = attachment.storage_path;
  if (typeof attachment.native_path === "string" && attachment.native_path)
    normalized.native_path = attachment.native_path;
  if (typeof attachment.program === "string" && attachment.program)
    normalized.program = attachment.program;
  if (typeof attachment.protocol === "string" && attachment.protocol)
    normalized.protocol = attachment.protocol;
  if (typeof attachment.jurisdiction === "string" && attachment.jurisdiction)
    normalized.jurisdiction = attachment.jurisdiction;

  if (persistLocalUri) {
    if (localUri) normalized.local_uri = localUri;
  } else {
    delete normalized.local_uri;
  }

  return normalized;
}

export function normalizeAttachmentIds(ids) {
  return Array.isArray(ids)
    ? Array.from(
        new Set(
          ids.map((value) => getAttachmentLookupId(value)).filter(Boolean),
        ),
      )
    : [];
}

export function applyAttachmentContext(
  attachments = [],
  attachmentIds = [],
  context = {},
) {
  const selectedIds = new Set(normalizeAttachmentIds(attachmentIds));
  const normalizedContext = {
    owner_type: normalizeOwnerType(
      context.owner_type || (context.event_id ? "event" : "draft"),
    ),
    owner_id: pickFirstNonEmpty(context.owner_id, context.event_id),
    event_id: pickFirstNonEmpty(context.event_id),
    sync_state: pickFirstNonEmpty(
      context.sync_state,
      DEFAULT_ATTACHMENT_SYNC_STATE,
    ),
  };

  return (Array.isArray(attachments) ? attachments : [])
    .map((attachment) => {
      const attachmentId = getAttachmentLookupId(attachment);
      const isSelected = selectedIds.has(attachmentId);
      const canPromoteSelection =
        isSelected &&
        !pickFirstNonEmpty(attachment?.event_id, attachment?.owner_id);
      const attachmentForNormalization = canPromoteSelection
        ? {
            ...attachment,
            owner_type: "",
            owner_id: "",
            event_id: "",
          }
        : attachment;
      return normalizeAttachmentContract(attachmentForNormalization, {
        context: isSelected ? normalizedContext : {},
      });
    })
    .filter(Boolean);
}

export async function computeAttachmentChecksum(blob) {
  if (!blob || typeof blob.arrayBuffer !== "function") return "";
  const bytes = new Uint8Array(await blob.arrayBuffer());
  return digestBytes(bytes);
}

export async function computeAttachmentChecksumFromBase64(base64) {
  return digestBytes(base64ToBytes(base64));
}
