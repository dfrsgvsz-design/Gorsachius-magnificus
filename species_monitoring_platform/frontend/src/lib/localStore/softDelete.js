// localStore/softDelete.js — cascading soft-delete + restore + trash listing.
//
// Faithful port of B18 server logic in backend/survey_store.py:
//   - `_delete_entity_locked` walks the cascade table per entity type and
//     stamps `deleted_at` on every descendant before stamping the parent.
//   - `_restore_entity_locked` clears `deleted_at` on a single row only —
//     restoration is intentionally non-cascading.
//   - `list_trash` aggregates soft-deleted rows across all business tables.
//
// All public mutations here run inside a single SQLite transaction so a
// partial cascade can never leave the store half-tombstoned.

import { execute, query, withTransaction } from "./db.js";
import {
  CASCADE_RULES,
  ENTITY_META,
  ENTITY_TYPES,
  resolveEntityType,
} from "./entityMeta.js";
import { listIdsByPayloadKey, listIdsByWhere } from "./crud.js";

function nowIso() {
  return new Date().toISOString();
}

async function readDeletedAt(meta, entityId) {
  const rows = await query(
    `SELECT deleted_at FROM ${meta.table} WHERE ${meta.idField}=? LIMIT 1`,
    [entityId],
  );
  return rows.length ? String(rows[0].deleted_at || "") : null;
}

async function applyCascade(entityType, entityId, deletedAt) {
  const rules = CASCADE_RULES[entityType] || [];
  for (const rule of rules) {
    if (rule.kind === "recursive") {
      const ids = await listIdsByWhere(rule.childType, rule.where, [entityId]);
      for (const childId of ids) {
        await softDeleteInternal(rule.childType, childId, deletedAt);
      }
    } else if (rule.kind === "recursive_payload") {
      const ids = await listIdsByPayloadKey(
        rule.childType,
        rule.payloadKey,
        entityId,
      );
      for (const childId of ids) {
        await softDeleteInternal(rule.childType, childId, deletedAt);
      }
    } else if (rule.kind === "stamp") {
      await execute(
        `UPDATE ${rule.table} SET deleted_at=?, updated_at=? WHERE ${rule.where}`,
        [deletedAt, deletedAt, entityId],
      );
    } else if (rule.kind === "purge") {
      await execute(
        `DELETE FROM ${rule.table} WHERE ${rule.where}`,
        [entityId],
      );
    }
  }
}

async function softDeleteInternal(entityType, entityId, deletedAt) {
  const resolved = resolveEntityType(entityType);
  const meta = ENTITY_META[resolved];
  if (!meta) return false;
  const id = String(entityId || "").trim();
  if (!id) return false;

  const existingDeletedAt = await readDeletedAt(meta, id);
  if (existingDeletedAt === null) return false;
  if (existingDeletedAt) return false; // already tombstoned, idempotent no-op

  await applyCascade(resolved, id, deletedAt);

  const res = await execute(
    `UPDATE ${meta.table} SET deleted_at=?, updated_at=? WHERE ${meta.idField}=? AND deleted_at=''`,
    [deletedAt, deletedAt, id],
  );
  return Number(res?.changes?.changes || 0) > 0;
}

/**
 * Soft-delete an entity and its descendants. Returns true if the row
 * transitioned from live to tombstoned.
 *
 * Always wraps in a transaction so cascade is atomic.
 */
export async function softDelete(entityType, entityId) {
  const deletedAt = nowIso();
  return withTransaction(() =>
    softDeleteInternal(entityType, entityId, deletedAt),
  );
}

/**
 * Restore a single soft-deleted row. Non-cascading: callers must restore
 * descendants individually if they want them visible again. Returns true
 * iff the row was previously tombstoned.
 */
export async function restore(entityType, entityId) {
  const resolved = resolveEntityType(entityType);
  const meta = ENTITY_META[resolved];
  if (!meta) return false;
  const id = String(entityId || "").trim();
  if (!id) return false;

  return withTransaction(async () => {
    const res = await execute(
      `UPDATE ${meta.table} SET deleted_at='', updated_at=? WHERE ${meta.idField}=? AND deleted_at!=''`,
      [nowIso(), id],
    );
    return Number(res?.changes?.changes || 0) > 0;
  });
}

/**
 * List soft-deleted rows across all business tables (or one table if
 * `entityType` is supplied). Each row is augmented with `entity_type` so
 * callers can render a unified trash UI.
 */
export async function listTrash(entityType = "") {
  const targets = [];
  if (entityType) {
    const resolved = resolveEntityType(entityType);
    if (!ENTITY_META[resolved]) return [];
    targets.push([resolved, ENTITY_META[resolved]]);
  } else {
    for (const t of ENTITY_TYPES) targets.push([t, ENTITY_META[t]]);
  }

  const aggregated = [];
  for (const [type, meta] of targets) {
    const rows = await query(
      `SELECT * FROM ${meta.table} WHERE deleted_at!='' ORDER BY deleted_at DESC`,
      [],
    );
    for (const row of rows) {
      let payload;
      try {
        payload = JSON.parse(row.payload_json || "{}");
      } catch {
        payload = {};
      }
      aggregated.push({
        entity_type: type,
        ...payload,
        [meta.idField]: row[meta.idField] || payload[meta.idField] || "",
        deleted_at: row.deleted_at || "",
        updated_at: row.updated_at || "",
        created_at: row.created_at || "",
      });
    }
  }
  aggregated.sort((a, b) =>
    String(b.deleted_at || "").localeCompare(String(a.deleted_at || "")),
  );
  return aggregated;
}

export const __testing__ = {
  applyCascade,
  softDeleteInternal,
};
