# Project: ITOM Portal Enterprise Transformation

## Architecture
The ITOM Portal is an enterprise-grade IT Operations Management platform featuring a high-contrast Obsidian dark-mode frontend UI, a high-performance asynchronous FastAPI REST backend, PostgreSQL 16 relational persistence with time-series history tracking, and a resilient, read-only background ingestion engine synchronized with Microsoft Intune and SolarWinds Orion.

### High-Level Topology
```
[ Browser / Client ]
        │  (HTTP / WebSockets)
        ▼
[ NGINX Reverse Proxy (Port 8080) ]
        ├── /              ──> Static Obsidian Frontend (HTML5 / Vanilla JS / Chart.js)
        ├── /api/v1/       ──> FastAPI Async Backend (Uvicorn / Port 8000)
        └── /healthz       ──> System Liveness Probe
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
         [ PostgreSQL 16 Database ]       [ Background Ingestion Engine ]
         - configuration_items            - APScheduler (10-min cadence)
         - ci_relationships               - Advisory Lock (pg_try_advisory_lock)
         - ci_status_history (Time-Series)- SHA-256 Delta Change Detection
         - sync_runs & sync_error_logs    - Read-Only SWQL Validation (HTTP 405)
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Obsidian Dark UI Design Tokens | Canonical CSS variables (`#0B0B0B`, `#141414`, `#16161A`, `#222222`, `#F97316`) across all styles | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Unified 3-Zone Telemetry Table | 200ms debounced search, 10/25/50/100 page sizing, index repositioning, sliding window pagination, scroll reset | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Interactive Chart.js Drill-Downs | Click slice/bar to filter table, tooltip hints, safe lifecycle destruction (`destroyChartSafe()`) | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Strict XSS Sanitization & DOM Safety | 100% cell escaping via `escapeHtml()`, zero dynamic evaluation sinks | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Accessibility & Screen Reader A11y | `role="tablist"`, `role="region"`, `aria-label`, `aria-current="page"`, keyboard hotkeys | M1 | ORIGINAL_REQUEST §R1 |
| 6 | Sub-50ms Dashboard Initial Paint | Two-phase progressive summary loading and instant DOM render | M1 | Acceptance Criteria |
| 7 | Dual-Asset Synchronicity | Synchronize `./` and `src/frontend/` assets to comply with zero-build invariants | M1 | Codebase Survey |
| 8 | PostgreSQL 16 Relational Models | SQLAlchemy 2.0 async models for CIs, relationships, history, sync runs, and error logs | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Alembic Async Migration Pipeline | Async migration environment and initial schema migrations (`0001_initial_schema.py`) | M2 | ORIGINAL_REQUEST §R2 |
| 10 | High-Performance Indexing & Trigrams | Composite B-trees, covering indexes, and GIN trigram indexes for sub-20ms queries | M2 | Backend Survey |
| 11 | Historical Status Delta Tracking | Append-only time-series tracking in `ci_status_history` on state transitions | M2 | ORIGINAL_REQUEST §R2 |
| 12 | Database Ingestion & Seeding Script | Seed script populating PostgreSQL with all 25,987 Intune CIs and 1,543 SolarWinds CIs | M2 | Acceptance Criteria |
| 13 | Modular FastAPI Async Backend | Clean architecture (`app/api/v1`, `app/services`, `app/repositories`, `app/models`, `app/schemas`) | M3 | ORIGINAL_REQUEST §R2 |
| 14 | Paginated REST API Endpoints | CMDB (`/api/v1/cmdb/*`), Intune (`/api/v1/intune/*`), SolarWinds (`/api/v1/solarwinds/*`), System (`/healthz`, `/ready`) | M3 | ORIGINAL_REQUEST §R2 |
| 15 | Response Freshness Middleware | Headers `X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status` (FRESH <=900s, STALE >900s) | M3 | ORIGINAL_REQUEST §R2 |
| 16 | Decoupled APScheduler Sync Engine | Async periodic worker executing 10-minute telemetry ingestion cycle | M4 | ORIGINAL_REQUEST §R3 |
| 17 | Multi-Worker Advisory Locks | Session-level PostgreSQL advisory locks (`pg_try_advisory_lock(1048576)`) for multi-worker safety | M4 | ORIGINAL_REQUEST §R3 |
| 18 | Read-Only SWQL Validation & 405 Guards | SWQL query validator and HTTP 405 Method Not Allowed error envelopes for mutating verbs | M4 | ORIGINAL_REQUEST §R3 |
| 19 | Volatile Delta Detection | SHA-256 state hashing to minimize unnecessary history writes | M4 | ORIGINAL_REQUEST §R3 |
| 20 | Docker Multi-Stage API Image | Production `Dockerfile` with multi-stage build, non-root `itom` user, and healthcheck | M5 | ORIGINAL_REQUEST §R4 |
| 21 | Multi-Container Docker Compose | Compose stack defining `nginx` (8080), `api` (8000), `postgres` (5432) with healthchecks | M5 | ORIGINAL_REQUEST §R4 |
| 22 | NGINX Reverse Proxy Configuration | `nginx.conf` routing `/` to static frontend and `/api/` to FastAPI backend | M5 | ORIGINAL_REQUEST §R4 |
| 23 | E2E Regression & Integration Test Suite | Comprehensive test suite covering existing 119 E2E tests + 95 new integration tests (100% pass) | M6 | Acceptance Criteria |
| 24 | Adversarial Security & Coverage Hardening | Tier 5 adversarial stress testing, SQL injection guards, XSS validation, mutate verb rejection | M6 | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Frontend UI/UX Polish & Accessibility | Obsidian CSS tokens, 3-zone table a11y & polish, Chart.js lifecycle, dual-asset sync | none | DONE |
| M2 | Relational Database Persistence & Schema | SQLAlchemy 2.0 async models, Alembic migrations, PostgreSQL indexing, seeding script | none | DONE |
| M3 | FastAPI Asynchronous REST Backend | Clean architecture API routes, paginated repository, freshness middleware, sub-20ms queries | M2 | DONE |
| M4 | Read-Only Sync Engine & Security | APScheduler worker, advisory locks, SHA-256 delta detection, read-only SWQL validator & 405 guards | M2, M3 | DONE |
| M5 | Multi-Container Docker Infrastructure | Multi-stage Dockerfile, Docker Compose stack (nginx, api, postgres), nginx reverse proxy | M1, M3, M4 | DONE |
| M6 | E2E Verification & Adversarial Hardening | Phase 1: 100% pass across 214 tests; Phase 2: Tier 5 adversarial hardening | M1, M2, M3, M4, M5 | DONE |

