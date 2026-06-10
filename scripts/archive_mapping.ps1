<#
.SYNOPSIS
  Archive the ProGuard / R8 mapping file from a release build into the
  submission directory so future Play Console crash reports stay
  deobfuscatable for the lifetime of that version.

.DESCRIPTION
  One command per release. Drops the mapping file at
  `submission/playstore/mapping_<Version>_<YYYY-MM-DD>.txt` and prints the
  destination so it can be pasted into the release log.

  Default source path matches the Capacitor android project layout used by
  `species_monitoring_platform/frontend/android/app/build.gradle`. Override
  with -SourcePath when running for the acoustic app or a non-default
  Capacitor project.

.PARAMETER Version
  The version string to embed in the archived filename (e.g. "1.0.0").
  Required.

.PARAMETER SourcePath
  Optional path to mapping.txt. Defaults to the species_monitoring_platform
  Capacitor release output. The script throws if the file does not exist.

.PARAMETER DestDir
  Optional destination directory. Defaults to "submission/playstore" relative
  to the workspace root.

.EXAMPLE
  scripts\archive_mapping.ps1 -Version "1.0.0"
    # Archives the species app's mapping for release 1.0.0.

.EXAMPLE
  scripts\archive_mapping.ps1 -Version "0.9.3" -SourcePath `
    "acoustic_platform/frontend/android/app/build/outputs/mapping/release/mapping.txt"
    # Archives the acoustic app's mapping.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$SourcePath = "species_monitoring_platform/frontend/android/app/build/outputs/mapping/release/mapping.txt",
    [string]$DestDir = "submission/playstore"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -Path $SourcePath -PathType Leaf)) {
    throw "mapping.txt not found at '$SourcePath'. Run `./gradlew bundleRelease` (with `minifyEnabled true`) first."
}

if (-not (Test-Path -Path $DestDir -PathType Container)) {
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
}

$date = Get-Date -Format 'yyyy-MM-dd'
$destFile = Join-Path $DestDir "mapping_${Version}_${date}.txt"

Copy-Item -Path $SourcePath -Destination $destFile -Force

$size = (Get-Item $destFile).Length
Write-Host "Archived mapping.txt for version $Version" -ForegroundColor Green
Write-Host "  source: $SourcePath"
Write-Host "  dest:   $destFile  ($([math]::Round($size / 1KB, 1)) KB)"
Write-Host ""
Write-Host "Paste this line into the release log:"
Write-Host "  mapping: $destFile" -ForegroundColor Cyan
