# Algo-D / P0-W1: Train ConvNeXt V7 (teacher+student+OOD calibrate) with head=223
#
# Wraps species_monitoring_platform/scripts/train_gpu_v7.py with the right
# manifest (xc_expanded, 19401 rows, 223 species) and writes to
# checkpoints_v7_223/. Runs the pre-audit, the training, and the post-audit
# in one shot. Aborts at first failure.
#
# Usage (from anywhere):
#   pwsh "f:\Gorsachius magnificus\scripts\algo_d\train_v7_head_223.ps1"
#   pwsh "f:\Gorsachius magnificus\scripts\algo_d\train_v7_head_223.ps1" -BatchSize 8 -Workers 1
#
# Requires: CUDA-capable GPU, torch + librosa installed in the active venv.
[CmdletBinding()]
param(
    [int]$BatchSize       = 16,
    [int]$EpochsTeacher   = 200,
    [int]$EpochsStudent   = 150,
    [int]$Workers         = 2,
    [string]$Phase        = "all"  # all|teacher|student|calibrate
)

$ErrorActionPreference = "Stop"

$repo  = "f:\Gorsachius magnificus"
$smp   = Join-Path $repo "species_monitoring_platform"
$data  = Join-Path $smp  "data\xc_expanded"
$out   = Join-Path $smp  "checkpoints_v7_223"
$audit = Join-Path $repo "scripts\algo_d\audit_species_head_gap.py"

if (-not (Test-Path (Join-Path $data "manifest.json"))) {
    throw "manifest.json not found at $data"
}
New-Item -Path $out -ItemType Directory -Force | Out-Null

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Algo-D :: Train V7 head=223" -ForegroundColor Cyan
Write-Host "  repo            = $repo"
Write-Host "  manifest        = $data\manifest.json"
Write-Host "  output dir      = $out"
Write-Host "  batch_size      = $BatchSize"
Write-Host "  epochs_teacher  = $EpochsTeacher"
Write-Host "  epochs_student  = $EpochsStudent"
Write-Host "  workers         = $Workers"
Write-Host "  phase           = $Phase"
Write-Host "==========================================================" -ForegroundColor Cyan

Write-Host "`n[1/4] Pre-audit (expects FAIL because head=217 < mapping=223)..." -ForegroundColor Yellow
& python $audit
$preExit = $LASTEXITCODE
Write-Host "  pre-audit exit = $preExit  (expected: 2)"

Write-Host "`n[2/4] GPU probe..." -ForegroundColor Yellow
& python -c "import torch; print('  cuda available =', torch.cuda.is_available()); print('  device        =', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
if ($LASTEXITCODE -ne 0) { throw "GPU probe failed; check torch install" }

Write-Host "`n[3/4] Run train_gpu_v7.py (this is the long step)..." -ForegroundColor Yellow
Push-Location $smp
try {
    & python scripts\train_gpu_v7.py `
        --data $data `
        --output $out `
        --batch-size $BatchSize `
        --epochs-teacher $EpochsTeacher `
        --epochs-student $EpochsStudent `
        --workers $Workers `
        --phase $Phase
    if ($LASTEXITCODE -ne 0) { throw "train_gpu_v7.py failed with exit $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "`n[4/4] Post-train artefact sanity check..." -ForegroundColor Yellow
$mustExist = @(
    "best_teacher_v7.pth",
    "best_student_v7.pth",
    "species_mapping.json",
    "train_config.json"
)
foreach ($f in $mustExist) {
    $p = Join-Path $out $f
    if (-not (Test-Path $p)) { throw "Missing expected artefact: $p" }
    $size = (Get-Item $p).Length
    Write-Host ("  OK  {0,-26} {1,12} bytes" -f $f, $size)
}

Write-Host "`nDONE. Next steps:" -ForegroundColor Green
Write-Host "  1) python `"$repo\scripts\algo_d\calibrate_temperature.py`" --checkpoint `"$out\best_student_v7.pth`" --manifest `"$data\manifest.json`" --output `"$out\calibration.json`""
Write-Host "  2) pwsh `"$repo\scripts\algo_d\deploy_v7_223.ps1`""
Write-Host "  3) python `"$audit`"  # expects exit 0 (PASS)"
