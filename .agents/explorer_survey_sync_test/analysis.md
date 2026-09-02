# Technical Analysis: Background Ingestion Engine, Read-Only Security, Docker Multi-Container Infrastructure & Test Suite Architecture

**Author**: Sync Engine & Testing Explorer (`explorer_survey_sync_test`)  
**Date**: 2026-09-02  
**Mission**: Comprehensive survey and architectural blueprints for R1-R4 backend transformation requirements: APScheduler background ingestion, read-only SWQL guards, Docker Compose topology, and E2E test suite coverage.

---

## 1. Executive Summary

The IT Operations Management (ITOM) platform is undergoing a major enterprise transformation from a flat-file JSON web application to an asynchronous, persistent FastAPI backend backed by PostgreSQL 16, orchestrated via Docker Compose, and protected by strict read-only security guards.

This investigation analyzes four core domains:
1. **Background Ingestion Engine**: Upgrading from thread/subprocess-based sync (`scripts/start_server.py`, `scripts/run_sync.py`) to an embedded `APScheduler` (`AsyncIOScheduler`) in the ASGI lifespan, running every 10 minutes (600s), utilizing PostgreSQL advisory locks (`SELECT pg_try_advisory_lock(1048576)`) for multi-worker safety, SHA-256 state fingerprinting for delta history logging (`ci_status_history`), and structured audit logging (`sync_runs`, `sync_error_logs`).
2. **External Integrations & Read-Only SWQL Validation**: Enhancing the existing SWQL guard (`src/sync/solarwinds_client.py`) into API-level Starlette middleware and endpoint handlers that strictly enforce `ALLOWED_METHODS = ["GET"]` and return standard HTTP 405 error envelopes for any mutating verb (`POST`, `PUT`, `DELETE`, `PATCH`).
3. **Docker Compose Multi-Container Topology**: Transitioning from a single-container static Nginx container to a production 3-tier topology (`nginx` reverse proxy & static frontend, `api` FastAPI container with multi-stage non-root Python build, `postgres` 16 with healthchecks and persistent volumes).
4. **Test Suite & Coverage Gap Analysis**: Analyzing the current suite (119 E2E tests across 9 modules in `tests/run_e2e_tests.py`, 120 pytest items) and mapping complete 5-tier test specifications and coverage gaps for requirements R1-R4 to ensure 100% test pass rate.

---

## 2. Background Ingestion Engine Architecture (Requirement R3)

### 2.1 Current State vs. Target Architecture

| Dimension | Current Legacy Implementation | Target Enterprise Implementation |
|---|---|---|
| **Scheduler Engine** | Python `threading.Thread` loop in `scripts/start_server.py` | Embedded `APScheduler` (`AsyncIOScheduler`) in FastAPI lifespan |
| **Execution Trigger** | `time.sleep(600)` blocking thread loop | `IntervalTrigger(minutes=10)` / cron cadence |
| **Execution Mechanism**| `subprocess.run(["python", "scripts/run_sync.py", ...])` | Async Python service method `SyncService.execute_full_sync()` |
| **Concurrency Guard** | None (risk of race conditions if multiple workers run) | PostgreSQL Advisory Locks (`pg_try_advisory_lock(1048576)`) |
| **Persistence Target**| Static JSON files (`data/intune_summary.json`, etc.) | Relational DB tables (`configuration_items`, `ci_status_history`) |
| **History Strategy** | Overwrites JSON snapshot, zero historical tracking | Append-only time-series in `ci_status_history` on state delta |
| **Audit Logging** | Plaintext log files (`itom_server.log`, `itom_cron.log`) | Relational audit tables (`sync_runs`, `sync_error_logs`) |

### 2.2 APScheduler ASGI Lifespan Integration

To ensure zero-broker deployment on local private server infrastructure without requiring external message brokers (such as Celery/Redis/RabbitMQ), `APScheduler` is embedded directly into FastAPI's `lifespan` context manager in `app/core/scheduler.py`:

