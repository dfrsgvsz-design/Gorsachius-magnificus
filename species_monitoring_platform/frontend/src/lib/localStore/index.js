// localStore/index.js — public entry point for the on-device survey store.
//
// Bootstrap order:
//   1. ensureSchema() runs the bootstrap script idempotently on first call.
//   2. CRUD / soft-delete helpers are re-exported for upstream service
//      modules (frontend/src/lib/localSurveyService.js will compose them).
//
// Anyone calling a CRUD helper before `ensureSchema()` will still work, but
// the very first call pays the migration cost. App startup should `await
// ensureSchema()` once during bootstrap to keep latency off the hot path.

import { closeDb, executeScript, getDb, query } from "./db.js";
import { migrateLegacyLocalStorage } from "./migrateLegacy.js";
import { SCHEMA_BOOTSTRAP_SQL, SCHEMA_VERSION } from "./schema.js";

let bootstrapPromise = null;

async function readSchemaVersion() {
  try {
    const rows = await query(
      "SELECT value FROM survey_meta WHERE key='schema_version' LIMIT 1",
      [],
    );
    return rows.length ? Number(rows[0].value) : 0;
  } catch {
    return 0;
  }
}

/** Idempotent. Safe to call from many call-sites; only the first one runs
 *  the bootstrap SQL and the legacy localStorage migration. */
export async function ensureSchema() {
  if (bootstrapPromise) return bootstrapPromise;
  bootstrapPromise = (async () => {
    await getDb(); // open connection
    await executeScript(SCHEMA_BOOTSTRAP_SQL);
    const current = await readSchemaVersion();
    if (current !== SCHEMA_VERSION) {
      // All DDL is IF NOT EXISTS — re-running the bootstrap script above
      // already created any tables/indexes added since `current` (e.g. the
      // v2 sync outbox). Only the recorded version needs a refresh.
      await executeScript(
        `INSERT OR REPLACE INTO survey_meta (key, value) VALUES ('schema_version', '${SCHEMA_VERSION}');`,
      );
    }
    // Legacy localStorage → SQLite migration runs once; the sentinel inside
    // survey_meta short-circuits subsequent launches.
    try {
      await migrateLegacyLocalStorage();
    } catch (err) {
      console.warn("[localStore] legacy migration failed (non-fatal)", err);
    }
  })();
  return bootstrapPromise;
}

/** Reset the bootstrap latch — for tests only. */
export async function __resetForTests__() {
  bootstrapPromise = null;
  await closeDb();
}

export { migrateLegacyLocalStorage } from "./migrateLegacy.js";

export { closeDb } from "./db.js";
export {
  ENTITY_META,
  ENTITY_TYPES,
  CASCADE_RULES,
  resolveEntityType,
  getEntityMeta,
} from "./entityMeta.js";
export {
  getById,
  listEntities,
  upsert,
  purgeRow,
  listIdsByWhere,
  listIdsByPayloadKey,
  makeId,
} from "./crud.js";
export {
  softDelete,
  restore,
  listTrash,
} from "./softDelete.js";
export {
  OUTBOX_CHANGED_EVENT,
  enqueueOutbox,
  listOutbox,
  countOutbox,
  clearOutboxByEntityKeys,
  markOutboxConflicts,
  clearOutboxAll,
} from "./outbox.js";
