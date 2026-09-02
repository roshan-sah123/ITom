# Comprehensive Backend Architecture Survey & Technical Blueprint

**Author**: `explorer_survey_backend` (Backend Architecture Explorer)  
**Date**: 2026-09-02  
**Status**: Authoritative Blueprint  
**Target Platform**: ITOM Operations Analytics & Enterprise CMDB Platform  

---

## 1. Executive Summary & Problem Boundary

The ITOM platform is transitioning from an initial flat-file JSON and standard library HTTP server (`scripts/start_server.py`) to a production-grade, persistent, asynchronous enterprise backend running on private/local server infrastructure.

This survey establishes the complete technical blueprint and architectural specification for:
1. **Clean Layered FastAPI Async Architecture** (`app/api/v1`, `app/services`, `app/repositories`, `app/integrations`, `app/models`, `app/schemas`, `app/core`).
2. **PostgreSQL 16 Relational Persistence Layer** supporting current state configuration items (`configuration_items`, `ci_relationships`), append-only time-series status history (`ci_status_history`), sync execution runs (`sync_runs`), and diagnostic error logs (`sync_error_logs`).
3. **Alembic Database Migration Pipeline** with async SQLAlchemy 2.0 and `asyncpg` connection pooling.
4. **Paginated REST Endpoints** across CMDB, Microsoft Intune, and SolarWinds domains returning standard data freshness response headers.
5. **Security Enforcers & Read-Only Boundaries** blocking mutating HTTP verbs (`POST`, `PUT`, `DELETE`, `PATCH`) with HTTP 405 Method Not Allowed and enforcing read-only SWQL validation.
6. **Sub-20ms Query Optimization** via composite B-tree, covering, and GIN trigram indexes with multi-process PostgreSQL advisory locks.
7. **Zero-Loss Seeding and Reconciliation** guaranteeing mathematical parity across 25,987 Intune devices and 1,548 SolarWinds nodes (1,543 active CIs).

---

## 2. Current State vs. Target State Analysis

### 2.1 Current Architecture Survey

| Dimension | Current Implementation (`src/`, `scripts/`, `data/`) | Architectural Limitation / Gap |
| :--- | :--- | :--- |
| **Persistence Layer** | Flat-file JSON snapshots (`data/cmdb_summary.json`, `data/intune_ops_analytics.json`, `data/solarwinds_nodes.json`). | No relational integrity, lack of concurrent write locks, unbounded file memory growth, no transaction boundaries, no point-in-time rollback. |
| **Web Server** | `http.server.HTTPServer` with `ThreadingMixIn` (`scripts/start_server.py`). | Synchronous thread-per-request blocking I/O, lacks OpenAPI/Swagger documentation, manual string query parsing, no input schema validation (Pydantic). |
| **Time-Series Tracking** | Static snapshots overwriting previous state via atomic rename (`atomic_json_dump`). | Historical telemetry deltas and trend analysis are completely lost between sync intervals. |
| **Schema Migrations** | None. Unversioned schema evolution. | Impossible to version database structures or safely deploy schema changes across test/staging/production environments. |
| **Background Processing** | Uncoordinated Python `threading.Thread` loop in server process (`scripts/start_server.py:350`). | Vulnerable to worker collision and duplicate sync executions when scaled across multiple ASGI server workers. |

### 2.2 Target Clean Architecture Blueprint

