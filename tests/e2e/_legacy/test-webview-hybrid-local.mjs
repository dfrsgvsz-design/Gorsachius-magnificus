// CDP attach to running Android WebView; capture all console events + reload + dump errors.
// Usage: node test-webview-hybrid-local.mjs <CDP-URL> <output-prefix>
//   adb forward tcp:9222 localabstract:webview_devtools_remote_<PID>
//   node test-webview-hybrid-local.mjs http://127.0.0.1:9222 hybridlocal-pixel7

import { chromium } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

const CDP_URL = process.argv[2] || "http://127.0.0.1:9222";
const OUT = process.argv[3] || "webview-result";

async function main() {
  console.log(`[cdp] connecting ${CDP_URL}...`);
  const browser = await chromium.connectOverCDP(CDP_URL);
  const contexts = browser.contexts();
  const ctx = contexts[0] || (await browser.newContext());
  const pages = ctx.pages();
  console.log(`[cdp] ${pages.length} page(s)`);

  let page =
    pages.find((p) => p.url().includes("localhost")) || pages[0];
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
      events.push({
        t: Date.now(),
        kind: "http>=400",
        text: `${s} ${res.url()}`,
      });
    }
  });

  console.log("[cdp] installing global error hook...");
  await page.evaluate(() => {
    if (window.__webviewHookInstalled) return;
    window.__webviewHookInstalled = true;
    window.__capturedErrors = [];
    const origErr = console.error.bind(console);
    console.error = (...args) => {
      try {
        const ser = args.map((a) => {
          if (a instanceof Error) {
            return { message: a.message, stack: a.stack, name: a.name };
          }
          if (typeof a === "object" && a !== null) {
            try {
              return JSON.parse(JSON.stringify(a));
            } catch {
              return String(a);
            }
          }
          return a;
        });
        window.__capturedErrors.push({ t: Date.now(), args: ser });
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

  console.log("[cdp] settling 10s...");
  await sleep(10000);

  console.log("[cdp] dumping captured errors from window.__capturedErrors...");
  const captured = await page
    .evaluate(() => (window.__capturedErrors || []).slice(0, 100))
    .catch((e) => ({ evalError: e.message }));

  console.log("[cdp] probing hybrid local store state...");
  const probeResult = await page
    .evaluate(async () => {
      const out = { steps: [] };
      try {
        out.steps.push({ step: "ua", value: navigator.userAgent });
        out.steps.push({
          step: "capacitor",
          value: typeof window.Capacitor !== "undefined",
          isNative: window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform(),
          plugins: window.Capacitor && Object.keys(window.Capacitor.Plugins || {}),
        });
        out.steps.push({
          step: "indexeddb",
          databases: typeof indexedDB.databases === "function"
            ? await indexedDB.databases()
            : "not supported",
        });
        out.steps.push({
          step: "service-worker",
          regs: navigator.serviceWorker
            ? (await navigator.serviceWorker.getRegistrations()).map((r) => r.scope)
            : "not supported",
        });
        out.steps.push({
          step: "local-store-counts",
          // From DOM: bottom nav text presence
          fieldopsTabActive: document.querySelector('[data-tab="fieldops"][aria-selected="true"], .active[data-tab="fieldops"]') ? true : null,
        });
      } catch (e) {
        out.error = e.message;
        out.stack = e.stack;
      }
      return out;
    })
    .catch((e) => ({ probeError: e.message }));

  console.log("[cdp] taking screenshot...");
  await page
    .screenshot({ path: `test-screenshots/${OUT}-after-reload.png`, fullPage: false })
    .catch((e) => console.log("screenshot fail:", e.message));

  const summary = {
    cdpUrl: CDP_URL,
    pageUrl: page.url(),
    eventCount: events.length,
    consoleErrors: events.filter((e) => e.kind === "console.error").length,
    pageErrors: events.filter((e) => e.kind === "pageerror").length,
    requestFailures: events.filter((e) => e.kind === "requestfailed").length,
    http4xx5xx: events.filter((e) => e.kind === "http>=400").length,
    capturedErrorsCount: Array.isArray(captured) ? captured.length : 0,
    probe: probeResult,
  };

  writeFileSync(`${OUT}-events.json`, JSON.stringify(events, null, 2));
  writeFileSync(`${OUT}-captured.json`, JSON.stringify(captured, null, 2));
  writeFileSync(`${OUT}-summary.json`, JSON.stringify(summary, null, 2));

  console.log("\n=== SUMMARY ===");
  console.log(JSON.stringify(summary, null, 2));

  await browser.close();
  console.log("[cdp] disconnected");
}

main().catch((err) => {
  console.error("FATAL:", err);
  process.exit(1);
});
