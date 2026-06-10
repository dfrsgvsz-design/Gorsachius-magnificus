$ErrorActionPreference = "Stop"

$root = "f:\Gorsachius magnificus"
Set-Location $root

$requiredFiles = @(
    "scripts/release_gate.ps1",
    "submission/01_android_ios_submission_checklist.md",
    "submission/02_submission_material_template.md",
    "submission/03_missing_required_business_inputs.md",
    "submission/04_release_execution_runbook.md",
    "submission/05_go_live_decision_report.md",
    "species_monitoring_platform/frontend/.env.production.example",
    "acoustic_platform/frontend/.env.production.example"
)

$missing = @()
foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        $missing += $file
    }
}

Write-Host "== Release Status =="
Write-Host ("Required files: " + $requiredFiles.Count)
Write-Host ("Missing files : " + $missing.Count)

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing:"
    $missing | ForEach-Object { Write-Host (" - " + $_) }
}

Write-Host ""
Write-Host "Go-Live Decision:"
if (Test-Path "submission/05_go_live_decision_report.md") {
    Write-Host " - See submission/05_go_live_decision_report.md"
} else {
    Write-Host " - Not generated"
}

if ($missing.Count -eq 0) {
    Write-Host ""
    Write-Host "Status: READY FOR FINAL BUSINESS/FORMAL REVIEW"
    exit 0
}

Write-Host ""
Write-Host "Status: NOT READY"
exit 1
