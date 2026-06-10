/**
 * APK deep functional tester v2 — robust selectors + complete survey flow.
 *
 * Improvements over v1:
 *   - Mobile bottom nav uses nth-child indexes (1=总览 2=外业 3=物种 4=监测 5=更多)
 *   - Closes any open more-sheet before tab switching
 *   - PMP create project: click "新建项目" → fill placeholder=项目名称 → click "创建项目"
 *   - Returns to fieldops via bottom nav nth-child(2) and exercises full survey flow
 *   - T6 fetches /api/health from inside WebView and reports body excerpt
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';

const CDP = process.env.CDP_URL || 'http://127.0.0.1:9223';
const OUT = './test-screenshots/apk-deep-v2';
mkdirSync(OUT, { recursive: true });

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const results = { startedAt: new Date().toISOString(), scenarios: [], consoleErrors: [], pageErrors: [] };

function log(level, name, detail = '') {
  const tag = level === 'pass' ? 'PASS' : level === 'warn' ? 'WARN' : 'FAIL';
  console.log(`  [${tag}] ${name}${detail ? ' — ' + detail : ''}`);
  results.scenarios.push({ name, status: level, detail });
}

async function snap(page, name) {
  try {
    await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: false });
    console.log(`        ↳ ${name}.png`);
  } catch (err) { console.log(`        ↳ snap failed: ${err.message}`); }
}

async function closeMoreSheet(page) {
  // The more sheet appears as a fixed inset-0 overlay; click on the dim backdrop.
  await page.evaluate(() => {
    const sheet = document.querySelector('.fixed.inset-0.z-\\[60\\]');
    if (sheet) sheet.click();
  });
  await wait(400);
}

async function clickBottomNav(page, idx) {
  await closeMoreSheet(page);
  const navBtn = page.locator(`.mobile-bottom-nav button:nth-child(${idx})`).first();
  if (!(await navBtn.count())) return null;
  try {
    await navBtn.click();
    return true;
  } catch (e) {
    return null;
  }
}

async function readStorage(page) {
  return page.evaluate(() => {
    const raw = localStorage.getItem('bird-platform-field-survey-v1') || '{}';
    let parsed = {};
    try { parsed = JSON.parse(raw); } catch {}
    return {
      projects: (parsed.projects || []).length,
      sites: (parsed.sites || []).length,
      routes: (parsed.routes || []).length,
      observations: (parsed.observations || []).length,
      tracks: (parsed.tracks || []).length,
      events: (parsed.events || []).length,
      syncQueue: (parsed.syncQueue || []).length,
      mediaInbox: (parsed.mediaInbox || []).length,
      activeProjectId: parsed.activeProjectId || '',
      activeSiteId: parsed.activeSiteId || '',
      activeProtocol: parsed.activeProtocol || '',
      project_names: (parsed.projects || []).map((p) => p.name),
    };
  });
}

async function run() {
  console.log(`\n=== APK deep functional tester v2 ===\nCDP: ${CDP}\n`);

  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => p.url().includes('localhost')) || ctx.pages()[0];

  page.on('console', (msg) => { if (msg.type() === 'error') results.consoleErrors.push(msg.text()); });
  page.on('pageerror', (err) => results.pageErrors.push(err.message));

  console.log(`URL: ${page.url()}, Title: ${await page.title()}`);
  await snap(page, '00-attached');

  const base = await readStorage(page);
  console.log(`Baseline storage: ${JSON.stringify(base)}`);
  results.baseline = base;

  // ── T1 mobile bottom-nav: tap each slot ──
  console.log('\n--- T1: mobile bottom-nav 5 slots ---');
  const navLabels = ['总览', '外业', '物种', '监测', '更多'];
  for (let i = 1; i <= 5; i++) {
    const ok = await clickBottomNav(page, i);
    await wait(900);
    await snap(page, `01-nav-${i}-${navLabels[i - 1]}`);
    log(ok ? 'pass' : 'fail', `T1 bottom-nav slot ${i} (${navLabels[i - 1]})`, ok ? 'clicked' : 'no element');
  }

  // ── T2 Settings → ProjectManagementPanel CRUD ──
  console.log('\n--- T2: Settings → ProjectManagementPanel ---');
  // Open more sheet, then settings
  await clickBottomNav(page, 5);
  await wait(800);
  const settingsItem = page.locator('.mobile-quick-action').filter({ hasText: '设置' }).first();
  if (await settingsItem.count()) {
    await settingsItem.click();
    await wait(1500);
  }
  await snap(page, '02-settings-loaded');

  const settingsHeadings = await page.evaluate(() => Array.from(document.querySelectorAll('h1,h2,h3,h4'))
    .map(el => el.textContent.trim()).filter(t => t).slice(0, 12));
  log('pass', 'T2 Settings tab opened', `headings: ${settingsHeadings.join(' | ').slice(0, 200)}`);

  // Look for ProjectManagementPanel header (with badge)
  const pmpHeader = page.locator('h3:has-text("项目管理"), h3:has-text("Project Management")').first();
  const pmpFound = await pmpHeader.count();
  log(pmpFound ? 'pass' : 'fail', 'T2 ProjectManagementPanel header present', pmpFound ? 'h3 项目管理 located' : 'not found');

  if (pmpFound) {
    // Scroll to header and ensure expanded (it's expanded by default per source)
    await pmpHeader.scrollIntoViewIfNeeded();
    await wait(300);
    await snap(page, '03-pmp-visible');

    // Click "新建项目" button to show form
    const newProjectBtn = page.locator('button:has-text("新建项目"), button:has-text("New project")').first();
    log(await newProjectBtn.count() ? 'pass' : 'fail', 'T2 "新建项目" button visible',
      await newProjectBtn.count() ? 'button present' : 'missing');
    if (await newProjectBtn.count()) {
      try {
        await newProjectBtn.scrollIntoViewIfNeeded();
        await newProjectBtn.click();
        await wait(600);
        await snap(page, '04-new-project-form');
      } catch (e) {
        log('fail', 'T2 click 新建项目', e.message);
      }
    }

    const beforeCreate = await readStorage(page);

    // Fill project name + region
    const projName = `E2E项目-${Date.now().toString().slice(-6)}`;
    const nameInput = page.locator('input[placeholder="项目名称"], input[placeholder="Project name"]').first();
    if (await nameInput.count()) {
      await nameInput.fill(projName);
      await wait(200);
    }
    const regionInput = page.locator('input[placeholder*="区域"], input[placeholder*="Region"]').first();
    if (await regionInput.count()) {
      await regionInput.fill('广西测试区');
      await wait(200);
    }
    await snap(page, '05-form-filled');

    // Click "创建项目" submit
    const createSubmit = page.locator('button:has-text("创建项目"), button:has-text("Create project")').first();
    if (await createSubmit.count()) {
      try {
        await createSubmit.click();
        await wait(2500);
        await snap(page, '06-after-create');
      } catch (e) {
        log('fail', 'T2 click 创建项目', e.message);
      }
    }

    const afterCreate = await readStorage(page);
    const created = afterCreate.projects > beforeCreate.projects ||
      afterCreate.project_names.includes(projName);
    log(
      created ? 'pass' : 'fail',
      'T2 ProjectManagementPanel actually created project',
      `projects: ${beforeCreate.projects}→${afterCreate.projects}, names: ${afterCreate.project_names.slice(-3).join(', ')}`,
    );
    results.created_project_name = projName;
    results.t2_after = afterCreate;
  }

  // ── T3 FieldOps full survey flow ──
  console.log('\n--- T3: FieldOps full survey flow ---');
  await clickBottomNav(page, 2);
  await wait(1500);
  await snap(page, '07-fieldops-entered');

  // The setup view shows a "选择项目" list. Pick the most recent project (the one we just created).
  const projectRow = page.locator(`button:has-text("${results.created_project_name || ''}")`).first();
  if (await projectRow.count()) {
    try {
      await projectRow.click();
      await wait(1200);
      await snap(page, '08-project-picked');
      log('pass', 'T3 project row picked from list', results.created_project_name);
    } catch (e) {
      log('warn', 'T3 project row click', e.message);
    }
  } else {
    // Fallback: tap the first project row if any exists
    const firstProj = page.locator('button:has(.lucide-folder-open) span').first();
    if (await firstProj.count()) {
      await firstProj.click();
      await wait(1200);
      log('warn', 'T3 picked first project row (fallback)', '');
    }
  }

  // Type observer
  const observerInput = page.locator('input[placeholder="输入姓名"], input[placeholder="Enter name"]').first();
  if (await observerInput.count()) {
    await observerInput.fill('张三 (E2E)');
    await wait(300);
  }
  const weatherInput = page.locator('input[placeholder*="晴"], input[placeholder*="Sunny"]').first();
  if (await weatherInput.count()) {
    await weatherInput.fill('晴, 18℃');
    await wait(300);
  }
  await snap(page, '09-observer-typed');
  log(await observerInput.count() ? 'pass' : 'fail', 'T3 observer + weather inputs accessible', '');

  // Read GPS field
  const gpsTxt = await page.locator('text=经纬度').locator('..').innerText().catch(() => '');
  const gpsHit = /\d{1,3}\.\d{3,}/.test(gpsTxt);
  log(gpsHit ? 'pass' : 'warn', 'T3 GPS coordinates rendered', gpsTxt.split('\n').slice(0, 2).join(' | ').slice(0, 80));

  // Click 开始调查
  const beforeStart = await readStorage(page);
  const startBtn = page.locator('button:has-text("开始调查"), button:has-text("Start Survey")').first();
  if (await startBtn.count()) {
    const dis = await startBtn.isDisabled().catch(() => null);
    log(dis === false ? 'pass' : 'warn', 'T3 开始调查 button enabled', `disabled=${dis}`);
    if (dis === false) {
      await startBtn.click();
      await wait(2500);
      await snap(page, '10-survey-active');
    }
  }
  const afterStart = await readStorage(page);
  log(
    afterStart.events > beforeStart.events ||
    afterStart.tracks > beforeStart.tracks ||
    afterStart.syncQueue > beforeStart.syncQueue ? 'pass' : 'warn',
    'T3 start survey created entity',
    `events ${beforeStart.events}→${afterStart.events}, tracks ${beforeStart.tracks}→${afterStart.tracks}, queue ${beforeStart.syncQueue}→${afterStart.syncQueue}`,
  );

  // ── T4 native plugin reachability ──
  console.log('\n--- T4: native plugin reachability ---');
  const probe = await page.evaluate(async () => {
    const r = {};
    const Cap = window.Capacitor;
    r.platform = Cap?.getPlatform?.();
    r.is_native = Cap?.isNativePlatform?.() || false;
    r.plugins = Object.keys(Cap?.Plugins || {});
    try {
      const pos = await new Promise((res, rej) => {
        navigator.geolocation.getCurrentPosition(p => res(p), e => rej(e), { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 });
      });
      r.gps = { lat: pos.coords.latitude, lon: pos.coords.longitude, acc: pos.coords.accuracy };
    } catch (e) { r.gps = { error: String(e?.message || e) }; }
    try {
      const Cam = Cap?.Plugins?.Camera;
      r.camera_perms = await Cam?.checkPermissions?.();
    } catch {}
    try {
      const FS = Cap?.Plugins?.Filesystem;
      // try writing + reading + deleting a sentinel
      const fname = `e2e-sentinel-${Date.now()}.txt`;
      const data = btoa('hello-from-cdp-test');
      await FS.writeFile({ path: fname, data, directory: 'DATA' });
      const back = await FS.readFile({ path: fname, directory: 'DATA' });
      const text = atob(typeof back.data === 'string' ? back.data : '');
      await FS.deleteFile({ path: fname, directory: 'DATA' }).catch(() => {});
      r.filesystem_roundtrip = { ok: text === 'hello-from-cdp-test', readback: text };
    } catch (e) { r.filesystem_roundtrip = { error: String(e?.message || e) }; }
    return r;
  });
  console.log(`    platform=${probe.platform}, native=${probe.is_native}`);
  console.log(`    plugins (${probe.plugins.length}): ${probe.plugins.join(',')}`);
  console.log(`    GPS: ${JSON.stringify(probe.gps)}`);
  console.log(`    Camera perms: ${JSON.stringify(probe.camera_perms)}`);
  console.log(`    Filesystem roundtrip: ${JSON.stringify(probe.filesystem_roundtrip)}`);
  results.native = probe;
  log(probe.is_native ? 'pass' : 'fail', 'T4 isNativePlatform=true', `platform=${probe.platform}, plugins=${probe.plugins.length}`);
  log(probe.gps?.lat ? 'pass' : 'fail', 'T4 Geolocation getCurrentPosition',
    probe.gps?.lat ? `${probe.gps.lat.toFixed(4)}, ${probe.gps.lon.toFixed(4)}` : probe.gps?.error);
  log(probe.filesystem_roundtrip?.ok ? 'pass' : 'fail', 'T4 Filesystem write+read roundtrip',
    probe.filesystem_roundtrip?.ok ? 'sentinel matched' : (probe.filesystem_roundtrip?.error || 'mismatch'));

  // ── T5 backend connectivity (real content check) ──
  console.log('\n--- T5: backend /api/health (content verify) ---');
  const apiHealth = await page.evaluate(async () => {
    try {
      const res = await fetch('/api/health', { method: 'GET' });
      const text = await res.text();
      let body = null;
      try { body = JSON.parse(text); } catch {}
      return {
        status: res.status,
        ok: res.ok,
        content_type: res.headers.get('content-type'),
        body_keys: body ? Object.keys(body).slice(0, 12) : null,
        is_html_fallback: text.startsWith('<!') || text.startsWith('<html'),
        len: text.length,
        excerpt: text.slice(0, 250),
      };
    } catch (e) { return { error: String(e?.message || e) }; }
  });
  console.log(`    /api/health: ${JSON.stringify(apiHealth)}`);
  results.backend_health = apiHealth;
  log(
    apiHealth.body_keys && apiHealth.body_keys.includes('status') && !apiHealth.is_html_fallback ? 'pass' :
    apiHealth.is_html_fallback ? 'fail' : 'warn',
    'T5 /api/health returns real JSON (not SPA fallback)',
    apiHealth.is_html_fallback ? 'SPA HTML fallback detected' : `keys: ${apiHealth.body_keys?.join(',')}`,
  );

  // ── T6 SW + cache final + IndexedDB inspection ──
  const finalState = await page.evaluate(async () => {
    const regs = await navigator.serviceWorker.getRegistrations();
    const cnames = await caches.keys();
    const cacheCounts = {};
    for (const n of cnames) {
      const c = await caches.open(n);
      const ks = await c.keys();
      cacheCounts[n] = ks.length;
    }
    let dbList = [];
    try { dbList = (await indexedDB.databases()).map(d => `${d.name}@v${d.version}`); } catch {}
    return {
      sw_count: regs.length,
      sw_active: regs.map(r => r.active?.state),
      cache_names: cnames,
      cache_counts: cacheCounts,
      idb_databases: dbList,
    };
  });
  console.log(`\nFinal state: ${JSON.stringify(finalState)}`);
  results.final_state = finalState;
  results.final_storage = await readStorage(page);

  // ── Summary ──
  results.summary = {
    pass: results.scenarios.filter(s => s.status === 'pass').length,
    warn: results.scenarios.filter(s => s.status === 'warn').length,
    fail: results.scenarios.filter(s => s.status === 'fail').length,
    consoleErrors: results.consoleErrors.length,
    pageErrors: results.pageErrors.length,
  };
  results.endedAt = new Date().toISOString();
  writeFileSync(join(OUT, 'summary.json'), JSON.stringify(results, null, 2));

  console.log('\n=== Summary ===');
  console.log(JSON.stringify(results.summary, null, 2));
  if (results.pageErrors.length) {
    console.log('Page errors:'); results.pageErrors.slice(0,5).forEach((e,i)=>console.log(`  ${i+1}. ${e.slice(0,200)}`));
  }
  if (results.consoleErrors.length) {
    console.log('Console errors (first 5):');
    results.consoleErrors.slice(0,5).forEach((e,i)=>console.log(`  ${i+1}. ${e.slice(0,200)}`));
  }

  await browser.close();
}

run().catch(err => { console.error('Crash:', err); process.exitCode = 2; });
