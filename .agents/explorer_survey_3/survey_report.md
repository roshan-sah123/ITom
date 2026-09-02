# Architectural Survey & Design Specification: FastAPI REST Backend (R2), Background Ingestion Engine (R3), and Docker Infrastructure (R4)

**Document Version**: 1.0.0  
**Author**: `explorer_survey_3`  
**Target Milestone**: ITOM Enterprise Transformation (Requirements R2, R3, R4)  
**Date**: 2026-09-01  
**Project Root**: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur`  

---

## 1. Executive Summary & System Overview

The ITOM Operations Analytics and CMDB platform is transitioning from a flat-file JSON and file-server-based model (`scripts/start_server.py`, `data/*.json`) to an enterprise-grade, persistent, asynchronous backend infrastructure. This survey report provides the authoritative architectural blueprint for:
1. **Requirement R2**: An asynchronous **FastAPI REST Backend** built with Clean Architecture, comprehensive domain routing (`/api/v1/cmdb/*`, `/api/v1/intune/*`, `/api/v1/solarwinds/*`, `/api/v1/sync/*`), standardized data freshness headers, sub-20ms paginated query responses, and dependency injection.
2. **Requirement R3**: A decoupled **APScheduler Background Ingestion Engine** operating on a 10-minute recurring schedule, enforcing strict read-only SWQL validation (`ALLOWED_METHODS = ["GET"]`, HTTP 405 on mutations), multi-tier identity resolution, delta change detection, and comprehensive audit logging into `sync_runs` and `sync_error_logs`.
3. **Requirement R4**: A multi-container **Docker Compose Infrastructure** featuring `nginx` (reverse proxy and static frontend host), `api` (multi-stage Python 3.11 FastAPI backend), and `postgres` (PostgreSQL 16 relational database), with standardized liveness (`/healthz`) and readiness (`/ready`) probes.

### Authoritative Invariants & Baseline Metrics
* **Microsoft Intune**: 25,987 total endpoints across Windows (25,334), macOS (602), Linux (24), iOS (2), Android (1). 83.08% fleet compliance (21,589 compliant, 3,422 non-compliant, 976 other), 37.4% average storage utilization.
* **SolarWinds Orion**: 1,548 total server nodes (1,543 active CMDB CIs). High Health (1,357), Medium Health (150), Low/Critical (41).
* **Data Freshness SLA**: Data is marked `"FRESH"` if last successful synchronization was $\le 15\text{ minutes}$ (900 seconds) ago; marked `"STALE"` if $> 15\text{ minutes}$.

---

## 2. FastAPI Asynchronous REST Backend (Requirement R2)

### 2.1 Clean Architecture Directory Structure
The backend application follows Clean Architecture principles, isolating interface adapters, business services, data repositories, and infrastructure integrations:

```
app/
├── __init__.py
├── main.py                     # FastAPI application factory, lifespan, middleware, routers
├── core/
│   ├── __init__.py
│   ├── config.py               # Pydantic BaseSettings (env parsing, validation)
│   ├── database.py             # Async SQLAlchemy engine & sessionmaker (asyncpg)
│   ├── logging.py              # Structured JSON/Console logger configuration
│   ├── security.py             # SWQL validation, CORS guards, read-only enforcers
│   └── middleware.py           # Freshness headers, request timing, correlation IDs
├── api/
│   ├── __init__.py
│   ├── deps.py                 # FastAPI dependency injection providers (db, services)
│   └── v1/
│       ├── __init__.py
│       ├── api.py              # Main v1 APIRouter bundling all sub-routers
│       └── endpoints/
│           ├── __init__.py
│           ├── cmdb.py         # /api/v1/cmdb/* endpoints
│           ├── intune.py       # /api/v1/intune/* endpoints
│           ├── solarwinds.py   # /api/v1/solarwinds/* endpoints
│           ├── sync.py         # /api/v1/sync/* endpoints
│           └── system.py       # /healthz, /ready, /metrics endpoints
├── schemas/
│   ├── __init__.py
│   ├── common.py               # PaginationParams, PaginatedResponse[T], HealthResponse
│   ├── cmdb.py                 # CIResponse, CMDBSummaryResponse, CIRelationshipResponse
│   ├── intune.py               # IntuneDeviceResponse, IntuneSummaryResponse, MetricsResponse
│   ├── solarwinds.py           # NodeResponse, SolarWindsSummaryResponse, DegradedNodeResponse
│   └── sync.py                 # SyncRunResponse, SyncTriggerResponse, SyncErrorLogResponse
├── models/
│   ├── __init__.py
│   ├── base.py                 # DeclarativeBase, TimestampMixin, UUIDMixin
│   ├── ci.py                   # ConfigurationItem, CIRelationship, CIStatusHistory
│   ├── device.py               # IntuneDevice (or unified CI mapping)
│   ├── node.py                 # SolarWindsNode
│   └── sync.py                 # SyncRun, SyncErrorLog
├── repositories/
│   ├── __init__.py
│   ├── base.py                 # Generic Async BaseRepository (CRUD, pagination, filters)
│   ├── ci_repository.py        # CI queries, status history, relationships, distributions
│   ├── device_repository.py    # Intune queries, breakdown aggregations
│   ├── node_repository.py      # SolarWinds queries, health aggregations
│   └── sync_repository.py      # SyncRun & SyncErrorLog persistence
├── services/
│   ├── __init__.py
│   ├── cmdb_service.py         # CMDB domain logic, role classification, summary synthesis
│   ├── intune_service.py       # Intune domain logic, invariant validation, compliance math
│   ├── solarwinds_service.py   # SolarWinds domain logic, health tier classifications
│   └── sync_service.py         # Ingestion orchestration, delta detection, audit tracking
└── integrations/
    ├── __init__.py
    ├── graph_client.py         # Async/Sync Microsoft Graph OAuth2 Client
    ├── solarwinds_client.py    # Async/Sync SolarWinds SWIS Client with SWQL guards
    └── normalizers.py          # Case-insensitive OEM, OS, role, and vendor normalizers
```

---

### 2.2 Application Lifespan & Dependency Injection

#### Lifespan Context Manager (`app/main.py`)
FastAPI's `lifespan` async context manager initializes database connection pools, verifies schema migration readiness, and starts the background APScheduler:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import get_settings
from app.core.database import async_engine
from app.services.sync_service import SyncService
from app.core.scheduler import TelemetryScheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database pool & verify connectivity
    settings = get_settings()
    logger.info("Initializing ITOM Enterprise REST Backend...")
    
    # Initialize & Start Background Telemetry Scheduler
    scheduler = TelemetryScheduler(sync_interval_seconds=settings.SYNC_INTERVAL_SECONDS)
    if settings.SYNC_ENABLED:
        await scheduler.start()
        app.state.scheduler = scheduler
    
    yield
    
    # Shutdown: Gracefully stop scheduler and close DB engine pool
    if hasattr(app.state, "scheduler"):
        await app.state.scheduler.shutdown()
    await async_engine.dispose()
    logger.info("ITOM REST Backend cleanly shut down.")
```

#### Dependency Injection Providers (`app/api/deps.py`)
```python
from typing import AsyncGenerator
from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.schemas.common import PaginationParams, FilterParams

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yields request-scoped async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

def get_pagination(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page")
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)

def get_filter_params(
    query: str | None = Query(None, description="Global text search"),
    ci_type: str | None = Query(None, description="Filter by CI Type / Device Role"),
    status: str | None = Query(None, description="Filter by status (Up, Down, Warning, etc.)"),
    vendor: str | None = Query(None, description="Filter by vendor (Cisco, Dell, HP, etc.)"),
    health_tier: str | None = Query(None, description="Filter by Health Tier (High, Medium, Low)")
) -> FilterParams:
    return FilterParams(query=query, ci_type=ci_type, status=status, vendor=vendor, health_tier=health_tier)
```

---

### 2.3 Response Header Contracts & Data Freshness Specification

All API responses originating from `/api/v1/*` must return dynamic response headers declaring telemetry age and sync health.

#### Response Headers
| Header Name | HTTP Header Key | Type | Description | Example |
|---|---|---|---|---|
| `last_synchronized_at` | `X-Last-Synchronized-At` | ISO 8601 UTC string | Timestamp of the most recent successful sync run | `2026-09-01T22:30:00Z` |
| `data_age_seconds` | `X-Data-Age-Seconds` | Integer | Seconds elapsed since `last_synchronized_at` | `142` |
| `sync_status` | `X-Sync-Status` | Enum (`"FRESH"`, `"STALE"`) | Freshness status based on 15-minute SLA | `FRESH` ($\le 900\text{s}$) or `STALE` ($> 900\text{s}$) |
| `data_source` | `X-Data-Source` | String | Underlying system source (`"PostgreSQL"`, `"SolarWinds"`, `"Intune"`) | `PostgreSQL (Persisted CMDB)` |

#### Freshness Middleware Implementation (`app/core/middleware.py`)
```python
import time
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.services.sync_service import get_latest_sync_state

class FreshnessHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        
        # Only attach to API routes
        if request.url.path.startswith("/api/v1/"):
            sync_state = await get_latest_sync_state()
            last_sync_dt = sync_state.get("last_successful_sync") # datetime UTC
            
            if last_sync_dt:
                age_seconds = int((datetime.now(timezone.utc) - last_sync_dt).total_seconds())
                is_fresh = age_seconds <= 900  # 15 minutes = 900 seconds
                
                response.headers["X-Last-Synchronized-At"] = last_sync_dt.isoformat()
                response.headers["X-Data-Age-Seconds"] = str(max(0, age_seconds))
                response.headers["X-Sync-Status"] = "FRESH" if is_fresh else "STALE"
            else:
                response.headers["X-Sync-Status"] = "INITIALIZING"
                response.headers["X-Data-Age-Seconds"] = "-1"
            
            # Anti-caching and CORS expose headers
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Access-Control-Expose-Headers"] = (
                "X-Last-Synchronized-At, X-Data-Age-Seconds, X-Sync-Status, X-Total-Count, X-Page, X-Page-Size"
            )
        
        return response
```

---

### 2.4 Complete Endpoint Specifications

#### 1. CMDB Router (`/api/v1/cmdb`)
* **`GET /api/v1/cmdb/summary`**: Returns overall CMDB metrics (1,548 total CIs, active monitored, health tier breakdowns, CI type distributions, hardware distributions, top locations, top risk assets).
* **`GET /api/v1/cmdb/cis`** (and `/api/v1/cmdb/items`): Returns paginated list of CIs with search, filter (by `ci_type`, `status`, `vendor`, `health_tier`, `location`), and sorting. Returns `PaginatedResponse[CIResponse]`.
* **`GET /api/v1/cmdb/servers`**: Shortcut filtered endpoint returning only server-type CIs (`ci_type == "Server"`).
* **`GET /api/v1/cmdb/network-devices`**: Shortcut filtered endpoint returning only network hardware (`ci_type` in `["Access Switch", "Distribution Switch", "Core Switch", "Router", "Firewall", "Wireless Controller", "Network Appliance"]`).
* **`GET /api/v1/cmdb/cis/{ci_id}`**: Retrieves single CI details including metadata, real-time performance indicators, and attached relationship links.
* **`GET /api/v1/cmdb/cis/{ci_id}/relationships`**: Returns graph relationships for the CI (e.g., `located_at` site, `connects_to` switch, `depends_on` service).
* **`GET /api/v1/cmdb/cis/{ci_id}/history`**: Returns time-series status history log records (`ci_status_history`) for tracking degradation or recovery events.
* **`GET /api/v1/cmdb/health`**: Returns CMDB service health, database connectivity, and backend sync status.
* **`POST / PUT / DELETE / PATCH /api/v1/cmdb/*`**: Strictly rejected with **HTTP 405 Method Not Allowed** and payload `{"error": "Forbidden: CMDB API is strictly READ-ONLY.", "allowed_methods": ["GET"]}`.

#### 2. Intune Router (`/api/v1/intune`)
* **`GET /api/v1/intune/summary`**: Returns verified Intune telemetry summary (25,987 total endpoints, 83.08% compliance rate, 37.4% storage used, OS distribution, compliance state distribution, manufacturer breakdown).
* **`GET /api/v1/intune/devices`**: Returns paginated device records with multi-field search (`deviceName`, `userPrincipalName`, `serialNumber`, `model`), OS filtering, compliance filtering, and storage sorting.
* **`GET /api/v1/intune/devices/{device_id}`**: Single device inspection with detailed hardware, storage, and compliance properties.
* **`GET /api/v1/intune/compliance`**: Compliance-specific breakdown with historical trend data.
* **`GET /api/v1/intune/manufacturers`**: Case-insensitively normalized OEM distribution (Dell, HP, Lenovo, Apple, Other).

#### 3. SolarWinds Router (`/api/v1/solarwinds`)
* **`GET /api/v1/solarwinds/summary`**: Returns SolarWinds Orion summary (1,548 nodes, High: 1,357, Medium: 150, Low: 41, fleet CPU: 16.2%, RAM: 22.6%, latency: 42.5ms).
* **`GET /api/v1/solarwinds/nodes`**: Paginated server node records with filtering and sorting.
* **`GET /api/v1/solarwinds/nodes/{node_id}`**: Details for an individual node by SolarWinds `NodeID`.
* **`GET /api/v1/solarwinds/degraded`**: Top resource-pressured / degraded server assets (CPU > 75%, RAM > 80%, status != Up).

#### 4. Sync Management Router (`/api/v1/sync`)
* **`GET /api/v1/sync/status`**: Current ingestion worker state, last completed run, data age, running execution count, next scheduled sync trigger.
* **`GET /api/v1/sync/runs`**: Paginated audit list of historical sync runs from `sync_runs` table.
* **`GET /api/v1/sync/runs/{run_id}/errors`**: Error logs associated with a specific sync execution.
* **`POST /api/v1/sync/trigger`**: Triggers immediate asynchronous sync run in background task worker. Returns HTTP 202 Accepted with `run_id`.

#### 5. System Probes (`/healthz`, `/ready`, `/metrics`)
* **`GET /healthz`**: Lightweight liveness probe returning HTTP 200 `{"status": "ok", "uptime_seconds": 3600}`.
* **`GET /ready`**: Readiness probe executing `SELECT 1` against PostgreSQL. Returns HTTP 200 `{"status": "ready", "database": "connected", "migration_version": "001_initial"}` or HTTP 503 `{"status": "unhealthy", "database": "disconnected"}`.

---

### 2.5 Schemas and Sub-20ms Performance Strategy

#### Paginated Response Model (`app/schemas/common.py`)
```python
from typing import Generic, TypeVar, List
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=1000)

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
    
    model_config = ConfigDict(from_attributes=True)
```

#### Sub-20ms Query Optimization Architecture
To meet the acceptance criterion of **sub-20ms response time for paginated queries**:
1. **Targeted PostgreSQL Indexes**:
   - Single-column B-tree indexes: `configuration_items.ci_id`, `configuration_items.hostname`, `configuration_items.ip_address`, `configuration_items.status`, `configuration_items.ci_type`, `configuration_items.vendor`, `configuration_items.health_tier`.
   - Trigram (GIN) indexes on `hostname`, `caption`, `ip_address`, and `serial_number` for fast ILIKE/fuzzy text searching.
   - Composite index on `(ci_type, status, health_tier)` for compound dashboard filter queries.
2. **Selective Projection & Keyset/Offset Optimization**:
   - Queries project only columns defined in the response schema, avoiding full text description payloads on list views.
   - Count queries use indexed scans or fast approximate count caching for high-page queries.
3. **Async Connection Pooling**:
   - `asyncpg` connection pool with `pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`, and `pool_recycle=3600`.

---

## 3. Background Ingestion Engine (Requirement R3)

### 3.1 APScheduler Architecture & Ingestion Lifecycle

The ingestion engine runs as an asynchronous worker utilizing `apscheduler.schedulers.asyncio.AsyncIOScheduler`:

```
+-------------------------------------------------------------------------------+
|                             APScheduler Engine                                |
|                                                                               |
|  +--------------------+   Every 10 mins   +--------------------------------+  |
|  |  IntervalTrigger   | ----------------> |  execute_telemetry_sync_job()  |  |
|  | (10 min / 600 sec) |                   |  (max_instances=1, coalesce)   |  |
|  +--------------------+                   +---------------+----------------+  |
+-----------------------------------------------------------|-------------------+
                                                            |
                     +--------------------------------------+--------------------------------------+
                     |                                                                             |
                     v                                                                             v
      +-----------------------------+                                               +-----------------------------+
      |  Microsoft Intune Pipeline  |                                               |  SolarWinds SWIS Pipeline   |
      |                             |                                               |                             |
      | 1. OAuth2 Token Acquisition |                                               | 1. SWQL Read-Only Validator |
      | 2. OData Paged Device Query |                                               | 2. Basic/NTLM SWIS Query    |
      |    ($select, 25,987 items)  |                                               |    (1,548 Node Records)     |
      | 3. Invariant Checks         |                                               | 3. Health Classification    |
      +--------------+--------------+                                               +--------------+--------------+
                     |                                                                             |
                     +--------------------------------------+--------------------------------------+
                                                            |
                                                            v
                                            +-------------------------------+
                                            |   Identity Resolution Engine  |
                                            |   - Primary Key Mapping       |
                                            |   - Serial & Hostname Match   |
                                            +---------------+---------------+
                                                            |
                                                            v
                                            +-------------------------------+
                                            | Delta Change Detection (Diff) |
                                            | - SHA-256 State Fingerprint   |
                                            | - Attribute-level Comparison  |
                                            +---------------+---------------+
                                                            |
                                     +----------------------+----------------------+
                                     |                                             |
                              [Change Detected]                             [No Change]
                                     |                                             |
                                     v                                             v
                     +-------------------------------+             +-------------------------------+
                     | 1. Upsert ConfigurationItem   |             | 1. Update last_seen_at &      |
                     | 2. Insert CIStatusHistory     |             |    last_sync_time             |
                     | 3. Update Relationships       |             | 2. Skip Status History Insert |
                     +---------------+---------------+             +---------------+---------------+
                                     |                                             |
                                     +----------------------+----------------------+
                                                            |
                                                            v
                                            +-------------------------------+
                                            | Audit & Execution Logging     |
                                            | - Record in sync_runs         |
                                            | - Log errors to sync_error_logs
                                            +-------------------------------+
```

#### Scheduler Configuration & Lock Safety
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore

class TelemetryScheduler:
    def __init__(self, sync_interval_seconds: int = 600):
        self.scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "coalesce": True,            # Coalesce missed jobs into single run
                "max_instances": 1,          # Prevent overlapping sync runs
                "misfire_grace_time": 60     # 60s tolerance for delayed starts
            }
        )
        self.interval = sync_interval_seconds

    async def start(self):
        self.scheduler.add_job(
            func=self.run_sync_task,
            trigger=IntervalTrigger(seconds=self.interval),
            id="telemetry_sync_job",
            name="10-Minute Multi-Domain Telemetry Sync",
            replace_existing=True
        )
        self.scheduler.start()

    async def run_sync_task(self):
        # Calls SyncService.execute_full_sync() with database advisory lock
        pass
```

---

### 3.2 Read-Only SWQL Security Enforcement

To strictly guarantee that SolarWinds integration cannot execute state-mutating operations:

1. **HTTP Method Enforcement**: `ALLOWED_METHODS = ["GET"]`. Any invocation attempting `POST`, `PUT`, `DELETE`, `PATCH` is immediately blocked.
2. **SWQL Syntax & Keyword Validation**:
   - Validates that the query string starts with `SELECT` (ignoring leading SQL comments `--` and `/* */`).
   - Rejects any query containing forbidden mutating tokens as standalone words: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `EXEC`, `EXECUTE`, `GRANT`, `REVOKE`, `MERGE`.
   - Rejects semicolon statement chaining (preventing SQL injection).

```python
class SolarWindsSecurityError(Exception):
    """Raised when a forbidden mutation or invalid SWQL query is attempted."""
    pass

