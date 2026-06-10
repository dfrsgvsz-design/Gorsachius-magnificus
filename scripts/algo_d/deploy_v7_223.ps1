# Algo-D / P0-W1: deploy v7-head-223 artefacts to the runtime checkpoints dir
# with automatic v4 backup. Idempotent and atomic-ish (uses Copy-Item -Force).
#
# Usage:
#   pwsh "f:\Gorsachius magnificus\scripts\algo_d\deploy_v7_223.ps1"
[CmdletBinding()]
param(
    [string]$SourceDir = "f:\Gorsachius magnificus\species_monitoring_platform\checkpoints_v7_223",
    [string]$DestDir   = "f:\Gorsachius magnificus\species_monitoring_platform\backend\checkpoints"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SourceDir)) { throw "Source dir not found: $SourceDir" }
if (-not (Test-Path $DestDir))   { throw "Dest dir not found: $DestDir" }

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupSuffix = ".v4_baseline_$timestamp"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Algo-D :: deploy v7-head-223" -ForegroundColor Cyan
Write-Host "  source = $SourceDir"
Write-Host "  dest   = $DestDir"
Write-Host "  backup suffix = $backupSuffix"
Write-Host "==========================================================" -ForegroundColor Cyan

$needed = @(
    @{ src = "best_student_v7.pth"; dst = "best_model.pth"        },
    @{ src = "best_teacher_v7.pth"; dst = "best_teacher_v7.pth"   },
    @{ src = "species_mapping.json"; dst = "species_mapping.json" },
    @{ src = "calibration.json"; dst = "calibration.json"         }
)

Write-Host "`n[1/3] sanity check source artefacts..."
foreach ($pair in $needed) {
    $p = Join-Path $SourceDir $pair.src
    if (-not (Test-Path $p)) { throw "Missing source artefact: $p" }
}
Write-Host "  OK"

Write-Host "`n[2/3] backup current v4 baseline..."
foreach ($pair in $needed) {
    $dstFull = Join-Path $DestDir $pair.dst
    if (Test-Path $dstFull) {
        $bk = "$dstFull$backupSuffix"
        Copy-Item $dstFull $bk -Force
        Write-Host "  backed up $($pair.dst) -> $($pair.dst)$backupSuffix"
    } else {
        Write-Host "  skip backup, dest does not exist: $($pair.dst)"
    }
}

Write-Host "`n[3/3] copy v7-223 artefacts into place..."
foreach ($pair in $needed) {
    $srcFull = Join-Path $SourceDir $pair.src
    $dstFull = Join-Path $DestDir $pair.dst
    Copy-Item $srcFull $dstFull -Force
    Write-Host "  copied $($pair.src) -> $($pair.dst)"
}

Write-Host "`nDONE. Run the audit to verify 0 trim warnings:" -ForegroundColor Green
Write-Host "  python `"f:\Gorsachius magnificus\scripts\algo_d\audit_species_head_gap.py`""
Write-Host "Then restart the backend and grep its log for `"does not match checkpoint head`" (expected: no match)."
