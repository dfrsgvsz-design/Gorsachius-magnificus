<#
.SYNOPSIS
    Emergency restore of survey_store from a snapshot taken by
    scripts/snapshot_survey_store.ps1.

.DESCRIPTION
    Restore procedure (the script enforces every step):
      1. Backup file must pass PRAGMA integrity_check before anything moves.
      2. The live database must not be in active use - the script takes a
         short EXCLUSIVE lock to prove no backend process is attached.
         STOP THE APP FIRST (docker compose stop app / kill uvicorn).
      3. Current database is snapshotted to backups\pre_restore_<ts>.db so
         the restore itself is reversible. If the current DB is too corrupt
         for the backup API, a raw forensic copy is kept instead.
      4. Snapshot is copied over the live file; stale -wal/-shm sidecars
         are removed (they belong to the overwritten generation).
      5. Restored database passes integrity_check; alembic revision is
         printed via scripts/db_migrate.py for the operator log.

.PARAMETER BackupFile
    Snapshot to restore from. Mutually optional with -Latest.

.PARAMETER Latest
    Pick the newest survey_store_*.db inside <DataDir>\backups.

.PARAMETER DataDir
    Data directory (same resolution as snapshot script:
    param > SURVEY_DATA_DIR > BIRD_PLATFORM_DATA_DIR).

.PARAMETER Force
    Skip the interactive confirmation AND proceed even when the exclusive
    lock cannot be taken (use only when the lock failure is caused by the
    corruption you are recovering from, never while the app is running).

.EXAMPLE
    .\scripts\restore_survey_store.ps1 -Latest
    .\scripts\restore_survey_store.ps1 -BackupFile D:\backups\survey_store_20260611_233000.db -Force
#>
param(
    [string]$BackupFile,
    [switch]$Latest,
    [string]$DataDir,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# --- resolve data dir ---
if (-not $DataDir) { $DataDir = $env:SURVEY_DATA_DIR }
if (-not $DataDir) { $DataDir = $env:BIRD_PLATFORM_DATA_DIR }
if (-not $DataDir) {
    Write-Host "FAIL: no data dir. Pass -DataDir or set SURVEY_DATA_DIR / BIRD_PLATFORM_DATA_DIR." -ForegroundColor Red
    exit 2
}
$DataDir = (Resolve-Path $DataDir).Path
$DbPath = Join-Path $DataDir "survey_store\survey_store.db"
$BackupDir = Join-Path $DataDir "backups"

# --- resolve backup file ---
if ($Latest) {
    $candidate = Get-ChildItem (Join-Path $BackupDir "survey_store_*.db") -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $candidate) {
        Write-Host "FAIL: -Latest given but no survey_store_*.db found in $BackupDir" -ForegroundColor Red
        exit 2
    }
    $BackupFile = $candidate.FullName
}
if (-not $BackupFile) {
    Write-Host "FAIL: pass -BackupFile <path> or -Latest" -ForegroundColor Red
    exit 2
}
if (-not (Test-Path $BackupFile)) {
    Write-Host "FAIL: backup file not found: $BackupFile" -ForegroundColor Red
    exit 2
}

Write-Host "== restore_survey_store ==" -ForegroundColor Yellow
Write-Host "backup : $BackupFile"
Write-Host "target : $DbPath"

# --- step 1: never restore from a broken snapshot ---
python -c "import sqlite3, sys; r = sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0]; print('backup integrity_check:', r); sys.exit(0 if r == 'ok' else 1)" $BackupFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: backup file failed integrity_check - refusing to restore from it" -ForegroundColor Red
    exit 1
}

# --- step 2: prove the live DB is not in use (app must be stopped) ---
if (Test-Path $DbPath) {
    python -c "import sqlite3, sys; c = sqlite3.connect(sys.argv[1], timeout=2); c.execute('BEGIN EXCLUSIVE'); c.rollback(); c.close(); print('exclusive lock: ok (no active writers)')" $DbPath
    if ($LASTEXITCODE -ne 0) {
        if ($Force) {
            Write-Host "WARN: could not take exclusive lock but -Force given - continuing. If the backend is still running, STOP NOW (Ctrl+C) or you will corrupt the restore." -ForegroundColor Yellow
        } else {
            Write-Host "FAIL: could not take exclusive lock - backend still attached or DB badly corrupted. Stop the app first (docker compose stop app). Use -Force only if the lock failure IS the corruption you are recovering from." -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "note: live DB missing ($DbPath) - treating as disaster recovery onto empty slot"
    New-Item -ItemType Directory -Force -Path (Split-Path $DbPath) | Out-Null
}

# --- confirmation gate ---
if (-not $Force) {
    Write-Host ""
    Write-Host "About to OVERWRITE the live database with the backup above." -ForegroundColor Yellow
    $answer = Read-Host "Type YES to continue"
    if ($answer -ne "YES") {
        Write-Host "aborted by operator (nothing changed)"
        exit 3
    }
}

# --- step 3: make the restore itself reversible ---
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (Test-Path $DbPath) {
    $preRestore = Join-Path $BackupDir "pre_restore_$stamp.db"
    python -c "import sqlite3, sys; src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close(); print('pre-restore safety copy: done')" $DbPath $preRestore
    if ($LASTEXITCODE -ne 0) {
        $rawCopy = Join-Path $BackupDir "pre_restore_$stamp.raw.db"
        Write-Host "WARN: backup api failed on current DB (likely the corruption being recovered). Keeping raw forensic copy instead: $rawCopy" -ForegroundColor Yellow
        Copy-Item $DbPath $rawCopy -Force
        $preRestore = $rawCopy
    }
    Write-Host "pre-restore copy: $preRestore"
}

# --- step 4: restore + drop stale WAL sidecars ---
Copy-Item $BackupFile $DbPath -Force
Remove-Item "$DbPath-wal", "$DbPath-shm" -Force -ErrorAction SilentlyContinue

# --- step 5: verify what we just installed ---
python -c "import sqlite3, sys; r = sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0]; print('restored integrity_check:', r); sys.exit(0 if r == 'ok' else 1)" $DbPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: restored DB failed integrity_check - investigate before starting the app (pre-restore copy is in $BackupDir)" -ForegroundColor Red
    exit 1
}

Write-Host "-- alembic revision of restored DB (operator log) --"
$prevSurveyDataDir = $env:SURVEY_DATA_DIR
$env:SURVEY_DATA_DIR = $DataDir
try {
    python (Join-Path $RepoRoot "scripts\db_migrate.py") current
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: db_migrate current failed (non-fatal). If the snapshot predates head, run: python scripts/db_migrate.py upgrade head" -ForegroundColor Yellow
    }
} finally {
    $env:SURVEY_DATA_DIR = $prevSurveyDataDir
}

Write-Host ""
Write-Host "restore OK. Next: start the app, then run scripts/smoke_production_health.sh (or hit /api/health) before declaring recovery done." -ForegroundColor Green
exit 0
