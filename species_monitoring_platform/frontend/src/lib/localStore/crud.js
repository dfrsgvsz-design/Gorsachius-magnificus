// localStore/crud.js — generic CRUD primitives keyed by entity type.
//
// Mirrors the read/upsert side of backend/survey_store.py. Payload is the
// source of truth: indexed columns are denormalized from the payload purely
// to speed up filtering. On read we always return `JSON.parse(payload_json)`
// (with the id field re-asserted) so callers see a single canonical shape.
//
// Soft-delete and cascade live in `./softDelete.js`; this module never
// mutates `deleted_at` directly and only filters on it during reads.

import { execute, query } from "./db.js";
import { ENTITY_META, resolveEntityType } from "./entityMeta.js";

const ID_FIELD_RE = /_id$/;

function nowIso() {
  return new Date().toISOString();
}

function randomSuffix() {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 12);
  }
  return Math.random().toString(16).slice(2, 14);
}

export function makeId(entityType) {
  const meta = ENTITY_META[resolveEntityType(entityType)];
  if (!meta) throw new Error(`Unknown entity type: ${entityType}`);
  return `${meta.defaultPrefix}_${randomSuffix()}`;
}

function pickIndexedValue(payload, column) {
  const raw = payload?.[column];
  if (raw === undefined || raw === null) {
    if (column === "deleted_at") return "";
    if (column.endsWith("_id")) return "";
    return "";
  }
  if (typeof raw === "number") return raw;
  return String(raw);
}

function parseRow(row, meta) {
  if (!row) return null;
  let payload;
  try {
    payload = JSON.parse(row.payload_json || "{}");
    if (!payload || typeof payload !== "object") payload = {};
  } catch {
    payload = {};
  }
  // Indexed columns win over payload_json for the id field — protects
  // against payload corruption.
  const idField = meta.idField;
  return {
    ...payload,
    [idField]: row[idField] || payload[idField] || "",
    created_at: row.created_at || payload.created_at || "",
    updated_at: row.updated_at || payload.updated_at || "",
    deleted_at: row.deleted_at || "",
  };
}

/** Fetch a single entity by id. Excludes soft-deleted rows by default. */
export async function getById(entityType, entityId, options = {}) {
  const resolved = resolveEntityType(entityType);
  const meta = ENTITY_META[resolved];
  if (!meta) return null;
  const id = String(entityId || "").trim();
  if (!id) return null;

  const includeDeleted = Boolean(options.includeDeleted);
  const where = includeDeleted
    ? `${meta.idField}=?`
    : `${meta.idField}=? AND deleted_at=''`;
  const rows = await query(
    `SELECT * FROM ${meta.table} WHERE ${where} LIMIT 1`,
    [id],
  );
  return rows.length ? parseRow(rows[0], meta) : null;
}

/**
 * List entities with optional filters. Defaults exclude soft-deleted rows.
 *
 * @param {string} entityType
 * @param {object} options
 *   - includeDeleted: true → only soft-deleted, false (default) → only live,
 *     "all" → both.
 *   - filters: { column: value } where column is in `indexedColumns`.
 *   - search: { column, value } LIKE filter (value will be wrapped with %).
 *   - orderBy: SQL fragment without "ORDER BY" prefix.
 *   - limit / offset: numbers.
 */
export async function listEntities(entityType, options = {}) {
  const resolved = resolveEntityType(entityType);
  const meta = ENTITY_META[resolved];
  if (!meta) return [];

  const clauses = [];
  const params = [];

  if (options.includeDeleted === true) {
    clauses.push("deleted_at!=''");
  } else if (options.includeDeleted === "all") {
    /* no clause */
  } else {
    clauses.push("deleted_at=''");
  }

  if (options.filters && typeof options.filters === "object") {
    for (const [column, value] of Object.entries(options.filters)) {
      if (value === undefined || value === null || value === "") continue;
      if (
        !meta.indexedColumns.includes(column) &&
        !meta.columns.includes(column)
      ) {
        continue;
      }
      clauses.push(`${column}=?`);
      params.push(typeof value === "number" ? value : String(value));
    }
  }

  if (options.search?.column && options.search?.value) {
    const { column, value } = options.search;
    if (
      meta.indexedColumns.includes(column) ||
      meta.columns.includes(column)
    ) {
      clauses.push(`${column} LIKE ?`);
      params.push(`%${String(value)}%`);
    }
  }

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const orderBy = options.orderBy
    ? `ORDER BY ${options.orderBy}`
    : "ORDER BY updated_at DESC";
  const limit = Number.isFinite(options.limit)
    ? `LIMIT ${Math.max(0, Math.floor(options.limit))}`
    : "";
  const offset =
    limit && Number.isFinite(options.offset)
      ? `OFFSET ${Math.max(0, Math.floor(options.offset))}`
      : "";

  const rows = await query(
    `SELECT * FROM ${meta.table} ${where} ${orderBy} ${limit} ${offset}`.trim(),
    params,
  );
  return rows.map((row) => parseRow(row, meta));
}

