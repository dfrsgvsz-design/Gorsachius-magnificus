// localStore/db.js — Capacitor SQLite connection manager.
//
// Single durable connection per app session, shared by all CRUD modules.
// On Android the database lives in the app sandbox; on web it persists via
// jeep-sqlite which uses IndexedDB under the hood.
//
// All write helpers run through `withTransaction` so cascading soft-delete
// stays atomic — the same guarantee `_delete_entity_locked` provides on the
// server.

import { Capacitor } from "@capacitor/core";
import {
  CapacitorSQLite,
  SQLiteConnection,
} from "@capacitor-community/sqlite";

const DB_NAME = "bird_survey_local";
const DB_VERSION = 1;
const ENCRYPTED = false;
const MODE = "no-encryption";
const READ_ONLY = false;

let sqliteConnection = null;
let database = null;
let openPromise = null;
let webStoreReady = null;
// Track whether we are inside `withTransaction`. Web-mode jeep-sqlite resets
// the transaction state when `saveToStore` runs mid-flight, which produces
// "CommitTransaction: cannot commit - no transaction is active" errors. We
// therefore skip per-statement persistence while a transaction is open and
// flush once at commit time.
let inTransaction = false;

/** Define the <jeep-sqlite> custom element + initialize its IndexedDB store
 *  before any web platform connection is opened. Idempotent. */
async function ensureWebStore() {
  if (Capacitor.getPlatform() !== "web") return;
  if (webStoreReady) return webStoreReady;

  webStoreReady = (async () => {
    const { defineCustomElements } = await import("jeep-sqlite/loader");
    await defineCustomElements(window);
    if (!document.querySelector("jeep-sqlite")) {
      const el = document.createElement("jeep-sqlite");
      document.body.appendChild(el);
    }
    await customElements.whenDefined("jeep-sqlite");
    await CapacitorSQLite.initWebStore();
  })();

  return webStoreReady;
}

function getConnectionFactory() {
  if (!sqliteConnection) {
    sqliteConnection = new SQLiteConnection(CapacitorSQLite);
  }
  return sqliteConnection;
}

/** Open the durable connection. Subsequent calls return the same handle. */
export async function getDb() {
  if (database) return database;
  if (openPromise) return openPromise;

  openPromise = (async () => {
    await ensureWebStore();
    const factory = getConnectionFactory();
    const exists = (await factory.isConnection(DB_NAME, ENCRYPTED)).result;
    let conn;
    if (exists) {
      conn = await factory.retrieveConnection(DB_NAME, ENCRYPTED);
    } else {
      try {
        conn = await factory.createConnection(
          DB_NAME,
          ENCRYPTED,
          MODE,
          DB_VERSION,
          READ_ONLY,
        );
      } catch (err) {
        // The native plugin keeps a global connection registry that survives
        // a JS-side `SQLiteConnection` reset. If the previous app process was
        // force-stopped without `closeConnection` (typical on Android), the
        // registry can still hold the entry while `isConnection` reports
        // false. Recover by retrieving the dangling connection instead of
        // bubbling the "already exists" error to the UI.
        const message = String(err?.message ?? err ?? "");
        if (/already exists/i.test(message)) {
          conn = await factory.retrieveConnection(DB_NAME, ENCRYPTED);
        } else {
          throw err;
        }
      }
    }
    await conn.open();
    database = conn;
    if (Capacitor.getPlatform() === "web") {
      // Persist immediately so a hard reload doesn't lose schema bootstrap.
      try {
        await CapacitorSQLite.saveToStore({ database: DB_NAME });
      } catch {
        /* first-run save attempt before any data — safe to ignore. */
      }
    }
    return conn;
  })();

  try {
    return await openPromise;
  } finally {
    openPromise = null;
  }
}

/** Close the connection. Used in tests and on explicit teardown. */
export async function closeDb() {
  if (!database || !sqliteConnection) return;
  await sqliteConnection.closeConnection(DB_NAME, ENCRYPTED);
  database = null;
}

/** Execute a single non-query statement (CREATE/INSERT/UPDATE/DELETE). */
export async function execute(stmt, params = []) {
  const db = await getDb();
  const res = await db.run(stmt, params, false);
  if (!inTransaction) {
    await persistIfWeb();
  }
  return res;
}

/** Run multiple statements as one batched script (for schema bootstrap). */
export async function executeScript(sql) {
  const db = await getDb();
  const res = await db.execute(sql, false);
  if (!inTransaction) {
    await persistIfWeb();
  }
  return res;
}

/** Run a SELECT and return rows as plain objects. */
export async function query(stmt, params = []) {
  const db = await getDb();
  const res = await db.query(stmt, params);
  return res.values || [];
}

/** Atomic transaction wrapper. Roll back on any thrown error.
 *
 *  Sets the module-level `inTransaction` flag so individual `execute` /
 *  `executeScript` calls inside `fn` do NOT trigger `saveToStore` — that
 *  call resets jeep-sqlite's transaction context in web mode and surfaces
 *  as a confusing "cannot commit - no transaction is active" failure.
 *  We persist once after the commit instead.
 */
export async function withTransaction(fn) {
  const db = await getDb();
  await db.beginTransaction();
  inTransaction = true;
  try {
    const out = await fn(db);
    await db.commitTransaction();
    inTransaction = false;
    await persistIfWeb();
    return out;
  } catch (err) {
    inTransaction = false;
    try {
      await db.rollbackTransaction();
    } catch {
      /* connection may already be closed; surface original error. */
    }
    throw err;
  }
}

async function persistIfWeb() {
  if (Capacitor.getPlatform() !== "web") return;
  try {
    await CapacitorSQLite.saveToStore({ database: DB_NAME });
  } catch {
    /* swallow — saveToStore failure shouldn't reject the user write. */
  }
}

export const __testing__ = { DB_NAME };