## Interface Contracts

### 1. Database Persistence Layer ↔ FastAPI Backend
- **Engine**: Async SQLAlchemy 2.0 `create_async_engine(DATABASE_URL)` with `asyncpg` driver and connection pooling.
- **Session Dependency**: `get_db_session()` / `get_db()` async generator yielding `AsyncSession`.
- **Model Entities**: `ConfigurationItem`, `CIRelationship`, `CIStatusHistory`, `SyncRun`, `SyncErrorLog`.

### 2. FastAPI Backend ↔ Frontend Client
- **Base Route Prefix**: `/api/v1`
- **Pagination Envelope**: `items`, `total`, `page`, `page_size`, `total_pages`, `has_next`, `has_prev`.
- **Response Freshness Headers**: `X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status` (FRESH <= 900s, STALE > 900s).

### 3. Read-Only Integrations & Security Contracts
- **Allowed Methods**: Strict `GET` only for `/api/v1/solarwinds/*`, `/api/v1/intune/*`, `/api/v1/cmdb/*`.
- **Mutating Requests**: `POST`, `PUT`, `DELETE`, `PATCH` return `HTTP 405 Method Not Allowed` with JSON error envelope and `Allow: GET, HEAD, OPTIONS`.
- **SWQL Query Guard**: Any forbidden keywords or SQL comment obfuscation throw `SolarWindsSecurityError`.
