// test-local-store.mjs — Playwright smoke test for the Hybrid Local
// architecture (Plan B). The backend is intentionally NOT consulted; this
// script exercises the on-device SQLite path end-to-end via the same
// surveyApi.* surface the application uses.
//
// Run with:
//   1. `npm run preview -- --port 4173 --host 127.0.0.1` (in another shell)
//   2. `node test-local-store.mjs`
//
// Output is mirrored to stdout AND written to test-local-store-log.txt.

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OFFLINE =
  process.env.OFFLINE === "1" ||
  String(process.env.OFFLINE || "").toLowerCase() === "true";
const SUFFIX = OFFLINE ? "-offline" : "";
const LOG_PATH = resolve(__dirname, `test-local-store${SUFFIX}-log.txt`);
const SHOT_PATH = resolve(__dirname, `test-local-store${SUFFIX}.png`);
const TARGET = process.env.TARGET_URL || "http://127.0.0.1:4173";

const logLines = [];
const log = (...args) => {
  const line = args
    .map((a) => (typeof a === "string" ? a : JSON.stringify(a)))
    .join(" ");
  logLines.push(line);
  // eslint-disable-next-line no-console
  console.log(line);
};

const consoleEvents = [];
const errorEvents = [];

async function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(
        () => reject(new Error(`Timeout (${ms} ms) waiting for ${label}`)),
        ms,
      ),
    ),
  ]);
}

async function preloadModules(page) {
  // Resolve all dynamic imports while the network is up and stash them on
  // `window.__hybridLocalTest`. Once stashed, calling these modules from
  // inside the offline phase does NOT trigger any new HTTP — exactly how an
  // APK behaves where every chunk is already bundled into the asset
  // archive.
  return page.evaluate(async () => {
    const api = await import("/src/lib/api.js");
    const localSurvey = await import("/src/lib/localSurveyService.js");
    const localStore = await import("/src/lib/localStore/index.js");
    await localStore.ensureSchema();
    window.__hybridLocalTest = { api, localSurvey, localStore };
    return {
      apiKeys: Object.keys(api).slice(0, 8),
      localSurveyKeys: Object.keys(localSurvey).slice(0, 8),
      localStoreKeys: Object.keys(localStore).slice(0, 8),
    };
  });
}

async function evaluateLocalStoreFlow(page) {
  // Inject a single async function into the page that walks the same code
  // path the application uses. Modules are read from `window.__hybridLocalTest`
  // populated by `preloadModules`, so the flow uses zero new network requests
  // — the same conditions a packaged APK runs under.
  return page.evaluate(async () => {
    const result = { steps: [] };
    function record(step, payload) {
      result.steps.push({ step, payload });
      try {
        console.log(`[flow] ${step}`, JSON.stringify(payload || {}));
      } catch {
        console.log(`[flow] ${step}`);
      }
    }

    try {
      record("phase_import_api", {});
      const stash = window.__hybridLocalTest;
      const apiMod = stash?.api || null;
      if (!apiMod) {
        record("import_api_failed", { message: "preloaded modules missing" });
      }
      if (apiMod) {
        record("imported", { keys: Object.keys(apiMod).slice(0, 8) });

        const ts = Date.now();
        const projectName = `LocalStoreSmoke ${ts}`;

        // 1. create
        const created = await apiMod.createSurveyProject({
          name: projectName,
          region: "Test Region",
          notes: "playwright smoke",
        });
        record("created", { project: created.project });

        const projectId = created.project?.project_id || "";
        if (!projectId) throw new Error("create did not return project_id");

        // 1b. B24 — the create must land in the durable sync outbox
        const localStoreMod = stash?.localStore || null;
        async function outboxOpFor(id) {
          if (!localStoreMod?.listOutbox) return null;
          const ops = await localStoreMod.listOutbox();
          return ops.find((op) => op.entity_id === id) || null;
        }
        const outboxAfterCreate = await outboxOpFor(projectId);
        record("outbox_after_create", {
          present: Boolean(outboxAfterCreate),
          operation: outboxAfterCreate?.operation || "",
          payloadName: outboxAfterCreate?.payload?.name || "",
        });
        if (
          localStoreMod?.listOutbox &&
          outboxAfterCreate?.operation !== "upsert"
        ) {
          throw new Error("B24: outbox missing upsert op after create");
        }

        // 2. list active
        const activeList = await apiMod.getSurveyProjects();
        record("listed_active", {
          total: activeList.total,
          contains: (activeList.projects || []).some(
            (p) => p.project_id === projectId,
          ),
        });

        // 3. soft delete
        const del = await apiMod.deleteSurveyProject(projectId);
        record("deleted", del);

        // 3b. B24 — outbox op should now be a delete (replaced the upsert)
        const outboxAfterDelete = await outboxOpFor(projectId);
        record("outbox_after_delete", {
          present: Boolean(outboxAfterDelete),
          operation: outboxAfterDelete?.operation || "",
        });
        if (
          localStoreMod?.listOutbox &&
          outboxAfterDelete?.operation !== "delete"
        ) {
          throw new Error("B24: outbox missing delete op after delete");
        }

        // 4. list active again — should be gone
        const afterDelete = await apiMod.getSurveyProjects();
        record("listed_after_delete", {
          total: afterDelete.total,
          contains: (afterDelete.projects || []).some(
            (p) => p.project_id === projectId,
          ),
        });

        // 5. trash should contain it
        const localServiceMod = stash?.localSurvey || null;
        if (!localServiceMod) {
          record("trash_skipped", { reason: "localSurveyService missing on stash" });
        } else {
          const trash = await localServiceMod.getSurveyTrash();
          record("trash_listed", {
            total: trash.total,
            containsProject: trash.items.some(
              (i) =>
                i.entity_type === "project" && i.project_id === projectId,
            ),
          });

          // 6. restore
          const restored = await localServiceMod.restoreSurveyEntity(
            "project",
            projectId,
          );
          record("restored", restored);

          // 6b. B24 — restore re-enqueues the live record as an upsert
          const outboxAfterRestore = await outboxOpFor(projectId);
          record("outbox_after_restore", {
            present: Boolean(outboxAfterRestore),
            operation: outboxAfterRestore?.operation || "",
            payloadName: outboxAfterRestore?.payload?.name || "",
          });
          if (
            localStoreMod?.listOutbox &&
            outboxAfterRestore?.operation !== "upsert"
          ) {
            throw new Error("B24: outbox missing upsert op after restore");
          }

          // 7. list active — should reappear
          const afterRestore = await apiMod.getSurveyProjects();
          record("listed_after_restore", {
            total: afterRestore.total,
            contains: (afterRestore.projects || []).some(
              (p) => p.project_id === projectId,
            ),
          });
        }

        result.success = true;
      } else {
        record("import_failed", {});
        result.success = false;
      }
    } catch (err) {
      record("error", { message: String(err?.message || err), stack: err?.stack });
      result.success = false;
    }
    return result;
  });
}

