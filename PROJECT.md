# Project: ITOM Platform Enterprise Transformation

## Architecture
The ITOM Operations Analytics & CMDB platform is transformed from flat-file JSON storage to a high-performance, persistent enterprise backend running on private/local server infrastructure.

### System Components
1. **Relational Database Layer (PostgreSQL 16 & SQLAlchemy 2.0 Async)**:
   - Primary persistence for configuration items (`configuration_items`), topology relationships (`ci_relationships`), time-series status history (`ci_status_history`), sync execution runs (`sync_runs`), and diagnostic error logs (`sync_error_logs`).
   - Version-controlled schema migrations via **Alembic**.
   - Async connection pooling with `asyncpg`.
2. **FastAPI Asynchronous REST API Backend**:
   - Clean Architecture modular package (`app/api/v1`, `app/services`, `app/repositories`, `app/integrations`, `app/models`, `app/schemas`).
   - Paginated REST endpoints for CMDB (`/api/v1/cmdb/*`), Intune telemetry (`/api/v1/intune/*`), SolarWinds (`/api/v1/solarwinds/*`), and sync runs (`/api/v1/sync/*`).
   - Dynamic data freshness response headers: `X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status` (`FRESH` $\le 900\text{s}$, `STALE` $> 900\text{s}$).
   - Sub-20ms paginated query performance via composite B-tree, covering, and GIN trigram indexes.
3. **Resilient Background Ingestion Engine**:
   - Decoupled `APScheduler` (`AsyncIOScheduler`) executing periodic synchronization every 10 minutes.
   - Strict read-only SWQL query enforcement (`ALLOWED_METHODS = ["GET"]`, keyword blocklist, HTTP 405 Method Not Allowed on mutating HTTP verbs).
   - Multi-tier identity resolution, SHA-256 state fingerprinting / delta change detection, and execution audit logging.
4. **Local Server Multi-Container Infrastructure (Docker Compose)**:
   - 3-tier container stack: `nginx` (reverse proxy & static web), `api` (FastAPI backend), `postgres` (PostgreSQL 16).
   - Multi-stage production `Dockerfile` with non-root user.
   - Standardized healthcheck endpoints: `/healthz` (liveness) and `/ready` (database & migration readiness).

---

