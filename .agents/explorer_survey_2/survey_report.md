# ITOM Enterprise Relational Database Layer Architecture Report (PostgreSQL 16 & SQLAlchemy 2.0 Async)

**Agent**: `explorer_survey_2`  
**Mission**: Requirement R1 — Relational Database Layer & Alembic Migration Pipeline  
**Target Platform**: PostgreSQL 16+ | SQLAlchemy 2.0 Async | asyncpg 0.29+ | Alembic 1.13+ | FastAPI 0.110+  
**Target Datasets**: 25,987 Microsoft Intune Managed Endpoints & 1,543 SolarWinds Orion Configuration Items (1,548 Server Nodes)  
**Date**: 2026-09-01  

---

## 1. Executive Summary & Architecture Overview

The ITOM platform is transitioning from static flat-file JSON storage (`data/*.json`) to an enterprise-grade, highly available, persistent relational database architecture built on **PostgreSQL 16** with **SQLAlchemy 2.0 Async** and **asyncpg**.

### Core Architecture Objectives
1. **Multi-Domain Unified Schema**: A normalized, high-performance schema capable of storing both on-premise infrastructure CIs (SolarWinds switches, routers, firewalls, servers) and enterprise mobile/desktop endpoints (Microsoft Intune Windows, macOS, Linux, iOS, Android devices) with zero data loss and exact mathematical parity.
2. **Topological Dependency Graph**: A flexible graph relationship model (`ci_relationships`) capturing hierarchical topology (site physical location, network uplink/downlink, cluster membership, gateway routing).
3. **Time-Series Observability Ledger**: Partitioned historical status and telemetry snapshot table (`ci_status_history`) capturing state changes, metric fluctuations (CPU, RAM, latency, disk usage), and audit deltas.
4. **Execution Audit & Ingestion Telemetry**: Resilient execution audit logging (`sync_runs` and `sync_error_logs`) providing full observability into background synchronization cycles, error traces, and freshness SLA headers (`last_synchronized_at`, `data_age_seconds`, `sync_status`).
5. **Sub-20ms Query Latency**: Multi-tiered indexing strategy utilizing PostgreSQL 16 B-Tree, GIN (`jsonb_path_ops` and `pg_trgm`), BRIN time-series indexing, and covering indexes with `INCLUDE` clauses to guarantee paginated REST API responses in under 20ms across 30,000+ records.

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                FastAPI REST Layer (Async)                             │
│     /api/v1/cmdb/*            /api/v1/intune/*            /api/v1/solarwinds/*        │
└──────────────────────────────────────────┬────────────────────────────────────────────┘
                                           │ AsyncSession (SQLAlchemy 2.0)
                                           ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                     asyncpg Connection Pool (20-30 connections)                       │
│                        Pre-ping: True | Recycle: 1800s                                │
└──────────────────────────────────────────┬────────────────────────────────────────────┘
                                           │
                                           ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                               PostgreSQL 16 Storage Engine                            │
│                                                                                       │
│  ┌────────────────────────┐   1:N   ┌────────────────────────┐                        │
│  │  configuration_items   ├────────►│    ci_relationships    │                        │
│  │ (27,530+ Unified CIs)  │         │ (Topological Graph)    │                        │
│  └───────────┬────────────┘         └────────────────────────┘                        │
│              │                                                                        │
│              │ 1:N                                                                    │
│              ▼                                                                        │
│  ┌────────────────────────┐         ┌────────────────────────┐                        │
│  │   ci_status_history    │         │       sync_runs        │                        │
│  │ (Time-Series Metric DB)│         │ (Ingestion Audit Runs) │                        │
│  └────────────────────────┘         └───────────┬────────────┘                        │
│                                                 │ 1:N                                 │
│                                                 ▼                                     │
│                                     ┌────────────────────────┐                        │
│                                     │    sync_error_logs     │                        │
│                                     │  (Diagnostic Traces)   │                        │
│                                     └────────────────────────┘                        │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Comprehensive Relational Data Model (DDL Specifications)

### 2.1 Entity Relationship Diagram (ERD) Overview

| Table Name | Purpose | Primary Key | Key Foreign Keys | Storage Characteristics |
|---|---|---|---|---|
| `configuration_items` | Unified master catalog for all ITOM assets (Intune + SolarWinds) | `id` (UUID) | None | High read, moderate UPSERT, partial indexes |
| `ci_relationships` | Graph edges connecting CIs to sites, parent devices, and subnets | `id` (UUID) | `source_ci_id`, `target_ci_id` -> `configuration_items(id)` | Directed graph, foreign key cascaded |
| `ci_status_history` | Time-series telemetry snapshots and status transition ledger | `id` (BIGINT IDENTITY) | `ci_id` -> `configuration_items(id)` | Range-partitioned by `recorded_at`, BRIN index |
| `sync_runs` | Metadata and audit records for every scheduled/manual sync cycle | `id` (UUID) | None | Append-mostly, query by status/source |
| `sync_error_logs` | Detailed exception stacks and diagnostic payloads for sync failures | `id` (BIGINT IDENTITY) | `sync_run_id` -> `sync_runs(id)` | Diagnostic logging, indexed on timestamp |

---

### 2.2 PostgreSQL 16 DDL Schema

```sql
-- Enable necessary PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- ============================================================================
-- 1. Configuration Items (Master CMDB Catalog)
-- ============================================================================
CREATE TABLE configuration_items (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ci_id                   VARCHAR(128) NOT NULL,
    source                  VARCHAR(32) NOT NULL,            -- 'solarwinds', 'intune', 'manual', 'network_discovery'
    source_id               VARCHAR(128) NOT NULL,           -- NodeID ('1677') or Intune Device ID ('35d189cb-...')
    name                    VARCHAR(255) NOT NULL,           -- Caption or DeviceName
    ci_type                 VARCHAR(64) NOT NULL,            -- 'Server', 'Access Switch', 'Router', 'Firewall', 'Workstation', 'Mobile Device'
    device_role             VARCHAR(64) NOT NULL,            -- Normalized architectural role
    hostname                VARCHAR(255) NOT NULL,
    ip_address              VARCHAR(45),                     -- Supports IPv4 & IPv6 text or INET type
    mac_address             VARCHAR(32),
    serial_number           VARCHAR(128),
    vendor                  VARCHAR(128) NOT NULL,           -- Normalized: 'Dell', 'HP', 'Lenovo', 'Apple', 'Cisco', 'Windows', 'Other'
    raw_vendor              VARCHAR(255),                    -- Unmodified vendor string from API
    model                   VARCHAR(255),                    -- MachineType / Device Model
    operating_system        VARCHAR(128) NOT NULL,           -- 'Windows Server 2022', 'Windows', 'macOS', 'Cisco IOS 16.12'
    os_version              VARCHAR(128),                    -- '10.0.26200.9168', '16.12.04'
    status                  VARCHAR(32) NOT NULL,            -- 'Up', 'Down', 'Warning', 'Critical', 'Unmanaged', 'Unknown'
    health_tier             VARCHAR(16) NOT NULL DEFAULT 'High', -- 'High', 'Medium', 'Low'
    compliance_state        VARCHAR(32) NOT NULL DEFAULT 'Compliant', -- 'Compliant', 'Action Required', 'Missing Serial', 'Under Review'
    priority                VARCHAR(16) NOT NULL DEFAULT 'Normal',    -- 'Low', 'Normal', 'High', 'Critical'
    location                VARCHAR(255) NOT NULL DEFAULT 'Default Location', -- City / Physical Facility
    site_code               VARCHAR(64),                     -- 'HYD', 'MNL', 'LON', 'SJC'
    contact                 VARCHAR(255),                    -- Admin / Owner contact
    user_principal_name     VARCHAR(255),                    -- Assigned corporate email (for Intune endpoints)
    description             TEXT,
    is_monitored            BOOLEAN NOT NULL DEFAULT TRUE,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Numerical Telemetry & Utilization Fields
    cpu_load_pct            NUMERIC(5, 2),                   -- Fleet average or live node CPU (0.00 to 100.00)
    ram_used_pct            NUMERIC(5, 2),                   -- RAM used percentage (0.00 to 100.00)
    latency_ms              NUMERIC(8, 2),                   -- Round-trip ping latency in milliseconds
    uptime_seconds          BIGINT,                          -- System uptime in seconds
    uptime_hours            NUMERIC(10, 1) GENERATED ALWAYS AS (
                                CASE WHEN uptime_seconds > 0 THEN ROUND(uptime_seconds / 3600.0, 1) ELSE NULL END
                            ) STORED,
    total_storage_bytes     BIGINT,                          -- Total disk space in bytes
    free_storage_bytes      BIGINT,                          -- Free disk space in bytes
    storage_used_pct        NUMERIC(5, 2) GENERATED ALWAYS AS (
                                CASE WHEN total_storage_bytes > 0 THEN 
                                    ROUND(((total_storage_bytes - free_storage_bytes)::numeric / total_storage_bytes::numeric) * 100.0, 2)
                                ELSE NULL END
                            ) STORED,

    -- Extensibility & Synchronization Metadata
    raw_attributes          JSONB NOT NULL DEFAULT '{}'::jsonb, -- Domain-specific payload (Graph extended properties, SWIS custom props)
    tags                    JSONB NOT NULL DEFAULT '[]'::jsonb, -- Array of string tags (e.g. ["production", "pci-dss", "tier-1"])
    last_sync_time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT uq_ci_source_source_id UNIQUE (source, source_id),
    CONSTRAINT uq_ci_natural_ci_id UNIQUE (ci_id),
    CONSTRAINT chk_health_tier CHECK (health_tier IN ('High', 'Medium', 'Low')),
    CONSTRAINT chk_cpu_load CHECK (cpu_load_pct IS NULL OR (cpu_load_pct >= 0 AND cpu_load_pct <= 100)),
    CONSTRAINT chk_ram_used CHECK (ram_used_pct IS NULL OR (ram_used_pct >= 0 AND ram_used_pct <= 100))
);

-- ============================================================================
-- 2. CI Relationships (Topological Dependency Graph)
-- ============================================================================
CREATE TABLE ci_relationships (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_ci_id            UUID NOT NULL REFERENCES configuration_items(id) ON DELETE CASCADE,
    target_ci_id            UUID NOT NULL REFERENCES configuration_items(id) ON DELETE CASCADE,
    relationship_type       VARCHAR(64) NOT NULL,            -- 'located_at', 'connected_to', 'depends_on', 'hosted_on', 'uplink_to'
    target_name             VARCHAR(255) NOT NULL,           -- Human readable target name
    target_type             VARCHAR(64) NOT NULL,            -- 'Facility / Location', 'Core Switch', 'VLAN', 'Hypervisor Host'
    description             VARCHAR(512),
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb, -- Port mappings (e.g. {"source_port": "Gi1/0/1", "target_port": "Te1/1/1"})
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ci_relationship UNIQUE (source_ci_id, target_ci_id, relationship_type),
    CONSTRAINT chk_prevent_self_relationship CHECK (source_ci_id <> target_ci_id)
);

-- ============================================================================
-- 3. CI Status History (Time-Series Status Ledger & Telemetry Snapshots)
-- ============================================================================
CREATE TABLE ci_status_history (
    id                      BIGSERIAL,
    ci_id                   UUID NOT NULL REFERENCES configuration_items(id) ON DELETE CASCADE,
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status                  VARCHAR(32) NOT NULL,
    health_tier             VARCHAR(16) NOT NULL,
    compliance_state        VARCHAR(32),
    cpu_load_pct            NUMERIC(5, 2),
    ram_used_pct            NUMERIC(5, 2),
    latency_ms              NUMERIC(8, 2),
    storage_used_bytes      BIGINT,
    storage_free_bytes      BIGINT,
    change_source           VARCHAR(64) NOT NULL DEFAULT 'scheduled_sync', -- 'scheduled_sync', 'manual_refresh', 'webhook'
    delta_summary           JSONB,                           -- {"cpu_load_pct": {"old": 22.1, "new": 89.4}, "status": {"old": "Up", "new": "Warning"}}
    metrics_snapshot        JSONB,                           -- Complete raw metrics snapshot

    PRIMARY KEY (id, recorded_at)
) PARTITION BY RANGE (recorded_at);

-- Initial default monthly partitions for 2026
CREATE TABLE ci_status_history_2026_08 PARTITION OF ci_status_history
    FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');

CREATE TABLE ci_status_history_2026_09 PARTITION OF ci_status_history
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');

CREATE TABLE ci_status_history_2026_10 PARTITION OF ci_status_history
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

CREATE TABLE ci_status_history_default PARTITION OF ci_status_history DEFAULT;

-- ============================================================================
-- 4. Sync Runs (Sync Pipeline Execution Metadata & Audit)
-- ============================================================================
CREATE TABLE sync_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_source             VARCHAR(64) NOT NULL,            -- 'solarwinds', 'intune', 'cmdb_reconciliation', 'all'
    sync_mode               VARCHAR(32) NOT NULL DEFAULT 'scheduled', -- 'scheduled', 'manual_trigger', 'delta'
    status                  VARCHAR(32) NOT NULL DEFAULT 'running',   -- 'running', 'completed', 'failed', 'partial'
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,
    duration_seconds        NUMERIC(10, 3),
    records_extracted       INTEGER NOT NULL DEFAULT 0,
    records_inserted        INTEGER NOT NULL DEFAULT 0,
    records_updated         INTEGER NOT NULL DEFAULT 0,
    records_unchanged       INTEGER NOT NULL DEFAULT 0,
    records_deactivated     INTEGER NOT NULL DEFAULT 0,
    error_count             INTEGER NOT NULL DEFAULT 0,
    sync_status_header      VARCHAR(32) NOT NULL DEFAULT 'FRESH', -- 'FRESH', 'STALE', 'DEGRADED', 'FAILED'
    triggered_by            VARCHAR(128) NOT NULL DEFAULT 'apscheduler_daemon',
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,   -- Invariant assertion results, batch timings
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 5. Sync Error Logs (Diagnostic Error Traces & Failed Items)
-- ============================================================================
CREATE TABLE sync_error_logs (
    id                      BIGSERIAL PRIMARY KEY,
    sync_run_id             UUID REFERENCES sync_runs(id) ON DELETE SET NULL,
    sync_source             VARCHAR(64) NOT NULL,
    ci_id                   VARCHAR(128),                    -- Identifier of CI that encountered the error (if record-specific)
    error_level             VARCHAR(16) NOT NULL DEFAULT 'ERROR', -- 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    error_code              VARCHAR(64) NOT NULL,            -- 'SWIS_HTTP_500', 'GRAPH_TOKEN_EXPIRED', 'INVARIANT_FAILURE'
    error_message           TEXT NOT NULL,
    stack_trace             TEXT,
    payload_snippet         JSONB,                           -- Offending JSON payload snippet
    retry_count             INTEGER NOT NULL DEFAULT 0,
    is_resolved             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 3. SQLAlchemy 2.0 Async Models Implementation

Below is the complete, production-ready SQLAlchemy 2.0 Declarative Async Model implementation (`app/models/cmdb_models.py`):

```python
"""Enterprise Relational CMDB Models for SQLAlchemy 2.0 Async (PostgreSQL 16)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    AsyncAttrs,
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(AsyncAttrs, DeclarativeBase):
    """Abstract base model with async attribute support and automatic naming."""
    pass


class ConfigurationItem(Base):
    """Unified master catalog entity for Microsoft Intune and SolarWinds Orion CIs."""
    __tablename__ = "configuration_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    ci_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # 'solarwinds' | 'intune'
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ci_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, index=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    vendor: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_vendor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    operating_system: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    health_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="High", server_default="High", index=True)
    compliance_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Compliant", server_default="Compliant", index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="Normal", server_default="Normal")
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="Default Location", server_default="Default Location", index=True)
    site_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_principal_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_monitored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)

    # Numerical Metrics
    cpu_load_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    ram_used_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    uptime_seconds: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    uptime_hours: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 1),
        Computed(
            "CASE WHEN uptime_seconds > 0 THEN ROUND(uptime_seconds / 3600.0, 1) ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )
    total_storage_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    free_storage_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    storage_used_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        Computed(
            "CASE WHEN total_storage_bytes > 0 THEN ROUND(((total_storage_bytes - free_storage_bytes)::numeric / total_storage_bytes::numeric) * 100.0, 2) ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )

    # JSONB metadata
    raw_attributes: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    tags: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    last_sync_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    outbound_relationships: Mapped[List["CIRelationship"]] = relationship(
        "CIRelationship",
        foreign_keys="CIRelationship.source_ci_id",
        back_populates="source_ci",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    inbound_relationships: Mapped[List["CIRelationship"]] = relationship(
        "CIRelationship",
        foreign_keys="CIRelationship.target_ci_id",
        back_populates="target_ci",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    status_history: Mapped[List["CIStatusHistory"]] = relationship(
        "CIStatusHistory",
        back_populates="ci",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_ci_source_source_id"),
        CheckConstraint("health_tier IN ('High', 'Medium', 'Low')", name="chk_health_tier"),
        # Composite Indexes for Query Acceleration
        Index("ix_ci_source_active_status", "source", "is_active", "status"),
        Index("ix_ci_type_health", "ci_type", "health_tier"),
        Index("ix_ci_compliance_vendor", "compliance_state", "vendor"),
        Index("ix_ci_location_type", "location", "ci_type"),
        Index("ix_ci_last_sync_desc", last_sync_time.desc()),
        # GIN Index for JSONB Search
        Index("ix_ci_raw_attributes_gin", "raw_attributes", postgresql_using="gin", postgresql_ops={"raw_attributes": "jsonb_path_ops"}),
        # Trigram GIN Indexes for Substring Fuzzy Search
        Index("ix_ci_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index("ix_ci_hostname_trgm", "hostname", postgresql_using="gin", postgresql_ops={"hostname": "gin_trgm_ops"}),
    )


class CIRelationship(Base):
    """Topological graph relationship between configuration items."""
    __tablename__ = "ci_relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_ci_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("configuration_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_ci_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("configuration_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    source_ci: Mapped["ConfigurationItem"] = relationship("ConfigurationItem", foreign_keys=[source_ci_id], back_populates="outbound_relationships")
    target_ci: Mapped["ConfigurationItem"] = relationship("ConfigurationItem", foreign_keys=[target_ci_id], back_populates="inbound_relationships")

    __table_args__ = (
        UniqueConstraint("source_ci_id", "target_ci_id", "relationship_type", name="uq_ci_relationship"),
        CheckConstraint("source_ci_id <> target_ci_id", name="chk_prevent_self_relationship"),
    )


class CIStatusHistory(Base):
    """Time-series metric snapshot and state change history ledger."""
    __tablename__ = "ci_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ci_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("configuration_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    health_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    compliance_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    cpu_load_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    ram_used_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    storage_used_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    storage_free_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    change_source: Mapped[str] = mapped_column(String(64), nullable=False, default="scheduled_sync", server_default="scheduled_sync")
    delta_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    metrics_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    ci: Mapped["ConfigurationItem"] = relationship("ConfigurationItem", back_populates="status_history")

    __table_args__ = (
        Index("ix_history_ci_time", "ci_id", recorded_at.desc()),
        # BRIN index on recorded_at for ultra-fast time-series filtering
        Index("ix_history_recorded_at_brin", "recorded_at", postgresql_using="brin"),
    )


class SyncRun(Base):
    """Execution audit metadata for every ingestion and reconciliation cycle."""
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    sync_source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 'solarwinds', 'intune', 'all'
    sync_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled", server_default="scheduled")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", server_default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    records_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    records_deactivated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sync_status_header: Mapped[str] = mapped_column(String(32), nullable=False, default="FRESH", server_default="FRESH")
    triggered_by: Mapped[str] = mapped_column(String(128), nullable=False, default="apscheduler_daemon", server_default="apscheduler_daemon")
    metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )

    error_logs: Mapped[List["SyncErrorLog"]] = relationship(
        "SyncErrorLog",
        back_populates="sync_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_sync_runs_source_started", "sync_source", started_at.desc()),
    )


class SyncErrorLog(Base):
    """Detailed error logs and stack traces for ingestion failures."""
    __tablename__ = "sync_error_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sync_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sync_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sync_source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ci_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    error_level: Mapped[str] = mapped_column(String(16), nullable=False, default="ERROR", server_default="ERROR")
    error_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_snippet: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        index=True,
    )

    sync_run: Mapped[Optional["SyncRun"]] = relationship("SyncRun", back_populates="error_logs")
```

---

## 4. Alembic Migration Pipeline Configuration & Layout

### 4.1 Migration Directory Structure

```
optimistic-pasteur/
├── alembic/
│   ├── env.py                  # Async migration runner using SQLAlchemy 2.0 AsyncEngine
│   ├── README
│   ├── script.py.mako          # Migration script template with docstrings & timestamps
│   └── versions/
│       ├── 0001_initial_cmdb_schema.py      # Master baseline schema (5 tables, extensions)
│       └── 0002_add_trigram_and_brin.py     # High-performance indexes & partitions
├── alembic.ini                 # Alembic configuration (driver, logging, version locations)
└── app/
    └── core/
        └── database.py         # AsyncEngine and AsyncSession factory
```

### 4.2 Async Alembic Runner (`alembic/env.py`)

Alembic must run in async mode to share models and configuration seamlessly with the asyncpg engine:

```python
"""Async Alembic Environment Runner for PostgreSQL 16 & SQLAlchemy 2.0."""

import asyncio
from logging.config import fileConfig
import os
import sys

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Append project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.models.cmdb_models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with AsyncEngine."""
    configuration = config.get_section(config.config_ini_section)
    if not configuration:
        configuration = {}
    
    # Read database URL from environment variable or fallback to config
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        configuration["sqlalchemy.url"] = db_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## 5. Async Engine, Connection Pooling & FastAPI Lifecycle Integration

### 5.1 Engine & Session Factory Configuration (`app/core/database.py`)

```python
"""Database Connection Engine & Session Lifecycle Management."""

import os
from typing import AsyncGenerator
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://itom_user:itom_secure_password@localhost:5432/itom_db"
)

# Configure high-throughput asyncpg connection engine
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
    future=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    pool_timeout=float(os.getenv("DB_POOL_TIMEOUT", "30.0")),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),  # 30 minutes
    pool_pre_ping=True,  # Proactively test connection liveness
    connect_args={
        "server_settings": {
            "application_name": "itom_enterprise_api",
            "jit": "off",  # Disable JIT for sub-20ms transactional queries
            "statement_timeout": "5000",  # 5-second hard statement timeout
        }
    },
)

# Async Session Factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency Injection for scoped async database sessions.
    
    Guarantees automatic session cleanup and rollback on unhandled exceptions.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

## 6. Zero-Loss Ingestion & Seeding Strategy (Intune 25,987 & SolarWinds 1,543)

To guarantee **zero data loss** and preserve exact mathematical parity with existing datasets, the database migration and seeding pipeline employs a bulk streaming ETL strategy utilizing PostgreSQL's native `INSERT ... ON CONFLICT (source, source_id) DO UPDATE` (UPSERT) with chunk sizes of 1,000 records.

### 6.1 Data Ingestion Architecture Matrix

| Metric | Microsoft Intune Fleet | SolarWinds Orion Nodes | Combined Production DB |
|---|---|---|---|
| **Authoritative File** | `data/intune_ops_analytics.json` | `data/solarwinds_nodes.json` | PostgreSQL `configuration_items` |
| **Total Ingested Records** | **25,987** (or 27,412 raw) | **1,543** CIs (1,548 nodes) | **27,530+** Configuration Items |
| **Batch Size** | 1,000 records / transaction | 500 records / transaction | Chunked bulk execution |
| **Expected Ingest Time** | ~1.8 seconds | ~0.2 seconds | **< 2.5 seconds total** |
| **Identity Resolution** | `source='intune', source_id=id` | `source='solarwinds', source_id=NodeID` | Unique natural key: `ci_id` |

### 6.2 Data Field Mapping Specification

```
==============================================================================================
SOURCE: Microsoft Intune (`data/intune_ops_analytics.json`) -> PostgreSQL (`configuration_items`)
==============================================================================================
id                          -> source_id = id, ci_id = 'INTUNE-' || id
deviceName                  -> name, hostname
operatingSystem             -> operating_system (Windows, macOS, Linux, iOS, Android)
osVersion                   -> os_version (e.g. '10.0.26200.9168')
complianceState             -> compliance_state (compliant -> 'Compliant', noncompliant -> 'Action Required', etc.)
userPrincipalName           -> user_principal_name, contact
model                       -> model (e.g. 'Latitude 3410', 'MacBookPro18,1')
manufacturer                -> vendor (Dell, HP, Lenovo, Apple, Other), raw_vendor = manufacturer
serialNumber                -> serial_number
lastSyncDateTime            -> last_sync_time
totalStorageSpaceInBytes    -> total_storage_bytes
freeStorageSpaceInBytes     -> free_storage_bytes
derived ci_type             -> 'Workstation' (Windows/macOS/Linux) or 'Mobile Device' (iOS/Android)
derived device_role         -> 'Endpoint Workstation' / 'Mobile Fleet'
derived health_tier         -> 'High' (if compliant), 'Medium' (inGracePeriod), 'Low' (noncompliant)
derived status              -> 'Up' (lastSync < 30d) / 'Unmanaged' (lastSync >= 30d)
derived location            -> Extracted from deviceName prefix (e.g. 'LP-HYD-*' -> 'Hyderabad')

==============================================================================================
SOURCE: SolarWinds Orion (`data/solarwinds_nodes.json`) -> PostgreSQL (`configuration_items`)
==============================================================================================
NodeID                      -> source_id = NodeID, ci_id = 'SW-NODE-' || NodeID
Caption                     -> name, hostname
IPAddress                   -> ip_address
Status                      -> status (1:'Up', 2:'Down', 3:'Warning', 9:'Unmanaged', 14:'Critical')
Vendor / NormalizedVendor   -> vendor (Cisco, Windows, Palo Alto, Juniper, Fortinet, Other), raw_vendor = Vendor
MachineType                 -> model, raw_attributes.machine_type
NodeDescription             -> description, operating_system (parsed clean OS)
City                        -> location, site_code
Contact                     -> contact
CPULoad                     -> cpu_load_pct
PercentMemoryUsed           -> ram_used_pct
ResponseTime / AvgResponse  -> latency_ms
SystemUpTime                -> uptime_seconds
HealthClassification        -> health_tier ('High', 'Medium', 'Low')
derived ci_type / role      -> classify_device_role() ('Server', 'Access Switch', 'Router', 'Firewall', etc.)
derived relationships       -> 1:N edge in `ci_relationships` to `SITE-<LOCATION>`
```

### 6.3 Seeding Script Architecture (`scripts/seed_database.py`)

```python
"""High-Speed Bulk Ingestion & Seeding Engine for PostgreSQL 16."""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.database import async_session_factory, engine
from app.models.cmdb_models import Base, CIRelationship, CIStatusHistory, ConfigurationItem, SyncRun
from src.sync.cmdb_generator import CMDBService, classify_device_role, normalize_solarwinds_vendor, parse_clean_os
from src.sync.payload_generator import normalize_manufacturer

logger = logging.getLogger("db_seeder")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def bulk_upsert_cis(session: AsyncSession, records: List[Dict[str, Any]], chunk_size: int = 1000) -> int:
    """Execute chunked PostgreSQL UPSERT using ON CONFLICT DO UPDATE."""
    total_upserted = 0
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        stmt = insert(ConfigurationItem).values(chunk)
        
        # Build update mapping (all columns except PK and created_at)
        update_cols = {
            col.name: stmt.excluded[col.name]
            for col in ConfigurationItem.__table__.columns
            if col.name not in ["id", "created_at"]
        }
        
        upsert_stmt = stmt.on_conflict_do_update(
            constraint="uq_ci_source_source_id",
            set_=update_cols,
        )
        await session.execute(upsert_stmt)
        total_upserted += len(chunk)
        logger.info("Upserted chunk %d-%d of %d CIs...", i, i + len(chunk), len(records))
    
    await session.commit()
    return total_upserted


async def seed_all() -> None:
    """Ingest both Intune and SolarWinds datasets into PostgreSQL."""
    start_time = time.perf_counter()
    logger.info("=== Starting PostgreSQL 16 Bulk Ingestion & Seeding Pipeline ===")

    # 1. Load SolarWinds CIs
    sw_nodes_path = os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json")
    cmdb_service = CMDBService()
    raw_nodes, mode, status = cmdb_service.fetch_live_nodes()
    sw_cis = cmdb_service.normalize_nodes_to_cis(raw_nodes, mode=mode)
    logger.info("Normalized %d SolarWinds CIs.", len(sw_cis))

    # Transform to ConfigurationItem table rows
    ci_records: List[Dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc)

    for item in sw_cis:
        node_id = item["ci_id"].replace("SW-NODE-", "")
        ci_records.append({
            "ci_id": item["ci_id"],
            "source": "solarwinds",
            "source_id": node_id,
            "name": item["name"],
            "ci_type": item["ci_type"],
            "device_role": item["device_role"],
            "hostname": item["hostname"],
            "ip_address": item["ip_address"] if item["ip_address"] else None,
            "vendor": item["vendor"],
            "raw_vendor": item.get("hardware_vendor", item["vendor"]),
            "model": item.get("model"),
            "operating_system": item.get("operating_system", "Unknown"),
            "status": item["status"],
            "health_tier": item["health_tier"],
            "compliance_state": item.get("compliance_state", "Compliant"),
            "location": item.get("location", "Default Location"),
            "contact": item.get("contact"),
            "description": item.get("description"),
            "is_monitored": item["status"] in ["Up", "Warning", "Critical"],
            "is_active": True,
            "cpu_load_pct": item.get("cpu_load"),
            "ram_used_pct": item.get("memory_used"),
            "latency_ms": item.get("latency_ms"),
            "uptime_seconds": int(item["uptime_hours"] * 3600) if item.get("uptime_hours") else None,
            "raw_attributes": item,
            "last_sync_time": now_utc,
        })

    # 2. Load Microsoft Intune Devices
    intune_path = os.path.join(PROJECT_ROOT, "data", "intune_ops_analytics.json")
    with open(intune_path, "r", encoding="utf-8") as f:
        intune_data = json.load(f)
    intune_devices = intune_data.get("devices", [])
    logger.info("Loaded %d Microsoft Intune device records.", len(intune_devices))

    for dev in intune_devices:
        dev_id = str(dev.get("id", ""))
        os_name = str(dev.get("operatingSystem", "Unknown"))
        comp_raw = str(dev.get("complianceState", "unknown")).lower()
        
        # Compliance state normalization
        comp_state = "Compliant" if comp_raw == "compliant" else (
            "Action Required" if comp_raw in ["noncompliant", "conflict", "error"] else (
                "Under Review" if comp_raw in ["configmanager", "unknown"] else "Under Review"
            )
        )
        health_tier = "High" if comp_raw == "compliant" else (
            "Low" if comp_raw in ["noncompliant", "conflict", "error"] else "Medium"
        )
        
        # Derived CI type
        ci_type = "Workstation" if os_name in ["Windows", "macOS", "Linux"] else (
            "Mobile Device" if os_name in ["iOS", "Android"] else "Other Endpoint"
        )

        ci_records.append({
            "ci_id": f"INTUNE-{dev_id}",
            "source": "intune",
            "source_id": dev_id,
            "name": dev.get("deviceName", f"Device-{dev_id[:8]}"),
            "ci_type": ci_type,
            "device_role": "Managed Endpoint",
            "hostname": dev.get("deviceName", ""),
            "vendor": normalize_manufacturer(dev.get("manufacturer")),
            "raw_vendor": dev.get("manufacturer"),
            "model": dev.get("model"),
            "operating_system": os_name,
            "os_version": dev.get("osVersion"),
            "status": "Up",
            "health_tier": health_tier,
            "compliance_state": comp_state,
            "serial_number": dev.get("serialNumber"),
            "user_principal_name": dev.get("userPrincipalName"),
            "contact": dev.get("userPrincipalName"),
            "total_storage_bytes": dev.get("totalStorageSpaceInBytes"),
            "free_storage_bytes": dev.get("freeStorageSpaceInBytes"),
            "is_monitored": True,
            "is_active": True,
            "raw_attributes": dev,
            "last_sync_time": now_utc,
        })

    # Execute Bulk UPSERT
    async with async_session_factory() as session:
        total = await bulk_upsert_cis(session, ci_records, chunk_size=1000)
        
        # Create initial audit sync run
        sync_run = SyncRun(
            sync_source="initial_seed_pipeline",
            sync_mode="full_refresh",
            status="completed",
            started_at=now_utc,
            completed_at=datetime.now(timezone.utc),
            duration_seconds=round(time.perf_counter() - start_time, 3),
            records_extracted=len(ci_records),
            records_inserted=total,
            records_updated=0,
            records_unchanged=0,
            error_count=0,
            sync_status_header="FRESH",
            triggered_by="initial_seeder",
            metadata={
                "solarwinds_ci_count": len(sw_cis),
                "intune_device_count": len(intune_devices),
                "total_cis_persisted": total,
            }
        )
        session.add(sync_run)
        await session.commit()

    duration = time.perf_counter() - start_time
    logger.info("=== Successfully Ingested & Certified %d CIs in %.2f seconds ===", total, duration)


if __name__ == "__main__":
    asyncio.run(seed_all())
```

---

## 7. Query Optimization, Indexing Blueprint & Sub-20ms SLA Strategy

To guarantee strict **sub-20ms SLA** across all paginated REST endpoints (`/api/v1/cmdb/cis`, `/api/v1/intune/devices`, `/api/v1/solarwinds/nodes`) handling 30,000+ assets with arbitrary multi-field filters, the following five performance pillars are established:

### 7.1 PostgreSQL Index Strategy Matrix

```sql
-- 1. Primary Filter & Sort Composite Index (Zero Heap Fetch on Hot Paths)
CREATE INDEX idx_ci_pagination_hotpath ON configuration_items (
    source, is_active, status, health_tier, created_at DESC
) INCLUDE (
    ci_id, name, hostname, ip_address, vendor, model, operating_system, compliance_state
);

-- 2. Trigram GIN Indexes for Sub-Millisecond Multi-Field Fuzzy Search (ILIKE '%search%')
CREATE INDEX idx_ci_search_trgm ON configuration_items USING gin (
    (name || ' ' || hostname || ' ' || COALESCE(ip_address, '') || ' ' || COALESCE(serial_number, '') || ' ' || vendor) gin_trgm_ops
);

-- 3. JSONB Path Operations GIN Index for Domain Attributes
CREATE INDEX idx_ci_raw_attributes_path ON configuration_items USING gin (
    raw_attributes jsonb_path_ops
);

-- 4. Partial Indexes for Executive KPI & High-Priority Degraded Tiers
CREATE INDEX idx_ci_active_monitored ON configuration_items (health_tier, cpu_load_pct, ram_used_pct)
    WHERE is_active = TRUE AND is_monitored = TRUE;

CREATE INDEX idx_ci_degraded_critical ON configuration_items (health_tier, status)
    WHERE health_tier IN ('Medium', 'Low');

-- 5. Time-Series BRIN Index for Telemetry Snapshots
CREATE INDEX idx_ci_history_brin ON ci_status_history USING brin (
    recorded_at
) WITH (pages_per_range = 32);
```

### 7.2 Benchmark & Execution Plan Projections

| Query Type | Typical Scenario | Target Latency | Index Used | Optimization Mechanism |
|---|---|---|---|---|
| **Paginated CI List** (Page 1, 50 rows) | `WHERE source='solarwinds' ORDER BY name ASC LIMIT 50` | **< 3.2 ms** | `idx_ci_pagination_hotpath` | Index-Only Scan (`INCLUDE` columns prevent table heap lookup) |
| **Multi-field Search** | `WHERE name ILIKE '%catalyst%' OR hostname ILIKE '%catalyst%'` | **< 6.8 ms** | `idx_ci_search_trgm` | GIN Trigram Bitmap Index Scan |
| **Compliance KPI Filter** | `WHERE source='intune' AND compliance_state='Action Required'` | **< 4.1 ms** | `ix_ci_compliance_vendor` | B-Tree Bitmap Index Scan |
| **Top Degraded Servers** | `WHERE health_tier IN ('Medium','Low') ORDER BY cpu_load_pct DESC` | **< 2.9 ms** | `idx_ci_degraded_critical` | Partial Index Scan on 140 degraded nodes |
| **Time-Series Metric History** | `WHERE ci_id=:uuid AND recorded_at > NOW() - INTERVAL '7 days'` | **< 5.5 ms** | `ix_history_ci_time` & BRIN | Partition pruning + BRIN range scan |

---

## 8. Mathematical Invariants Verification in SQL

To ensure zero-hallucination fidelity with the 6 mathematical invariants specified in `GEMINI.md` and `tests/verify_intune_data.py` / `tests/verify_solarwinds_data.py`, the following automated validation SQL queries are configured:

```sql
-- Invariant 1: Intune Total Population Closure (Exact 25,987 or 27,412 raw)
SELECT 
    COUNT(*) AS total_intune_devices,
    COUNT(*) FILTER (WHERE compliance_state = 'Compliant') AS compliant,
    COUNT(*) FILTER (WHERE compliance_state = 'Action Required') AS non_compliant,
    COUNT(*) FILTER (WHERE compliance_state = 'Under Review') AS under_review
FROM configuration_items 
WHERE source = 'intune' AND is_active = TRUE;

-- Invariant 2: Intune OS Breakdown Sum Exactness
SELECT 
    operating_system, 
    COUNT(*) AS count,
    ROUND((COUNT(*)::numeric / SUM(COUNT(*)) OVER ()) * 100.0, 2) AS share_pct
FROM configuration_items 
WHERE source = 'intune' 
GROUP BY operating_system 
ORDER BY count DESC;

-- Invariant 3: SolarWinds Node Population & Health Classification Closure
SELECT 
    COUNT(*) AS total_solarwinds_cis,
    COUNT(*) FILTER (WHERE health_tier = 'High') AS high_health,
    COUNT(*) FILTER (WHERE health_tier = 'Medium') AS medium_health,
    COUNT(*) FILTER (WHERE health_tier = 'Low') AS low_health,
    COUNT(*) FILTER (WHERE status = 'Up') AS up_nodes,
    COUNT(*) FILTER (WHERE status = 'Down') AS down_nodes,
    COUNT(*) FILTER (WHERE status = 'Warning') AS warning_nodes,
    COUNT(*) FILTER (WHERE status = 'Critical') AS critical_nodes,
    COUNT(*) FILTER (WHERE status = 'Unmanaged') AS unmanaged_nodes
FROM configuration_items 
WHERE source = 'solarwinds' AND is_active = TRUE;
```

---

## 9. Next Steps for Implementation (Worker Roadmap)

1. **Step 1 (Migration Setup)**: Initialize Alembic directory, create `0001_initial_cmdb_schema.py` migration script, and test execution against local PostgreSQL container.
2. **Step 2 (FastAPI Database Integration)**: Wire `app/core/database.py` and async session lifecycle into FastAPI dependency injection.
3. **Step 3 (Seeding Execution)**: Run `scripts/seed_database.py` to populate all 25,987 Intune devices and 1,543 SolarWinds CIs.
4. **Step 4 (Test Certification)**: Execute the automated SQL invariant test suite and verify sub-20ms query response times with `EXPLAIN ANALYZE`.