```
app/
├── __init__.py
├── main.py                     # FastAPI app factory, lifespan, CORS, routers, exception handlers
├── core/
│   ├── __init__.py
│   ├── config.py               # Settings management via pydantic-settings (.env parsing)
│   ├── database.py             # Async SQLAlchemy engine, async_sessionmaker, connection pool
│   ├── logging.py              # Structured JSON logging configuration
│   ├── security.py             # SWQL read-only validator & HTTP 405 security enforcers
│   ├── middleware.py           # Freshness headers injection & request timing middleware
│   └── scheduler.py            # APScheduler (AsyncIOScheduler) with PostgreSQL advisory lock
├── api/
│   ├── __init__.py
│   ├── deps.py                 # Dependency injection (AsyncSession, PaginationParams)
│   └── v1/
│       ├── __init__.py
│       ├── api.py              # Central APIRouter mounting all v1 endpoint routers
│       └── endpoints/
│           ├── __init__.py
│           ├── cmdb.py         # /api/v1/cmdb/* (CIs, relationships, summary, breakdown)
│           ├── intune.py       # /api/v1/intune/* (devices, summary, breakdowns, metrics)
│           ├── solarwinds.py   # /api/v1/solarwinds/* (nodes, summary, degraded servers)
│           ├── sync.py         # /api/v1/sync/* (runs, error logs, manual trigger)
│           └── system.py       # /healthz (liveness), /ready (readiness), /metrics
├── models/
│   ├── __init__.py
│   ├── base.py                 # DeclarativeBase, UUIDPrimaryKeyMixin, TimestampMixin
│   ├── ci.py                   # ConfigurationItem, CIRelationship, CIStatusHistory
│   └── sync.py                 # SyncRun, SyncErrorLog
├── schemas/
│   ├── __init__.py
│   ├── common.py               # PaginationParams, PaginatedResponseEnvelope, FreshnessMetadata
│   ├── cmdb.py                 # CIRead, CIRelationshipRead, CMDBSummaryRead
│   ├── intune.py               # IntuneDeviceRead, IntuneMetricsRead, BreakdownRead
│   ├── solarwinds.py           # SolarWindsNodeRead, SolarWindsSummaryRead, DegradedNodeRead
│   └── sync.py                 # SyncRunRead, SyncRunCreate, SyncErrorLogRead
├── repositories/
│   ├── __init__.py
│   ├── base.py                 # Generic Async BaseRepository (CRUD, paginate, count)
│   ├── ci_repository.py        # CI filtering, full-text trigram search, status history logging
│   └── sync_repository.py      # SyncRun tracking, latest run lookup, error logging
├── services/
│   ├── __init__.py
│   ├── cmdb_service.py         # CMDB business logic, aggregations, relationship traversal
│   ├── intune_service.py       # Intune analytics calculation & mathematical invariant validation
│   ├── solarwinds_service.py   # SolarWinds health classification & resource pressure ranking
│   └── sync_service.py         # Multi-domain ETL pipeline, delta detection, advisory locking
└── integrations/
    ├── __init__.py
    ├── graph_client.py         # Async/sync Microsoft Graph client with OAuth token caching
    ├── solarwinds_client.py    # SolarWinds SWIS client with strict SWQL SELECT enforcement
    └── normalizers.py          # OEM manufacturer, OS, vendor, and health tier normalizers
```

---

## 3. PostgreSQL 16 Relational Persistence Layer

### 3.1 Relational Schema Architecture & DDL

The database persistence layer is modeled around five high-performance tables with foreign keys, composite indexes, and JSONB flex fields:

