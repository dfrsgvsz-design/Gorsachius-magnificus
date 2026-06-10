// localStore/outbox.js — durable queue of local mutations awaiting sync push.
//
// B24: every localSurveyService mutation (create / delete / restore) lands
// here in the same SQLite database as the entity tables. useSyncEngine merges
// these rows into the in-memory `syncQueue` and pushes them to the backend
// via `pushSurveySync`; rows are removed once the server confirms the
// operation was applied (or marked 'conflict' when the server rejects them).
//
// One row per (entity_type, entity_id): enqueueing a new op for the same
// entity replaces the previous pending op. This mirrors the server's
// last-write-wins semantics and keeps the outbox from growing unbounded
// while the device is offline.

import { execute, query, withTransaction } from "./db.js";
import { resolveEntityType } from "./entityMeta.js";

export const OUTBOX_CHANGED_EVENT = "survey-outbox-changed";

function nowIso() {
  return new Date().toISOString();
}

function makeOpId() {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return `op_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  }
  return `op_${Math.random().toString(16).slice(2, 14)}`;
}

function notifyOutboxChanged() {
  if (typeof window === "undefined") return;
  try {
    window.dispatchEvent(new CustomEvent(OUTBOX_CHANGED_EVENT));
  } catch {
    /* CustomEvent unavailable — badge refresh becomes lazy, not broken. */
  }
}

function parseOutboxRow(row) {
  let payload;
  try {
    payload = JSON.parse(row.payload_json || "{}");
    if (!payload || typeof payload !== "object") payload = {};
  } catch {
    payload = {};
  }
  return {
    op_id: row.op_id,
    entity_type: row.entity_type,
    operation: row.operation || "upsert",
    entity_id: row.entity_id,
    payload,
    queued_at: row.queued_at || "",
    queue_status: row.queue_status || "pending",
  };
}

/**
 * Record a local mutation for later push. Replaces any pending op for the
 * same (entity_type, entity_id) — the newest local state wins.
 *
 * @param {string} entityType  resolvable entity type ("project", "site", ...)
 * @param {"upsert"|"delete"} operation
 * @param {string} entityId
 * @param {object} payload     full record for upserts; minimal id payload for deletes
 */
export async function enqueueOutbox(entityType, operation, entityId, payload = {}) {
  const resolved = resolveEntityType(entityType);
  const id = String(entityId || "").trim();
  if (!resolved || !id) return null;

  const op = {
    op_id: makeOpId(),
    entity_type: resolved,
    operation: operation === "delete" ? "delete" : "upsert",
    entity_id: id,
    payload: {
      ...payload,
      server_updated_at: payload?.server_updated_at || "",
    },
    queued_at: nowIso(),
    queue_status: "pending",
  };

  await withTransaction(async () => {
    await execute(
      `DELETE FROM survey_sync_outbox WHERE entity_type=? AND entity_id=?`,
      [resolved, id],
    );
    await execute(
      `INSERT INTO survey_sync_outbox
       (op_id, entity_type, operation, entity_id, payload_json, queued_at, queue_status)
       VALUES (?,?,?,?,?,?,?)`,
      [
        op.op_id,
        op.entity_type,
        op.operation,
        op.entity_id,
        JSON.stringify(op.payload),
        op.queued_at,
        op.queue_status,
      ],
    );
  });
  notifyOutboxChanged();
  return op;
}

/** All outbox rows (pending + conflict), oldest first — push order. */
export async function listOutbox() {
  const rows = await query(
    `SELECT * FROM survey_sync_outbox ORDER BY queued_at ASC`,
    [],
  );
  return rows.map(parseOutboxRow);
}

export async function countOutbox() {
  const rows = await query(
    `SELECT COUNT(*) AS n FROM survey_sync_outbox`,
    [],
  );
  return Number(rows[0]?.n || 0);
}

/**
 * Remove outbox rows whose `${entity_type}:${entity_id}` key appears in
 * `entityKeys` — called after the server confirms those operations.
 */
export async function clearOutboxByEntityKeys(entityKeys) {
  const keys = Array.from(entityKeys || []).filter(Boolean);
  if (keys.length === 0) return 0;
  let removed = 0;
  await withTransaction(async () => {
    for (const key of keys) {
      const sep = key.indexOf(":");
      if (sep <= 0) continue;
      const entityType = key.slice(0, sep);
      const entityId = key.slice(sep + 1);
      const res = await execute(
        `DELETE FROM survey_sync_outbox WHERE entity_type=? AND entity_id=?`,
        [entityType, entityId],
      );
      removed += Number(res?.changes?.changes || 0);
    }
  });
  if (removed > 0) notifyOutboxChanged();
  return removed;
}

/** Flag rows the server rejected so the UI can surface them. */
export async function markOutboxConflicts(entityKeys) {
  const keys = Array.from(entityKeys || []).filter(Boolean);
  if (keys.length === 0) return 0;
  let marked = 0;
  await withTransaction(async () => {
    for (const key of keys) {
      const sep = key.indexOf(":");
      if (sep <= 0) continue;
      const entityType = key.slice(0, sep);
      const entityId = key.slice(sep + 1);
      const res = await execute(
        `UPDATE survey_sync_outbox SET queue_status='conflict' WHERE entity_type=? AND entity_id=?`,
        [entityType, entityId],
      );
      marked += Number(res?.changes?.changes || 0);
    }
  });
  if (marked > 0) notifyOutboxChanged();
  return marked;
}

/** Test/maintenance helper — wipe the queue. */
export async function clearOutboxAll() {
  await execute(`DELETE FROM survey_sync_outbox`, []);
  notifyOutboxChanged();
}
