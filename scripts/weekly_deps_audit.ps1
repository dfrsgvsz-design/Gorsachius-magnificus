<#
.SYNOPSIS
    Weekly dependency vulnerability audit for both apps. Outputs a Markdown
    report to submission/ and exits non-zero when high/critical findings exist.

.DESCRIPTION
    Created 2026-06-10 (ticket #C continuous deps hygiene). Runs:
      - `npm audit --json` against acoustic_platform/frontend and
        species_monitoring_platform/frontend (Node deps)
      - `pip-audit -r requirements.txt -r requirements-dev.txt -f json`
        against both backends (Python deps)

    Writes the consolidated report to:
      submission/weekly_deps_report_<yyyy-mm-dd>.md

    Exits 1 if any HIGH or CRITICAL severity finding exists across the four
    surfaces; CI can wire this to open a P0 ticket automatically.

.PARAMETER NoInstall
    Skip installing `pip-audit` (default behaviour is to `pip install --user
    pip-audit` if not on PATH).

.PARAMETER OutDir
    Override report output directory. Defaults to `submission/`.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File "f:\Gorsachius magnificus\scripts\weekly_deps_audit.ps1"
#>
param(
    [switch]$NoInstall,
    [string]$OutDir = ""
)

$ErrorActionPreference = "Continue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ($OutDir -eq "") {
    $OutDir = Join-Path $RepoRoot "submission"
}
$today = Get-Date -Format "yyyy-MM-dd"
$reportPath = Join-Path $OutDir "weekly_deps_report_$today.md"

$apps = @(
    [PSCustomObject]@{ Name = "acoustic_platform"; FrontendDir = "acoustic_platform\frontend"; BackendDir = "acoustic_platform\backend" }
    [PSCustomObject]@{ Name = "species_monitoring_platform"; FrontendDir = "species_monitoring_platform\frontend"; BackendDir = "species_monitoring_platform\backend" }
)

$findings = @()

function Add-Finding {
    param(
        [string]$App, [string]$Ecosystem, [string]$Package,
        [string]$InstalledVersion, [string]$Severity, [string]$Id,
        [string]$FixedIn, [string]$Title
    )
    $severityNorm = if ([string]::IsNullOrWhiteSpace($Severity)) { "UNKNOWN" } else { $Severity.ToUpper() }
    $script:findings += [PSCustomObject]@{
        App = $App; Ecosystem = $Ecosystem; Package = $Package
        InstalledVersion = $InstalledVersion; Severity = $severityNorm
        Id = $Id; FixedIn = $FixedIn; Title = $Title
    }
}

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-PipAudit {
    if (Test-CommandExists "pip-audit") { return $true }
    if ($NoInstall) {
        Write-Host "pip-audit not on PATH and -NoInstall specified — Python audit will be skipped." -ForegroundColor Yellow
        return $false
    }
    Write-Host "Installing pip-audit (--user)..." -ForegroundColor Cyan
    python -m pip install --user --quiet --disable-pip-version-check pip-audit
    if ($LASTEXITCODE -ne 0) {
        Write-Host "pip-audit install failed; Python audit will be skipped." -ForegroundColor Yellow
        return $false
    }
    return Test-CommandExists "pip-audit"
}

