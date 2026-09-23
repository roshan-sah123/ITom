<#
.SYNOPSIS
    Copies your current backend source into OneDrive so it can be read.

.DESCRIPTION
    The assistant has no access to C:\Users\...\antigravity\optimistic-pasteur.
    It can only read what is synced to OneDrive. Until now that was a stale
    copy from 3 September, which is why patches kept failing to match and why
    endpoints existed that were never documented.

    This script copies the SOURCE FILES ONLY into

        OneDrive\Desktop\itom-current\

    so the assistant is always working against what you actually have.

    WHAT IS COPIED
        app\        the FastAPI backend
        src\        the Graph and SolarWinds clients
        scripts\    operational tooling
        alembic\    migrations
        pytest.ini, requirements.txt, Dockerfile, docker-compose.yml

    WHAT IS NEVER COPIED
        .env                  credentials
        data\                 the database and telemetry snapshots
        __pycache__, *.pyc    build artefacts
        .git\                 repository internals
        tests\                large, rarely needed - use -IncludeTests
        legacy-frontend\      not backend code

    Run it after every change you want reviewed.

.EXAMPLE
    .\share_code.ps1
    Copies the backend source to OneDrive.

.EXAMPLE
    .\share_code.ps1 -IncludeTests
    Also copies the tests folder.

.EXAMPLE
    .\share_code.ps1 -Only app\api\v1\endpoints\sync.py
    Copies a single file - fastest when only one file matters.
#>

[CmdletBinding()]
param(
    [switch]$IncludeTests,
    [string]$Only
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Locate OneDrive. The folder name varies by tenant, so probe rather than guess.
# ---------------------------------------------------------------------------
$oneDrive = $null
foreach ($candidate in @($env:OneDriveCommercial, $env:OneDrive, "$env:USERPROFILE\OneDrive - Coforge Limited", "$env:USERPROFILE\OneDrive")) {
    if ($candidate -and (Test-Path $candidate)) { $oneDrive = $candidate; break }
}

if (-not $oneDrive) {
    Write-Host "Could not find your OneDrive folder." -ForegroundColor Red
    Write-Host "Folders in your profile:" -ForegroundColor Yellow
    Get-ChildItem $env:USERPROFILE -Directory | Where-Object Name -like "OneDrive*" | ForEach-Object { Write-Host "  $($_.FullName)" }
    exit 1
}

$dest = Join-Path $oneDrive "Desktop\itom-current"
$source = (Get-Location).Path

Write-Host ""
Write-Host "SHARE CODE FOR REVIEW" -ForegroundColor White
Write-Host "  From: $source"
Write-Host "  To:   $dest"

# ---------------------------------------------------------------------------
# Single-file mode
# ---------------------------------------------------------------------------
if ($Only) {
    $src = Join-Path $source $Only
    if (-not (Test-Path $src)) {
        Write-Host "`n  Not found: $Only" -ForegroundColor Red
        exit 1
    }
    $target = Join-Path $dest $Only
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    Copy-Item $src $target -Force
    $kb = [math]::Round((Get-Item $src).Length / 1KB, 1)
    Write-Host "`n  Copied $Only ($kb KB)" -ForegroundColor Green
    Write-Host "`n  Tell the assistant: 'read itom-current\$Only'"
    Write-Host ""
    exit 0
}

# ---------------------------------------------------------------------------
# Full copy
# ---------------------------------------------------------------------------
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$folders = @("app", "src", "scripts", "alembic")
if ($IncludeTests) { $folders += "tests" }

$excludeDirs = @("__pycache__", ".pytest_cache", "node_modules", ".git")
$totalFiles = 0
$totalBytes = 0

foreach ($folder in $folders) {
    $from = Join-Path $source $folder
    if (-not (Test-Path $from)) { continue }

    $files = Get-ChildItem $from -Recurse -File -Include *.py, *.ini, *.mako, *.cfg -EA SilentlyContinue |
             Where-Object {
                 $path = $_.FullName
                 -not ($excludeDirs | Where-Object { $path -like "*\$_\*" })
             }

    foreach ($file in $files) {
        $relative = $file.FullName.Substring($source.Length + 1)
        $target = Join-Path $dest $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Copy-Item $file.FullName $target -Force
        $totalFiles++
        $totalBytes += $file.Length
    }

    Write-Host ("  {0,-12} {1,4} files" -f $folder, $files.Count) -ForegroundColor Gray
}

# Root-level config files
foreach ($name in @("pytest.ini", "requirements.txt", "Dockerfile", "docker-compose.yml", "alembic.ini", ".env.example")) {
    $from = Join-Path $source $name
    if (Test-Path $from) {
        Copy-Item $from (Join-Path $dest $name) -Force
        $totalFiles++
        $totalBytes += (Get-Item $from).Length
    }
}

# ---------------------------------------------------------------------------
# Safety check - nothing sensitive should have travelled
# ---------------------------------------------------------------------------
$leaked = Get-ChildItem $dest -Recurse -File -Force -EA SilentlyContinue |
          Where-Object { $_.Name -eq ".env" -or $_.Extension -in ".db", ".sqlite", ".log" }

if ($leaked) {
    Write-Host "`n  WARNING - removing files that should not be shared:" -ForegroundColor Red
    $leaked | ForEach-Object {
        Write-Host "    $($_.Name)" -ForegroundColor Red
        Remove-Item $_.FullName -Force
    }
}

$mb = [math]::Round($totalBytes / 1MB, 2)
Write-Host ""
Write-Host "  $totalFiles files, $mb MB" -ForegroundColor Green
Write-Host "  No credentials, no database, no build artefacts." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Wait ~30 seconds for OneDrive to sync, then tell the assistant:" -ForegroundColor White
Write-Host "    'code is updated in itom-current'" -ForegroundColor Cyan
Write-Host ""