```
+-----------------------------------------------------------------------------------+
|                               configuration_items                                 |
+-----------------------------------------------------------------------------------+
| * id: UUID (PK)                                                                   |
| * source_id: VARCHAR(128) [Indexed]                                               |
| * source_system: VARCHAR(32) [Enum: SOLARWINDS, INTUNE]                           |
| * name: VARCHAR(255) [Indexed]                                                    |
| * ci_type: VARCHAR(64) [Indexed]                                                  |
| * status: VARCHAR(32) [Indexed]                                                   |
| * health_tier: VARCHAR(16) [Indexed: High, Medium, Low]                           |
| * ip_address: VARCHAR(64) [Indexed]                                               |
| * vendor: VARCHAR(64) [Indexed]                                                   |
| * model: VARCHAR(128)                                                             |
| * serial_number: VARCHAR(128) [Indexed]                                           |
| * operating_system: VARCHAR(128)                                                  |
| * location: VARCHAR(128)                                                          |
| * last_sync_time: TIMESTAMPTZ                                                     |
| * state_hash: VARCHAR(64)                                                         |
| * attributes: JSONB                                                               |
| * created_at: TIMESTAMPTZ                                                         |
| * updated_at: TIMESTAMPTZ                                                         |
+-----------------------------------------------------------------------------------+
       | 1                                       | 1                       | 1
       |                                         |                         |
       | 0..* (source_ci_id)                     | 0..* (target_ci_id)     | 0..* (ci_id)
       v                                         v                         v
+-----------------------------+          +-------------------+     +-----------------------------+
|       ci_relationships      |          |  ci_relationships |     |      ci_status_history      |
+-----------------------------+          +-------------------+     +-----------------------------+
| * id: UUID (PK)             |                                    | * id: UUID (PK)             |
| * source_ci_id: UUID (FK)   |                                    | * ci_id: UUID (FK, Indexed) |
| * target_ci_id: UUID (FK)   |                                    | * status: VARCHAR(32)       |
| * relationship_type: VARCHAR|                                    | * health_tier: VARCHAR(16)  |
| * attributes: JSONB         |                                    | * cpu_utilization: FLOAT    |
| * created_at: TIMESTAMPTZ   |                                    | * memory_utilization: FLOAT |
+-----------------------------+                                    | * storage_used_pct: FLOAT   |
                                                                   | * latency_ms: FLOAT         |
                                                                   | * recorded_at: TIMESTAMPTZ  |
                                                                   +-----------------------------+

+-------------------------------------------------------------+
|                          sync_runs                          |
+-------------------------------------------------------------+
| * id: UUID (PK)                                             |
| * source_system: VARCHAR(32) [SOLARWINDS, INTUNE, ALL]      |
| * status: VARCHAR(32) [SUCCESS, FAILED, PARTIAL, RUNNING]   |
| * records_processed: INTEGER                                |
| * records_updated: INTEGER                                  |
| * records_unchanged: INTEGER                                |
| * duration_ms: INTEGER                                      |
| * started_at: TIMESTAMPTZ                                   |
| * completed_at: TIMESTAMPTZ                                 |
+-------------------------------------------------------------+
       | 1
       | 0..* (sync_run_id)
       v
+-------------------------------------------------------------+
|                       sync_error_logs                       |
+-------------------------------------------------------------+
| * id: UUID (PK)                                             |
| * sync_run_id: UUID (FK, Indexed)                           |
| * error_code: VARCHAR(64)                                   |
| * error_message: TEXT                                       |
| * stack_trace: TEXT                                         |
| * context_data: JSONB                                       |
| * created_at: TIMESTAMPTZ                                   |
+-------------------------------------------------------------+
```

### 3.2 SQLAlchemy 2.0 Async Models Definition

