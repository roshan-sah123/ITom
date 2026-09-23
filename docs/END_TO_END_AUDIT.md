# End-to-End Data Flow Audit

**Audit date:** 2026-09-20  
**Scope:** Active FastAPI + database + frontend SPA path only. No manual live
ingestion was triggered. Credentials, tokens, and connection strings were not
printed.

## Executive Summary — PARTIALLY VERIFIED

Stored SolarWinds and Intune data travels successfully from the active SQLite
database through repositories, FastAPI, and the frontend-served API surface.
The stored SolarWinds dataset reconciles at 1,583 devices across standardized
locations. The system accurately reports its data as stale and the latest
SolarWinds sync as failed rather than fabricating a healthy state.

Live source connectivity and a new end-to-end fetch were **not verified** in
this run. PostgreSQL is configured as the expected production database but was
not reachable; the running application used SQLite fallback.

## Architecture Verified — VERIFIED

`SolarWinds SWIS / Intune Graph → app.services.telemetry_sources → SyncService → SQLite (current local runtime) → repositories/services → FastAPI /api/v1 → frontend SPA`

- SolarWinds client: `src/sync/solarwinds_client.py::SolarWindsClient`.
- Intune client: `src/sync/graph_client.py::GraphClient`.
- Orchestration: `app/services/sync_service.py::SyncService`.
- Persistence: `configuration_items`, `ci_status_history`, `sync_runs`, and
  `sync_error_logs`.

## Source Connectivity — PARTIALLY VERIFIED

### SolarWinds

- **Code verified:** SWIS REST endpoint `/SolarWinds/InformationService/v3/Json/Query` is called by HTTP GET only.
- **Code verified:** every SWQL query is passed through
  `app.core.security.validate_swql_read_only`; it requires `SELECT` and blocks
  mutating keywords.
- **Live evidence:** the newest recorded SolarWinds run failed connecting to
  SWIS. The status endpoint reports `DEGRADED` with `SOLARWINDS` failed.
- **Not verified:** current live authentication and a successful live response.

The active node query requests NodeID, caption, IP, status, CPU, memory,
response-time fields, vendor, machine type, LastSync, uptime, description,
contact, City, and ITSM_Location. It does not fetch interfaces, volumes, alert
events, or topology.

### Intune

- **Code verified:** OAuth client-credentials flow targets Microsoft Entra token
  endpoint, then Graph `v1.0/deviceManagement/managedDevices`.
- **Code verified:** Graph pagination follows `@odata.nextLink`.
- **Stored-run evidence:** latest recorded Intune run succeeded with 28,815
  processed records in 117,106 ms; the current persisted total is 29,433.
- **Not verified:** a fresh token acquisition, Graph response, and current page
  count in this audit.

The active Graph selection includes ID, name, OS/version, compliance, UPN,
model, manufacturer, serial number, last sync and storage. It does not include
a usable location/site field, patch posture, lifecycle age, or security signals.

## Live Fetch — NOT VERIFIED

No controlled source fetch was initiated. This preserves the audit state and
avoids modifying the local database while the live SolarWinds route is known to
have recently failed. No fake result was substituted.

## Normalization — VERIFIED BY CODE INSPECTION

- SolarWinds: `NodeID → SW-NODE-{NodeID}`, City then ITSM_Location → location,
  numeric status → Orion status label, vendor → canonical bucket.
- Intune: Graph `id → external_id`, compliance state → normalized status/health,
  manufacturer → canonical vendor.
- Invalid/missing source IDs are rejected by normalizers; invalid metric values
  become null rather than aborting the full batch.
- The state fingerprint is SHA-256 of `status:health_tier`. Only a changed
  fingerprint produces a history record; unchanged records refresh
  `last_sync_time`.

Sanitized lineage example (shape only):

`{NodeID, Caption, Status, City} → {external_id: SW-NODE-…, name, status, location} → configuration_items(source_system, source_id, …) → /solarwinds/nodes response`

## Location Reconciliation — VERIFIED

Read-only local database and API checks produced:

| Measure | Result |
| --- | ---: |
| SolarWinds CIs in database | 1,583 |
| Raw distinct location values | 72 |
| Case-folded nonblank location groups | 61 |
| Standardized API location groups, including Unassigned | 62 |
| Blank/null locations | 4 |
| Case-only spelling groups merged | 10 |
| Sum of `/solarwinds/sites` device totals | 1,583 |
| Duplicate `(source_system, source_id)` pairs | 0 |

The reconciliation equation holds: **1,583 source-backed stored SolarWinds
devices = 1,583 standardized-location device total**. Four blank values are
intentionally represented as `Unassigned`; no device was dropped.

## Database Persistence — PARTIALLY VERIFIED

- **Verified by execution:** active database is SQLite (`data/itom.db`), with
  31,016 CIs: 1,583 SolarWinds and 29,433 Intune; 95,116 history rows and 271
  sync runs.
- **Verified by query:** zero duplicate source-system/source-ID pairs.
- **Verified by code:** CI uniqueness is enforced by
  `uq_ci_source_system_source_id`; common filter indexes exist on source,
  health, status, name, vendor, and related fields.
- **Not verified:** PostgreSQL connectivity, PostgreSQL advisory-lock behavior,
  and Alembic revision. `alembic/versions/0001_initial_schema.py` exists, but
  SQLite has no `alembic_version` table.

