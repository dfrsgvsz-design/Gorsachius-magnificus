# Clone Pixel_7.avd into N device profiles for low-/mid-/high-end + tablet matrix.
# Big .img / .qcow2 / state files are excluded; emulator will rebuild userdata on first boot.
# Run from species_monitoring_platform\.

$ErrorActionPreference = 'Stop'
$avdRoot = "$env:USERPROFILE\.android\avd"
$srcAvdDir = "$avdRoot\Pixel_7.avd"
$srcIni = "$avdRoot\Pixel_7.ini"

if (-not (Test-Path $srcAvdDir)) {
    Write-Error "Source AVD not found: $srcAvdDir"
    exit 1
}

# 10 AVDs: low-mid-high RAM x small/regular/tablet screen.
$profiles = @(
    @{ Name='Phone_LowEnd_1GB_480p';   RAM=1024; Cores=1; Width=480;  Height=854;  Density=240; Display='LowEnd 1GB 480p' },
    @{ Name='Phone_LowEnd_1GB_HD';     RAM=1024; Cores=2; Width=720;  Height=1280; Density=320; Display='LowEnd 1GB HD' },
    @{ Name='Phone_LowMid_1.5GB_HD';   RAM=1536; Cores=2; Width=720;  Height=1280; Density=320; Display='LowMid 1.5GB HD' },
    @{ Name='Phone_Mid_2GB_FHD';       RAM=2048; Cores=4; Width=1080; Height=1920; Density=420; Display='Mid 2GB FHD' },
    @{ Name='Phone_Mid_2GB_FHDPlus';   RAM=2048; Cores=4; Width=1080; Height=2400; Density=420; Display='Mid 2GB FHD+' },
    @{ Name='Phone_High_3GB_QHD';      RAM=3072; Cores=6; Width=1440; Height=2960; Density=480; Display='High 3GB QHD' },
    @{ Name='Phone_High_4GB_QHDPlus';  RAM=4096; Cores=8; Width=1440; Height=3120; Density=560; Display='High 4GB QHD+' },
    @{ Name='Phone_Compact_2GB';       RAM=2048; Cores=4; Width=720;  Height=1480; Density=320; Display='Compact 2GB' },
    @{ Name='Tablet_3GB_2K';           RAM=3072; Cores=4; Width=1600; Height=2560; Density=320; Display='Tablet 3GB 2K' },
    @{ Name='Tablet_4GB_2K';           RAM=4096; Cores=6; Width=2000; Height=1200; Density=320; Display='Tablet 4GB 2K' }
)

$summary = @()

foreach ($p in $profiles) {
    $dstDir = "$avdRoot\$($p.Name).avd"
    $dstIni = "$avdRoot\$($p.Name).ini"

    if (Test-Path $dstDir) {
        Write-Host "[skip] $($p.Name) already exists"
        continue
    }

    Write-Host "[clone] $($p.Name) -> RAM=$($p.RAM)MB cores=$($p.Cores) $($p.Width)x$($p.Height)@$($p.Density)dpi"

    # Use robocopy to copy structure but exclude all heavy disk images and state files.
    & robocopy $srcAvdDir $dstDir /E `
        /XF '*.img' '*.qcow2' '*.lock' 'hardware-qemu.ini' 'bootcompleted.ini' 'quickbootChoice.ini' 'read-snapshot.txt' '*.cache' 'AVD.conf' 'emu-launch-params.txt' `
        /XD 'snapshots' 'tmpAdbCmds' 'modem_simulator' /NFL /NDL /NJH /NJS /NC /NS 1>$null 2>$null

    # Rewrite config.ini
    $cfgPath = "$dstDir\config.ini"
    $cfg = Get-Content $cfgPath -Raw
    $cfg = $cfg `
        -replace '(?m)^AvdId=.*', "AvdId=$($p.Name)" `
        -replace '(?m)^avd\.ini\.displayname=.*', "avd.ini.displayname=$($p.Display)" `
        -replace '(?m)^hw\.ramSize=\d+', "hw.ramSize=$($p.RAM)" `
        -replace '(?m)^hw\.cpu\.ncore=\d+', "hw.cpu.ncore=$($p.Cores)" `
        -replace '(?m)^hw\.lcd\.width=\d+', "hw.lcd.width=$($p.Width)" `
        -replace '(?m)^hw\.lcd\.height=\d+', "hw.lcd.height=$($p.Height)" `
        -replace '(?m)^hw\.lcd\.density=\d+', "hw.lcd.density=$($p.Density)"

    # Cap dataPartition.size to 4G to save disk; default was 6G.
    $cfg = $cfg -replace '(?m)^disk\.dataPartition\.size=.*', 'disk.dataPartition.size=4G'
    # Disable PlayStore for low-RAM devices (it adds 200MB+).
    if ($p.RAM -lt 2048) {
        $cfg = $cfg -replace '(?m)^PlayStore\.enabled=true', 'PlayStore.enabled=false'
    }

    Set-Content -Path $cfgPath -Value $cfg -Encoding ASCII

    # Top-level .ini just contains path to the AVD dir.
    $iniContent = @"
avd.ini.encoding=UTF-8
path=$dstDir
path.rel=avd\$($p.Name).avd
target=android-37.0
"@
    Set-Content -Path $dstIni -Value $iniContent -Encoding ASCII

    $summary += [pscustomobject]@{
        Name = $p.Name
        RAM_MB = $p.RAM
        Cores = $p.Cores
        Resolution = "$($p.Width)x$($p.Height)"
        Density = $p.Density
        Created = Test-Path $dstDir
    }
}

Write-Host ""
$summary | Format-Table -AutoSize
Write-Host ""
Write-Host "==== avdmanager-equivalent listing (emulator -list-avds) ===="
$env:ANDROID_HOME = 'C:\Users\Administrator\AppData\Local\Android\Sdk'
& "$env:ANDROID_HOME\emulator\emulator.exe" -list-avds
