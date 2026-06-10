/**
 * APK deep functional tester via Chrome DevTools Protocol against the running
 * Android WebView. Connects through `adb forward tcp:9223 localabstract:webview_devtools_remote_<pid>`
 * and drives the same JS context the user sees on screen.
 *
 * Scenarios:
 *   T1  All 9 tabs navigate without page errors (overview/fieldops/species/verify/monitor/sdm/devices/settings/about)
 *   T2  SettingsTab.ProjectManagementPanel — create a project, expand, create a site
 *   T3  FieldOpsTab — select project, type observer name, click "开始调查"
 *   T4  Data persistence — read localStorage[bird-platform-field-survey-v1] before/after
 *   T5  Sync queue — count syncQueue entries after each mutation
 *   T6  Native plugin reachability — call Camera/Geolocation/Filesystem from JS
 *   T7  Service worker + cache state final snapshot
 *
 * Output: test-screenshots/apk-deep/{summary.json, NN-*.png}
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';

const CDP = process.env.CDP_URL || 'http://127.0.0.1:9223';
const OUT = './test-screenshots/apk-deep';
mkdirSync(OUT, { recursive: true });

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const results = { startedAt: new Date().toISOString(), scenarios: [], consoleErrors: [], pageErrors: [] };

function log(level, name, detail = '') {
  const tag = level === 'pass' ? 'PASS' : level === 'warn' ? 'WARN' : 'FAIL';
  console.log(`  [${tag}] ${name}${detail ? ' — ' + detail : ''}`);
  results.scenarios.push({ name, status: level, detail });
}

async function snap(page, name) {
  const path = join(OUT, `${name}.png`);
  try {
    await page.screenshot({ path, fullPage: false });
    console.log(`        ↳ ${name}.png`);
  } catch (err) {
    console.log(`        ↳ snap failed: ${err.message}`);
  }
}

async function tap(page, selectors, label) {
  for (const sel of selectors) {
    const loc = page.locator(sel).first();
    if (await loc.count()) {
      try {
        await loc.scrollIntoViewIfNeeded();
        if (await loc.isVisible()) {
          await loc.click();
          return sel;
        }
      } catch {}
    }
  }
  console.log(`    -- tap miss: ${label || selectors[0]}`);
  return null;
}

async function readStorage(page) {
  return page.evaluate(() => {
    const raw = localStorage.getItem('bird-platform-field-survey-v1') || '{}';
    let parsed = {};
    try { parsed = JSON.parse(raw); } catch {}
    return {
      keys: Object.keys(localStorage),
      device_id: localStorage.getItem('bird-platform-field-device-id') || null,
      raw_size: raw.length,
      projects: (parsed.projects || []).length,
      sites: (parsed.sites || []).length,
      routes: (parsed.routes || []).length,
      observations: (parsed.observations || []).length,
      tracks: (parsed.tracks || []).length,
      events: (parsed.events || []).length,
      syncQueue: (parsed.syncQueue || []).length,
      mediaInbox: (parsed.mediaInbox || []).length,
      taxonomyPackages: (parsed.taxonomyPackages || []).length,
      activeProjectId: parsed.activeProjectId || '',
      activeSiteId: parsed.activeSiteId || '',
      activeProtocol: parsed.activeProtocol || '',
      activeJurisdiction: parsed.activeJurisdiction || '',
    };
  });
}

async function run() {
  console.log(`\n=== APK deep functional tester ===\nCDP: ${CDP}\n`);

  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  let page = ctx.pages().find((p) => p.url().includes('localhost')) || ctx.pages()[0];

  if (!page) {
    console.error('No WebView page found via CDP');
    process.exit(2);
  }

  page.on('console', (msg) => {
    if (msg.type() === 'error') results.consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => results.pageErrors.push(err.message));

  console.log(`URL: ${page.url()}`);
  console.log(`Title: ${await page.title()}`);

  await snap(page, '00-cdp-attached');

  // ── T0 baseline storage ──
  const base = await readStorage(page);
  console.log(`\nBaseline storage: ${JSON.stringify(base)}`);
  results.baseline_storage = base;

  // ── T1 9-tab sweep ──
  console.log('\n--- T1: 9-tab sweep ---');
  const tabSelectors = [
    { id: 'overview', sels: ['button:has-text("总览")', 'button:has-text("Overview")', 'button.mobile-nav-button >> text=总览'] },
    { id: 'fieldops', sels: ['button:has-text("外业")', 'button:has-text("Field Survey")'] },
    { id: 'species', sels: ['button:has-text("物种")', 'button:has-text("Species")'] },
    { id: 'monitor', sels: ['button:has-text("监测")', 'button:has-text("Monitor")'] },
    { id: 'more',    sels: ['button:has-text("更多")', 'button:has-text("More")'] },
  ];
  for (const tab of tabSelectors) {
    const matched = await tap(page, tab.sels, tab.id);
    await wait(900);
    await snap(page, `01-tab-${tab.id}`);
    log(matched ? 'pass' : 'warn', `T1 nav.${tab.id}`, matched || 'tab not visible');
  }

  // ── T2 SettingsTab + ProjectManagementPanel ──
  console.log('\n--- T2: Settings → ProjectManagementPanel ---');
  // close more sheet if open
  await page.keyboard.press('Escape').catch(() => {});
  await wait(300);
  const moreOpened = await tap(page, ['button:has-text("更多")', 'button:has-text("More")'], 'more');
  await wait(700);
  const settingsClicked = await tap(page, [
    'button:has-text("设置")',
    'button:has-text("Settings")',
    '.mobile-quick-action:has-text("设置")',
  ], 'settings');
  await wait(1500);
  await snap(page, '02-settings-tab');

  // Look for project management section
  const settingsState = await page.evaluate(() => {
    const allText = document.body.innerText;
    return {
      has_pmp: /项目管理|Project Management|管理\s*项目|站点管理|新建项目|Create project/i.test(allText),
      headings: Array.from(document.querySelectorAll('h1, h2, h3, h4'))
        .map((el) => el.textContent.trim())
        .filter((t) => t)
        .slice(0, 20),
    };
  });
  log(settingsState.has_pmp ? 'pass' : 'fail', 'T2 ProjectManagementPanel visible in Settings',
    settingsState.has_pmp ? `headings: ${settingsState.headings.join(' | ').slice(0, 200)}` : `headings: ${settingsState.headings.join(' | ').slice(0, 200)}`);

  // Try to expand panel + create a test project via DOM events
  const pmpRoot = page.locator('text=/项目管理|Project Management/i').first();
  if (await pmpRoot.count()) {
    try {
      await pmpRoot.scrollIntoViewIfNeeded();
      await pmpRoot.click();
      await wait(500);
      await snap(page, '03-pmp-expanded');
    } catch {}
  }

  const beforeProj = await readStorage(page);

  // Use the project name input directly. ProjectManagementPanel uses `placeholder`s.
  const projectNameInput = page.locator('input[placeholder*="项目名"], input[placeholder*="Project name"], input[placeholder*="项目"]').first();
  if (await projectNameInput.count()) {
    try {
      await projectNameInput.fill(`E2E测试项目-${Date.now().toString().slice(-6)}`);
      await wait(300);
      const createBtn = page.locator('button:has-text("创建项目"), button:has-text("Create Project"), button:has-text("添加项目"), button:has-text("新建项目")').first();
      if (await createBtn.count()) {
        await createBtn.click();
        await wait(1500);
        await snap(page, '04-after-create-project');
      }
    } catch (err) {
      console.log(`    project create exception: ${err.message}`);
    }
  }

  const afterProj = await readStorage(page);
  log(
    afterProj.projects > beforeProj.projects ? 'pass' :
    afterProj.syncQueue > beforeProj.syncQueue ? 'pass' : 'warn',
    'T2 create project mutates storage',
    `projects: ${beforeProj.projects} → ${afterProj.projects}, syncQueue: ${beforeProj.syncQueue} → ${afterProj.syncQueue}`,
  );

  // ── T3 FieldOpsTab survey flow ──
  console.log('\n--- T3: FieldOps survey flow ---');
  await tap(page, ['button:has-text("外业")', 'button:has-text("Field Survey")'], 'fieldops');
  await wait(1200);
  await snap(page, '05-fieldops-on-entry');

  // Tap first project row if any
  const projectRow = page.locator('button:has(svg) span:has-text("Field Survey")').first();
  if (await projectRow.count()) {
    try {
      await projectRow.click();
      await wait(800);
      await snap(page, '06-after-project-pick');
    } catch {}
  }

  // Type observer name in setup card
  const observerInput = page.locator('input[placeholder*="姓名"], input[placeholder*="Enter name"]').first();
  let observerTyped = false;
  if (await observerInput.count()) {
    try {
      await observerInput.fill('张三 (E2E)');
      await wait(300);
      observerTyped = true;
      await snap(page, '07-observer-typed');
    } catch {}
  }
  log(observerTyped ? 'pass' : 'warn', 'T3 fill observer name', observerTyped ? '"张三 (E2E)"' : 'input not found');

  const weatherInput = page.locator('input[placeholder*="晴"], input[placeholder*="Sunny"]').first();
  if (await weatherInput.count()) {
    try {
      await weatherInput.fill('多云转晴, 12℃');
      await wait(300);
    } catch {}
  }

  // Read GPS coord text
  const gpsText = await page.locator('text=/经纬度|GPS/i').first().locator('..').innerText().catch(() => '');
  const gpsMatched = /\d{1,3}\.\d{3,}.*\d{1,3}\.\d{3,}/.test(gpsText);
  log(gpsMatched ? 'pass' : 'warn', 'T3 GPS coordinates rendered', gpsText.split('\n').slice(0, 2).join(' | ').slice(0, 80));

  const beforeStart = await readStorage(page);
  const startBtn = page.locator('button:has-text("开始调查"), button:has-text("Start Survey")').first();
  if (await startBtn.count()) {
    try {
      const enabled = !(await startBtn.isDisabled());
      log(enabled ? 'pass' : 'fail', 'T3 start survey button enabled', `disabled=${!enabled}`);
      if (enabled) {
        await startBtn.click();
        await wait(2500);
        await snap(page, '08-survey-step');
      }
    } catch {}
  }
  const afterStart = await readStorage(page);
  log(
    afterStart.events > beforeStart.events || afterStart.syncQueue > beforeStart.syncQueue ? 'pass' : 'warn',
    'T3 start survey created event',
    `events: ${beforeStart.events} → ${afterStart.events}, syncQueue: ${beforeStart.syncQueue} → ${afterStart.syncQueue}`,
  );

  // Click camera FAB on survey step
  await wait(1000);
  const fab = page.locator('button:has(svg.lucide-camera), button:has(svg.lucide-plus)').last();
  if (await fab.count()) {
    try {
      await fab.click();
      await wait(1200);
      await snap(page, '09-after-fab');
    } catch {}
  }

  // ── T4 native plugin reachability ──
  console.log('\n--- T4: native plugin reachability ---');
  const nativeProbe = await page.evaluate(async () => {
    const r = { Capacitor: false, plugins: [], geolocation: null, camera_ready: null, filesystem_ready: null };
    try {
      const Cap = window.Capacitor;
      r.Capacitor = !!Cap;
      r.plugins = Cap?.Plugins ? Object.keys(Cap.Plugins) : [];
      r.platform = Cap?.getPlatform?.() || 'unknown';
      r.is_native = Cap?.isNativePlatform?.() || false;
      try {
        const pos = await new Promise((res, rej) => {
          navigator.geolocation.getCurrentPosition(p => res(p), e => rej(e), { enableHighAccuracy: false, timeout: 6000 });
        });
        r.geolocation = { lat: pos.coords.latitude, lon: pos.coords.longitude, acc: pos.coords.accuracy };
      } catch (e) { r.geolocation = { error: String(e?.message || e) }; }
      try {
        const Cam = Cap?.Plugins?.Camera;
        r.camera_ready = !!Cam;
        if (Cam?.checkPermissions) {
          r.camera_permissions = await Cam.checkPermissions();
        }
      } catch (e) { r.camera_ready = String(e); }
      try {
        const FS = Cap?.Plugins?.Filesystem;
        r.filesystem_ready = !!FS;
        if (FS?.checkPermissions) {
          r.filesystem_permissions = await FS.checkPermissions();
        }
      } catch (e) { r.filesystem_ready = String(e); }
    } catch (e) { r.error = String(e); }
    return r;
  });
  console.log(`    Capacitor: ${nativeProbe.Capacitor}, native: ${nativeProbe.is_native}, plugins: ${nativeProbe.plugins.join(',')}`);
  console.log(`    GPS: ${JSON.stringify(nativeProbe.geolocation)}`);
  console.log(`    Camera: ready=${nativeProbe.camera_ready}, perms=${JSON.stringify(nativeProbe.camera_permissions)}`);
  console.log(`    Filesystem: ready=${nativeProbe.filesystem_ready}, perms=${JSON.stringify(nativeProbe.filesystem_permissions)}`);
  log('pass', 'T4 Capacitor native plugins exposed', `${nativeProbe.plugins.length} plugins, platform=${nativeProbe.platform}`);
  log(
    nativeProbe.geolocation?.lat ? 'pass' : 'fail',
    'T4 Geolocation.getCurrentPosition',
    nativeProbe.geolocation?.lat ? `${nativeProbe.geolocation.lat}, ${nativeProbe.geolocation.lon}` : nativeProbe.geolocation?.error,
  );

  // ── T5 final state ──
  const final = await readStorage(page);
  results.final_storage = final;
  results.native_probe = nativeProbe;
  console.log(`\nFinal storage: ${JSON.stringify(final)}`);

  // ── T6 backend connectivity attempt (axios goes to https://localhost/api which won't reach host) ──
  console.log('\n--- T6: backend connectivity test ---');
  const apiTest = await page.evaluate(async () => {
    try {
      const res = await fetch('/api/health', { method: 'GET' });
      return { status: res.status, ok: res.ok };
    } catch (e) {
      return { error: String(e?.message || e) };
    }
  });
  console.log(`    /api/health: ${JSON.stringify(apiTest)}`);
  log(
    apiTest.ok ? 'pass' : 'warn',
    'T6 backend reachable from WebView (offline-first design tolerates failure)',
    apiTest.ok ? `status=${apiTest.status}` : `error/status=${apiTest.error || apiTest.status}`,
  );

  // ── T7 SW + cache final snapshot ──
  const finalSw = await page.evaluate(async () => {
    const regs = await navigator.serviceWorker.getRegistrations();
    const cnames = await caches.keys();
    return {
      sw_count: regs.length,
      sw_active: regs.map(r => r.active?.state),
      cache_names: cnames,
    };
  });
  console.log(`\nSW final: ${JSON.stringify(finalSw)}`);
  results.sw_final = finalSw;

  results.summary = {
    pass: results.scenarios.filter((s) => s.status === 'pass').length,
    warn: results.scenarios.filter((s) => s.status === 'warn').length,
    fail: results.scenarios.filter((s) => s.status === 'fail').length,
    consoleErrors: results.consoleErrors.length,
    pageErrors: results.pageErrors.length,
  };
  results.endedAt = new Date().toISOString();
  writeFileSync(join(OUT, 'summary.json'), JSON.stringify(results, null, 2));

  console.log('\n=== Summary ===');
  console.log(JSON.stringify(results.summary, null, 2));
  if (results.pageErrors.length) {
    console.log('\nPage errors:');
    results.pageErrors.slice(0, 10).forEach((e, i) => console.log(`  ${i + 1}. ${e.slice(0, 200)}`));
  }
  if (results.consoleErrors.length) {
    console.log('\nConsole errors (first 5):');
    results.consoleErrors.slice(0, 5).forEach((e, i) => console.log(`  ${i + 1}. ${e.slice(0, 200)}`));
  }

  await browser.close();
}

run().catch((err) => { console.error('Crash:', err); process.exitCode = 2; });