**Fix applied:** `app/core/database.py` now permits SQLite fallback only outside
production. A production process fails at startup when configured PostgreSQL is
unreachable. The current audit runtime remains SQLite because it is development.

## Sync Pipeline — PARTIALLY VERIFIED

- Scheduler configuration: APScheduler interval of 600 seconds; `max_instances=1`,
  coalescing enabled, 60-second misfire grace.
- Audit runtime: scheduler disabled with `SCHEDULER_ENABLED=false`; therefore
  actual ten-minute execution was not verified.
- Sync persists a per-source SyncRun, counters, completion time, and error log.
- Current status: `DEGRADED`; latest SolarWinds failed, latest Intune succeeded,
  and both freshness timestamps are stale.
- PostgreSQL uses transaction advisory lock; SQLite uses process-local fallback.
  Cross-process overlap protection is therefore **not verified** on SQLite.

## Analytics Validation — PARTIALLY VERIFIED

| Metric | Evidence | Result |
| --- | --- | --- |
| SolarWinds total | summary API / stored CIs | 1,583 / 1,583 |
| Health tiers | API | 1,417 + 80 + 86 = 1,583 |
| Status totals | API | 1,431 + 21 + 61 + 24 + 46 = 1,583 |
| Location totals | sites API | 1,583 |
| CMDB total | summary API | 31,016 = 1,583 + 29,433 |
| Freshness | system API | STALE, not presented as fresh |

Intune compliance and storage metrics are calculated from stored data but were
not reconciled to a fresh Graph response. Unsupported source fields remain
unsupported: alerts, interfaces, volumes, topology, patch coverage, lifecycle,
and security analytics.

## API Validation — VERIFIED

Executed against `http://127.0.0.1:8001`:

| Route | HTTP | Evidence |
| --- | ---: | --- |
| `/healthz` | 200 | service starts |
| `/ready` | 200 | SQLite database connected |
| `/api/v1/solarwinds/summary` | 200 | 1,583 source-backed total |
| `/api/v1/intune/summary` | 200 | 29,433 persisted devices |
| `/api/v1/cmdb/summary` | 200 | 31,016 total CIs |
| `/api/v1/system/freshness` | 200 | explicit STALE state |
| `/api/v1/sync/status` | 200 | explicit DEGRADED state |
| `/api/v1/sync/runs` | 200 | run/error history available |
| `/api/v1/solarwinds/sites` | 200 | 62 source-derived groups |
| `/solarwinds/nodes?location=BANGALORE&page_size=10` | 200 | 131 matching devices |
| `/solarwinds/network-devices?location=BANGALORE&page_size=10` | 200 | 45 matching devices |

List routes validate page size against 10/25/50/100. Invalid size returns 422.

## Frontend Validation — PARTIALLY VERIFIED

- Frontend static entrypoint at `http://127.0.0.1:8080/` returned 200.
- The frontend consumes source-backed SolarWinds, Intune, CMDB, freshness, and
  sync APIs through `frontend/js/api.js` and module components.
- Location selection is backed by `/solarwinds/sites`; matching API counts were
  verified above.
- **Not verified:** browser console, DOM rendering, loading/error/empty visual
  states, or exact on-screen pagination because a browser automation run was
  not performed in this audit.

## Failure / Security Verification — PARTIALLY VERIFIED

- Recorded SWIS failure is visible in SyncRun and SyncErrorLog; it was not
  converted to success.
- Freshness correctly remains stale after failure.
- SolarWinds write methods and non-SELECT SWQL are blocked in active client
  code.
- Secrets were not displayed. Environment-file loading exists; committed-secret
  status and production auth/authz policy need a dedicated security review.

## Issues Found

1. **Required:** production database fallback can silently change PostgreSQL to
   SQLite when PostgreSQL is unavailable.
2. **Required:** current source data is stale and the latest SolarWinds fetch
   failed; presentation must show degraded/stale state.
3. **Required:** the scheduler’s runtime behavior is unproven in this audit.
4. **Required:** site trend endpoint exists but current site responses contain
   empty `trend_24h`; it must remain unavailable rather than be visualized as
   a real trend.
5. **Optional:** `POST /sync/trigger` is a local ingestion action, not a
   SolarWinds write. Its access control should be reviewed before deployment.

## Fixes Applied

- Removed fabricated CMDB fallback inventory and fake offline metrics.
- Removed unused frontend components and legacy frontend directory.
- Unified SolarWinds read-only query guard.
- Removed duplicate health-router registration and unconsumed frontend manual
  sync API helper.
- Disabled automatic schema creation and SQLite fallback in production; Alembic
  migration is now the required production schema path.

## Remaining Risks / Production Readiness Gaps

- PostgreSQL has not been verified as the active database.
- No current successful SolarWinds live sync has been executed.
- Intune fresh-token and fresh-paging behavior has not been executed.
- SQLite fallback and automatic table creation must not be relied upon in a
  production VM deployment.
- Authentication/authorization for externally reachable API endpoints requires
  a deployment security decision.

## Final Data Flow — PARTIALLY VERIFIED

`Stored source-derived CIs → SQLite → repository/service → API → frontend HTTP entrypoint` is verified.

`Live SolarWinds / Intune → fetch → normalize → persist` is verified by code
and historical sync records, but **not verified by a fresh live execution in
this audit**. The correct overall verdict is **PARTIAL PASS**, not production
ready.