function Run-NpmAudit {
    param([string]$App, [string]$AbsFrontend)

    if (-not (Test-Path (Join-Path $AbsFrontend "package-lock.json"))) {
        Write-Host "[$App/npm] no package-lock.json — running npm install --package-lock-only first..." -ForegroundColor Cyan
        Push-Location $AbsFrontend
        npm install --package-lock-only --silent 2>&1 | Out-Null
        Pop-Location
    }

    Push-Location $AbsFrontend
    $jsonRaw = npm audit --json 2>$null
    $exit = $LASTEXITCODE
    Pop-Location

    if ([string]::IsNullOrWhiteSpace($jsonRaw)) {
        Write-Host "[$App/npm] empty audit output (exit $exit)" -ForegroundColor Yellow
        return
    }
    try {
        $data = $jsonRaw | ConvertFrom-Json
    } catch {
        Write-Host "[$App/npm] could not parse audit JSON: $($_.Exception.Message)" -ForegroundColor Yellow
        return
    }

    $vulns = $data.vulnerabilities
    if (-not $vulns) { return }

    $vulns.PSObject.Properties | ForEach-Object {
        $pkg = $_.Name
        $info = $_.Value
        $vias = @($info.via)
        $titles = @($vias | Where-Object { $_ -is [psobject] } | ForEach-Object { $_.title })
        $ids = @($vias | Where-Object { $_ -is [psobject] } | ForEach-Object { $_.url -replace ".*/", "" })
        $fixedIn = $info.fixAvailable
        $fixedInStr = if ($fixedIn -is [bool]) {
            if ($fixedIn) { "yes (run `npm audit fix`)" } else { "no auto-fix" }
        } elseif ($fixedIn -and $fixedIn.name) {
            "$($fixedIn.name)@$($fixedIn.version)"
        } else {
            ($fixedIn | Out-String).Trim()
        }
        Add-Finding -App $App -Ecosystem "npm" -Package $pkg `
            -InstalledVersion ($info.range -as [string]) `
            -Severity ($info.severity -as [string]) `
            -Id (($ids | Select-Object -First 1) -as [string]) `
            -FixedIn $fixedInStr `
            -Title (($titles | Select-Object -First 1) -as [string])
    }
}

function Run-PipAudit {
    param([string]$App, [string]$AbsBackend)

    $reqMain = Join-Path $AbsBackend "requirements.txt"
    $reqDev = Join-Path $AbsBackend "requirements-dev.txt"
    if (-not (Test-Path $reqMain)) {
        Write-Host "[$App/pip] no requirements.txt at $reqMain — skipped" -ForegroundColor Yellow
        return
    }
    $args = @("-r", $reqMain)
    if (Test-Path $reqDev) { $args += @("-r", $reqDev) }
    $args += @("-f", "json", "--strict", "--disable-pip")

    Push-Location $AbsBackend
    $jsonRaw = pip-audit @args 2>$null
    Pop-Location

    if ([string]::IsNullOrWhiteSpace($jsonRaw)) {
        Write-Host "[$App/pip] empty audit output" -ForegroundColor Yellow
        return
    }
    try {
        $data = $jsonRaw | ConvertFrom-Json
    } catch {
        Write-Host "[$App/pip] could not parse audit JSON: $($_.Exception.Message)" -ForegroundColor Yellow
        return
    }

    $items = if ($data.dependencies) { $data.dependencies } else { @($data) }
    foreach ($dep in $items) {
        if (-not $dep.vulns) { continue }
        foreach ($v in $dep.vulns) {
            Add-Finding -App $App -Ecosystem "pip" -Package $dep.name `
                -InstalledVersion $dep.version `
                -Severity ($v.severity -as [string]) `
                -Id $v.id `
                -FixedIn (($v.fix_versions -join ", ") -as [string]) `
                -Title ($v.description -as [string])
        }
    }
}

# ── Run ─────────────────────────────────────────────────────────────────────

Write-Host "Weekly deps audit · $today" -ForegroundColor Yellow
Write-Host "Repo: $RepoRoot"
$pipAuditOk = Ensure-PipAudit

foreach ($app in $apps) {
    $absFrontend = Join-Path $RepoRoot $app.FrontendDir
    $absBackend = Join-Path $RepoRoot $app.BackendDir
    if (Test-Path $absFrontend) {
        Write-Host ""
        Write-Host "─── [$($app.Name)] npm audit ───" -ForegroundColor Cyan
        Run-NpmAudit -App $app.Name -AbsFrontend $absFrontend
    }
    if ($pipAuditOk -and (Test-Path $absBackend)) {
        Write-Host ""
        Write-Host "─── [$($app.Name)] pip-audit ───" -ForegroundColor Cyan
        Run-PipAudit -App $app.Name -AbsBackend $absBackend
    }
}

# ── Report ──────────────────────────────────────────────────────────────────

$severityRank = @{ "CRITICAL" = 4; "HIGH" = 3; "MODERATE" = 2; "MEDIUM" = 2; "LOW" = 1; "INFO" = 0; "UNKNOWN" = 0 }
$findingsSorted = $findings | Sort-Object @{ Expression = { $severityRank[$_.Severity] } ; Descending = $true }, App, Ecosystem, Package

