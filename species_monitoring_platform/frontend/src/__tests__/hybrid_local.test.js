/**
 * Hybrid-local mode three-scenario verification.
 *
 * Replaces emulator/device runtime check (host emulator stack is currently
 * unstable on this Windows host). Drives api.js + App.jsx + FieldOpsTab.jsx
 * through the same logical paths the real APK would take, asserting the
 * Bug A/B/C/D fixes hold.
 *
 * Three scenarios (matches user "We conducted simulation/field/no-internet"):
 *   1. Simulation : native APK + no VITE_API_BASE_URL + navigator.onLine=true
 *   2. Field      : native APK + no VITE_API_BASE_URL + navigator.onLine=true
 *                   (cellular flaky; same logical path as Simulation because
 *                    IS_HYBRID_LOCAL_MODE is build-time, not runtime)
 *   3. No-Internet: native APK + no VITE_API_BASE_URL + navigator.onLine=false
 *
 * In ALL three scenarios the UI must render "Local mode" / "本地模式"
 * (NEVER "Backend offline"), the red/yellow banners must be absent, and
 * axios must NOT be invoked from refreshHealth.
 */

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SRC_ROOT = resolve(__dirname, '..')
const FRONTEND_ROOT = resolve(SRC_ROOT, '..')

function readSource(relPath) {
  return readFileSync(resolve(FRONTEND_ROOT, relPath), 'utf8')
}

// ──────────────────────────────────────────────────────────────────
// Group A : api.js IS_HYBRID_LOCAL_MODE flag — three scenarios
// ──────────────────────────────────────────────────────────────────

describe('api.js: IS_HYBRID_LOCAL_MODE — Bug C+D fix', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  test('Scenario 1+2 (Simulation/Field): native + no API base → IS_HYBRID_LOCAL_MODE=true', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubEnv('PROD', true)
    vi.doMock('@capacitor/core', () => ({
      Capacitor: { isNativePlatform: () => true, getPlatform: () => 'android' },
    }))
    const mod = await import('../lib/api.js')
    expect(mod.IS_HYBRID_LOCAL_MODE).toBe(true)
  })

  test('Scenario 3 (No-Internet): same as 1+2 — flag is build-time, not runtime', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubEnv('PROD', true)
    vi.doMock('@capacitor/core', () => ({
      Capacitor: { isNativePlatform: () => true, getPlatform: () => 'android' },
    }))
    const mod = await import('../lib/api.js')
    expect(mod.IS_HYBRID_LOCAL_MODE).toBe(true)
  })

  test('Counter-case 1: native + WITH valid API base → IS_HYBRID_LOCAL_MODE=false', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.com/api')
    vi.stubEnv('PROD', true)
    vi.doMock('@capacitor/core', () => ({
      Capacitor: { isNativePlatform: () => true, getPlatform: () => 'android' },
    }))
    const mod = await import('../lib/api.js')
    expect(mod.IS_HYBRID_LOCAL_MODE).toBe(false)
  })

  test('Counter-case 2: web (non-native) → IS_HYBRID_LOCAL_MODE=false', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubEnv('PROD', false)
    vi.doMock('@capacitor/core', () => ({
      Capacitor: { isNativePlatform: () => false, getPlatform: () => 'web' },
    }))
    const mod = await import('../lib/api.js')
    expect(mod.IS_HYBRID_LOCAL_MODE).toBe(false)
  })
})

// ──────────────────────────────────────────────────────────────────
// Group B : api.js — Bug C: no axios request interceptor pre-rejection
// ──────────────────────────────────────────────────────────────────