(async () => {
  mkdirSync(dirname(LOG_PATH), { recursive: true });
  log(`=== Hybrid Local smoke test${OFFLINE ? " [OFFLINE]" : ""} ===`);
  log("target:", TARGET);
  log("offline:", String(OFFLINE));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  const page = await context.newPage();

  page.on("console", (msg) => {
    const entry = { type: msg.type(), text: msg.text() };
    consoleEvents.push(entry);
    log(`[browser:${entry.type}]`, entry.text);
  });
  page.on("pageerror", (err) => {
    errorEvents.push({ name: err.name, message: err.message, stack: err.stack });
    log(`[pageerror]`, `${err.name}: ${err.message}`);
  });
  page.on("requestfailed", (req) => {
    const text = `${req.method()} ${req.url()} :: ${req.failure()?.errorText || "unknown"}`;
    consoleEvents.push({ type: "requestfailed", text });
    log(`[reqfailed]`, text);
  });

  try {
    log("→ navigating");
    await withTimeout(
      page.goto(TARGET, { waitUntil: "domcontentloaded", timeout: 30000 }),
      30000,
      "page.goto",
    );
    log("→ waiting for hydration (5 s)");
    await page.waitForTimeout(5000);

    log("→ pre-loading modules + ensureSchema (online)");
    const preload = await withTimeout(
      preloadModules(page),
      30000,
      "preloadModules",
    );
    log("preloaded:", JSON.stringify(preload));

    if (OFFLINE) {
      log("→ enabling offline mode (context.setOffline=true)");
      await context.setOffline(true);
      // Sanity-check the network is really down by trying an external fetch.
      try {
        const reachable = await page.evaluate(async () => {
          try {
            const ctrl = new AbortController();
            setTimeout(() => ctrl.abort(), 2000);
            const r = await fetch("https://example.com", { signal: ctrl.signal });
            return { ok: true, status: r.status };
          } catch (err) {
            return { ok: false, error: String(err?.message || err) };
          }
        });
        log("offline check:", JSON.stringify(reachable));
      } catch {
        log("offline check: external fetch failed (expected)");
      }
    }

    log("→ taking screenshot");
    await page.screenshot({ path: SHOT_PATH, fullPage: true });

    log("→ running local-store flow inside the page");
    const flow = await withTimeout(
      evaluateLocalStoreFlow(page),
      45000,
      "evaluateLocalStoreFlow",
    );
    log("flow result:", JSON.stringify(flow, null, 2));

    log("");
    log("=== console events (last 20) ===");
    for (const e of consoleEvents.slice(-20)) {
      log(`[${e.type}]`, e.text);
    }
    log("");
    log("=== page errors ===");
    if (errorEvents.length === 0) log("(none)");
    for (const e of errorEvents) {
      log(`${e.name}: ${e.message}`);
    }

    log("");
    log(flow.success ? "✓ PASS — hybrid local flow succeeded" : "✗ FAIL");
  } catch (err) {
    log("✗ FATAL:", err?.stack || err?.message || String(err));
  } finally {
    await context.close();
    await browser.close();
    writeFileSync(LOG_PATH, logLines.join("\n"), "utf8");
    log("log written:", LOG_PATH);
    log("screenshot:", SHOT_PATH);
  }
})();
