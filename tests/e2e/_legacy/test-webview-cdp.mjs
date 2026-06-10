// CDP attach to running Android WebView; capture all console + page events + reload + dump errors.
// Run from frontend/ so it can resolve @playwright/test.
// Usage: node test-webview-cdp.mjs <CDP-URL> <output-prefix>
//   adb forward tcp:9222 localabstract:webview_devtools_remote_<PID>
//   node test-webview-cdp.mjs http://127.0.0.1:9222 hybridlocal-pixel7

import { chromium } from "playwright";
import { writeFileSync, mkdirSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

const CDP_URL = process.argv[2] || "http://127.0.0.1:9222";
const OUT = process.argv[3] || "webview-result";
const OUT_DIR = "..";
const SCREENSHOT_DIR = "../test-screenshots";

mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function main() {
  console.log(`[cdp] connecting ${CDP_URL}...`);
  const browser = await chromium.connectOverCDP(CDP_URL);
  const ctx = browser.contexts()[0] || (await browser.newContext());
  const pages = ctx.pages();
  console.log(`[cdp] ${pages.length} page(s)`);

  const page =
    pages.find((p) => p.url().includes("localhost") && !p.url().includes("service-worker")) ||
    pages.find((p) => !p.url().includes("service-worker")) ||
    pages[0];
  if (!page) {
    console.error("no page available");
    process.exit(2);
  }
  console.log(`[cdp] attached to ${page.url()}`);

  const events = [];
  page.on("console", (msg) => {
    const loc = msg.location();
    events.push({
      t: Date.now(),
      kind: `console.${msg.type()}`,
      text: msg.text(),
      url: loc.url,
      line: loc.lineNumber,
      col: loc.columnNumber,
    });
  });
  page.on("pageerror", (err) => {
    events.push({
      t: Date.now(),
      kind: "pageerror",
      text: err.message,
      stack: err.stack,
    });
  });
  page.on("requestfailed", (req) => {
    events.push({
      t: Date.now(),
      kind: "requestfailed",
      text: `${req.failure()?.errorText || ""} ${req.method()} ${req.url()}`,
    });
  });
  page.on("response", (res) => {
    const s = res.status();
    if (s >= 400) {
      events.push({ t: Date.now(), kind: "http>=400", text: `${s} ${res.url()}` });
    }
  });

  console.log("[cdp] installing global error hook in page...");
  await page.evaluate(() => {
    if (window.__webviewHookInstalled) return;
    window.__webviewHookInstalled = true;
    window.__capturedErrors = [];
    const origErr = console.error.bind(console);
    console.error = (...args) => {
      try {
        const ser = args.map((a) => {
          if (a instanceof Error) return { message: a.message, stack: a.stack, name: a.name };
          if (typeof a === "object" && a !== null) {
            try {
              return JSON.parse(JSON.stringify(a));
            } catch {
              return String(a);
            }
          }
          return a;
        });
        window.__capturedErrors.push({ t: Date.now(), kind: "console.error", args: ser });
      } catch {}
      origErr(...args);
    };
    window.addEventListener("unhandledrejection", (ev) => {
      window.__capturedErrors.push({
        t: Date.now(),
        kind: "unhandledrejection",
        reason: String(ev.reason),
        stack: ev.reason && ev.reason.stack,
      });
    });
    window.addEventListener("error", (ev) => {
      window.__capturedErrors.push({
        t: Date.now(),
        kind: "window.error",
        message: ev.message,
        filename: ev.filename,
        lineno: ev.lineno,
        colno: ev.colno,
        stack: ev.error && ev.error.stack,
      });
    });
  });

  console.log("[cdp] reloading to re-trigger startup errors...");
  try {
    await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
  } catch (e) {
    console.log("reload note:", e.message);
  }

  console.log("[cdp] settling 12s...");
  await sleep(12000);

  console.log("[cdp] dumping captured errors from window.__capturedErrors...");
  const captured = await page
    .evaluate(() => (window.__capturedErrors || []).slice(0, 200))
    .catch((e) => ({ evalError: e.message }));

  console.log("[cdp] probing webview state...");
  const probe = await page
    .evaluate(async () => {
      const out = {};
      try {
        out.userAgent = navigator.userAgent;
        out.online = navigator.onLine;
        out.capacitor = {
          present: typeof window.Capacitor !== "undefined",
          isNative:
            typeof window.Capacitor?.isNativePlatform === "function"
              ? window.Capacitor.isNativePlatform()
              : null,
          platform:
            typeof window.Capacitor?.getPlatform === "function"
              ? window.Capacitor.getPlatform()
              : null,
          plugins: Object.keys(window.Capacitor?.Plugins || {}),
        };
        if (typeof indexedDB.databases === "function") {
          out.indexedDB = await indexedDB.databases();
        } else {
          out.indexedDB = "not supported";
        }
        if (navigator.serviceWorker) {
          const regs = await navigator.serviceWorker.getRegistrations();
          out.serviceWorker = regs.map((r) => ({
            scope: r.scope,
            state: r.active?.state,
          }));
        } else {
          out.serviceWorker = "no SW api";
        }
        if (window.caches && typeof window.caches.keys === "function") {
          out.caches = await window.caches.keys();
        }
        // DOM probes
        const navButtons = Array.from(
          document.querySelectorAll("nav button, .mobile-bottom-nav button, [data-tab]"),
        ).map((b) => b.textContent?.trim().slice(0, 24)).filter(Boolean);
        out.navTabs = navButtons.slice(0, 12);
        out.activeProjectName = document.querySelector("[data-active-project-name]")?.textContent?.trim() || null;
        out.h1 = document.querySelector("h1")?.textContent?.trim() || null;
      } catch (e) {
        out.error = e.message;
        out.stack = e.stack;
      }
      return out;
    })
    .catch((e) => ({ probeError: e.message }));

  console.log("[cdp] saving screenshot...");
  await page
    .screenshot({ path: `${SCREENSHOT_DIR}/${OUT}-after-reload.png`, fullPage: false })
    .catch((e) => console.log("screenshot fail:", e.message));

  const summary = {
    cdpUrl: CDP_URL,
    pageUrl: page.url(),
    eventCount: events.length,
    consoleErrorCount: events.filter((e) => e.kind === "console.error").length,
    consoleWarnCount: events.filter((e) => e.kind === "console.warning").length,
    pageErrorCount: events.filter((e) => e.kind === "pageerror").length,
    requestFailedCount: events.filter((e) => e.kind === "requestfailed").length,
    http4xx5xxCount: events.filter((e) => e.kind === "http>=400").length,
    capturedErrorsCount: Array.isArray(captured) ? captured.length : 0,
    probe,
  };

  writeFileSync(`${OUT_DIR}/${OUT}-events.json`, JSON.stringify(events, null, 2));
  writeFileSync(`${OUT_DIR}/${OUT}-captured.json`, JSON.stringify(captured, null, 2));
  writeFileSync(`${OUT_DIR}/${OUT}-summary.json`, JSON.stringify(summary, null, 2));

  console.log("\n=== SUMMARY ===");
  console.log(JSON.stringify(summary, null, 2));

  await browser.close();
  console.log("[cdp] disconnected");
}

main().catch((err) => {
  console.error("FATAL:", err);
  process.exit(1);
});
