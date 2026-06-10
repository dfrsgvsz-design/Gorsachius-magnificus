// localStore/migrateLegacy.js — one-shot import of pre-SQLite localStorage
// state into the new on-device SQLite store.
//
// surveyOffline.js used to keep every entity in the
// `bird-platform-field-survey-v1` localStorage blob. After we switch to
// SQLite as the source of truth, we still want existing fielded devices to
// retain their data without a manual export/import cycle. This module:
//
//   1. Reads the legacy blob (if present).
//   2. Walks each entity collection and upserts every row.
//   3. Stamps a sentinel into `survey_meta` so subsequent app launches skip
//      the migration entirely.
//
// The legacy blob is intentionally NOT deleted. It stays as a recoverable
// backup for the first few releases — once we are confident the SQLite path
// is stable a future migration will retire it.

import { execute, query } from "./db.js";
import { upsert } from "./crud.js";

const LEGACY_STORAGE_KEY = "bird-platform-field-survey-v1";
const META_KEY = "legacy_localstorage_migrated_at";

const LIST_KEY_TO_ENTITY = Object.freeze({
  projects: "project",
  sites: "site",
  routes: "route",
  observations: "observation",
  tracks: "track",
  mapPackages: "map_package",
  designAssets: "design_asset",
  events: "event",
  exportJobs: "export_job",
});

function readLegacyBlob() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

async function readMetaFlag() {
  try {
    const rows = await query(
      "SELECT value FROM survey_meta WHERE key=? LIMIT 1",
      [META_KEY],
    );
    return rows.length ? String(rows[0].value || "") : "";
  } catch {
    return "";
  }
}

async function writeMetaFlag(value) {
  await execute(
    "INSERT OR REPLACE INTO survey_meta (key, value) VALUES (?, ?)",
    [META_KEY, value],
  );
}

/**
 * @returns {{ migrated: boolean, imported: number, skipped: number, errors: number }}
 */
export async function migrateLegacyLocalStorage() {
  const result = { migrated: false, imported: 0, skipped: 0, errors: 0 };
  const existingFlag = await readMetaFlag();
  if (existingFlag) {
    result.skipped = 1;
    return result;
  }
  const blob = readLegacyBlob();
  if (!blob) {
    // Nothing to import; still stamp the sentinel so we don't keep checking.
    await writeMetaFlag(new Date().toISOString());
    result.migrated = true;
    return result;
  }

  for (const [listKey, entityType] of Object.entries(LIST_KEY_TO_ENTITY)) {
    const rows = blob[listKey];
    if (!Array.isArray(rows) || rows.length === 0) continue;
    for (const row of rows) {
      if (!row || typeof row !== "object") continue;
      try {
        // Carry over the original deleted_at so soft-deleted entries stay in
        // the trash bucket after migration.
        await upsert(entityType, row, {
          preserveDeletedAt: Boolean(row.deleted_at),
        });
        result.imported += 1;
      } catch (err) {
        result.errors += 1;
        console.warn(
          `[migrateLegacy] failed to import ${entityType}`,
          row,
          err,
        );
      }
    }
  }

  await writeMetaFlag(new Date().toISOString());
  result.migrated = true;
  return result;
}

export const __testing__ = { LEGACY_STORAGE_KEY, META_KEY, LIST_KEY_TO_ENTITY };