$counts = @{
    CRITICAL = @($findings | Where-Object { $_.Severity -eq "CRITICAL" }).Count
    HIGH = @($findings | Where-Object { $_.Severity -eq "HIGH" }).Count
    MODERATE = @($findings | Where-Object { $_.Severity -in @("MODERATE", "MEDIUM") }).Count
    LOW = @($findings | Where-Object { $_.Severity -eq "LOW" }).Count
}

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

$report = @()
$report += "# Weekly Dependency Audit — $today"
$report += ""
$report += "> Generated by ``scripts/weekly_deps_audit.ps1`` (ticket #C continuous hygiene)."
$report += ""
$report += "## Summary"
$report += ""
$report += "| Severity | Count |"
$report += "|---|---|"
$report += "| CRITICAL | $($counts.CRITICAL) |"
$report += "| HIGH     | $($counts.HIGH) |"
$report += "| MODERATE | $($counts.MODERATE) |"
$report += "| LOW      | $($counts.LOW) |"
$report += ""

$mustFix = $counts.CRITICAL + $counts.HIGH
if ($mustFix -gt 0) {
    $report += "**Action required this week**: $mustFix HIGH/CRITICAL finding(s). See § Action Items."
} else {
    $report += "**No HIGH/CRITICAL findings.** Continue with the routine review of MODERATE items."
}
$report += ""

if ($findingsSorted.Count -gt 0) {
    $report += "## Findings"
    $report += ""
    $report += "| Severity | App | Eco | Package | Installed | Fixed in | Advisory ID | Title |"
    $report += "|---|---|---|---|---|---|---|---|"
    foreach ($f in $findingsSorted) {
        $title = ($f.Title -replace "\|", "\\|" -replace "\r?\n", " ")
        if ($title.Length -gt 80) { $title = $title.Substring(0, 80) + "…" }
        $report += "| $($f.Severity) | $($f.App) | $($f.Ecosystem) | $($f.Package) | $($f.InstalledVersion) | $($f.FixedIn) | $($f.Id) | $title |"
    }
    $report += ""

    if ($mustFix -gt 0) {
        $report += "## Action Items"
        $report += ""
        $report += "Address all HIGH/CRITICAL items **this week**:"
        $report += ""
        $report += "| App | Eco | Package | Command |"
        $report += "|---|---|---|---|"
        foreach ($f in ($findingsSorted | Where-Object { $_.Severity -in @("CRITICAL", "HIGH") })) {
            if ($f.Ecosystem -eq "npm") {
                $cmd = "cd $($f.App)/frontend && npm audit fix"
            } else {
                $cmd = "cd $($f.App)/backend && pip install --upgrade $($f.Package)"
            }
            $report += "| $($f.App) | $($f.Ecosystem) | $($f.Package) | ``$cmd`` |"
        }
        $report += ""
    }
} else {
    $report += "## Findings"
    $report += ""
    $report += "_No vulnerabilities reported across all four surfaces._"
    $report += ""
}

$report += "## Surfaces audited"
$report += ""
$report += "| App | Ecosystem | Manifest |"
$report += "|---|---|---|"
foreach ($app in $apps) {
    $report += "| $($app.Name) | npm | $($app.FrontendDir)/package-lock.json |"
    $report += "| $($app.Name) | pip | $($app.BackendDir)/requirements.txt + requirements-dev.txt |"
}
$report += ""
$report += "## Notes"
$report += ""
$report += "- `npm audit` reports use the npm registry advisory database."
$report += "- `pip-audit` reports use PyPI advisory database + OSV."
$report += "- This script is invoked weekly by `.github/workflows/deps-audit.yml`."
$report += "- For false positives, document the override in this PR review (do NOT silence at the script level)."

$reportText = $report -join "`r`n"
Set-Content -Path $reportPath -Value $reportText -Encoding UTF8

Write-Host ""
Write-Host "Report written: $reportPath" -ForegroundColor Green
Write-Host "  CRITICAL: $($counts.CRITICAL)  HIGH: $($counts.HIGH)  MODERATE: $($counts.MODERATE)  LOW: $($counts.LOW)" -ForegroundColor $(if ($mustFix -gt 0) { "Red" } else { "Green" })

if ($mustFix -gt 0) {
    Write-Host ""
    Write-Host "Deps audit FAILED: $mustFix HIGH/CRITICAL finding(s) — see $reportPath" -ForegroundColor Red
    exit 1
}
exit 0
