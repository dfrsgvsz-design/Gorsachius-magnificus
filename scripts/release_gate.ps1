<#
.SYNOPSIS
    Release gate — pre-release verification for both apps.

.DESCRIPTION
    Hardened in 2026-06 (ticket #C, P0 W1):
    - Switched from `python -m unittest` to `pytest` so it matches
      quality_gate.ps1 and the GitHub Actions release_gate workflow.
    - Step 0 now installs requirements.txt + requirements-dev.txt for each app
      (P0: previously assumed pytest was already on PATH).
    - Path-agnostic via $PSScriptRoot; no more hardcoded "f:\Gorsachius magnificus".
    - Runs the FULL backend test suite (not just the 3-test critical subset that
      quality_gate covers) — that is the only meaningful difference between the
      two gates.

.PARAMETER NoInstall
    Skip Step 0 (pip install). Use only when you know the env is already prepared.

.PARAMETER Project
    Which app(s) to release-gate. Defaults to "all". Accepts:
      - all        (acoustic + species)
      - acoustic
      - species

.EXAMPLE
    .\scripts\release_gate.ps1
#>
param(
    [ValidateSet("all", "acoustic", "species")]
    [string]$Project = "all",

    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

Write-Host "== Release Gate: start ==" -ForegroundColor Yellow
Write-Host "Repo root: $RepoRoot"

$script:results = @()

function Run-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host ("-- " + $Name) -ForegroundColor Cyan
    try {
        & $Action
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) { $exitCode = 0 }
    } catch {
        $exitCode = 1
        Write-Host ("Step failed with exception: " + $_.Exception.Message) -ForegroundColor Red
    }
    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $script:results += [PSCustomObject]@{
        Step = $Name; Status = $status; ExitCode = $exitCode
    }
    if ($status -eq "PASS") {
        Write-Host ("[PASS] " + $Name) -ForegroundColor Green
    } else {
        Write-Host ("[FAIL] " + $Name + " (exit " + $exitCode + ")") -ForegroundColor Red
    }
}

# Repo-wide python AST sweep (cheap, catches syntax errors anywhere in repo)
Run-Step "Python AST syntax check (repo, excluding generated dirs)" {
    $env:PYTHONIOENCODING = "utf-8"
    $pyScript = @"
import os, ast, sys
root = r'$RepoRoot'
ex = {'node_modules','.venv','venv','dist','build','__pycache__','.git','.cursor','.windsurf','android','ios','_internal'}
errs = []
total = 0
for dp, dns, fns in os.walk(root):
    dns[:] = [d for d in dns if d not in ex and not d.startswith('.')]
    for fn in fns:
        if fn.endswith('.py'):
            p = os.path.join(dp, fn)
            total += 1
            try:
                ast.parse(open(p, 'r', encoding='utf-8', errors='strict').read(), filename=p)
            except Exception as e:
                errs.append((p, str(e)))
print(f'PY_TOTAL={total}')
print(f'PY_ERRS={len(errs)}')
for p, e in errs[:20]:
    print('ERR', p, '::', e)
sys.exit(1 if errs else 0)
"@
    python -c $pyScript
}