```python
# app/core/scheduler.py
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.sync_service import SyncService

logger = logging.getLogger("itom.scheduler")
scheduler = AsyncIOScheduler()

async def scheduled_telemetry_sync():
    """Execute scheduled 10-minute telemetry synchronization."""
    logger.info("Triggering scheduled 10-minute ITOM telemetry synchronization...")
    sync_service = SyncService()
    await sync_service.run_ingestion_with_lock()

def start_scheduler():
    """Register and start the async background scheduler."""
    scheduler.add_job(
        scheduled_telemetry_sync,
        trigger=IntervalTrigger(minutes=10),
        id="telemetry_sync_10m",
        name="10-Minute Multi-Domain Telemetry Ingestion",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("APScheduler initialized: 10-minute telemetry ingestion cadence active.")

def shutdown_scheduler():
    """Gracefully shutdown background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down gracefully.")
```

### 2.3 Multi-Worker Concurrency Guard (PostgreSQL Advisory Locks)

In production deployments with multi-worker ASGI processes (`uvicorn app.main:app --workers 4`), multiple worker processes would each run an `AsyncIOScheduler` instance, causing 4 concurrent ingestion jobs every 10 minutes.

**Solution**: PostgreSQL Session-Level Advisory Locks:
- Constant Advisory Lock Key: `1048576` (32-bit integer or 64-bit bigint identifier).
- Ingestion worker queries `SELECT pg_try_advisory_lock(1048576);`.
- If `True`: The current worker holds exclusive lock and executes the ETL ingestion.
- If `False`: Another worker is currently executing the sync; current worker skips execution with log `Advisory lock 1048576 held by peer worker. Skipping run.`.
- In a `finally` block, the executing worker releases the lock via `SELECT pg_advisory_unlock(1048576);`.

```python
# PostgreSQL Advisory Lock Pattern in app/services/sync_service.py
from sqlalchemy import text
from app.core.database import async_session_factory

class SyncService:
    ADVISORY_LOCK_ID = 1048576

    async def run_ingestion_with_lock(self) -> None:
        async with async_session_factory() as session:
            # Attempt to acquire non-blocking advisory lock
            result = await session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": self.ADVISORY_LOCK_ID}
            )
            acquired = result.scalar()
            if not acquired:
                logger.info("Sync job already running on another worker (Lock %s held). Skipping.", self.ADVISORY_LOCK_ID)
                return

            try:
                logger.info("Advisory lock %s acquired. Executing ingestion pipeline...", self.ADVISORY_LOCK_ID)
                await self.execute_full_sync(session)
            finally:
                await session.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": self.ADVISORY_LOCK_ID}
                )
                await session.commit()
                logger.info("Advisory lock %s released.", self.ADVISORY_LOCK_ID)
```

### 2.4 State Delta Detection & Time-Series History

To avoid unbounded table growth and redundant I/O during 10-minute syncs:
1. Extract current state of CI from external API (Intune / SolarWinds).
2. Query existing CI record in `configuration_items`.
3. If CI does not exist: Insert into `configuration_items`, insert initial snapshot into `ci_status_history`.
4. If CI exists: Compute SHA-256 fingerprint of volatile operational state:
   $$\text{State Hash} = \text{SHA256}(\text{status} + \text{health\_tier} + \text{cpu\_load} + \text{ram\_used} + \text{storage\_used})$$
5. If state hash matches previous state: Update `last_sync_time` on `configuration_items` without writing a new history record.
6. If state hash differs: Update `configuration_items` and append a new row to `ci_status_history`.

### 2.5 Execution Audit Logging Schema (`sync_runs` & `sync_error_logs`)

```sql
-- PostgreSQL 16 Audit Logging DDL
CREATE TABLE sync_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system VARCHAR(32) NOT NULL, -- 'SOLARWINDS', 'INTUNE', 'CMDB_COMBINED'
    status VARCHAR(32) NOT NULL,        -- 'SUCCESS', 'FAILED', 'PARTIAL'
    records_processed INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE sync_error_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_run_id UUID REFERENCES sync_runs(id) ON DELETE CASCADE,
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sync_runs_source_started ON sync_runs(source_system, started_at DESC);
CREATE INDEX idx_sync_error_logs_run_id ON sync_error_logs(sync_run_id);
```

---

## 3. Read-Only SWQL Validation & HTTP 405 Guard Architecture (Requirement R3)

### 3.1 Security Principle & Zero Upstream Mutation

The ITOM platform is an observability and analytics system operating against production infrastructure monitoring databases (SolarWinds Orion SWIS API) and directory management (Microsoft Graph API). Under no circumstance may any API request, user action, or background task issue a mutating command (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `EXEC`) to upstream systems.

### 3.2 SWQL Validator Implementation

