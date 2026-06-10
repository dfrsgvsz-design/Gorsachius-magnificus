<#
.SYNOPSIS
    Local quality gate — install + lint + build + critical backend tests for one or both apps.

.DESCRIPTION
    Hardened in 2026-06 (ticket #C, P0 W1):
    - Step 0 now auto-installs requirements.txt + requirements-dev.txt (P0 fix:
      previously the script invoked pytest without ever installing it).
    - Path-agnostic: $PSScriptRoot is treated as the repo root, so the script no
      longer hardcodes `f:\Gorsachius magnificus`.
    - Default mode gates BOTH apps (-Project all) so the species platform can
      never silently slip past the gate.

.PARAMETER Project
    Which app(s) to gate. Defaults to "all". Accepts:
      - all        (acoustic + species, in that order)
      - acoustic   (acoustic_platform only)
      - species    (species_monitoring_platform only)

.PARAMETER ProjectRoot
    Legacy single-app escape hatch. Absolute path to one app dir (e.g.
    "f:\Gorsachius magnificus\acoustic_platform"). When provided, overrides -Project.

.PARAMETER NoInstall
    Skip Step 0 (pip install). Use only when you are sure the venv is already
    prepared — saves ~30s on warm runs but will FAIL the gate if pytest/ruff
    are missing.

.EXAMPLE
    # Gate both apps end-to-end (the way CI / release_gate.yml invoke this)
    .\quality_gate.ps1

.EXAMPLE
    # Gate only the species platform
    .\quality_gate.ps1 -Project species

.EXAMPLE
    # Legacy absolute-path interface (kept for back-compat with existing docs)
    .\quality_gate.ps1 -ProjectRoot "f:\Gorsachius magnificus\acoustic_platform"
#>
param(
    [ValidateSet("all", "acoustic", "species")]
    [string]$Project = "all",

    [string]$ProjectRoot = "",

    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot").Path
$script:results = @()

function Run-Step {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$Command
    )

    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    Write-Host "[$WorkingDirectory] $Command"

    Push-Location $WorkingDirectory
    try {
        Invoke-Expression $Command
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) { $exitCode = 0 }
    } catch {
        $exitCode = 1
        Write-Host "Step failed with exception: $($_.Exception.Message)" -ForegroundColor Red
    } finally {
        Pop-Location
    }

    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $script:results += [PSCustomObject]@{
        Step     = $Name
        Status   = $status
        ExitCode = $exitCode
    }

    if ($status -eq "PASS") {
        Write-Host "Result: PASS" -ForegroundColor Green
    } else {
        Write-Host "Result: FAIL (exit code $exitCode)" -ForegroundColor Red
    }
}

function Invoke-AppGate {
    param(
        [string]$AppName,
        [string]$AppRoot
    )

    $backendDir = Join-Path $AppRoot "backend"
    $frontendDir = Join-Path $AppRoot "frontend"
    if (-not (Test-Path $backendDir)) {
        throw "[$AppName] Backend directory not found: $backendDir"
    }
    if (-not (Test-Path $frontendDir)) {
        throw "[$AppName] Frontend directory not found: $frontendDir"
    }

    $pythonPathParts = @($RepoRoot, $backendDir)
    if ($env:PYTHONPATH) { $pythonPathParts += $env:PYTHONPATH }
    $env:PYTHONPATH = ($pythonPathParts | Where-Object { $_ }) -join [System.IO.Path]::PathSeparator

    if (-not $NoInstall) {
        Run-Step -Name "[$AppName] Step 0 - install runtime + dev deps" `
                 -WorkingDirectory $backendDir `
                 -Command "python -m pip install -r requirements.txt -r requirements-dev.txt --quiet --disable-pip-version-check"
    } else {
        Write-Host ""
        Write-Host "[$AppName] Step 0 install skipped (-NoInstall)" -ForegroundColor Yellow
    }

    Run-Step -Name "[$AppName] Backend syntax check (compileall)" `
             -WorkingDirectory $backendDir `
             -Command "python -m compileall ."

    Run-Step -Name "[$AppName] Backend lint (ruff critical rules)" `
             -WorkingDirectory $backendDir `
             -Command "python -m ruff check . --select E9,F63,F7,F82"

    Run-Step -Name "[$AppName] Frontend lint" `
             -WorkingDirectory $frontendDir `
             -Command "npm run lint --silent"

    Run-Step -Name "[$AppName] Frontend build" `
             -WorkingDirectory $frontendDir `
             -Command "npm run build --silent"

    Run-Step -Name "[$AppName] Backend critical tests (smoke/runtime/realtime)" `
             -WorkingDirectory $backendDir `
             -Command "python -m pytest tests/test_api_smoke.py tests/test_health_runtime.py tests/test_realtime.py -q"
}

$apps = @()
if ($ProjectRoot -ne "") {
    $resolved = (Resolve-Path $ProjectRoot).Path
    $apps += [PSCustomObject]@{ Name = (Split-Path -Leaf $resolved); Root = $resolved }
} else {
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
}

foreach ($app in $apps) {
    Write-Host ""
    Write-Host "##############################################" -ForegroundColor Magenta
    Write-Host "# Gate target: $($app.Name)" -ForegroundColor Magenta
    Write-Host "# Root: $($app.Root)" -ForegroundColor Magenta
    Write-Host "##############################################" -ForegroundColor Magenta
    Invoke-AppGate -AppName $app.Name -AppRoot $app.Root
}

Write-Host ""
Write-Host "=== Quality Gate Summary ===" -ForegroundColor Yellow
$script:results | Format-Table -AutoSize

$failed = @($script:results | Where-Object { $_.Status -eq "FAIL" })
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Quality gate FAILED: $($failed.Count) step(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Quality gate PASSED: all $($script:results.Count) step(s) succeeded." -ForegroundColor Green
exit 0