```python
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    String, Text, Float, Integer, DateTime, ForeignKey, 
    Index, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ConfigurationItem(Base):
    __tablename__ = "configuration_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)  # "SOLARWINDS" | "INTUNE"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ci_type: Mapped[str] = mapped_column(String(64), nullable=False)        # "Server", "Access Switch", etc.
    status: Mapped[str] = mapped_column(String(32), nullable=False)         # "Up", "Down", "Compliant", etc.
    health_tier: Mapped[str] = mapped_column(String(16), nullable=False)    # "High", "Medium", "Low"
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False, default="Other")
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    operating_system: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_sync_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    state_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    status_history: Mapped[List["CIStatusHistory"]] = relationship("CIStatusHistory", back_populates="ci", cascade="all, delete-orphan")
    outgoing_relationships: Mapped[List["CIRelationship"]] = relationship("CIRelationship", foreign_keys="CIRelationship.source_ci_id", back_populates="source_ci")
    incoming_relationships: Mapped[List["CIRelationship"]] = relationship("CIRelationship", foreign_keys="CIRelationship.target_ci_id", back_populates="target_ci")

    __table_args__ = (
        UniqueConstraint("source_system", "source_id", name="uq_ci_source_system_source_id"),
        Index("ix_ci_source_system_type_status", "source_system", "ci_type", "status"),
        Index("ix_ci_health_tier", "health_tier"),
        Index("ix_ci_ip_address", "ip_address"),
        Index("ix_ci_vendor", "vendor"),
        Index("ix_ci_serial_number", "serial_number"),
    )


class CIRelationship(Base):
    __tablename__ = "ci_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), nullable=False)
    target_ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)  # "located_at", "depends_on", etc.
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    source_ci: Mapped["ConfigurationItem"] = relationship("ConfigurationItem", foreign_keys=[source_ci_id], back_populates="outgoing_relationships")
    target_ci: Mapped["ConfigurationItem"] = relationship("ConfigurationItem", foreign_keys=[target_ci_id], back_populates="incoming_relationships")

    __table_args__ = (
        Index("ix_ci_rel_source_target", "source_ci_id", "target_ci_id"),
        Index("ix_ci_rel_type", "relationship_type"),
    )


class CIStatusHistory(Base):
    __tablename__ = "ci_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    health_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    cpu_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    storage_used_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    ci: Mapped["ConfigurationItem"] = relationship("ConfigurationItem", back_populates="status_history")

    __table_args__ = (
        Index("ix_status_history_ci_recorded", "ci_id", "recorded_at"),
        Index("ix_status_history_recorded_at", "recorded_at"),
    )


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)  # "SOLARWINDS" | "INTUNE" | "ALL"
    status: Mapped[str] = mapped_column(String(32), nullable=False)         # "SUCCESS" | "FAILED" | "PARTIAL" | "RUNNING"
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    error_logs: Mapped[List["SyncErrorLog"]] = relationship("SyncErrorLog", back_populates="sync_run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_sync_runs_source_completed", "source_system", "completed_at"),
        Index("ix_sync_runs_status", "status"),
    )


class SyncErrorLog(Base):
    __tablename__ = "sync_error_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sync_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False, default="GENERAL_ERROR")
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    sync_run: Mapped["SyncRun"] = relationship("SyncRun", back_populates="error_logs")

    __table_args__ = (
        Index("ix_sync_error_logs_run_id", "sync_run_id"),
        Index("ix_sync_error_logs_created_at", "created_at"),
    )
```

---

## 4. Async SQLAlchemy 2.0 Engine, Connection Pooling & Alembic

### 4.1 Async Engine & Session Lifecycle (`app/core/database.py`)

To ensure high-concurrency sub-20ms queries without blocking the event loop:
- **Driver**: `asyncpg` via `postgresql+asyncpg://...`
- **Pool Sizing**: `pool_size=20`, `max_overflow=10`, `pool_timeout=30`, `pool_recycle=1800`
- **Connection Health**: `pool_pre_ping=True` (guards against stale server socket drops)
- **FastAPI Dependency Injection**: `get_db()` providing scoped async transaction sessions with automatic rollback on unhandled exceptions.

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### 4.2 Alembic Async Migration Architecture (`alembic/env.py`)

Alembic must be configured to run asynchronous schema migrations against PostgreSQL:
1. `alembic.ini` defines migration script locations and format.
2. `alembic/env.py` uses `asyncio.run()` with `engine.connect()` and `connection.run_sync(do_run_migrations)` to introspect metadata from `app.models.base.Base.metadata`.
3. Initial migration script `0001_initial_schema.py` establishes the 5 core tables, indexes, and constraints.

---

## 5. Paginated REST API Endpoints & Contract Envelopes

### 5.1 Standard Response Envelopes

All list endpoints return standard pagination envelopes with metadata:

