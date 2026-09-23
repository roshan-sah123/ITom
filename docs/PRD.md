# IT Operations Intelligence Platform — Product Requirements

## 1. Product Overview

The IT Operations Intelligence Platform is an internal portal for finding and
inspecting operational device data from SolarWinds and Microsoft Intune. It
gives operations teams one source-backed view of infrastructure nodes, managed
endpoints, and CMDB-style inventory derived from those sources.

It is not an independent CMDB or a real-time monitoring replacement. The
current system polls sources and stores the resulting inventory locally for
search, filtering, analytics, and presentation.

## 2. Goals

- Provide trustworthy, source-backed device inventory and status information.
- Let users filter SolarWinds devices by their source location.
- Present only metrics that can be calculated from stored source data.
- Make data age and last sync outcome visible.
- Keep SolarWinds integration strictly read-only.

## 3. Users

- IT operations and infrastructure teams investigating node health.
- Workplace engineering teams reviewing Intune-managed device compliance.
- Service-management teams using the derived asset inventory.
- Leadership viewing a concise operational POC.

## 4. Current Data Sources

| Source | Current use | Verified fields used |
| --- | --- | --- |
| SolarWinds Orion SWIS | Infrastructure inventory | Node ID, caption, IP, status, CPU, memory, response time, vendor, machine type, custom-property City and ITSM location |
| Microsoft Intune through Microsoft Graph | Managed endpoint inventory | Device ID/name, OS/version, compliance, user principal name, model, manufacturer, serial number, last sync, total/free storage |
| Application database | Derived CMDB and analytics | Normalized CIs, status history, sync runs, sync errors |

## 5. Core Business Flow

`SolarWinds SELECT SWQL / Microsoft Graph GET → source adapter → normalized CI → configuration_items → repository/service calculations → FastAPI → frontend SPA`

Each source sync creates its own SyncRun record. The CI identity is unique by
`source_system + source_id`. Status/health transitions create CI history;
unchanged operational state only refreshes the last-sync timestamp.

## 6. Functional Requirements

- Paginated device and CI inventory, search, sorting, and source filtering.
- SolarWinds infrastructure inventory and network-device classification based
  on source vendor and machine type.
- Intune managed-device inventory, compliance and OS/vendor summaries.
- CMDB reports derived only from persisted SolarWinds and Intune inventory.
- Source-backed SolarWinds location catalog and location filtering.
- Device detail/history endpoints and sync run/error visibility.
- Data freshness and sync-status display.
- Automation shown only as a future roadmap placeholder.

## 7. Location Requirements

SolarWinds custom-property location is authoritative. The system trims and
case-folds it for matching, chooses the most frequent source spelling as the
display name, and represents blank values as `Unassigned`. A device must occur
in one standardized location group only. Intune Graph managedDevices currently
does not supply a site/location field in the active fetch, so Intune locations
are unsupported rather than inferred.

The current location count must always be calculated from the stored source
data, not hardcoded in the UI or documentation.

## 8. Non-Functional Requirements

- **Data integrity:** no fabricated production metrics or successful syncs.
- **Security:** secrets stay in environment configuration; SolarWinds accepts
  GET plus SELECT-only SWQL.
- **Reliability:** failures are recorded per source and freshness does not
  advance after a failed extraction.
- **Observability:** sync run/error history, readiness, freshness and status
  endpoints make state visible.
- **Performance:** list APIs require bounded pagination; indexed CI fields
  support common filters.
- **Maintainability:** one active path: FastAPI + database + frontend SPA.

## 9. Data Requirements and Lineage

SolarWinds node records require a node identifier and use `City`, then
`ITSM_Location`, for location. Intune records require Graph `id`; their
compliance state maps to normalized status and health tier. All normalized rows
retain source system, source ID, sync timestamps, and source-specific raw
attributes needed for traceability.

## 10. API Requirements

Important capabilities include:

- `GET /api/v1/solarwinds/summary`, `/nodes`, `/network-devices`, `/sites`
- `GET /api/v1/intune/summary`, `/devices`
- `GET /api/v1/cmdb/summary`, `/cis`, `/cis/{id}`, `/cis/{id}/history`
- `GET /api/v1/system/freshness`
- `GET /api/v1/sync/status`, `/runs`, `/runs/latest`

List APIs must support validated pagination and must return explicit empty or
unavailable states rather than synthetic values.

## 11. Sync Requirements

The scheduler is configured for a 600-second cadence when enabled. It prevents
overlap with a PostgreSQL transaction advisory lock, with an in-process fallback
for SQLite. Each source has its own result, counters, duration, completion time,
and error log. A sync failure must remain visible as failed/degraded and must
not make stale data appear fresh.

## 12. Database Requirements

Production requires PostgreSQL with Alembic migration `0001_initial_schema`.
SQLite fallback is permitted only outside production. A production process now
fails at startup when configured PostgreSQL is unreachable, preventing an
accidental database switch. Key tables are `configuration_items`,
`ci_status_history`, `sync_runs`, `sync_error_logs`, and `ci_relationships`.

## 13. Unsupported / Future Features

The current source queries do not support topology relationships, interface
analytics, volume/capacity analytics, advanced alert analytics, patch coverage,
device lifecycle, or security analytics. These must be displayed as unavailable
or future scope until source fields and calculations are added.

## 14. Acceptance Criteria

- Source-backed SolarWinds devices reconcile through DB, API, and location UI.
- Location selection returns only the matching source-device set.
- API totals reconcile with stored CI totals.
- No fake KPI fallback is displayed when a source/database is unavailable.
- SolarWinds query validation blocks non-GET and non-SELECT activity.
- Sync outcomes are recorded separately for SolarWinds and Intune.
- The active application runs exclusively through FastAPI, database, and SPA.

## 15. Known Limitations

- The active local audit database is SQLite, not PostgreSQL.
- Latest audited source data is stale; a current successful SolarWinds live
  fetch was not demonstrated in this audit.
- The scheduler was deliberately disabled during audit and therefore the
  configured cadence was not runtime-verified.
- Intune location filtering cannot be source-backed with the current Graph
  field selection.

## 16. Future Scope

Add only after source availability and data lineage are established: topology,
interfaces, volumes/capacity, alerts, patch and lifecycle analytics, and a
production PostgreSQL deployment with migrations and service supervision.
