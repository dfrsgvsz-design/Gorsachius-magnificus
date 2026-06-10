<#
.SYNOPSIS
    Validate Android release signing environment without leaking secrets.

.DESCRIPTION
    Created 2026-06-10 (ticket #C, P0 W2). Runs the 6 checks the runbook
    requires before any local `gradlew bundleRelease`:

    1. ANDROID_KEYSTORE_FILE is set and the file exists and is readable.
    2. ANDROID_KEYSTORE_PASSWORD is set (non-empty; value never printed).
    3. ANDROID_KEY_ALIAS is set.
    4. ANDROID_KEY_PASSWORD is set (non-empty; value never printed).
    5. `keytool -list` against the keystore + provided alias succeeds.
    6. The SHA-256 fingerprint matches the constant pinned in
       submission/06_packaging_signing_runbook.md §1 (defence against
       accidental keystore swap or compromise).

    Exit code:
      0 = all 6 checks PASS
      1 = at least one check FAIL

    Secrets handling:
      - Passwords are read from process env and passed to keytool via -storepass
        / -keypass arguments. They are never written to stdout, log files, or
        the script summary.
      - keytool's own output is captured and filtered before display.

.PARAMETER ExpectedSha256
    The pinned SHA-256 fingerprint to compare against. Defaults to the
    constant published in 06_packaging_signing_runbook.md §1. Pass an empty
    string to skip the SHA check (NOT recommended).

.EXAMPLE
    # Standard pre-build check
    .\scripts\verify_signing_env.ps1

.EXAMPLE
    # Skip SHA pin (development keystore, etc.)
    .\scripts\verify_signing_env.ps1 -ExpectedSha256 ""
#>
param(
    [string]$ExpectedSha256 = "CA:D0:C1:41:E2:75:21:6D:B2:84:18:58:FF:A0:FC:E6:1E:16:9C:E5:B3:FB:73:3B:0E:95:9B:7D:BF:A7:37:3E"
)

$ErrorActionPreference = "Stop"

$script:results = @()

function Record-Check {
    param([string]$Name, [bool]$Ok, [string]$Detail = "")
    $script:results += [PSCustomObject]@{
        Check  = $Name
        Status = if ($Ok) { "PASS" } else { "FAIL" }
        Detail = $Detail
    }
    $color = if ($Ok) { "Green" } else { "Red" }
    $tag = if ($Ok) { "[PASS]" } else { "[FAIL]" }
    Write-Host ("{0,-6} {1,-46} {2}" -f $tag, $Name, $Detail) -ForegroundColor $color
}

function Mask-Value {
    param([string]$Value)
    if ([string]::IsNullOrEmpty($Value)) { return "(empty)" }
    return "({0} chars)" -f $Value.Length
}

function Find-Keytool {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\keytool.exe")) {
        return "$env:JAVA_HOME\bin\keytool.exe"
    }
    $androidStudioJbr = "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"
    if (Test-Path $androidStudioJbr) { return $androidStudioJbr }
    $cmd = Get-Command keytool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

Write-Host ""
Write-Host "=== Android Signing Env Verification ===" -ForegroundColor Cyan
Write-Host "(passwords are never printed; only length shown)"
Write-Host ""

# 1. ANDROID_KEYSTORE_FILE
$kfile = $env:ANDROID_KEYSTORE_FILE
if ([string]::IsNullOrWhiteSpace($kfile)) {
    Record-Check "ANDROID_KEYSTORE_FILE is set" $false "env var empty"
    $kfileOk = $false
} else {
    if (Test-Path $kfile) {
        $bytes = (Get-Item $kfile).Length
        Record-Check "ANDROID_KEYSTORE_FILE is set + exists" $true ("{0} bytes -> {1}" -f $bytes, $kfile)
        $kfileOk = $true
    } else {
        Record-Check "ANDROID_KEYSTORE_FILE exists" $false ("file not found: {0}" -f $kfile)
        $kfileOk = $false
    }
}

# 2. ANDROID_KEYSTORE_PASSWORD
$kpass = $env:ANDROID_KEYSTORE_PASSWORD
$kpassOk = -not [string]::IsNullOrEmpty($kpass)
Record-Check "ANDROID_KEYSTORE_PASSWORD is set" $kpassOk (Mask-Value $kpass)

# 3. ANDROID_KEY_ALIAS
$alias = $env:ANDROID_KEY_ALIAS
$aliasOk = -not [string]::IsNullOrWhiteSpace($alias)
$aliasDisplay = if ($aliasOk) { $alias } else { "(empty)" }
Record-Check "ANDROID_KEY_ALIAS is set" $aliasOk $aliasDisplay

# 4. ANDROID_KEY_PASSWORD
$keypass = $env:ANDROID_KEY_PASSWORD
$keypassOk = -not [string]::IsNullOrEmpty($keypass)
Record-Check "ANDROID_KEY_PASSWORD is set" $keypassOk (Mask-Value $keypass)

# 5. keytool -list (alias presence + reachability)
$keytool = Find-Keytool
if (-not $keytool) {
    Record-Check "keytool found" $false "JAVA_HOME not set; Android Studio JBR not at default path; keytool not on PATH"
    $aliasFoundOk = $false
    $shaParsed = ""
} elseif (-not ($kfileOk -and $kpassOk -and $aliasOk)) {
    Record-Check "keytool -list reachable + alias present" $false "skipped (prerequisite env vars missing)"
    $aliasFoundOk = $false
    $shaParsed = ""
} else {
    try {
        # Use ArgumentList so keytool sees args correctly; capture stdout+stderr.
        $tmpOut = New-TemporaryFile
        $tmpErr = New-TemporaryFile
        $proc = Start-Process -FilePath $keytool `
            -ArgumentList @("-list","-v","-keystore",$kfile,"-storepass",$kpass,"-alias",$alias) `
            -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput $tmpOut.FullName `
            -RedirectStandardError $tmpErr.FullName
        $stdout = Get-Content $tmpOut.FullName -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content $tmpErr.FullName -Raw -ErrorAction SilentlyContinue
        Remove-Item $tmpOut.FullName, $tmpErr.FullName -Force -ErrorAction SilentlyContinue

        if ($proc.ExitCode -ne 0) {
            $errSnippet = if ($stderr) { ($stderr -split "`n")[0..2] -join " | " } else { "no stderr" }
            Record-Check "keytool -list reachable + alias present" $false ("exit {0}: {1}" -f $proc.ExitCode, $errSnippet)
            $aliasFoundOk = $false
            $shaParsed = ""
        } else {
            Record-Check "keytool -list reachable + alias present" $true ("alias '{0}' found" -f $alias)
            $aliasFoundOk = $true
            $shaLine = ($stdout -split "`r?`n") | Where-Object { $_ -match "SHA256:" -or $_ -match "SHA-256:" } | Select-Object -First 1
            if ($shaLine) {
                $shaParsed = ($shaLine -replace ".*?SHA[-]?256:\s*","").Trim()
            } else {
                $shaParsed = ""
            }
        }
    } catch {
        Record-Check "keytool -list reachable + alias present" $false ("exception: " + $_.Exception.Message)
        $aliasFoundOk = $false
        $shaParsed = ""
    }
}