ALLOWED_METHODS = ["GET"]
FORBIDDEN_SWQL_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", 
    "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "MERGE"
}

def validate_swql_read_only(query_str: str) -> None:
    if not query_str or not isinstance(query_str, str):
        raise SolarWindsSecurityError("SWQL query must be a non-empty string.")
    
    cleaned = query_str.strip()
    while cleaned.startswith("--") or cleaned.startswith("/*"):
        if cleaned.startswith("--"):
            cleaned = cleaned.split("\n", 1)[-1].strip()
        elif cleaned.startswith("/*"):
            cleaned = cleaned.split("*/", 1)[-1].strip()

    first_token = cleaned.split()[0].upper() if cleaned.split() else ""
    if first_token != "SELECT":
        raise SolarWindsSecurityError(
            f"SolarWinds SWIS queries must strictly begin with SELECT (got: '{first_token}')."
        )

    upper_query = f" {cleaned.upper()} "
    for kw in FORBIDDEN_SWQL_KEYWORDS:
        if f" {kw} " in upper_query or f"\n{kw} " in upper_query or f"\t{kw} " in upper_query:
            raise SolarWindsSecurityError(
                f"Forbidden mutating keyword detected in SWQL query: '{kw}'"
            )
```

---

### 3.3 Identity Resolution Algorithm

Assets ingested across multiple telemetry domains are resolved to canonical Configuration Items using a deterministic multi-tier resolution hierarchy:

| Asset Source | Tier 1 (Primary Key) | Tier 2 (Hardware Identity) | Tier 3 (Network Identity) | Canonical `ci_id` Format |
|---|---|---|---|---|
| **SolarWinds Server / Network Node** | SolarWinds `NodeID` | Hardware Serial / MAC (if present) | Caption / Hostname + Primary IP | `SW-NODE-{NodeID}` |
| **Intune Endpoint Device** | Intune Device GUID (`id`) | Hardware `serialNumber` | `deviceName` + `userPrincipalName` | `INTUNE-{id}` |
| **Facility / Location CI** | Site Code / Facility ID | Location Name Slug | City string | `SITE-{CITY-SLUG}` |

---

### 3.4 Delta Change Detection & History Logging

To avoid unbounded database growth while capturing all meaningful infrastructure state changes:
1. **Attribute Comparison Hash**: A SHA-256 fingerprint is calculated over state attributes: `status`, `health_tier`, `cpu_load`, `memory_used`, `ip_address`, `operating_system`, `compliance_state`.
2. **Delta Evaluation**:
   - If the new state hash matches the existing record's state hash:
     - Update `last_seen_at = now_utc`.
     - Do not create a record in `ci_status_history`.
   - If a change is detected:
     - Record previous vs new state in `ci_status_history`.
     - Update `configuration_items` with new attributes, updated timestamp, and new state hash.

```python
# ci_status_history record structure:
{
    "id": "uuid-v4",
    "ci_id": "SW-NODE-101",
    "previous_status": "Up",
    "new_status": "Warning",
    "previous_health_tier": "High",
    "new_health_tier": "Medium",
    "change_reason": "High CPU load (82.4%) exceeding 75% warning threshold",
    "changed_fields": {
        "cpu_load": {"old": 14.5, "new": 82.4},
        "health_tier": {"old": "High", "new": "Medium"},
        "status": {"old": "Up", "new": "Warning"}
    },
    "recorded_at": "2026-09-01T22:40:00Z"
}
```

---

### 3.5 Execution Audit Logging System

Every synchronization run is logged in the `sync_runs` table, and every encountered error is recorded in `sync_error_logs`.

#### `sync_runs` Table Schema
* `id` (`UUID` / `BigInt`, PK)
* `source` (`VARCHAR(32)`, e.g., `"SolarWinds"`, `"Intune"`, `"Unified"`)
* `trigger_type` (`VARCHAR(16)`, e.g., `"SCHEDULED"`, `"MANUAL"`, `"STARTUP"`)
* `status` (`VARCHAR(16)`, e.g., `"RUNNING"`, `"COMPLETED"`, `"FAILED"`, `"PARTIAL"`)
* `started_at` (`TIMESTAMPTZ`, UTC)
* `completed_at` (`TIMESTAMPTZ`, Nullable)
* `duration_ms` (`INTEGER`, Nullable)
* `records_extracted` (`INTEGER`, Default 0)
* `records_created` (`INTEGER`, Default 0)
* `records_updated` (`INTEGER`, Default 0)
* `records_unchanged` (`INTEGER`, Default 0)
* `records_errored` (`INTEGER`, Default 0)
* `error_summary` (`TEXT`, Nullable)

#### `sync_error_logs` Table Schema
* `id` (`UUID` / `BigInt`, PK)
* `sync_run_id` (`UUID` / `BigInt`, FK -> `sync_runs.id`)
* `timestamp` (`TIMESTAMPTZ`, UTC)
* `source` (`VARCHAR(32)`)
* `error_code` (`VARCHAR(64)`)
* `error_message` (`TEXT`)
* `traceback_text` (`TEXT`, Nullable)
* `payload_snippet` (`TEXT`, Nullable, sanitized of credentials)

---

## 4. Docker Compose & Local Infrastructure (Requirement R4)

### 4.1 Multi-Container Architecture

The production Docker Compose environment consists of three isolated services communicating over an internal bridge network (`itom-net`):

```
                                  Client Browser / API Consumer
                                                |
                                                | HTTP / HTTPS (:8080 or :80)
                                                v
                    +-------------------------------------------------------+
                    |                     nginx Service                     |
                    |              (Reverse Proxy & Static Web)             |
                    |                                                       |
                    |  - Serves static HTML/JS/CSS/CSV                     |
                    |  - Proxies /api/ -> http://api:8000/api/             |
                    |  - Proxies /healthz, /ready -> http://api:8000/       |
                    |  - Handles Gzip compression & security headers        |
                    +---------------------------+---------------------------+
                                                |
                                                | Proxy Pass (Internal network)
                                                v
                    +-------------------------------------------------------+
                    |                      api Service                      |
                    |           (FastAPI Backend + APScheduler)             |
                    |                                                       |
                    |  - Runs Uvicorn ASGI Server (Port 8000)               |
                    |  - APScheduler 10-minute Telemetry Ingestion Worker   |
                    |  - SQLAlchemy 2.0 Async / asyncpg connection pool     |
                    +---------------------------+---------------------------+
                                                |
                                                | asyncpg TCP (:5432)
                                                v
                    +-------------------------------------------------------+
                    |                   postgres Service                    |
                    |               (PostgreSQL 16 Database)                |
                    |                                                       |
                    |  - Stores configuration_items, ci_relationships       |
                    |  - Stores ci_status_history, sync_runs, error logs    |
                    |  - Persistent Named Volume: postgres_data             |
                    +-------------------------------------------------------+