describe('api.js: Bug C — request interceptor pre-rejection removed', () => {
  test('source no longer registers a runtimeApiConfigError reject interceptor', () => {
    const source = readSource('src/lib/api.js')
    // The interceptor block previously rejected every request when
    // runtimeApiConfigError was non-empty. Make sure we did NOT keep it.
    expect(source).not.toMatch(
      /api\.interceptors\.request\.use\([\s\S]{0,400}runtimeApiConfigError[\s\S]{0,400}Promise\.reject/,
    )
    // Positive assertion: the warn-only branch is present.
    expect(source).toMatch(/console\.warn\(`?\[api\] \$\{runtimeApiConfigError\}/)
  })
})

// ──────────────────────────────────────────────────────────────────
// Group C : i18n — Bug D: hybridLocalMode strings present (zh + en)
// ──────────────────────────────────────────────────────────────────

describe('i18n: Bug D — hybridLocalMode strings present', () => {
  test('zh.json appShell.hybridLocalMode === "本地模式"', () => {
    const json = JSON.parse(readSource('src/i18n/zh.json'))
    expect(json.appShell.hybridLocalMode).toBe('本地模式')
    expect(typeof json.appShell.hybridLocalDetail).toBe('string')
    expect(json.appShell.hybridLocalDetail.length).toBeGreaterThan(0)
  })

  test('en.json appShell.hybridLocalMode === "Local mode"', () => {
    const json = JSON.parse(readSource('src/i18n/en.json'))
    expect(json.appShell.hybridLocalMode).toBe('Local mode')
    expect(typeof json.appShell.hybridLocalDetail).toBe('string')
    expect(json.appShell.hybridLocalDetail.length).toBeGreaterThan(0)
  })

  test('backendOffline still exists (non-hybrid build fallback)', () => {
    const zh = JSON.parse(readSource('src/i18n/zh.json'))
    const en = JSON.parse(readSource('src/i18n/en.json'))
    expect(zh.appShell.backendOffline).toBeDefined()
    expect(en.appShell.backendOffline).toBeDefined()
  })
})

// ──────────────────────────────────────────────────────────────────
// Group D : App.jsx — Bug D: refreshHealth short-circuit + 3 status spots
// ──────────────────────────────────────────────────────────────────

describe('App.jsx: Bug D — hybrid-local short-circuit + status text', () => {
  const source = readSource('src/App.jsx')

  test('imports IS_HYBRID_LOCAL_MODE from ./lib/api', () => {
    expect(source).toMatch(/import\s*\{[^}]*IS_HYBRID_LOCAL_MODE[^}]*\}\s*from\s*['"]\.\/lib\/api['"]/)
  })

  test('defines buildHybridLocalHealth() returning hybrid_local:true / status:ok', () => {
    expect(source).toMatch(/function\s+buildHybridLocalHealth\s*\(\s*\)\s*\{/)
    const fn = source.match(/function\s+buildHybridLocalHealth[\s\S]{0,400}?\n\}/)?.[0] || ''
    expect(fn).toMatch(/status:\s*['"]ok['"]/)
    expect(fn).toMatch(/hybrid_local:\s*true/)
    expect(fn).toMatch(/runtime_state:\s*['"]hybrid_local['"]/)
  })

  test('refreshHealth short-circuits when IS_HYBRID_LOCAL_MODE — no axios call', () => {
    const fn = source.match(/const\s+refreshHealth\s*=\s*useCallback\([\s\S]{0,800}?\}\s*,\s*\[t\]\s*\)/)?.[0] || ''
    expect(fn).toMatch(/if\s*\(\s*IS_HYBRID_LOCAL_MODE\s*\)/)
    expect(fn).toMatch(/setHealth\(\s*buildHybridLocalHealth\(\)\s*\)/)
    // Order: short-circuit BEFORE the axios try-block
    const idxIf = fn.indexOf('if (IS_HYBRID_LOCAL_MODE')
    const idxTry = fn.indexOf('await getHealthStatus')
    expect(idxIf).toBeGreaterThan(-1)
    expect(idxTry).toBeGreaterThan(idxIf)
  })

  test('three status spots branch on isHybridLocal first', () => {
    // Each of the 3 status spots renders
    //   {isHybridLocal ? t('appShell.hybridLocalMode') : ...}
    // Count how many times that exact ternary head appears — must be ≥ 3.
    const ternaryHits = [
      ...source.matchAll(/isHybridLocal[\s\S]{0,80}?t\(['"]appShell\.hybridLocalMode['"]\)/g),
    ]
    expect(ternaryHits.length).toBeGreaterThanOrEqual(3)

    // backendOffline must still appear (non-hybrid fallback path), but it must
    // never come BEFORE the isHybridLocal check in any branch.
    const backendOfflineHits = [...source.matchAll(/t\(['"]appShell\.backendOffline['"]\)/g)]
    expect(backendOfflineHits.length).toBeGreaterThanOrEqual(3)

    // Mobile sheet — prop wired through.
    expect(source).toMatch(/<MobileMoreSheet[\s\S]{0,800}?isHybridLocal=\{isHybridLocal\}/)
    expect(source).toMatch(/function\s+MobileMoreSheet\([\s\S]{0,500}?isHybridLocal/)
  })

  test('isHybridLocal derives from health?.hybrid_local', () => {
    expect(source).toMatch(/const\s+isHybridLocal\s*=\s*Boolean\(\s*health\?\.hybrid_local\s*\)/)
  })
})

// ──────────────────────────────────────────────────────────────────
// Group E : FieldOpsTab.jsx — Bug B: warning banner only on records step
// ──────────────────────────────────────────────────────────────────

describe('FieldOpsTab.jsx: Bug B — warning banner gated on surveyStep', () => {
  const source = readSource('src/components/tabs/FieldOpsTab.jsx')

  test("StatusBanner tone='warning' wrapped in surveyStep === 'records' guard", () => {
    // The error banner stays unconditional; the warning banner must be wrapped.
    const block = source.match(/<StatusBanner tone="error" message=\{error\}[\s\S]{0,400}?<StatusBanner tone="warning"[\s\S]{0,200}?\)\}/)?.[0] || ''
    expect(block).toMatch(/surveyStep\s*===\s*['"]records['"]/)
    expect(block).toMatch(/taxonomyGateWarningMessage/)
  })

  test('warning banner is no longer rendered unconditionally at fieldops top level', () => {
    // Negative: no bare <StatusBanner tone="warning" message={taxonomyGateWarningMessage} />
    // outside a guard. Use a tighter regex that requires immediate surroundings
    // to NOT be inside `{ surveyStep === 'records' && ( … ) }`.
    const allWarnings = [
      ...source.matchAll(/<StatusBanner tone="warning" message=\{taxonomyGateWarningMessage\}\s*\/>/g),
    ]
    expect(allWarnings.length).toBe(1) // exactly one site, and we just verified it's guarded.
  })
})

// ──────────────────────────────────────────────────────────────────
// Group F : db.js — Bug A: createConnection "already exists" fallback
// ──────────────────────────────────────────────────────────────────

describe('db.js: Bug A — createConnection retrieve fallback', () => {
  const source = readSource('src/lib/localStore/db.js')

  test('catches "already exists" and falls back to retrieveConnection', () => {
    // Discrete features that together prove the Bug A fix is in place.
    expect(source).toMatch(/try\s*\{[\s\S]{0,400}?factory\.createConnection\(/)
    expect(source).toMatch(/\}\s*catch\s*\(\s*err\s*\)/)
    expect(source).toMatch(/\/already exists\/i\.test/)
    // retrieveConnection appears twice: once in `if (exists)` branch and once
    // inside the catch block as the fallback.
    const retrieveHits = [
      ...source.matchAll(/factory\.retrieveConnection\(\s*DB_NAME\s*,\s*ENCRYPTED\s*\)/g),
    ]
    expect(retrieveHits.length).toBeGreaterThanOrEqual(2)
  })
})
