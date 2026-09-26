# ITOM Portal Architecture

The ITOM portal collects Microsoft Intune and SolarWinds telemetry, stores a common inventory, and serves dashboards through a database-backed REST API. This guide follows the current implementation rather than historical snapshots or prototype pages.

## Architecture diagram

```mermaid
flowchart TD
    I[Microsoft Intune via Graph API] --> T[Source adapters: normalize device data]
    S[SolarWinds Orion via SWIS API] --> T
    W[Background scheduler: every 10 minutes] --> T
    T --> SY[Sync service: validate and update inventory]
    SY --> DB[(Database: inventory, history, sync logs)]
    DB --> R[Repositories: database queries]
    R --> B[Services: application logic]
    B --> A[FastAPI: REST endpoints]
    A --> F[Browser: dashboards, charts, tables]
```

There are two independent flows: scheduled collection updates the database, and browser requests read its latest stored snapshot. Opening a dashboard does not trigger a new source extraction. The default collection interval is 600 seconds, configurable through `SYNC_INTERVAL_SECONDS`.

## Frontend

The deployed frontend is `frontend/`, served directly without a bundler. It uses HTML, CSS, JavaScript ES modules, and Chart.js.

| Entry point | Responsibility |
| --- | --- |
| `frontend/index.html` | Workspace containers and page structure |
| `frontend/js/app.js` | Startup and navigation |
| `frontend/js/components/` | Overview, infrastructure, endpoints, CMDB, and sync views |
| `frontend/js/api.js` | Shared FastAPI client |
| `frontend/css/style.css` | Current portal styling |

The API client uses `/api/v1` behind a reverse proxy, or `http://127.0.0.1:8000/api/v1` for the local UI on ports 8080/8081. `window.ITOM_API_BASE` can override this selection. Failed requests propagate errors instead of silently substituting static JSON.

## Backend request flow

```mermaid
sequenceDiagram
    participant UI as Browser
    participant API as FastAPI endpoint
    participant Service as CIService
    participant Repo as CIRepository
    participant DB as Database
    UI->>API: GET /api/v1/cmdb/cis?page=1&page_size=25
    API->>API: Validate query parameters
    API->>Service: get_cis_paginated(...)
    Service->>Repo: Fetch matching records and count
    Repo->>DB: SQL query
    DB-->>Repo: Rows and total
    Repo-->>Service: Query result
    Service-->>API: JSON-safe items and pagination
    API-->>UI: JSON response
```

| Layer | Location | Responsibility |
| --- | --- | --- |
| Application | `app/main.py` | Lifespan, scheduler startup, middleware, route registration |
| Routes | `app/api/v1/endpoints/` | HTTP input validation and endpoint routing |
| Services | `app/services/` | Application logic, ingestion, response coordination |
| Repositories | `app/repositories/` | SQLAlchemy database queries and aggregates |
| Models | `app/models/` | Persistent table definitions |
| Schemas | `app/schemas/` | Response structures and JSON serialization |
| Core | `app/core/` | Configuration, database sessions, middleware, security helpers |

Summary values are computed from the database. An unavailable dataset can return HTTP 503. Inventory routes reject write methods; the separate sync trigger can start ingestion into the portal's own database.

## Collection and reconciliation

1. `app/workers/scheduler.py` invokes `SyncService` on the configured interval.
2. Source adapters in `app/services/telemetry_sources.py` call the clients in `src/sync/graph_client.py` and `src/sync/solarwinds_client.py`.
3. The adapters normalize different source fields into common configuration-item dictionaries and validate snapshot identities.
4. `app/services/sync_service.py` inserts or updates current inventory. PostgreSQL uses a transaction-scoped advisory lock to prevent overlapping sync execution; the non-PostgreSQL fallback lock is process-local.
5. A SHA-256 fingerprint of status and health tier controls transition-history writes. CPU or RAM changes alone do not create a new status-history row.
6. A validated complete source snapshot can retire missing assets by marking them inactive. Failed or incomplete extraction must not authorize retirement.
7. Each source has its own sync audit record, so one source succeeding cannot make another source appear fresh.

The normal scheduler fetches live source data directly. `FixtureSource` is an explicit offline/test adapter, not the default ingestion path or an automatic outage fallback.

## Database

CMDB means Configuration Management Database. A configuration item (CI) is a tracked asset such as a laptop, server, or switch.

| Table | Purpose |
| --- | --- |
| `configuration_items` | Current inventory, source identity, status, health, attributes, and retirement state |
| `ci_relationships` | Relationships between assets |
| `ci_status_history` | Status/health transitions and reconciliation events |
| `sync_runs` | Per-source outcomes, timestamps, duration, and record counts |
| `sync_error_logs` | Sync failure details |

PostgreSQL 16 is the production database. SQLAlchemy provides asynchronous sessions and queries. Alembic migrations live in `alembic/`; production schema changes must be applied before startup. Explicit development/local/demo/test modes support SQLite, including local PostgreSQL-unavailable fallback. Non-production startup can create missing tables.

History is change-oriented; it is not a complete sample of every performance measurement.

## Deployment

| Mode | Frontend | Backend | Persistence |
| --- | --- | --- | --- |
| Docker Compose | NGINX serves `frontend/`, normally exposed on port 8080 | Internal FastAPI port 8000; NGINX forwards `/api/` | PostgreSQL 16 |
| Local supervisor | Python static server serves `frontend/` on port 8080 | Uvicorn on port 8000 | SQLite supported in local mode |

See `docker-compose.yml`, `nginx.conf`, and `scripts/local_itom_supervisor.py` for the actual wiring. Credentials and source connectivity are required for live extraction; the diagram does not imply that a running API has successfully synchronized.

## Freshness and reliability

`/api/v1/system/freshness` reports source data freshness. Middleware also adds freshness headers. A database may contain records while a source is unreachable, so availability and freshness must be shown separately. Failed extraction does not count as a successful refresh.

## Compatibility code

Some root-level frontend assets, standalone pages, older domain modules, and `scripts/start_server.py` remain referenced by compatibility launchers or tests. Their presence does not make them the main portal entry point. New portal work should begin in `frontend/index.html` and `frontend/js/app.js`.

Unreferenced HTML prototypes under `frontend/archive/previews/` and the standalone `frontend/preview_infra_with_pie_and_sites.html` were removed. Git history preserves those designs. See [cleanup report](cleanup-reports/CODE_CLEANUP_2026-09-23.md).

## Suggested reading order

Follow one feature: `frontend/js/components/endpoints.js` → `frontend/js/api.js` → `app/api/v1/endpoints/intune.py` → `app/services/ci_service.py` → `app/repositories/ci_repository.py`. Then read `app/services/telemetry_sources.py` and `app/services/sync_service.py` to learn how those records arrive.