```json
{
  "items": [
    {
      "id": "c71a3962-430b-48ae-94a1-b4ecb819f7e5",
      "source_id": "SW-NODE-1",
      "source_system": "SOLARWINDS",
      "name": "IN-BLR-SWOS",
      "ci_type": "Server",
      "status": "Up",
      "health_tier": "High",
      "ip_address": "172.18.151.142",
      "vendor": "Windows",
      "model": "Windows 2019 Server",
      "serial_number": null,
      "operating_system": "Windows Server 2019",
      "location": "BANGALORE",
      "last_sync_time": "2026-08-31T06:50:13.520000Z",
      "attributes": {
        "cpu_load": 12.0,
        "memory_used": 9.0,
        "latency_ms": 1.0,
        "uptime_hours": 29.9
      }
    }
  ],
  "total": 1543,
  "page": 1,
  "page_size": 50,
  "total_pages": 31
}
```

### 5.2 API Route Inventory

| Route Path | Method | Description | Target Invariant / Scope |
| :--- | :--- | :--- | :--- |
| `/api/v1/cmdb/cis` | `GET` | Paginated listing of all CIs with filters (`ci_type`, `status`, `health_tier`, `vendor`, `search`). | Sub-20ms, returns total CIs (1,543 SolarWinds + 25,987 Intune). |
| `/api/v1/cmdb/cis/{ci_id}` | `GET` | Single CI detail with relationships and status history. | Direct PK/UUID lookup. |
| `/api/v1/cmdb/summary` | `GET` | Fleet-wide summary metrics, distributions, and top pressure items. | Aggregated summary payload. |
| `/api/v1/cmdb/relationships` | `GET` | Topology edges filtered by `source_ci_id` or `target_ci_id`. | Graph edge traversal. |
| `/api/v1/intune/devices` | `GET` | Paginated Intune devices with filters (`os`, `compliance`, `manufacturer`, `search`). | 25,987 managed endpoint dataset. |
| `/api/v1/intune/summary` | `GET` | Top-level Intune metrics, compliance rate, and storage averages. | Invariant validated math. |
| `/api/v1/intune/breakdown/os` | `GET` | OS distribution counts. | `sum(os_breakdown) == total_devices`. |
| `/api/v1/intune/breakdown/compliance` | `GET` | Compliance distribution counts. | `compliant + noncompliant + other == total`. |
| `/api/v1/intune/breakdown/manufacturer`| `GET` | Normalized OEM distribution (Dell, HP, Lenovo, Apple, Other). | Case-insensitive normalized OEM sums. |
| `/api/v1/solarwinds/nodes` | `GET` | Paginated SolarWinds server nodes. | 1,548 nodes (1,543 active CIs). |
| `/api/v1/solarwinds/summary` | `GET` | SolarWinds fleet health metrics, vendor distributions, status counts. | Health tier sums equal total nodes. |
| `/api/v1/solarwinds/degraded` | `GET` | Top 25 degraded / resource-pressured server nodes. | Sorted by Low health, CPU, RAM descending. |
| `/api/v1/sync/runs` | `GET` | Historical sync run execution audit trail. | Audit and execution telemetry. |
| `/api/v1/sync/runs/latest` | `GET` | Latest sync run metadata across domains. | Powers data freshness header calculation. |
| `/api/v1/sync/trigger` | `POST` | Manually trigger background sync ETL cycle. | Secured worker trigger with advisory lock. |
| `/healthz` | `GET` | Liveness probe returning `{"status": "ok"}`. | Zero-dependency container health check. |
| `/ready` | `GET` | Readiness probe verifying PostgreSQL connection and migration state. | Container orchestration readiness. |

---

## 6. Freshness Response Headers & Strict Read-Only Security

### 6.1 Data Freshness Header Contract

