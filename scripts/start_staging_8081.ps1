# Run this checkout as a staging portal on port 8081 beside the live 8080 service.
# Staging never runs the sync scheduler, uses its own PostgreSQL database (a copy of
# live itom_db), and a private copy of the asset workbooks, so nothing done on
# staging changes what live users see.
param(
    [int]$Port = 8081,
    [string]$Database = "itom_staging",
    [string]$LiveEnv = "C:\ProgramData\ITOM\app\.env",
    [string]$LiveAssetDir = "C:\ProgramData\ITOM\asset_inventory",
    [switch]$RefreshAssets
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Port -eq 8080) { throw "Port 8080 is the live portal. Use a different staging port." }

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "Stopping existing staging process on port $Port (PID $($listener.OwningProcess))."
    Stop-Process -Id $listener.OwningProcess -Force
    Start-Sleep -Seconds 2
}

if ($Database -eq "itom_db") { throw "itom_db is the live database. Staging must use its own database." }

$liveUrl = (Select-String -Path $LiveEnv -Pattern '^DATABASE_URL=' | Select-Object -First 1).Line
if (-not $liveUrl) { throw "DATABASE_URL not found in $LiveEnv." }
$liveUrl = ($liveUrl -replace '^DATABASE_URL=', '').Trim().Trim("'").Trim('"')
if ($liveUrl -notmatch '^postgres') { throw "Live DATABASE_URL is not PostgreSQL; cannot derive the staging database." }
$stagingUrl = $liveUrl -replace '/[^/?]+(\?.*)?$', "/$Database`$1"
$env:DATABASE_URL = $stagingUrl
$env:DATABASE_URL_2 = $stagingUrl

$stagingAssets = Join-Path $root "data\asset_inventory_staging"
if ($RefreshAssets -or -not (Test-Path $stagingAssets)) {
    New-Item -ItemType Directory -Force -Path $stagingAssets | Out-Null
    Copy-Item -Path (Join-Path $LiveAssetDir "*.xlsx") -Destination $stagingAssets -Force
}
$env:ASSET_INVENTORY_DIR = $stagingAssets
$env:SCHEDULER_ENABLED = "false"

New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
$log = Join-Path $root "logs\local_$Port.log"
$python = Join-Path $root ".venv\Scripts\python.exe"

Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port" `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err"

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $ready = Invoke-WebRequest "http://127.0.0.1:$Port/ready" -UseBasicParsing -TimeoutSec 5
        if ($ready.StatusCode -eq 200) {
            Write-Host "Staging portal ready at http://localhost:$Port/ (database $Database, scheduler disabled)."
            exit 0
        }
    } catch { }
}
Write-Host "Staging portal did not become ready. Check $log and $log.err."
exit 1