The SWQL query validator in `app/core/security.py` validates all outgoing queries before dispatch:
- **Allowed HTTP Method**: Strictly `["GET"]`.
- **Forbidden SWQL/SQL Keywords**: `{"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "MERGE"}`.
- **Comment Stripping**: Removes single-line comments (`--`) and multi-line comments (`/* ... */`) before evaluating tokens.
- **Starting Token Check**: The trimmed query must strictly begin with `SELECT`.
- **Token Boundary Check**: Forbidden keywords are checked as discrete words (`\bKEYWORD\b`) to avoid false positives on legitimate column names (e.g., `UpdatedDate`).

### 3.3 HTTP 405 REST Guard Middleware & Route Rejection

All state-modifying HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`) targeting SolarWinds, Intune, or CMDB routes return HTTP 405 Method Not Allowed with standardized JSON envelope:

```json
{
  "error": "Forbidden: Upstream monitoring integration is strictly READ-ONLY.",
  "allowed_methods": ["GET"]
}
```

```python
# app/core/security.py
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

READONLY_METHODS = {"GET", "HEAD", "OPTIONS"}
FORBIDDEN_MUTATION_ENVELOPE = {
    "error": "Forbidden: Upstream monitoring integration is strictly READ-ONLY.",
    "allowed_methods": ["GET"]
}

async def enforce_readonly_monitoring_guard(request: Request):
    """Dependency / Middleware guarding read-only upstream integrations."""
    if request.method.upper() not in READONLY_METHODS:
        return JSONResponse(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            content=FORBIDDEN_MUTATION_ENVELOPE,
            headers={"Allow": "GET, HEAD, OPTIONS"}
        )