```

---

### 4.2 Production Multi-Stage Dockerfile (`Dockerfile`)

```dockerfile
# Stage 1: Build & Dependency Wheel Cache
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Production Minimal Runtime Image
FROM python:3.11-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root application user
RUN groupadd -g 10001 itom && \
    useradd -u 10001 -g itom -s /bin/bash -m itom

# Copy application codebase and migration files
COPY --chown=itom:itom alembic.ini .
COPY --chown=itom:itom alembic/ ./alembic/
COPY --chown=itom:itom app/ ./app/
COPY --chown=itom:itom src/ ./src/
COPY --chown=itom:itom scripts/ ./scripts/
COPY --chown=itom:itom data/ ./data/

USER itom

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

---

### 4.3 Docker Compose Multi-Container Stack (`docker-compose.yml`)

```yaml
version: "3.8"

networks:
  itom-net:
    driver: bridge

volumes:
  postgres_data:
    driver: local

services:
  postgres:
    image: postgres:16-alpine
    container_name: itom-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-itom_db}
      POSTGRES_USER: ${POSTGRES_USER:-itom_admin}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-itom_secure_pass_2026}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-itom_admin} -d ${POSTGRES_DB:-itom_db}"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 5s
    networks:
      - itom-net
    ports:
      - "5432:5432"

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: itom-api
    restart: unless-stopped
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-itom_admin}:${POSTGRES_PASSWORD:-itom_secure_pass_2026}@postgres:5432/${POSTGRES_DB:-itom_db}
      - HOST=0.0.0.0
      - PORT=8000
      - SYNC_INTERVAL_SECONDS=${SYNC_INTERVAL_SECONDS:-600}
      - SYNC_ENABLED=${SYNC_ENABLED:-true}
      - AZURE_TENANT_ID=${AZURE_TENANT_ID}
      - AZURE_CLIENT_ID=${AZURE_CLIENT_ID}
      - AZURE_CLIENT_SECRET=${AZURE_CLIENT_SECRET}
      - SOLARWINDS_HOST=${SOLARWINDS_HOST}
      - SOLARWINDS_PORT=${SOLARWINDS_PORT:-17774}
      - SOLARWINDS_USERNAME=${SOLARWINDS_USERNAME}
      - SOLARWINDS_PASSWORD=${SOLARWINDS_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 3s
      retries: 3
    networks:
      - itom-net
    ports:
      - "8000:8000"

  nginx:
    image: nginx:alpine
    container_name: itom-nginx
    restart: unless-stopped
    ports:
      - "${PORT:-8080}:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./:/usr/share/nginx/html:ro
    depends_on:
      - api
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:80/"]
      interval: 10s
      timeout: 3s
      retries: 3
    networks:
      - itom-net
```