# 6. SHA-256 fingerprint pin
if ([string]::IsNullOrWhiteSpace($ExpectedSha256)) {
    Record-Check "SHA-256 fingerprint matches pinned constant" $true "skipped (no expected value provided)"
} elseif (-not $aliasFoundOk) {
    Record-Check "SHA-256 fingerprint matches pinned constant" $false "skipped (keytool step failed)"
} elseif ([string]::IsNullOrWhiteSpace($shaParsed)) {
    Record-Check "SHA-256 fingerprint matches pinned constant" $false "keytool output missing SHA256 line"
} else {
    $normalisedActual   = ($shaParsed -replace "\s","").ToUpper()
    $normalisedExpected = ($ExpectedSha256 -replace "\s","").ToUpper()
    if ($normalisedActual -eq $normalisedExpected) {
        Record-Check "SHA-256 fingerprint matches pinned constant" $true "match"
    } else {
        $actualShort   = $normalisedActual.Substring(0, [Math]::Min(23, $normalisedActual.Length)) + "..."
        $expectedShort = $normalisedExpected.Substring(0, [Math]::Min(23, $normalisedExpected.Length)) + "..."
        Record-Check "SHA-256 fingerprint matches pinned constant" $false ("MISMATCH (got {0} ; expected {1})" -f $actualShort, $expectedShort)
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Yellow
$script:results | Format-Table -AutoSize -Property Check, Status

$failed = @($script:results | Where-Object { $_.Status -eq "FAIL" })
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host ("Signing env verification FAILED ({0}/{1} check(s) failed)." -f $failed.Count, $script:results.Count) -ForegroundColor Red
    Write-Host "DO NOT run 'gradlew bundleRelease' until all checks pass." -ForegroundColor Red
    Write-Host "Refer to submission/06_packaging_signing_runbook.md §1.1 for Vault retrieval flow."
    exit 1
}

Write-Host ""
Write-Host ("Signing env verification PASSED ({0}/{0} checks)." -f $script:results.Count) -ForegroundColor Green
Write-Host "Safe to proceed to submission/06_packaging_signing_runbook.md §3."
exit 0