```

---

## 4. Docker Compose Multi-Container Topology (Requirement R4)

### 4.1 Topology Diagram

```
                             [ Client Browser / OPS Team ]
                                           │
                                           ▼ :8080
                    ┌──────────────────────────────────────────────┐
                    │               Nginx Container                │
                    │               (nginx:alpine)                 │
                    │  - Serves Obsidian UI static files (/)       │
                    │  - Reverse proxies /api/ -> api:8000/api/    │
                    │  - Gzip compression & Security Headers       │
                    └──────────────────────┬───────────────────────┘
                                           │ internal network
                                           ▼ :8000
                    ┌──────────────────────────────────────────────┐
                    │            FastAPI Backend Container         │
                    │         (Python 3.11-slim, Non-Root)         │
                    │  - REST Endpoints (/api/v1/*)                │
                    │  - Embedded APScheduler 10m Ingestion Worker │
                    │  - Read-Only Security Guard Middleware       │
                    │  - Healthchecks (/healthz, /ready)           │
                    └──────────────────────┬───────────────────────┘
                                           │ internal network
                                           ▼ :5432
                    ┌──────────────────────────────────────────────┐
                    │             PostgreSQL 16 Container          │
                    │             (postgres:16-alpine)             │
                    │  - Relational persistence                    │
                    │  - Time-series status history                │
                    │  - Volume: postgres_data                     │
                    │  - Healthcheck: pg_isready                   │
                    └──────────────────────────────────────────────┘
```

### 4.2 Multi-Stage Production Dockerfile

```dockerfile
# docker/Dockerfile
# Multi-stage production build for ITOM FastAPI Backend

# --- Stage 1: Build & Dependencies ---
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Stage 2: Minimal Runtime ---
FROM python:3.11-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root system user and group
RUN groupadd -g 10001 itom && \
    useradd -u 10001 -g itom -m -s /bin/bash itom

# Copy Python packages from builder
COPY --from=builder /root/.local /home/itom/.local
ENV PATH=/home/itom/.local/bin:$PATH
ENV PYTHONPATH=/app

# Copy application source
COPY --chown=itom:itom . /app

USER itom

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.3 Multi-Container `docker-compose.yml`

```yaml
# docker/docker-compose.yml
version: "3.8"

networks:
  itom-network:
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
      POSTGRES_USER: ${POSTGRES_USER:-itom_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-itom_secure_password}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - itom-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-itom_user} -d ${POSTGRES_DB:-itom_db}"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: itom-api
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-itom_user}:${POSTGRES_PASSWORD:-itom_secure_password}@postgres:5432/${POSTGRES_DB:-itom_db}
      ENVIRONMENT: production
      PORT: 8000
      AZURE_TENANT_ID: ${AZURE_TENANT_ID}
      AZURE_CLIENT_ID: ${AZURE_CLIENT_ID}
      AZURE_CLIENT_SECRET: ${AZURE_CLIENT_SECRET}
      SOLARWINDS_HOST: ${SOLARWINDS_HOST}
      SOLARWINDS_PORT: ${SOLARWINDS_PORT:-17774}
      SOLARWINDS_USERNAME: ${SOLARWINDS_USERNAME}
      SOLARWINDS_PASSWORD: ${SOLARWINDS_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - itom-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s

  nginx:
    image: nginx:alpine
    container_name: itom-nginx
    restart: unless-stopped
    ports:
      - "${PORT:-8080}:80"
    volumes:
      - ../index.html:/usr/share/nginx/html/index.html:ro
      - ../ops_analytics.html:/usr/share/nginx/html/ops_analytics.html:ro
      - ../style.css:/usr/share/nginx/html/style.css:ro
      - ../app.js:/usr/share/nginx/html/app.js:ro
      - ../ops_analytics.js:/usr/share/nginx/html/ops_analytics.js:ro
      - ../logo.png:/usr/share/nginx/html/logo.png:ro
      - ../js:/usr/share/nginx/html/js:ro
      - ../data:/usr/share/nginx/html/data:ro
      - ../exports:/usr/share/nginx/html/exports:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      api:
        condition: service_healthy
    networks:
      - itom-network
```

### 4.4 Nginx Reverse Proxy Configuration (`docker/nginx.conf`)

```nginx
# docker/nginx.conf
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Gzip Compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;
    gzip_min_length 1000;
    gzip_proxied any;

    # HTTP Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # API Reverse Proxy Routing
    location /api/ {
        proxy_pass http://api:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 90s;
    }

    # Static Files Caching & Fallback
    location / {
        try_files $uri $uri/ /index.html;
        expires 1h;
        add_header Cache-Control "public, no-transform";
    }

    # Dynamic JSON data anti-cache
    location ~* \.(json)$ {
        expires -1;
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
    }
}
```

### 4.5 Healthcheck & Readiness Probes (`/healthz` and `/ready`)

- `GET /healthz`: Liveness probe. Returns HTTP 200 `{"status": "ok", "timestamp": "2026-09-02T06:00:00Z"}`.
- `GET /ready`: Readiness probe. Executes `SELECT 1` on the PostgreSQL async engine and verifies current Alembic migration version. Returns HTTP 200 `{"status": "ready", "database": "connected", "migration_head": true}` or HTTP 503 `{"status": "unhealthy", "database": "disconnected"}`.

---

## 5. Existing Test Suite Analysis

### 5.1 Test Suite Inventory (119 Tests in `run_e2e_tests.py`, 120 in pytest)

| Suite Name | Test Class(es) | Count | Duration | Status |
|---|---|:---:|:---:|:---:|
| **Data Integrity & Invariants (Intune)** | `TestIntuneDataIntegrity` | 8 | 0.149s | 100% Pass |
| **Data Integrity & Invariants (SolarWinds)** | `TestSolarWindsDataInvariants` | 6 | 0.013s | 100% Pass |
| **Payload Engine & Normalization** | `TestManufacturerNormalization`, `TestStorageCalculations`, `TestSampleRecordGeneration`, `TestPayloadGenerationIntegration` | 14 | 0.000s | 100% Pass |
| **Tab Navigation, Routing, Search & CSV** | `TestTabNavigationHTMLStructure`, `TestTabRouterController`, `TestSearchFilterEngine`, `TestCSVExportCompliance`, `TestLauncherBridge` | 15 | 0.008s | 100% Pass |
| **Real-World Enterprise Scenarios (Tier 4)** | `TestScenario1` through `TestScenario5` | 14 | 0.724s | 100% Pass |
| **Adversarial Hardening: UI & Routing** | `TestAdversarialUrlHashRouting`, `TestConcurrentTabTransitions`, `TestSearchBarMaliciousInjectionFuzzing`, `TestTableFilteringScale`, `TestCsvExportRfc4180`, `TestChartJsLifecycle`, `TestDOMSecurity` | 23 | 0.337s | 100% Pass |
| **Adversarial Hardening: Invariants & Sync** | `TestTier5InvariantFuzzing`, `TestTier5ManufacturerNormalizationPermutations`, `TestTier5ComplianceAndPrecisionMath`, `TestTier5SyncPipelineResilience`, `TestTier5AuthoritativeDatasetReconciliation` | 22 | 0.195s | 100% Pass |
| **Adversarial Security: XSS & Secrets** | `TestHostileXSSAndDOMSanitization`, `TestRFC4180CSVExportCompliance`, `TestUIRoutingAndMemoryGuards`, `TestRepositorySecretScan` | 11 | 2.796s | 100% Pass |
| **Zero-Build Architecture Compliance** | `TestZeroBuildCompliance` | 6 | 0.015s | 100% Pass |
| **Server Resilience & Live CMDB** | `TestSolarWindsSecurityGuards`, `TestCIClassification`, `test_dynamic_ip_resolution`, `test_systemd_service_file_specifications` | 1 | 5.71s | 100% Pass |
| **Total** | | **120** | **9.95s** | **100% PASS** |

---

## 6. Coverage Gap Matrix & TDD Implementation Strategy for R1-R4

### 6.1 Requirements Coverage Gap Matrix

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       COVERAGE GAP ANALYSIS (R1 - R4)                       │
├────────────┬─────────────────────────────┬──────────┬───────────────────────┤
│ Req ID     │ Description                 │ Current  │ Required Target Tests │
│            │                             │ Status   │                       │
├────────────┼─────────────────────────────┼──────────┼───────────────────────┤
│ R1: DB     │ PostgreSQL 16 Models,       │ GAP      │ 15 new tests in       │
│            │ Alembic Migrations,         │          │ test_database_        │
│            │ Bulk Seeding Parity         │          │ persistence.py        │
├────────────┼─────────────────────────────┼──────────┼───────────────────────┤
│ R2: API    │ FastAPI Endpoints,          │ GAP      │ 25 new tests in       │
│            │ Freshness Headers,          │          │ test_fastapi_         │
│            │ Sub-20ms Pagination         │          │ backend.py            │
├────────────┼─────────────────────────────┼──────────┼───────────────────────┤
│ R3: Sync   │ APScheduler Lifespan,       │ GAP      │ 15 new tests in       │
│            │ Advisory Locks, Delta Hash, │          │ test_background_sync_ │
│            │ HTTP 405 Method Blocker     │          │ security.py           │
├────────────┼─────────────────────────────┼──────────┼───────────────────────┤
│ R4: Docker │ Dockerfile Multi-Stage,     │ GAP      │ 10 new tests in       │
│            │ Docker Compose, Probes      │          │ test_docker_infra_    │
│            │ (/healthz, /ready)          │          │ compliance.py         │
└────────────┴─────────────────────────────┴──────────┴───────────────────────┘
```

### 6.2 Detailed Gap Breakdown & Test Specifications

#### Gap 1: Database Persistence & Migrations (R1)
- **Target Test File**: `tests/test_database_persistence.py`
- **Tests to Implement**:
  1. `test_alembic_upgrade_head_and_downgrade_base()`: Verifies full schema migration creation and rollback without errors.
  2. `test_ci_model_crud_and_unique_constraints()`: Verifies `ConfigurationItem` creation, composite uniqueness `(source_system, source_id)`.
  3. `test_ci_relationships_foreign_key_cascades()`: Verifies graph relationships between CIs with foreign key integrity.
  4. `test_ci_status_history_append_only()`: Verifies status snapshots accumulate over time linked to `ci_id`.
  5. `test_sync_runs_and_error_logs_fk_integrity()`: Verifies `sync_runs` tracking and `sync_error_logs` cascade delete.
  6. `test_bulk_streaming_seed_mathematical_invariants()`: Verifies seeding all 25,987 Intune devices and 1,543 SolarWinds CIs matches raw counts with zero data loss.

#### Gap 2: FastAPI Asynchronous REST Backend (R2)
- **Target Test File**: `tests/test_fastapi_backend.py`
- **Tests to Implement**:
  1. `test_cmdb_paginated_endpoints_envelope()`: Verifies `/api/v1/cmdb/cis` returns items, total, page, total_pages, and sub-20ms query time.
  2. `test_intune_endpoints_invariants_parity()`: Verifies `/api/v1/intune/summary` returns exact counts (25,987 devices, 21,589 compliant, 37.4% storage).
  3. `test_solarwinds_endpoints_health_breakdown()`: Verifies `/api/v1/solarwinds/summary` returns 1,548 nodes (1,357 High, 150 Medium, 41 Low).
  4. `test_freshness_middleware_headers_fresh_sla()`: Verifies responses contain `X-Last-Synchronized-At`, `X-Data-Age-Seconds`, and `X-Sync-Status: FRESH` when age $\le 900\text{s}$.
  5. `test_freshness_middleware_headers_stale_sla()`: Verifies `X-Sync-Status: STALE` when age $> 900\text{s}$ (15m SLA).
  6. `test_pagination_parameter_validation()`: Verifies 422 Unprocessable Entity on negative page or page_size > 1000.

#### Gap 3: Background Ingestion Engine & Read-Only Security (R3)
- **Target Test File**: `tests/test_background_sync_security.py`
- **Tests to Implement**:
  1. `test_apscheduler_lifecycle_and_interval()`: Verifies scheduler registration with 10-minute cadence.
  2. `test_postgresql_advisory_lock_concurrency()`: Simulates 2 concurrent worker calls, asserts only 1 executes ETL while second skips.
  3. `test_delta_change_detection_avoids_redundant_history()`: Verifies identical telemetry leaves `ci_status_history` count unchanged.
  4. `test_delta_change_detection_logs_modified_attributes()`: Verifies changed CPU/RAM creates a new history record.
  5. `test_http_405_mutation_guard_all_verbs()`: Sends `POST`, `PUT`, `DELETE`, `PATCH` to `/api/v1/solarwinds/*`, `/api/v1/intune/*`, `/api/v1/cmdb/*` and asserts HTTP 405 + JSON envelope.
  6. `test_swql_validator_blocks_injection_and_ddl()`: Asserts `validate_swql_read_only` rejects `INSERT`, `UPDATE`, `DELETE`, `DROP`, `-- DELETE`, `/* DELETE */`.
  7. `test_sync_error_log_captures_exceptions_and_traceback()`: Injects network failure and verifies `sync_error_logs` record creation.

#### Gap 4: Docker Compose Multi-Container Topology (R4)
- **Target Test File**: `tests/test_docker_infra_compliance.py`
- **Tests to Implement**:
  1. `test_dockerfile_multi_stage_and_non_root_user()`: Inspects `docker/Dockerfile` ensuring multi-stage build and `USER itom`.
  2. `test_docker_compose_service_topology()`: Parses `docker/docker-compose.yml` asserting `postgres`, `api`, `nginx`, healthchecks, networks, volumes.
  3. `test_nginx_reverse_proxy_routing_and_gzip()`: Validates `docker/nginx.conf` routing rules and security headers.
  4. `test_liveness_healthz_endpoint()`: Tests `GET /healthz` returns HTTP 200.
  5. `test_readiness_ready_endpoint_db_probe()`: Tests `GET /ready` returns HTTP 200 when DB is active and HTTP 503 when DB is down.

---

## 7. Recommended Implementation Sequence for Workers

1. **M1 (Database Layer & Seeding)**:
   - Establish `app/models/ci.py`, `app/models/sync.py`, `app/core/database.py`.
   - Setup Alembic migration in `alembic/versions/001_initial_schema.py`.
   - Implement `scripts/seed_database.py` and run migration against PostgreSQL.
   - Run `tests/test_database_persistence.py`.

2. **M2 (FastAPI REST Backend & Freshness Headers)**:
   - Implement `app/main.py`, `app/api/v1/endpoints/cmdb.py`, `intune.py`, `solarwinds.py`, `sync.py`, `system.py`.
   - Implement Freshness Middleware in `app/core/middleware.py`.
   - Run `tests/test_fastapi_backend.py`.

3. **M3 (Background Ingestion Engine & Security Guards)**:
   - Implement `app/core/scheduler.py`, `app/services/sync_service.py` with advisory locks.
   - Implement Read-Only SWQL validation and HTTP 405 error envelopes in `app/core/security.py`.
   - Run `tests/test_background_sync_security.py`.

4. **M4 (Docker Multi-Container Stack)**:
   - Create `docker/Dockerfile`, `docker/docker-compose.yml`, `docker/nginx.conf`.
   - Implement `/healthz` and `/ready` probes.
   - Run `tests/test_docker_infra_compliance.py`.

5. **M5 (Full E2E Verification)**:
   - Update master test runner `tests/run_e2e_tests.py` to include all new backend suites alongside existing 119 E2E tests.
   - Verify 100% pass rate.