/**
 * Insert or replace an entity row. Generates an id if the payload doesn't
 * carry one. Returns the merged payload that was actually written.
 */
export async function upsert(entityType, payload, options = {}) {
  const resolved = resolveEntityType(entityType);
  const meta = ENTITY_META[resolved];
  if (!meta) throw new Error(`Unknown entity type: ${entityType}`);

  const incoming = { ...(payload || {}) };
  const idField = meta.idField;
  const entityId =
    String(incoming[idField] || "").trim() || makeId(resolved);
  incoming[idField] = entityId;

  // Preserve created_at on update; refresh updated_at unless explicitly set.
  let createdAt = String(incoming.created_at || "").trim();
  if (!createdAt) {
    const existing = await getById(resolved, entityId, {
      includeDeleted: true,
    });
    createdAt = existing?.created_at || nowIso();
  }
  const updatedAt = String(incoming.updated_at || "").trim() || nowIso();
  incoming.created_at = createdAt;
  incoming.updated_at = updatedAt;

  // Build column tuple in the order declared by the meta. payload_json
  // always carries the full incoming object so unknown fields survive.
  const cols = meta.columns;
  const values = cols.map((col) => {
    if (col === "payload_json") return JSON.stringify(incoming);
    if (col === "deleted_at") {
      return options.preserveDeletedAt
        ? String(incoming.deleted_at || "")
        : "";
    }
    if (col === idField) return entityId;
    if (col === "created_at") return createdAt;
    if (col === "updated_at") return updatedAt;
    return pickIndexedValue(incoming, col);
  });

  const placeholders = cols.map(() => "?").join(", ");
  await execute(
    `INSERT OR REPLACE INTO ${meta.table} (${cols.join(", ")}) VALUES (${placeholders})`,
    values,
  );
  return { ...incoming, deleted_at: options.preserveDeletedAt ? incoming.deleted_at || "" : "" };
}

/** Hard-delete (used only by export_job purge in cascade rules). */
export async function purgeRow(entityType, entityId) {
  const resolved = resolveEntityType(entityType);
  const meta = ENTITY_META[resolved];
  if (!meta) return false;
  const id = String(entityId || "").trim();
  if (!id) return false;
  const res = await execute(
    `DELETE FROM ${meta.table} WHERE ${meta.idField}=?`,
    [id],
  );
  return Number(res?.changes?.changes || 0) > 0;
}

/** Helper for cascade rules: list ids matching arbitrary WHERE. */
export async function listIdsByWhere(entityType, whereClause, params) {
  const resolved = resolveEntityType(entityType);
  const meta = ENTITY_META[resolved];
  if (!meta) return [];
  const rows = await query(
    `SELECT ${meta.idField} AS id FROM ${meta.table} WHERE ${whereClause}`,
    params,
  );
  return rows.map((r) => r.id).filter(Boolean);
}

/** Helper for cascade rules: list ids whose payload_json contains a matching
 *  scalar at `payloadKey`. Mirrors the server's payload-walk for parent
 *  references stored inside JSON. */
export async function listIdsByPayloadKey(entityType, payloadKey, expectedValue) {
  const resolved = resolveEntityType(entityType);
  const meta = ENTITY_META[resolved];
  if (!meta) return [];
  const rows = await query(
    `SELECT ${meta.idField} AS id, payload_json FROM ${meta.table} WHERE deleted_at=''`,
    [],
  );
  const matches = [];
  const expected = String(expectedValue || "").trim();
  if (!expected) return matches;
  for (const row of rows) {
    let payload;
    try {
      payload = JSON.parse(row.payload_json || "{}");
    } catch {
      continue;
    }
    if (String(payload?.[payloadKey] || "").trim() === expected) {
      if (row.id) matches.push(row.id);
    }
  }
  return matches;
}

export { ID_FIELD_RE, nowIso };
