<#
.SYNOPSIS
    Emergency snapshot of the live survey_store SQLite database.

.DESCRIPTION
    Companion to scripts/restore_survey_store.ps1 (P0 W3 rollback drill,
    ticket follow-up after alembic integration).

    survey_store runs with PRAGMA journal_mode=WAL, so a raw file copy of a
    live database is NOT safe (the -wal sidecar may hold unmerged pages).
    This script therefore snapshots through Python's sqlite3 backup API,
    which produces a consistent point-in-time copy even while the backend
    keeps writing.

    Database location contract (mirrors shared/backend/utils/runtime_paths):
        <DataDir>\survey_store\survey_store.db
    where DataDir resolves from: -DataDir param > SURVEY_DATA_DIR >
    BIRD_PLATFORM_DATA_DIR. No silent dev fallback on purpose - an
    emergency tool must never guess which database it is copying.

.PARAMETER DataDir
    Data directory (the one SURVEY_DATA_DIR points at in production).

.PARAMETER OutDir
    Where snapshots land. Default: <DataDir>\backups

.PARAMETER Tag
    Optional label appended to the snapshot file name.

.PARAMETER Keep
    If > 0, prune old snapshots keeping only the newest N (pre_restore_*
    safety copies are never pruned).

.EXAMPLE
    .\scripts\snapshot_survey_store.ps1
    .\scripts\snapshot_survey_store.ps1 -Tag before_v0_9_rollout -Keep 10
#>
param(
    [string]$DataDir,
    [string]$OutDir,
    [string]$Tag,
    [int]$Keep = 0
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

# --- resolve data dir (param > SURVEY_DATA_DIR > BIRD_PLATFORM_DATA_DIR) ---
if (-not $DataDir) { $DataDir = $env:SURVEY_DATA_DIR }
if (-not $DataDir) { $DataDir = $env:BIRD_PLATFORM_DATA_DIR }
if (-not $DataDir) {
    Write-Host "FAIL: no data dir. Pass -DataDir or set SURVEY_DATA_DIR / BIRD_PLATFORM_DATA_DIR." -ForegroundColor Red
    exit 2
}
$DataDir = (Resolve-Path $DataDir).Path

$DbPath = Join-Path $DataDir "survey_store\survey_store.db"
if (-not (Test-Path $DbPath)) {
    Write-Host "FAIL: database not found: $DbPath" -ForegroundColor Red
    exit 2
}

if (-not $OutDir) { $OutDir = Join-Path $DataDir "backups" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$name = "survey_store_$stamp"
if ($Tag) { $name = "$name`_$Tag" }
$Dest = Join-Path $OutDir "$name.db"

Write-Host "== snapshot_survey_store ==" -ForegroundColor Yellow
Write-Host "source : $DbPath"
Write-Host "dest   : $Dest"

# --- consistent point-in-time copy via sqlite3 backup API (WAL-safe) ---
python -c "import sqlite3, sys; src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close(); print('backup api: done')" $DbPath $Dest
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: sqlite backup api failed (exit $LASTEXITCODE)" -ForegroundColor Red
    Remove-Item $Dest -ErrorAction SilentlyContinue
    exit 1
}

# --- verify the snapshot before trusting it ---
python -c "import sqlite3, sys; r = sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0]; print('integrity_check:', r); sys.exit(0 if r == 'ok' else 1)" $Dest
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: snapshot failed integrity_check - NOT usable for restore" -ForegroundColor Red
    exit 1
}

$sizeKb = [math]::Round((Get-Item $Dest).Length / 1KB, 1)
$sha = (Get-FileHash $Dest -Algorithm SHA256).Hash.Substring(0, 16)
Write-Host "size   : $sizeKb KB"
Write-Host "sha256 : $sha (first 16)"

# --- optional pruning (never touches pre_restore_* safety copies) ---
if ($Keep -gt 0) {
    $old = Get-ChildItem (Join-Path $OutDir "survey_store_*.db") |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $Keep
    foreach ($f in $old) {
        Write-Host "prune  : $($f.Name)"
        Remove-Item $f.FullName -Force
    }
}

Write-Host "snapshot OK: $Dest" -ForegroundColor Green
exit 0