---

### 4.4 Nginx Reverse Proxy Configuration (`nginx.conf`)

```nginx
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    sendfile        on;
    keepalive_timeout  65;

    # Gzip Compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    upstream backend_api {
        server api:8000;
        keepalive 32;
    }

    server {
        listen 80;
        server_name localhost;
        root /usr/share/nginx/html;
        index index.html;

        # Static Frontend Assets
        location / {
            try_files $uri $uri/ /index.html;
            expires -1;
            add_header Cache-Control "no-cache, no-store, must-revalidate";
        }

        # Data JSON fallback
        location /data/ {
            try_files $uri =404;
            expires -1;
            add_header Cache-Control "no-cache, no-store, must-revalidate";
        }

        # Reverse Proxy for REST API Endpoints
        location /api/ {
            proxy_pass http://backend_api/api/;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 5s;
            proxy_read_timeout 60s;
        }

        # Reverse Proxy for Health & Readiness Probes
        location /healthz {
            proxy_pass http://backend_api/healthz;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }

        location /ready {
            proxy_pass http://backend_api/ready;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }
    }
}
```

---

### 4.5 Environment Configuration Template (`.env.example`)

```env
# ==============================================================================
# ITOM Enterprise Operations Platform - Environment Configuration Template
# ==============================================================================

# --- PostgreSQL Relational Database Configuration ---
POSTGRES_DB=itom_db
POSTGRES_USER=itom_admin
POSTGRES_PASSWORD=itom_secure_password_here
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://itom_admin:itom_secure_password_here@postgres:5432/itom_db

# --- FastAPI REST Server & Supervisor Configuration ---
HOST=0.0.0.0
PORT=8080
API_PORT=8000
ENVIRONMENT=production
LOG_LEVEL=INFO
WORKERS_COUNT=4
CORS_ORIGINS=*

# --- Background Telemetry Ingestion Engine (APScheduler) ---
SYNC_INTERVAL_SECONDS=600
SYNC_ENABLED=true
SYNC_TIMEOUT_SECONDS=300

# --- Microsoft Intune / Microsoft Graph API ---
AZURE_TENANT_ID=your-azure-tenant-id-guid
AZURE_CLIENT_ID=your-azure-app-client-id
AZURE_CLIENT_SECRET=your-azure-app-client-secret

# --- SolarWinds Orion SWIS API v3 ---
SOLARWINDS_HOST=gnoc.coforge.com
SOLARWINDS_PORT=17774
SOLARWINDS_USERNAME=your-swis-username
SOLARWINDS_PASSWORD=your-swis-password-here
```