## Feature Inventory
Every feature identified during the survey phase is enumerated below with its assigned milestone:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Database Schema & Models | SQLAlchemy 2.0 Async models for `configuration_items`, `ci_relationships`, `ci_status_history`, `sync_runs`, `sync_error_logs` | M1 | R1 Spec |
| 2 | Alembic Migration Pipeline | Initial Alembic migration scripts and `env.py` async runner | M1 | R1 Spec |
| 3 | Zero-Loss Ingestion/Seeding | Streaming seed script loading 25,987 Intune devices and 1,543 SolarWinds CIs into PostgreSQL with 100% mathematical parity | M1 | R1 Spec / Invariant Audit |
| 4 | Clean Architecture FastAPI App | FastAPI application factory, lifespan, asyncpg connection pool, CORS, and centralized exception handling | M2 | R2 Spec |
| 5 | Paginated CMDB Endpoints | `/api/v1/cmdb/cis`, `/api/v1/cmdb/summary`, `/api/v1/cmdb/cis/{ci_id}`, `/api/v1/cmdb/relationships` with sub-20ms latency | M2 | R2 Spec |
| 6 | Intune Telemetry Endpoints | `/api/v1/intune/devices`, `/api/v1/intune/summary`, `/api/v1/intune/metrics`, `/api/v1/intune/breakdown/*` | M2 | R2 Spec |
| 7 | SolarWinds Telemetry Endpoints | `/api/v1/solarwinds/nodes`, `/api/v1/solarwinds/summary`, `/api/v1/solarwinds/degraded` | M2 | R2 Spec |
| 8 | Freshness Headers Middleware | Starlette middleware injecting `X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status` (FRESH vs STALE) | M2 | R2 Spec |
| 9 | APScheduler Ingestion Engine | Decoupled 10-minute async background ingestion worker with concurrency locking | M3 | R3 Spec |
| 10 | Read-Only SWQL Security Guard | Strict SWQL query validator (`ALLOWED_METHODS = ["GET"]`, HTTP 405 on POST/PUT/DELETE/PATCH) | M3 | R3 Spec |
| 11 | Delta Change & History Engine | SHA-256 fingerprinting, status delta detection, and time-series audit logging in `ci_status_history` | M3 | R3 Spec |
| 12 | Ingestion Execution Audit Logging | Comprehensive run tracking in `sync_runs` and error logging in `sync_error_logs` | M3 | R3 Spec |
| 13 | Multi-Stage Production Dockerfile | Python 3.11-slim multi-stage build with non-root `itom` user and `/healthz` probe | M4 | R4 Spec |
| 14 | Docker Compose Stack | 3-service compose file (`nginx`, `api`, `postgres`) with healthchecks, environment variables, and volume persistence | M4 | R4 Spec |
| 15 | Nginx Reverse Proxy Config | `nginx.conf` routing `/` to static frontend and `/api/` to FastAPI backend with Gzip & security headers | M4 | R4 Spec |
| 16 | Healthcheck & Readiness Probes | `/healthz` (liveness) and `/ready` (database & migration readiness) endpoints | M4 | R4 Spec |
| 17 | E2E Regression & Integration Tests | 100% pass across all existing 119 E2E tests + new database integration & API tests | M5 | Acceptance Criteria |
| 18 | Adversarial Coverage Hardening | White-box stress testing, SQL injection guards, boundary conditions, and invariant verification | M5 | Acceptance Criteria |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| **M1** | Database Layer & Alembic Migrations | PostgreSQL 16 schema DDL, SQLAlchemy 2.0 Async models, Alembic migrations, async database pool (`app/core/database.py`), and zero-loss bulk seeding script (`scripts/seed_database.py`) | None | PLANNED |
| **M2** | FastAPI Asynchronous REST Backend | Modular Clean Architecture (`app/api/v1`, `app/services`, `app/repositories`, `app/schemas`), paginated endpoints (`/cmdb`, `/intune`, `/solarwinds`, `/sync`), freshness middleware headers, sub-20ms query optimization | M1 | PLANNED |
| **M3** | Background Ingestion Engine & Security | APScheduler 10m cron, strict read-only SWQL enforcer (`ALLOWED_METHODS = ["GET"]`, HTTP 405), delta change detector, `ci_status_history` logger, `sync_runs` & `sync_error_logs` audit | M1, M2 | PLANNED |
| **M4** | Docker Compose Infrastructure & Nginx Proxy | Multi-stage Dockerfile, Docker Compose stack (`nginx`, `api`, `postgres`), `nginx.conf` reverse proxy, `/healthz` and `/ready` probes, `.env` config | M1, M2, M3 | PLANNED |
| **M5** | Full E2E Verification & Adversarial Hardening | Phase 1: 100% pass rate across all E2E test suites (Tiers 1-4) with database integration; Phase 2: Adversarial coverage hardening (Tier 5) | M1, M2, M3, M4 | PLANNED |

---

## Interface Contracts

### 1. Database Model & Repository Contract
- `ConfigurationItem`:
  - `id`: UUID (PK)
  - `source_id`: String(128) (Unique index across source_system + source_id)
  - `source_system`: Enum (`"SOLARWINDS"`, `"INTUNE"`)
  - `name`: String(255)
  - `ci_type`: String(64) (`"Server"`, `"Workstation"`, `"Network"`, `"Mobile"`)
  - `status`: String(32) (`"Up"`, `"Down"`, `"Warning"`, `"Critical"`, `"Compliant"`, `"NonCompliant"`)
  - `health_tier`: String(16) (`"High"`, `"Medium"`, `"Low"`)
  - `ip_address`: String(64)
  - `vendor`: String(64)
  - `model`: String(128)
  - `serial_number`: String(128)
  - `last_sync_time`: DateTime(timezone=True)
  - `attributes`: JSONB
- `CIRelationship`:
  - `id`: UUID (PK)
  - `source_ci_id`: UUID (FK `configuration_items.id`)
  - `target_ci_id`: UUID (FK `configuration_items.id`)
  - `relationship_type`: String(64) (`"DEPENDS_ON"`, `"HOSTED_ON"`, `"CONNECTS_TO"`)
- `CIStatusHistory`:
  - `id`: UUID (PK)
  - `ci_id`: UUID (FK `configuration_items.id`)
  - `status`: String(32)
  - `health_tier`: String(16)
  - `cpu_utilization`: Float
  - `memory_utilization`: Float
  - `storage_used_pct`: Float
  - `recorded_at`: DateTime(timezone=True)
- `SyncRun`:
  - `id`: UUID (PK)
  - `source_system`: String(32)
  - `status`: String(32) (`"SUCCESS"`, `"FAILED"`, `"PARTIAL"`)
  - `records_processed`: Integer
  - `records_updated`: Integer
  - `duration_ms`: Integer
  - `started_at`: DateTime(timezone=True)
  - `completed_at`: DateTime(timezone=True)