# Production runtime contract: assert deployments cannot ship in "demo" mode.
# Stages the env vars that B-stage release plan requires (SURVEY_DATA_DIR /
# CHECKPOINTS_DIR / FRONTEND_DIST_DIR / BIRD_API_KEY / CORS_ORIGINS) and
# verifies describe_runtime_paths() + load_config() both agree the runtime is
# externalized and shared platform_config.json is present + valid.
Run-Step "Production runtime contract (no demo mode)" {
    $env:PYTHONIOENCODING = "utf-8"
    $prevSurvey   = $env:SURVEY_DATA_DIR
    $prevCkpt     = $env:CHECKPOINTS_DIR
    $prevFront    = $env:FRONTEND_DIST_DIR
    $prevBirdKey  = $env:BIRD_API_KEY
    $prevCors     = $env:CORS_ORIGINS
    $prevAppEnv   = $env:APP_ENV
    $prevOutput   = $env:BIRD_PLATFORM_OUTPUT_DIR

    $stage = Join-Path $env:TEMP "bird_platform_release_gate_stage"
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "data") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "checkpoints") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "frontend_dist") | Out-Null

    $env:SURVEY_DATA_DIR             = Join-Path $stage "data"
    $env:CHECKPOINTS_DIR             = Join-Path $stage "checkpoints"
    $env:FRONTEND_DIST_DIR           = Join-Path $stage "frontend_dist"
    $env:BIRD_API_KEY                = "release-gate-test-key"
    $env:CORS_ORIGINS                = "https://example.com"
    $env:APP_ENV                     = "production"
    $env:BIRD_PLATFORM_OUTPUT_DIR    = Join-Path $stage "data"

    try {
        $pyAssert = @"
import os, sys, json
sys.path.insert(0, r'$RepoRoot')
from shared.backend.utils.runtime_paths import describe_runtime_paths
paths = describe_runtime_paths()
required = [
    'data_dir_externalized',
    'checkpoints_dir_externalized',
    'frontend_dist_dir_externalized',
    'mutable_runtime_externalized',
]
missing = [k for k in required if not paths.get(k)]
if missing:
    print('FAIL externalization flags missing:', missing)
    print(json.dumps(paths, indent=2, default=str))
    sys.exit(1)

from shared.backend.utils.platform_config import load_config, validate_config
cfg = load_config()
val = validate_config(cfg)
if not val['valid']:
    print('FAIL shared platform_config validation:', val)
    sys.exit(1)
if not cfg.get('platform', {}).get('name'):
    print('FAIL shared platform_config missing platform.name')
    sys.exit(1)
print('OK runtime contract (no demo mode):', cfg['platform']['name'])
sys.exit(0)
"@
        python -c $pyAssert
    } finally {
        $env:SURVEY_DATA_DIR            = $prevSurvey
        $env:CHECKPOINTS_DIR            = $prevCkpt
        $env:FRONTEND_DIST_DIR          = $prevFront
        $env:BIRD_API_KEY               = $prevBirdKey
        $env:CORS_ORIGINS               = $prevCors
        $env:APP_ENV                    = $prevAppEnv
        $env:BIRD_PLATFORM_OUTPUT_DIR   = $prevOutput
        Remove-Item $stage -Recurse -ErrorAction SilentlyContinue
    }
}

$apps = @()
switch ($Project) {
    "acoustic" {
        $apps += [PSCustomObject]@{ Name = "acoustic_platform"; Root = (Join-Path $RepoRoot "acoustic_platform") }
    }
    "species" {
        $apps += [PSCustomObject]@{ Name = "species_monitoring_platform"; Root = (Join-Path $RepoRoot "species_monitoring_platform") }
    }
    "all" {
        $apps += [PSCustomObject]@{ Name = "acoustic_platform"; Root = (Join-Path $RepoRoot "acoustic_platform") }
        $apps += [PSCustomObject]@{ Name = "species_monitoring_platform"; Root = (Join-Path $RepoRoot "species_monitoring_platform") }
    }
}

foreach ($app in $apps) {
    $backendDir = Join-Path $app.Root "backend"
    $frontendDir = Join-Path $app.Root "frontend"

    if (-not $NoInstall) {
        Run-Step "[$($app.Name)] Step 0 - install runtime + dev deps" {
            Set-Location $backendDir
            python -m pip install -r requirements.txt -r requirements-dev.txt --quiet --disable-pip-version-check
        }
    }

    Run-Step "[$($app.Name)] Full backend pytest suite" {
        Set-Location $backendDir
        $env:PYTHONPATH = "$RepoRoot;$backendDir"
        python -m pytest tests -q --maxfail=3
    }

    Run-Step "[$($app.Name)] Frontend production build" {
        Set-Location $frontendDir
        npm run build --silent
    }
}

Write-Host ""
Write-Host "=== Release Gate Summary ===" -ForegroundColor Yellow
$script:results | Format-Table -AutoSize

$failed = @($script:results | Where-Object { $_.Status -eq "FAIL" })
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Release gate FAILED: $($failed.Count) step(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Release gate PASSED: all $($script:results.Count) step(s) succeeded." -ForegroundColor Green
exit 0