---

## 5. Implementation Roadmap & Verification Plan

### 5.1 Phased Implementation Work Breakdown
1. **Phase 1: Project Setup & Dependencies (`requirements.txt`, `alembic`, `app/core`)**:
   - Add required libraries: `fastapi>=0.110.0`, `uvicorn[standard]>=0.28.0`, `sqlalchemy[asyncio]>=2.0.28`, `asyncpg>=0.29.0`, `alembic>=1.13.1`, `apscheduler>=3.10.4`, `pydantic>=2.6.4`, `pydantic-settings>=2.2.1`, `httpx>=0.27.0`, `pytest-asyncio>=0.23.5`.
   - Setup `app/core/config.py`, `app/core/database.py`, and `app/core/logging.py`.
2. **Phase 2: Schemas, Repositories, and Services**:
   - Implement `app/schemas/*` and `app/repositories/*`.
   - Implement `app/services/*` connecting database models to API response schemas.
3. **Phase 3: FastAPI Routers & Middleware**:
   - Implement `app/api/v1/endpoints/cmdb.py`, `intune.py`, `solarwinds.py`, `sync.py`, `system.py`.
   - Register `FreshnessHeaderMiddleware` and CORS configuration.
4. **Phase 4: APScheduler Ingestion Engine & SWQL Validator**:
   - Implement `app/core/scheduler.py` and `app/services/sync_service.py`.
   - Implement SWQL read-only query guard and identity resolution engine.
5. **Phase 5: Dockerfile, Docker Compose & Nginx**:
   - Author multi-stage `Dockerfile`, `docker-compose.yml`, and `nginx.conf`.
6. **Phase 6: Integration Testing & Verification**:
   - Author async test suite in `tests/test_api_v1_endpoints.py`, `tests/test_scheduler_sync.py`, and `tests/test_docker_health.py`.

### 5.2 Verification Methods
* **E2E & Invariant Test Suite**: Run `python tests/run_e2e_tests.py` to confirm zero regression across 119 baseline tests.
* **REST API Endpoint Testing**: Execute `pytest tests/test_api_v1_endpoints.py` verifying:
  - Sub-20ms latency on paginated queries.
  - Presence and correctness of freshness headers (`X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status`).
  - Read-only protection: `POST /api/v1/cmdb/cis` returns HTTP 405 Method Not Allowed.
  - Query filtering and sorting across all CI roles.
* **Ingestion Engine Testing**: Execute unit tests mocking Graph and SWIS endpoints to verify delta change logging into `ci_status_history` and `sync_runs`.
* **Container Healthcheck Testing**: Run `docker compose up -d` and verify `docker compose ps` shows all containers healthy (`postgres`, `api`, `nginx`).

---
