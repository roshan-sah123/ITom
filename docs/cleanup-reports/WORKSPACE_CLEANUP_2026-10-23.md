# Workspace save and cleanup — 23 October 2026

## Saved work

- The existing portal, SolarWinds groups, and Intune location research were
  preserved in local Git checkpoint `7070bff`.
- The inventory feature adds reporting locations, provisional review labels,
  a location filter, and complete filtered CSV exports.
- [Inventory guide](../INVENTORY_LOCATIONS.md),
  [workspace guide](../WORKSPACE_GUIDE.md), and
  [documentation index](../README.md) provide short entry points.

## Cleanup completed

- Removed 56 old isolated-test directories: 2,100 generated database/fixture
  files, reclaiming about 478.7 MiB.
- Removed 22 generated Python/pytest cache directories, including empty stray
  pytest cache folders at the repository root.
- Added `pytest-cache-files-*/` to `.gitignore` to prevent future clutter.
- Retained live data, backups, research exports and workbooks, operator scripts,
  existing audit documents, and browser evidence. Documentation links remain
  in place; the new index distinguishes current guides from historical evidence.

Every recursive removal was checked to stay inside this workspace. Old test
directories were removed only after confirming every file was a generated
`.db` or `.json` fixture under a `test_*` directory. No application source or
live database was removed.

## Verification

- Backend: 393 passed, 2 known expected failures; 41 subtests passed.
- Browser regressions: 85 passed.
- Focused desktop/mobile screenshot check: passed.
- JavaScript syntax, Python compilation, changed-file whitespace and new guide
  links: passed.
- Local portal restarted and ready; location filtering and review badges were
  checked against the live inventory.

Private recovery data: `backups/location-rules-2026-10-22.json`.
Detailed cleanup receipt: `outputs/workspace-cleanup-result-2026-10-23.json`.
Screenshots: `output/playwright/endpoint-inventory-locations/`.
These local artifacts are ignored by Git and excluded from the application image.