Every HTTP response returned by the backend across `/api/v1/*` must include authoritative freshness headers injected by Starlette middleware (`FreshnessHeaderMiddleware`):

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
X-Last-Synchronized-At: 2026-09-02T06:00:00Z
X-Data-Age-Seconds: 120
X-Sync-Status: FRESH
```

#### Freshness State Invariants:
- `X-Last-Synchronized-At`: ISO 8601 UTC timestamp of the most recent completed `SyncRun` with `status = "SUCCESS"`.
- `X-Data-Age-Seconds`: Integer seconds elapsed between `X-Last-Synchronized-At` and `now(UTC)`.
- `X-Sync-Status`:
  - `"FRESH"` if `X-Data-Age-Seconds` $\le 900$ (15 minutes).
  - `"STALE"` if `X-Data-Age-Seconds` $> 900$ (15 minutes).

### 6.2 Strict Read-Only Mutation Blockers

To guarantee compliance with zero upstream mutation policies:
1. **HTTP Verb Blocker**: Mutating HTTP requests (`POST`, `PUT`, `DELETE`, `PATCH`) targeting `/api/v1/solarwinds/*` or `/api/v1/intune/*` are intercepted by router security dependencies and immediately rejected with:
   - **HTTP Status Code**: `405 Method Not Allowed`
   - **Response Payload**:
     ```json
     {
       "error": "Forbidden: Upstream monitoring integration is strictly READ-ONLY.",
       "allowed_methods": ["GET"]
     }
     ```
2. **SWQL Query Validator**: All SWQL strings sent to SolarWinds SWIS must begin with `SELECT` and contain zero mutating keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `EXEC`, `EXECUTE`, `GRANT`, `REVOKE`, `MERGE`).

---

## 7. Sub-20ms Query Optimization & Indexing Blueprint

### 7.1 PostgreSQL Index Definitions

To achieve consistent sub-20ms latency across 25,987+ records with dynamic filtering:

1. **Composite B-Tree Indexes**:
   ```sql
   CREATE INDEX ix_ci_source_type_status ON configuration_items (source_system, ci_type, status);
   CREATE INDEX ix_ci_health_tier ON configuration_items (health_tier);
   CREATE INDEX ix_ci_vendor ON configuration_items (vendor);
   CREATE INDEX ix_status_history_ci_recorded ON ci_status_history (ci_id, recorded_at DESC);
   CREATE INDEX ix_sync_runs_source_completed ON sync_runs (source_system, completed_at DESC);
   ```
2. **Covering Indexes for Fast Pagination**:
   ```sql
   CREATE INDEX ix_ci_pagination_covering ON configuration_items (source_system, created_at DESC) 
   INCLUDE (id, source_id, name, ci_type, status, health_tier, ip_address, vendor);
   ```
3. **GIN Trigram Fuzzy Search Index (`pg_trgm`)**:
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE INDEX ix_ci_trgm_search ON configuration_items USING gin (
       (name || ' ' || COALESCE(ip_address, '') || ' ' || COALESCE(serial_number, '')) gin_trgm_ops
   );
   ```

### 7.2 Multi-Worker Concurrency Guard (Advisory Locks)

When running with multiple Uvicorn worker processes (`uvicorn app.main:app --workers 4`), the background `APScheduler` job must acquire a PostgreSQL advisory lock before executing sync:

```python
async def execute_locked_sync(session: AsyncSession, sync_fn):
    # Lock ID 1048576 allocated for ITOM telemetry ETL
    lock_acquired = await session.scalar(
        select(func.pg_try_advisory_lock(1048576))
    )
    if not lock_acquired:
        logger.info("Another worker holds the telemetry sync advisory lock. Skipping run.")
        return

    try:
        await sync_fn(session)
    finally:
        await session.execute(
            select(func.pg_advisory_unlock(1048576))
        )
```

---

## 8. Multi-Domain Telemetry Invariants & Seeding Reconciliation

### 8.1 Microsoft Intune Telemetry Invariants (25,987 Endpoints)
- **Total Endpoints**: 25,987 managed devices (Windows, macOS, Linux, iOS, Android).
- **Compliance Partition Sum**: `compliant_devices + noncompliant_devices + other_compliance == total_managed_devices`.
- **Compliance Rate Formula**: $\text{Rate} = \text{round}\left(\frac{\text{Compliant}}{\text{Total}} \times 100, 2\right)$.
- **Manufacturer Normalization**: Normalized strictly to `Dell`, `HP`, `Lenovo`, `Apple`, `Other`. `sum(manufacturer_breakdown.values()) == total_managed_devices`.
- **Storage Calculation**: $\text{Storage Used \%} = \text{round}\left(\frac{\text{Total Storage GB} - \text{Free Storage GB}}{\text{Total Storage GB}} \times 100, 1\right)$.

### 8.2 SolarWinds Orion Telemetry Invariants (1,548 Server Nodes / 1,543 Active CIs)
- **Total Server Nodes**: 1,548 nodes; Active CIs: 1,543 CIs.
- **Health Classification Rule**:
  - `High`: Status = 1 (Up) AND (CPU < 75% or None) AND (RAM < 80% or None).
  - `Medium`: Status = 3 (Warning) OR (Status in [1, 3] AND (75% $\le$ CPU $\le$ 90% OR 80% $\le$ RAM $\le$ 90%)).
  - `Low`: Status in [2 (Down), 14 (Critical), 0 (Unknown)] OR CPU > 90% OR RAM > 90%.
- **Health Partition Sum**: `High + Medium + Low == total_nodes`.
- **Status Partition Sum**: `Up + Down + Warning + Critical + Unmanaged/Unknown == total_nodes`.
- **Vendor Normalization**: Standardized to `Windows`, `Cisco`, `Linux`, `SolarWinds`, `Other`.

### 8.3 Zero-Loss Bulk Database Seeding Strategy (`scripts/seed_database.py`)

A high-performance streaming seeding script will:
1. Load existing raw datasets (`data/intune_ops_analytics.json` and `data/solarwinds_nodes.json`).
2. Stream records in chunks of 1,000 using SQLAlchemy Core bulk `insert()` or PostgreSQL `COPY`.
3. Generate initial `ci_relationships` (e.g. location/site edges).
4. Create initial baseline `ci_status_history` records.
5. Create an initial successful `SyncRun` entry establishing baseline freshness.
6. Verify 100% record count parity: exactly 25,987 Intune devices and 1,543 SolarWinds CIs persisted.

---

## 9. Implementation Roadmap & Milestone Assignment

| Milestone | Target Deliverables | Associated Files |
| :--- | :--- | :--- |
| **M1: Relational Persistence Layer** | PostgreSQL schema DDL, SQLAlchemy 2.0 Async models, Alembic migration scripts, async engine and connection pooling, zero-loss bulk seeding script. | `app/models/*`, `alembic/*`, `app/core/database.py`, `scripts/seed_database.py` |
| **M2: FastAPI Asynchronous REST Backend** | Modular FastAPI app factory, Pydantic schemas, async repositories, service layer, paginated endpoints (`/cmdb`, `/intune`, `/solarwinds`, `/sync`), freshness middleware. | `app/main.py`, `app/api/v1/*`, `app/schemas/*`, `app/repositories/*`, `app/services/*`, `app/core/middleware.py` |
| **M3: Background Sync Engine & Security Guards** | Decoupled APScheduler 10m cron, advisory lock manager, strict read-only SWQL validator, delta change detector, audit logging in `sync_runs` & `sync_error_logs`. | `app/core/scheduler.py`, `app/core/security.py`, `app/services/sync_service.py`, `app/integrations/*` |
| **M4: Docker Infrastructure & Local Deployment** | Multi-stage production Dockerfile (non-root `itom` user), Docker Compose stack (`nginx`, `api`, `postgres`), `nginx.conf` reverse proxy, `/healthz` & `/ready` probes. | `Dockerfile`, `docker-compose.yml`, `nginx.conf`, `app/api/v1/endpoints/system.py` |
| **M5: Verification & Adversarial Hardening** | 100% pass across all 119 existing E2E tests + new database integration tests, sub-20ms latency benchmarks, HTTP 405 mutation rejection tests, invariant certifications. | `tests/*` |

---

## 10. Conclusion

The surveyed architecture provides a clean separation of concerns, strict adherence to enterprise security invariants, sub-20ms query latency, and mathematically proven multi-domain telemetry synchronization.
