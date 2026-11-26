param(
    [string]$ProductionEnv = "C:\ProgramData\ITOM\app\.env",
    [string]$ExperimentalEnv = "data\experimental\.env",
    [string]$Python = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 8081 is already in use; the existing process was not changed."
}
if (-not (Test-Path $Python)) { throw "Python executable not found: $Python" }
if (-not (Test-Path $ProductionEnv) -or -not (Test-Path $ExperimentalEnv)) {
    throw "Production and experimental configuration files are required."
}

& $Python scripts/run_staging.py --production-env $ProductionEnv --experimental-env $ExperimentalEnv --check
if ($LASTEXITCODE -ne 0) { throw "Experimental configuration failed isolation checks." }

$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$process = Start-Process -FilePath $Python -ArgumentList @(
    "scripts/run_staging.py", "--production-env", "`"$ProductionEnv`"",
    "--experimental-env", "`"$ExperimentalEnv`""
) -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir "experimental_8081_$stamp.log") `
    -RedirectStandardError (Join-Path $logDir "experimental_8081_$stamp.err.log")
Write-Host "Started experimental portal on 127.0.0.1:8081 (PID $($process.Id)); check /ready and the experimental logs."
