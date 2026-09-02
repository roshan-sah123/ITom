---
name: backend-engineering
description: Enterprise backend architecture, asynchronous FastAPI patterns, PostgreSQL 16 relational data persistence, time-series history, strict read-only external integrations, and resilient background synchronization.
---

# Enterprise Backend Architecture & Data Platform Skill

## 1. Scope & Core Principles
This skill defines industry-standard backend engineering standards for private/local enterprise servers, IT Operations Management (ITOM) platforms, and CMDB telemetry engines.

### Architectural Invariants:
1. **Clean Layered Architecture**: Strict separation of concerns (`api/v1` → `services` → `repositories` → `integrations` → `database`).
2. **Zero Upstream Mutation**: Strict read-only boundaries for monitoring integrations (SolarWinds SWIS v3, Microsoft Graph API).
3. **Data Persistence Guarantee**: All operational metrics, CIs, relationships, and execution histories must persist in relational storage (PostgreSQL 16).
4. **Data Freshness Contract**: Every response must return authoritative freshness metadata (`last_synchronized_at`, `data_age_seconds`, `sync_status`).

---

## 2. API Contract & Response Envelopes

### Standard Paginated Collection Envelope
```json
{
  "status": "success",
  "data": {
    "items": [...],
    "pagination": {
      "total_records": 25987,
      "page": 1,
      "page_size": 50,
      "total_pages": 520,
      "has_next": true,
      "has_prev": false
    },
    "freshness": {
      "last_synchronized_at": "2026-09-02T05:30:00Z",
      "data_age_seconds": 124,
      "sync_status": "HEALTHY",
      "source_mode": "LIVE_MIRROR"
    }
  }
}
```

### Strict Read-Only Mutation Blocker
All state-modifying requests (`POST`, `PUT`, `DELETE`, `PATCH`) targeting read-only upstream integrations must return:
```json
{
  "error": "Forbidden: Upstream monitoring integration is strictly READ-ONLY.",
  "allowed_methods": ["GET"]
}
```
HTTP Status Code: `405 Method Not Allowed`.

---

## 3. Database Modeling & Time-Series Strategy

```text
PostgreSQL 16 Relational Schema Structure:
├── configuration_items      : Authoritative current state (ci_id, name, type, ip, vendor, health_tier)
├── ci_relationships         : Topology mapping (source_ci_id, target_ci_id, relationship_type)
├── ci_status_history        : Append-only time-series (ci_id, recorded_at, status, cpu, ram, latency)
├── sync_runs                : Execution telemetry (run_id, source, started_at, completed_at, status)
└── sync_error_logs          : Diagnostic audit trail (error_id, run_id, error_code, error_message, stack)
```

* **Schema Evolution & Migrations**:
  - All database schema modifications must be tracked version-by-version using **Alembic** (`alembic upgrade head`).
  - Never run manual unversioned `CREATE TABLE` or `ALTER TABLE` DDL directly in production.

---

## 4. Resilient Background Synchronization Engine

* **Scheduler**: Use `APScheduler` (`AsyncIOScheduler`) embedded within the ASGI lifespan for zero-broker local VM deployments.
* **Worker Execution Invariants**:
  - Run sync every 10 minutes (600 seconds).
  - Wrap external network calls in exponential backoff retry adapters (`max_retries=3`, `backoff_factor=0.5`).
  - Perform delta comparison before writing to history tables to minimize unnecessary storage growth.
  - Record execution duration and record counts in `sync_runs`.
  - **Multi-Worker Concurrency Guard**: In multi-process ASGI configurations (`--workers > 1`), synchronize worker jobs using PostgreSQL advisory locks (`SELECT pg_try_advisory_lock(1048576)`) to ensure exactly-once sync execution.

---

## 5. Security & Deployment

* **Environment Isolation**: Read all credentials from `.env` or container environment variables via Pydantic `BaseSettings`.
* **Containerization**: Deploy via Docker Compose (`Nginx` reverse proxy + `FastAPI` + `PostgreSQL 16`).

