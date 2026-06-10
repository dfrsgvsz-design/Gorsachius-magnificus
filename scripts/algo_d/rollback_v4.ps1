# Algo-D / P0-W1: roll back from v7-head-223 deploy to the most recent
# v4_baseline backup created by deploy_v7_223.ps1.
#
# Usage:
#   pwsh "f:\Gorsachius magnificus\scripts\algo_d\rollback_v4.ps1"
#   pwsh "f:\Gorsachius magnificus\scripts\algo_d\rollback_v4.ps1" -BackupSuffix ".v4_baseline_20260610_120000"
[CmdletBinding()]
param(
    [string]$DestDir       = "f:\Gorsachius magnificus\species_monitoring_platform\backend\checkpoints",
    [string]$BackupSuffix  = ""    # empty -> auto-pick newest .v4_baseline_* backup of best_model.pth
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DestDir)) { throw "Dest dir not found: $DestDir" }

if (-not $BackupSuffix) {
    $latest = Get-ChildItem $DestDir -Filter "best_model.pth.v4_baseline_*" |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "No v4_baseline backup found in $DestDir" }
    $BackupSuffix = $latest.Name.Substring("best_model.pth".Length)
    Write-Host "Auto-picked backup suffix: $BackupSuffix"
}

$pairs = @(
    @{ dst = "best_model.pth"        },
    @{ dst = "best_teacher_v7.pth"   },
    @{ dst = "species_mapping.json"  },
    @{ dst = "calibration.json"      }
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Algo-D :: rollback to v4" -ForegroundColor Cyan
Write-Host "  dest          = $DestDir"
Write-Host "  backup suffix = $BackupSuffix"
Write-Host "==========================================================" -ForegroundColor Cyan

foreach ($p in $pairs) {
    $cur = Join-Path $DestDir $p.dst
    $bk  = "$cur$BackupSuffix"
    if (-not (Test-Path $bk)) {
        Write-Host "  skip $($p.dst) (no backup at $bk)" -ForegroundColor Yellow
        continue
    }
    Copy-Item $bk $cur -Force
    Write-Host "  restored $($p.dst) from $($p.dst)$BackupSuffix"
}

Write-Host "`nDONE. Run the audit and expect FAIL (head=217 < mapping=223)" -ForegroundColor Green
Write-Host "  python `"f:\Gorsachius magnificus\scripts\algo_d\audit_species_head_gap.py`""
Write-Host "If you also rolled back species_mapping.json from a pre-223 backup, exit code should be 0."
