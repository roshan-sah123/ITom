<#
.SYNOPSIS
    Removes build noise and dead files from the ITOM Portal backend.

.DESCRIPTION
    SAFE BY DEFAULT. Running it with no switches only PRINTS what it would
    remove. Nothing is deleted until you add -Execute.

    Work is split into three tiers so you can decide how far to go:

      Tier 1  Build artefacts and backups. Always safe. Regenerated on demand.
      Tier 2  Development leftovers. Safe, but read the list first.
      Tier 3  Large data and image files. Your judgement required.

    Files this script REFUSES to touch are listed at the bottom, with the
    reason. Several look unused and are not.

.EXAMPLE
    .\cleanup_backend.ps1
    Shows what would be removed. Changes nothing.

.EXAMPLE
    .\cleanup_backend.ps1 -Tier1 -Execute
    Removes build artefacts and .bak files for real.

.EXAMPLE
    .\cleanup_backend.ps1 -Tier1 -Tier2 -Execute
    Also removes development leftovers.
#>

[CmdletBinding()]
param(
    [switch]$Tier1,
    [switch]$Tier2,
    [switch]$Tier3,
    [switch]$Execute
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

# If no tier is chosen, preview Tier 1 and Tier 2.
if (-not ($Tier1 -or $Tier2 -or $Tier3)) { $Tier1 = $true; $Tier2 = $true }

$script:totalBytes = 0
$script:totalItems = 0

function Show-Header($text) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host $text -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

function Remove-Target {
    param(
        [string]$Path,
        [string]$Reason
    )

    $full = Join-Path $root $Path
    if (-not (Test-Path $full)) { return }

    $item = Get-Item $full -Force
    if ($item.PSIsContainer) {
        $size = (Get-ChildItem $full -Recurse -File -Force -EA SilentlyContinue |
                 Measure-Object -Property Length -Sum).Sum
    } else {
        $size = $item.Length
    }
    if (-not $size) { $size = 0 }

    $script:totalBytes += $size
    $script:totalItems++

    $mb = [math]::Round($size / 1MB, 2)
    $label = if ($mb -ge 0.01) { "$mb MB" } else { "$([math]::Round($size/1KB,1)) KB" }

    if ($Execute) {
        Remove-Item $full -Recurse -Force -EA SilentlyContinue
        Write-Host ("  REMOVED  {0,-46} {1,10}" -f $Path, $label) -ForegroundColor Green
    } else {
        Write-Host ("  would remove  {0,-42} {1,10}" -f $Path, $label) -ForegroundColor Yellow
    }
    if ($Reason) { Write-Host "                $Reason" -ForegroundColor DarkGray }
}

function Remove-Pattern {
    param(
        [string]$Pattern,
        [string]$Reason,
        [switch]$Directory
    )

    $found = if ($Directory) {
        Get-ChildItem $root -Recurse -Directory -Filter $Pattern -Force -EA SilentlyContinue
    } else {
        Get-ChildItem $root -Recurse -File -Filter $Pattern -Force -EA SilentlyContinue
    }

    # Never walk into .git
    $found = $found | Where-Object { $_.FullName -notmatch '\\\.git\\' }
    if (-not $found) { return }

    $size = 0
    foreach ($f in $found) {
        if ($f.PSIsContainer) {
            $s = (Get-ChildItem $f.FullName -Recurse -File -Force -EA SilentlyContinue |
                  Measure-Object -Property Length -Sum).Sum
        } else { $s = $f.Length }
        if ($s) { $size += $s }
    }

    $script:totalBytes += $size
    $script:totalItems += $found.Count
    $mb = [math]::Round($size / 1MB, 2)

    if ($Execute) {
        $found | ForEach-Object { Remove-Item $_.FullName -Recurse -Force -EA SilentlyContinue }
        Write-Host ("  REMOVED  {0,-30} x{1,-14} {2,8} MB" -f $Pattern, $found.Count, $mb) -ForegroundColor Green
    } else {
        Write-Host ("  would remove  {0,-26} x{1,-14} {2,8} MB" -f $Pattern, $found.Count, $mb) -ForegroundColor Yellow
    }
    if ($Reason) { Write-Host "                $Reason" -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "ITOM BACKEND CLEANUP" -ForegroundColor White
Write-Host "Working in: $root"
if ($Execute) {
    Write-Host "MODE: EXECUTE - files will be deleted" -ForegroundColor Red
} else {
    Write-Host "MODE: PREVIEW - nothing will be deleted" -ForegroundColor Green
    Write-Host "Add -Execute when you are happy with the list."
}

# --------------------------------------------------------------------------
# TIER 1 - always safe
# --------------------------------------------------------------------------
if ($Tier1) {
    Show-Header "TIER 1 - Build artefacts and backups (always safe)"

    Remove-Pattern -Pattern "__pycache__" -Directory `
        -Reason "Compiled Python. Rebuilt automatically."
    Remove-Pattern -Pattern "*.pyc" `
        -Reason "Compiled Python files."
    Remove-Target -Path ".pytest_cache" `
        -Reason "Test runner cache. Rebuilt on the next test run."
    Remove-Pattern -Pattern "*.bak" `
        -Reason "Backup copies made during editing. Git holds the history."
    Remove-Target -Path "itom_server.log" `
        -Reason "Old log file. Should never have been committed."
    Remove-Target -Path "scripts/Untitled-1.txt" `
        -Reason "Empty scratch file."
}

# --------------------------------------------------------------------------
# TIER 2 - development leftovers
# --------------------------------------------------------------------------
if ($Tier2) {
    Show-Header "TIER 2 - Development leftovers (read the list first)"

    Remove-Target -Path "scratch" `
        -Reason "One-off scripts used while building. Not imported anywhere."
    Remove-Target -Path "frontend/demo_previews" `
        -Reason "Duplicate of docs/demo_previews."
    Remove-Target -Path "frontend/archive/previews" `
        -Reason "Old HTML mockups, superseded by the real pages."
    Remove-Target -Path "logo_original_backup.png" `
        -Reason "Backup of the logo. The live one is logo.png."
    Remove-Target -Path "avatar.jpg" `
        -Reason "Sample avatar image, not referenced by the backend."
}

# --------------------------------------------------------------------------
# TIER 3 - your judgement
# --------------------------------------------------------------------------
if ($Tier3) {
    Show-Header "TIER 3 - Large files (decide for yourself)"

    Write-Host "  These are big but may still be wanted. Check before deleting." -ForegroundColor DarkYellow
    Write-Host ""

    Remove-Target -Path "docs/demo_previews" `
        -Reason "Design mockup images. Keep if the team still refers to them."
    Remove-Target -Path "docs/screenshots" `
        -Reason "Dashboard screenshots for documentation."
    Remove-Target -Path "exports" `
        -Reason "Old CSV exports. Regenerate from the API when needed."
    Remove-Target -Path "data/intune_ops_analytics.json" `
        -Reason "16.9 MB snapshot. Only used by offline test mode."
}

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
Show-Header "SUMMARY"
$totalMb = [math]::Round($script:totalBytes / 1MB, 2)
if ($Execute) {
    Write-Host "  Removed $script:totalItems items, freeing $totalMb MB" -ForegroundColor Green
} else {
    Write-Host "  Would remove $script:totalItems items, freeing $totalMb MB" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  To do it for real:" -ForegroundColor White
    Write-Host "    .\cleanup_backend.ps1 -Tier1 -Execute"
}

# --------------------------------------------------------------------------
# Protected - explain what we deliberately left alone
# --------------------------------------------------------------------------
Show-Header "NOT TOUCHED - these look unused but are not"

@(
    @{ f = "src/sync/payload_generator.py"; r = "src/sync/__init__.py imports it. Deleting breaks live sync." },
    @{ f = "src/sync/cmdb_generator.py";    r = "Same import chain. Also holds classify_device_role()." },
    @{ f = "src/sync/firestore_sync.py";    r = "Same import chain. Unused at runtime but imported at load." },
    @{ f = "data/*.json";                   r = "Used by offline test mode (FixtureSource)." },
    @{ f = "data/itom.db";                  r = "May be your live database. Never delete without checking." },
    @{ f = ".env";                          r = "Your credentials." },
    @{ f = ".agents/rules, .agents/skills"; r = "Project conventions, still referenced." },
    @{ f = "alembic/";                      r = "Database migrations." }
) | ForEach-Object {
    Write-Host ("  {0,-34} {1}" -f $_.f, $_.r) -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "IMPORTANT: src/sync/__init__.py imports all five modules in that folder." -ForegroundColor Yellow
Write-Host "Removing any one of them breaks 'from src.sync.graph_client import GraphClient'," -ForegroundColor Yellow
Write-Host "which is how live syncing works. Tidy that file first if you want them gone." -ForegroundColor Yellow
Write-Host ""

# --------------------------------------------------------------------------
# Next steps
# --------------------------------------------------------------------------
Show-Header "AFTER CLEANING"
Write-Host @"
  1. Check nothing broke:
       python -m pytest tests/ -q

  2. Stop these files coming back - add to .gitignore:
       __pycache__/
       *.pyc
       .pytest_cache/
       *.bak
       *.log

  3. Remove already-committed noise from git (keeps the files on disk):
       git rm -r --cached __pycache__ .pytest_cache
       git rm --cached itom_server.log
       git commit -m "Remove build artefacts from version control"
"@
Write-Host ""
