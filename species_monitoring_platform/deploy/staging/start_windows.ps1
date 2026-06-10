# Windows Server start script for gm-backend
# Run from C:\gm-backend after creating venv and installing requirements
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^([^#=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
        }
    }
}
$env:PYTHONUNBUFFERED = '1'
$port = if ($env:APP_PORT) { $env:APP_PORT } else { '8000' }
$workers = if ($env:WEB_CONCURRENCY) { $env:WEB_CONCURRENCY } else { '1' }
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port $port --workers $workers