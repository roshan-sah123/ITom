# ITOM Project Context

This file preserves the working context from the implementation conversation. It is a handoff reference for future chats and engineers.

## Product

Internal IT Operations Intelligence Platform combining:

- SolarWinds infrastructure telemetry
- Microsoft Intune managed-device intelligence
- CMDB-style inventory derived from persisted source records

The supported application path is:

`SolarWinds / Intune → live fetch → validation → normalization → database → analytics → FastAPI → frontend SPA`

SolarWinds access is strictly read-only. SolarWinds queries use HTTP GET and SELECT-only SWQL.

## Main modules

1. Infrastructure Analytics
2. Digital Workplace Experience
3. CMDB Reports
4. Automation (roadmap placeholder only)

## Current verified live state

The local SQLite runtime has been tested end to end:

- SolarWinds fetched and normalized 1,644 records.
- Intune fetched and normalized 29,112 records across 292 Graph pages.
- Active database totals match the live snapshots.
- Duplicate source identities: 0.
- Location groups: 69.
- SolarWinds location totals reconcile to 1,644 devices.
- Freshness and sync status APIs reported healthy/fresh after the test.
- One isolated scheduled execution passed at the configured 600-second cadence.
- Focused backend/frontend tests passed.

Production PostgreSQL deployment still requires separate migration, connection, and readiness verification on the company VM.

## Frontend decisions

- Homepage has four module cards with distinct semantic accents.
- Homepage uses the Coforge logo and dark theme.
- Unsupported “Unavailable” network/lifecycle panels were removed.
- Inspect/Actions controls were removed from inventory tables.
- Tables use consistent spacing, filters, pagination, and empty states.
- Location Health replaces the old Global Campus Facilities concept.
- Location Health is source-backed and shows total, Up, Down, Warning, Critical, and Other/Unmanaged counts.
- Locations with Down/Critical devices are prioritized.
- Search, issue-only filtering, pagination, and status-count drill-down are supported.
- Clicking a location/status count opens the matching SolarWinds device list.

## Data boundaries

Do not fabricate metrics, trends, topology, patch coverage, lifecycle scores, security scores, or inferred Intune locations. If the required source field/API is unavailable, hide the feature or mark it as future/unsupported.

## Important files

- `app/services/telemetry_sources.py` — live source adapters and normalization
- `app/services/sync_service.py` — validation, persistence, reconciliation, and sync audit
- `src/sync/solarwinds_client.py` — read-only SWIS client
- `src/sync/graph_client.py` — Microsoft Graph pagination client
- `app/repositories/ci_repository.py` — inventory queries and location aggregation
- `app/repositories/summary_repository.py` — source-backed analytics
- `frontend-revamp/src/App.tsx` — current React workspaces and Location Health UI
- `frontend-revamp/src/Inventory.tsx` — source-backed inventories and device details
- `frontend-revamp/src/api.ts`, `src/data.ts` — API integration and view models
- `frontend-revamp/src/index.css` — current Figma design
- `frontend/` — generated static deployment output
- `not-in-use/legacy-frontend/` — ignored local archive, never used for current UI work

## API groups

- `/api/v1/solarwinds/summary`
- `/api/v1/solarwinds/nodes`
- `/api/v1/solarwinds/network-devices`
- `/api/v1/solarwinds/sites`
- `/api/v1/intune/summary`
- `/api/v1/intune/devices`
- `/api/v1/cmdb/summary`
- `/api/v1/cmdb/cis`
- `/api/v1/system/freshness`
- `/api/v1/sync/status`
- `/api/v1/sync/runs`
- `/healthz`
- `/ready`

## Local URLs

- Frontend: `http://localhost:8080/`
- Backend: `http://localhost:8001/`

## Git connection

- Repository: `https://github.com/roshan-sah123/ITom.git`
- Local folder: `C:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur`
- Existing branch: `fix/step1-live-summaries`

Use a feature branch for each new task, review selected files, commit, push, and open a pull request. Preserve unrelated work in the dirty working tree.
