<#
.SYNOPSIS
    De-obfuscate an Android crash stack trace using an archived R8 mapping.txt.

.DESCRIPTION
    Created 2026-06-10 (ticket #C P1 W3). Wraps the R8 `retrace` tool (or
    falls back to ProGuard's `retrace.jar` when R8 is not installed) so that
    crash stacks pasted from Play Console, Sentry, or user reports can be
    reversed to original Kotlin/Java class + method names.

    Mapping archive convention (single source of truth):
      submission/_mapping_archive/<versionCode>/mapping.txt

    Pass `-VersionCode <int>` to look up the right mapping from the archive.
    For one-off use against a mapping file that hasn't been archived yet,
    pass `-MappingFile <absolute_path>` instead.

.PARAMETER VersionCode
    Android versionCode that produced the crash (e.g., 10001 for 1.0.1).
    Used to find submission/_mapping_archive/<versionCode>/mapping.txt.

.PARAMETER VersionName
    Human version string (e.g., "1.0.1"). Used as fallback to locate B's
    `archive_mapping.ps1` outputs at submission/playstore/mapping_<VersionName>_<date>.txt
    when the primary versionCode-keyed archive is missing.

.PARAMETER MappingFile
    Direct path to a mapping.txt. Overrides -VersionCode / -VersionName lookups.

.PARAMETER StackFile
    Path to a text file containing the raw obfuscated stack trace.

.PARAMETER StackText
    The stack trace as a single string (useful for paste-once invocations).
    If neither -StackFile nor -StackText is provided, reads from stdin.

.PARAMETER OutFile
    Optional output file path. When omitted, writes to stdout.

.EXAMPLE
    # 1) Archive a mapping (one-time, after each release)
    Copy-Item .\species_monitoring_platform\frontend\android\app\build\outputs\mapping\release\mapping.txt `
              .\submission\_mapping_archive\10001\mapping.txt

    # 2) De-obfuscate a stack pasted from Play Console
    .\scripts\deobfuscate.ps1 -VersionCode 10001 -StackText @"
    java.lang.NullPointerException
        at a.b.c.D.e(:42)
    "@

.EXAMPLE
    # De-obfuscate a stack from a file with an explicit mapping
    .\scripts\deobfuscate.ps1 -MappingFile "F:\downloads\mapping-10001.txt" -StackFile crash.txt -OutFile crash.deobf.txt
#>
param(
    [int]$VersionCode = 0,
    [string]$VersionName = "",
    [string]$MappingFile = "",
    [string]$StackFile = "",
    [string]$StackText = "",
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-MappingPath {
    param([int]$VersionCode, [string]$MappingFile, [string]$VersionName)

    if ($MappingFile -ne "") {
        if (-not (Test-Path $MappingFile)) {
            throw "mapping file not found: $MappingFile"
        }
        return (Resolve-Path $MappingFile).Path
    }

    # Primary lookup: C's convention `_mapping_archive/<versionCode>/mapping.txt`
    if ($VersionCode -gt 0) {
        $primary = Join-Path $RepoRoot "submission\_mapping_archive\$VersionCode\mapping.txt"
        if (Test-Path $primary) {
            return (Resolve-Path $primary).Path
        }
    }

    # Secondary lookup: B's `archive_mapping.ps1` convention
    # `submission/playstore/mapping_<VersionName>_<YYYY-MM-DD>.txt`.
    # Use -VersionName when you only have the human version string (e.g. "1.0.0").
    if ($VersionName -ne "") {
        $playstoreDir = Join-Path $RepoRoot "submission\playstore"
        if (Test-Path $playstoreDir) {
            $b = Get-ChildItem -Path $playstoreDir -Filter "mapping_${VersionName}_*.txt" -ErrorAction SilentlyContinue |
                 Sort-Object Name -Descending | Select-Object -First 1
            if ($b) { return $b.FullName }
        }
    }

    # Last-resort: when only -VersionCode was provided but C's archive is empty,
    # warn explicitly so the user can switch to -VersionName or -MappingFile.
    if ($VersionCode -gt 0) {
        throw @"
mapping for versionCode=$VersionCode not found at the primary archive:
  submission\_mapping_archive\$VersionCode\mapping.txt

Other places to check (see submission/_mapping_archive/README.md):
  - submission\playstore\mapping_<VersionName>_<date>.txt  (B's archive_mapping.ps1 output;
    re-run with -VersionName "<VersionName>" to look it up by human version string)
  - Play Console -> Internal testing -> Releases -> <versionCode> -> Download deobfuscation file

To re-archive a mapping you have on disk:
  New-Item -ItemType Directory -Force -Path "$RepoRoot\submission\_mapping_archive\$VersionCode" | Out-Null
  Copy-Item "<path-to-mapping.txt>" "$RepoRoot\submission\_mapping_archive\$VersionCode\mapping.txt"
"@
    }

    throw "Provide one of -VersionCode <int> / -VersionName <string> / -MappingFile <path>."
}

function Resolve-StackContent {
    param([string]$StackFile, [string]$StackText)

    if ($StackFile -ne "") {
        if (-not (Test-Path $StackFile)) {
            throw "stack file not found: $StackFile"
        }
        return (Get-Content -Path $StackFile -Raw)
    }
    if ($StackText -ne "") {
        return $StackText
    }
    Write-Host "Reading stack trace from stdin (Ctrl+Z then Enter to finish)..." -ForegroundColor Cyan
    return ([Console]::In.ReadToEnd())
}

function Find-RetraceTool {
    $candidates = @()

    if ($env:ANDROID_HOME) {
        $cmdlineLatest = Join-Path $env:ANDROID_HOME "cmdline-tools\latest\bin\retrace.bat"
        if (Test-Path $cmdlineLatest) {
            $candidates += [PSCustomObject]@{ Kind = "R8"; Command = $cmdlineLatest; Args = @() }
        }
        Get-ChildItem -Path (Join-Path $env:ANDROID_HOME "build-tools") -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object {
                $r8jar = Join-Path $_.FullName "r8.jar"
                if (Test-Path $r8jar) {
                    $candidates += [PSCustomObject]@{
                        Kind = "R8 (build-tools $($_.Name))"
                        Command = "java"
                        Args = @("-cp", $r8jar, "com.android.tools.r8.retrace.Retrace")
                    }
                }
            }
        $proguardRetrace = Join-Path $env:ANDROID_HOME "tools\proguard\bin\retrace.bat"
        if (Test-Path $proguardRetrace) {
            $candidates += [PSCustomObject]@{ Kind = "ProGuard (legacy)"; Command = $proguardRetrace; Args = @() }
        }
    }

    $studioJbr = "C:\Program Files\Android\Android Studio\jbr\bin\java.exe"
    if ((Test-Path $studioJbr) -and $env:ANDROID_HOME) {
        $latestR8 = Get-ChildItem -Path (Join-Path $env:ANDROID_HOME "build-tools") -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1
        if ($latestR8) {
            $r8jar = Join-Path $latestR8.FullName "r8.jar"
            if (Test-Path $r8jar) {
                $candidates += [PSCustomObject]@{
                    Kind = "R8 via Android Studio JBR ($($latestR8.Name))"
                    Command = $studioJbr
                    Args = @("-cp", $r8jar, "com.android.tools.r8.retrace.Retrace")
                }
            }
        }
    }

    return $candidates | Select-Object -First 1
}

$mappingPath = Resolve-MappingPath -VersionCode $VersionCode -VersionName $VersionName -MappingFile $MappingFile
$stackContent = Resolve-StackContent -StackFile $StackFile -StackText $StackText

if ([string]::IsNullOrWhiteSpace($stackContent)) {
    throw "stack trace is empty — pass -StackText or -StackFile, or pipe via stdin."
}

Write-Host "Using mapping: $mappingPath" -ForegroundColor Cyan

$retrace = Find-RetraceTool
if (-not $retrace) {
    throw @"
No retrace tool found. Install one of:
  1. Android SDK cmdline-tools (recommended): contains retrace.bat
     sdkmanager "cmdline-tools;latest"
  2. Android build-tools >= 30 (ships r8.jar with com.android.tools.r8.retrace.Retrace)
  3. ProGuard (legacy fallback)

Then set `$env:ANDROID_HOME` so this script can find it.
"@
}

Write-Host "Using retrace: $($retrace.Kind)" -ForegroundColor Cyan

$tempStackFile = New-TemporaryFile
try {
    Set-Content -Path $tempStackFile.FullName -Value $stackContent -Encoding UTF8

    $args = @()
    if ($retrace.Args.Count -gt 0) { $args += $retrace.Args }
    $args += $mappingPath
    $args += $tempStackFile.FullName

    Write-Host ""
    Write-Host "--- De-obfuscated output ---" -ForegroundColor Yellow

    $deobfTmp = New-TemporaryFile
    & $retrace.Command @args > $deobfTmp.FullName
    $exit = $LASTEXITCODE
    $output = Get-Content -Path $deobfTmp.FullName -Raw
    Remove-Item -Path $deobfTmp.FullName -Force -ErrorAction SilentlyContinue

    if ($exit -ne 0) {
        Write-Host $output
        throw "retrace exited with code $exit"
    }

    if ($OutFile -ne "") {
        Set-Content -Path $OutFile -Value $output -Encoding UTF8
        Write-Host "De-obfuscated output written to: $OutFile" -ForegroundColor Green
    } else {
        Write-Output $output
    }
} finally {
    Remove-Item -Path $tempStackFile.FullName -Force -ErrorAction SilentlyContinue
}