- `SyncErrorLog`:
  - `id`: UUID (PK)
  - `sync_run_id`: UUID (FK `sync_runs.id`)
  - `error_message`: Text
  - `stack_trace`: Text
  - `created_at`: DateTime(timezone=True)

### 2. REST API & Middleware Contract
- Request Headers: standard HTTP headers.
- Response Headers (Injected by Middleware on all `/api/v1/*` routes):
  - `X-Last-Synchronized-At`: ISO 8601 UTC timestamp of latest sync run
  - `X-Data-Age-Seconds`: Integer seconds since latest sync run
  - `X-Sync-Status`: `"FRESH"` if $\le 900\text{s}$, `"STALE"` if $> 900\text{s}$
- Mutation Guard on SolarWinds & Intune Endpoints:
  - `POST`, `PUT`, `DELETE`, `PATCH` against `/api/v1/solarwinds/*` or `/api/v1/intune/*` return HTTP 405 Method Not Allowed.
- Pagination Query Parameters: `page` (default 1, ge 1), `page_size` (default 50, ge 1, le 1000).
- Paginated Response Envelope:
  ```json
  {
    "items": [...],
    "total": 25987,
    "page": 1,
    "page_size": 50,
    "total_pages": 520
  }
  ```

---

## Code Layout
```
app/
├── __init__.py
├── main.py                     # FastAPI app factory, lifespan, CORS, routers
├── core/
│   ├── __init__.py
│   ├── config.py               # Settings (pydantic-settings)
│   ├── database.py             # Async SQLAlchemy engine & async_sessionmaker
│   ├── logging.py              # Structured logger
│   ├── security.py             # SWQL validation & HTTP 405 security enforcers
│   ├── middleware.py           # Freshness headers & timing middleware
│   └── scheduler.py            # APScheduler background telemetry worker
├── api/
│   ├── __init__.py
│   ├── deps.py                 # Dependency injection (db session, pagination)
│   └── v1/
│       ├── __init__.py
│       ├── api.py              # Combined APIRouter for v1
│       └── endpoints/
│           ├── __init__.py
│           ├── cmdb.py         # /api/v1/cmdb/*
│           ├── intune.py       # /api/v1/intune/*
│           ├── solarwinds.py   # /api/v1/solarwinds/*
│           ├── sync.py         # /api/v1/sync/*
│           └── system.py       # /healthz, /ready, /metrics
├── models/
│   ├── __init__.py
│   ├── base.py                 # DeclarativeBase, mixins
│   ├── ci.py                   # ConfigurationItem, CIRelationship, CIStatusHistory
│   └── sync.py                 # SyncRun, SyncErrorLog
├── schemas/
│   ├── __init__.py
│   ├── common.py               # PaginationParams, PaginatedResponse
│   ├── cmdb.py                 # CMDB Pydantic schemas
│   ├── intune.py               # Intune Pydantic schemas
│   ├── solarwinds.py           # SolarWinds Pydantic schemas
│   └── sync.py                 # Sync Pydantic schemas
├── repositories/
│   ├── __init__.py
│   ├── base.py                 # Async BaseRepository
│   ├── ci_repository.py        # CI queries, status history, relationships
│   └── sync_repository.py      # SyncRun & error log queries
├── services/
│   ├── __init__.py
│   ├── cmdb_service.py         # CMDB business logic
│   ├── intune_service.py       # Intune analytics & invariant validation
│   ├── solarwinds_service.py   # SolarWinds health & metrics
│   └── sync_service.py         # Ingestion orchestration & delta change detection
└── integrations/
    ├── __init__.py
    ├── graph_client.py         # Microsoft Graph API client
    ├── solarwinds_client.py    # SolarWinds SWIS client with SWQL validation
    └── normalizers.py          # OEM, OS, and health normalizers

alembic/
├── env.py                      # Async migration runner
├── script.py.mako              # Migration template
└── versions/                   # Migration script versions

docker/
├── Dockerfile                  # Multi-stage Python 3.11 build
├── docker-compose.yml          # Multi-container stack (nginx, api, postgres)
└── nginx.conf                  # Reverse proxy & static frontend host

scripts/
├── seed_database.py            # High-performance bulk database seeding
├── run_sync.py                 # Standalone sync CLI
└── test_backend.py             # Direct API & DB validation script
```
