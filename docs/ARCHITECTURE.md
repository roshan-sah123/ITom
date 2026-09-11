# ITOM Operations Analytics & Telemetry Platform — System Architecture

> **Canonical system-of-record**: FastAPI + PostgreSQL 16 (`app/`). The legacy Python
> `http.server` + flat-JSON stack described in earlier revisions of this document has
> been superseded and is documented in §6 (Legacy/Alternate Path) for operational
> awareness only — it is not the architecture new features should be built against.

## 1. Executive Summary & Architecture Overview

The IT Operations Management (ITOM) Operations Analytics platform provides centralized, real-time observability across enterprise endpoints, server infrastructure, network devices, and Configuration Management Database (CMDB) Configuration Items (CIs).

The platform adheres to **Clean Layered Architecture**, **Industry-Standard Monorepo Structure**, and **Zero-Build Frontend** principles:
- **Presentation Layer (`frontend/`)**: Pure vanilla HTML5/CSS3/ES6+ served directly from `frontend/` — no bundlers, no Node.js, no transpilation. Domain logic is split into modular scripts (`frontend/js/shared.js`, `frontend/js/intune.js`, `frontend/js/solarwinds.js`, `frontend/js/cmdb.js`) consuming the live REST API.
- **API & Persistence Layer (`backend/`)**: Asynchronous FastAPI application (`backend/app/api/v1`) exposing paginated, filterable REST endpoints backed by SQLAlchemy 2.0 async repositories, with authoritative freshness headers on every response.
- **Persistence Tier**: PostgreSQL 16 relational storage — current CI state (`configuration_items`), topology (`ci_relationships`), append-only time-series history (`ci_status_history`), and sync execution audit trail (`sync_runs`, `sync_error_logs`). Schema evolution is tracked exclusively via Alembic migrations (`backend/alembic`).
- **Ingestion Layer**: A resilient APScheduler background worker (`backend/app/workers/scheduler.py`) executes a 10-minute delta-sync cycle guarded by a PostgreSQL advisory lock, ensuring multi-worker safety across ASGI workers.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            1. PRESENTATION TIER                             │
│                                                                             │
│   ┌───────────────────────────────┐     ┌───────────────────────────────┐   │
│   │     ITOM Portal Launcher      │     │    OPS Analytics Dashboard    │   │
│   │    (index.html / app.js)      │────▶│ (ops_analytics.html + js/*)  │   │
│   │  • System-Wide Search (/)     │     │  • Tab Router (js/shared.js)  │   │
│   │  • Domain Drilldown Modal     │     │  • Domain Modules (intune.js, │   │
│   │  • Deep Link Tab Routing      │     │    solarwinds.js, cmdb.js)    │   │
│   └──────────────┬────────────────┘     └──────────────┬────────────────┘   │
│                  └──────────────────┬──────────────────┘                    │
│                                     ▼                                       │
│          Fetch /api/v1/* (paginated JSON, static-file fallback only)        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP GET (proxied by NGINX /api/ ⇒ :8000/api/)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   2. FASTAPI ASYNC REST API TIER (app/)                     │
│                                                                             │
│   /api/v1/cmdb/{summary,cis,cis/{id},cis/{id}/history,relationships}        │
│   /api/v1/intune/{summary,devices}     /api/v1/solarwinds/{summary,nodes}   │
│   /api/v1/sync/{runs,runs/latest,runs/{id}}          /healthz  /ready       │
│                                                                             │
│   Middleware: FreshnessHeadersMiddleware (X-Last-Synchronized-At,          │
│   X-Data-Age-Seconds, X-Sync-Status) + strict-405 read-only guard.          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ SQLAlchemy 2.0 async (asyncpg)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    3. POSTGRESQL 16 PERSISTENCE TIER                        │
│  configuration_items │ ci_relationships │ ci_status_history │ sync_runs      │
└──────────────────────────────────────▲──────────────────────────────────────┘
                                       │ upsert + SHA-256 delta detection
                                       │ (app/services/sync_service.py)
┌──────────────────────────────────────┴──────────────────────────────────────┐
│              4. BACKGROUND INGESTION (app/workers/scheduler.py)             │
│   APScheduler, 10-min interval, pg_try_advisory_lock(1048576) multi-worker   │
│   guard. Reads staged JSON written by the live extraction clients below.    │
└──────────────────────────────────────▲──────────────────────────────────────┘
                                       │ data/intune_ops_analytics.json
                                       │ data/solarwinds_nodes.json
┌──────────────────────────────────────┴──────────────────────────────────────┐
│         5. LIVE EXTRACTION (GitHub Actions cron → scripts/run_sync.py)      │
│   src/sync/graph_client.py (MS Graph OAuth2)  │ src/sync/solarwinds_client   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Data flow in one sentence**: live telemetry is pulled from Microsoft Graph / SolarWinds SWIS by scheduled GitHub Actions into staged JSON files, which the in-process APScheduler worker deltas into PostgreSQL every 10 minutes; the FastAPI REST API reads exclusively from PostgreSQL; the frontend reads exclusively from the FastAPI REST API (static JSON is a fallback-only safety net if the API is unreachable).


## 2. Multi-Domain Telemetry Scope & Metrics

The platform reconciles metrics across four authoritative operational domains:

### 2.1 Microsoft Intune Managed Endpoints (25,987 Devices)
* **Total Managed Endpoints**: 25,987
* **Operating System Breakdown**:
  * Windows: 25,334 (97.49%)
  * macOS: 602 (2.32%)
  * Linux: 24 (0.09%)
  * Unspecified: 24 (0.09%)
  * iOS: 2 (0.01%)
  * Android: 1 (0.004%)
* **Compliance Policy Breakdown**:
  * Compliant: 21,589 (83.08%)
  * Non-Compliant: 3,422 (13.17%)
  * ConfigManager Managed: 935 (3.60%)
  * Unknown: 31 (0.12%)
  * In Grace Period: 10 (0.04%)
* **Hardware OEM Normalization**:
  * Dell: 15,716 (60.48%)
  * HP: 8,610 (33.13%)
  * Lenovo: 959 (3.69%)
  * Apple: 604 (2.32%)
  * Other: 98 (0.38%)
* **Fleet Storage Utilization**:
  * Average Storage Used: **37.4%** across 25,937 valid storage-reporting devices (~9,761.55 TB total fleet capacity).

### 2.2 SolarWinds Orion Server Infrastructure (1,548 Nodes)
* **Total Monitored Nodes**: 1,548
* **Health Tiers (Multi-Metric Evaluation)**:
  * **High Health** (`Up` AND `CPU < 75%` AND `RAM < 80%`): 1,357 nodes (87.66%)
  * **Medium Health** (`Warning` OR `CPU/RAM 75–90%`): 150 nodes (9.69%)
  * **Low/Critical Health** (`Down`/`Critical` OR `CPU/RAM > 90%`): 41 nodes (2.65%)
* **Node Operational Status**:
  * Up: 1,370 (88.50%)
  * Warning: 25 (1.61%)
  * Critical: 35 (2.26%)
  * Down: 6 (0.39%)
  * Unmanaged / Unknown: 112 (7.23%)
* **Fleet Performance Invariants**:
  * Average CPU Load: **16.2%**
  * Average Memory Utilization: **22.6%**
  * Average Network Latency: **42.5 ms**

### 2.3 CMDB Network Configuration Items (1,548 CIs)
* **Total Configuration Items**: 1,548
* **CI Type Distribution**:
  * Access Switches: 612
  * Distribution Switches: 340
  * Core Switches: 210
  * Firewalls: 200
  * Routers: 186
* **Relational Integrity**: 100% mapped to monitored nodes with **0** orphaned records.

### 2.4 Executive Fleet Digest (28,955 Monitored Assets)
* **Total Monitored Fleet**: 28,955 assets (25,987 Intune + 1,548 SolarWinds + 1,420 Network Core).
* **Consolidated Operational Health**: 92.4% fleet health index.

---

## 3. Tier Breakdown & Detailed Components

### 3.1 Presentation Tier (repository root — single canonical source, zero-build)
1. **Zero-Build Architecture**: No bundlers, compilation, or npm install commands. Pure HTML5, CSS3, and modern ES6+ JavaScript, served as-is by NGINX/any static file server.
2. **Shared Modular Helpers (`js/`)**:
   - `constants.js`: Design tokens (`THEME`), chart palettes (`CHART_PALETTES`), invariant numbers (`INVARIANTS`), tab definitions, and REST `ENDPOINTS` (including the live `/api/v1/*` routes).
   - `utils.js`: DOM XSS sanitizer (`escapeHtml()`), input debouncer (`debounce()`), and localized formatters.
   - `services.js`: Generic `fetchJson()` HTTP wrapper and the RFC 4180 CSV export engine (`exportToCsv()`).
   - `shared.js`: Domain-agnostic tab router (`switchTab`, `initTabRouter`, `updateHeaderStat`), a `registerDomain()` registry so new domains never require editing the router, the unified pagination controller, Chart.js lifecycle guard (`destroyChartSafe()`), the bounded-concurrency `fetchAllPages()` REST paginator, and the 10-minute auto-refresh engine.
3. **Domain Modules** (`js/intune.js`, `js/solarwinds.js`, `js/cmdb.js`): each owns its own state, KPI/Chart.js rendering, search/pagination, and CSV export, and registers itself with `shared.js` on load. Every module's primary data source is the live FastAPI REST API; a static JSON snapshot fetch is attempted only if the API call fails, purely as an availability fallback.
4. **Enterprise Launcher (`index.html` & `app.js`)**: universal search (`/` to focus, `Esc` to clear), domain drilldown modal, and deep-linking bridge to dashboard tabs.
5. **Operations Analytics Dashboard (`ops_analytics.html` + `js/ops_analytics.js` bootstrap)**: loads `constants.js` → `utils.js` → `services.js` → `shared.js` → the three domain modules → the bootstrap, which wires the router, search inputs, CSV export buttons, and the initial `loadAllTelemetry()` call.

### 3.2 API Tier (`app/api/v1`, `app/services`, `app/repositories`)
1. **Clean layering**: `api/v1/endpoints` (routing/validation) → `services` (business logic, e.g. `CIService`) → `repositories` (`CIRepository`, `SyncRepository` — SQL query construction) → `models` (SQLAlchemy 2.0 declarative tables).
2. **Endpoints**: paginated `cmdb/cis`, `intune/devices`, `solarwinds/nodes` (search, filter, sort, `page`/`page_size` in `{10,25,50,100}`); DB-aggregated `cmdb/summary`, `intune/summary`, `solarwinds/summary` (chart-ready breakdowns, computed live from `configuration_items`/`ci_status_history` with a hardcoded-baseline fallback only when the table is empty); `sync/runs*` execution audit trail; `/healthz`, `/ready`.
3. **Freshness contract**: `FreshnessHeadersMiddleware` stamps every response with `X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status` and rejects `POST`/`PUT`/`DELETE`/`PATCH` on telemetry routes with `405`.

### 3.3 Ingestion Tier (`app/workers/scheduler.py`, `app/services/sync_service.py`)
1. **APScheduler** runs `run_periodic_telemetry_sync()` every `SYNC_INTERVAL_SECONDS` (600s), guarded by `pg_try_advisory_lock(1048576)` so multiple ASGI workers never double-sync.
2. **`SyncService.execute_sync_with_lock()`** reads the staged JSON files below, computes a SHA-256 state fingerprint per record, and only writes to `ci_status_history` when the fingerprint changes (delta detection).
3. **Staged JSON inputs** (`data/intune_ops_analytics.json`, `data/solarwinds_nodes.json`) are produced by the live extraction clients in §3.4 — they are an ETL staging format, not a serving format; nothing downstream of PostgreSQL reads them directly except the frontend's fallback path.

### 3.4 Live Extraction Tier (`src/sync/`, `scripts/`, `.github/workflows/`)
1. **`src/sync/graph_client.py`**: Azure AD / Entra ID OAuth 2.0 Client Credentials Grant, bearer token caching, jittered exponential backoff, paginated OData streaming for 25,987+ devices.
2. **`src/sync/solarwinds_client.py`**: SolarWinds Information Service (SWIS) v3 REST client executing SWQL against `Orion.Nodes`.
3. **`scripts/run_sync.py`**: CLI orchestrator invoked by `.github/workflows/telemetry-sync-cron.yml` (every 30 min) and `intune_telemetry_sync.yml` (weekly), writing the staged JSON files consumed by §3.3.

### 3.5 Persistence Tier (PostgreSQL 16)
- `configuration_items` — authoritative current state (indexed on `source_system`, `ci_type`, `vendor`, `health_tier`, `status`, with GIN trigram indexes for free-text search).
- `ci_relationships` — topology graph edges.
- `ci_status_history` — append-only time-series (status/health/CPU/RAM/storage/latency transitions).
- `sync_runs` / `sync_error_logs` — execution telemetry and diagnostic audit trail.
- Schema changes are tracked exclusively via **Alembic** migrations (`alembic upgrade head`); manual DDL is prohibited.

---

## 4. Mathematical Invariants & Verification Gates

The pipeline enforces hard mathematical invariant checks. Any discrepancy raises an `AssertionError` and terminates the sync pipeline:

| Invariant Gate | Verified Constraint | Mathematical Formula | Authoritative Value |
| :--- | :--- | :--- | :--- |
| **Intune Population** | $\sum \text{OS Breakdown} = \text{Total Devices}$ | $25334 + 602 + 24 + 2 + 1 + 24$ | **25,987** |
| **Intune Compliance** | $\sum \text{Compliance States} = \text{Total Devices}$ | $21589 + 3422 + 935 + 31 + 10$ | **25,987** |
| **Intune OEM Closure** | $\sum \text{Manufacturers} = \text{Total Devices}$ | $15716 + 8610 + 959 + 604 + 98$ | **25,987** |
| **Intune Compliance Rate**| $\text{Rate} = (\text{Compliant} / \text{Total}) \times 100$ | $(21589 / 25987) \times 100$ | **83.08%** |
| **Intune Storage Ratio** | $\text{Used} = (\text{Used GB} / \text{Total GB}) \times 100$ | $(3733536.2 / 9995826.5) \times 100$ | **37.4%** |
| **SolarWinds Population**| $\sum \text{Status Counts} = \text{Total Nodes}$ | $1370 + 25 + 35 + 6 + 112$ | **1,548** |
| **SolarWinds Health Closure**| $\sum \text{Health Tiers} = \text{Total Nodes}$ | $1357 + 150 + 41$ | **1,548** |
| **CMDB CI Closure** | $\sum \text{CI Types} = \text{Total CIs}$ | $612 + 340 + 210 + 200 + 186$ | **1,548** |

---

## 5. Security & IT Audit Controls

1. **Zero Hardcoded Secrets**:
   - All tenant credentials, client secrets, and passwords are exclusively read from `.env` via `os.getenv()`.
   - `.gitignore` and `.dockerignore` strictly prevent `.env`, logs, and temporary caches from entering Git commits or container images.
2. **DOM XSS Sanitization**:
   - All dynamic text interpolated into DOM innerHTML passes through `escapeHtml()`, neutralizing standard tags, event handlers, attribute breakouts, and javascript URI schemes.
3. **Strict Read-Only REST API**:
   - The FastAPI backend permits only HTTP `GET` requests for `/api/v1/cmdb/*`, `/api/v1/intune/*`, and `/api/v1/solarwinds/*`. All mutating verbs (`POST`, `PUT`, `DELETE`, `PATCH`) return `405 Method Not Allowed` with a JSON error envelope.
4. **Air-Gapped On-Premise Execution**:
   - Operates completely within the local network or internal VPN without transmitting corporate telemetry to external cloud endpoints.

---

## 6. Legacy / Alternate Deployment Path & Known Gaps

1. **Legacy Python `http.server` mode still exists**: `scripts/start_server.py` (a `ThreadingHTTPServer` supervisor with its own `/api/cmdb/*` routes and background sync daemon) predates the FastAPI/PostgreSQL stack. It is still what `start_itom_service.bat`, `register_startup_service.ps1`, and `systemd/itom.service` launch today. **Known gap**: production process-management scripts have not yet been migrated to launch `uvicorn app.main:app`; this is a recommended follow-up, not yet implemented.
2. **Static JSON snapshots (`data/*.json`)** are retained as (a) the ETL staging format consumed by the background ingestion worker (§3.3) and (b) a frontend fallback-only data source if `/api/v1/*` is unreachable. They are never the primary read path for the frontend.
3. **Docker Compose (`docker-compose.yml`)** runs the canonical stack (`nginx` + `api` (uvicorn) + `postgres`) and is the recommended way to run this platform end-to-end.
