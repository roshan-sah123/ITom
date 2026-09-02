"""Execution audit run and error log models for telemetry synchronization."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, UUIDPrimaryKeyMixin, UUIDType


class SyncRun(Base, UUIDPrimaryKeyMixin):
    """Audit log tracking each telemetry ingestion run across external domains."""

    __tablename__ = "sync_runs"

    source_system: Mapped[str] = mapped_column(String(32), nullable=False)  # "SOLARWINDS" | "INTUNE" | "ALL"
    status: Mapped[str] = mapped_column(String(32), nullable=False)         # "SUCCESS" | "FAILED" | "PARTIAL" | "RUNNING"
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_persisted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    error_logs: Mapped[List["SyncErrorLog"]] = relationship(
        "SyncErrorLog",
        back_populates="sync_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_sync_runs_source_completed", "source_system", "completed_at"),
        Index("ix_sync_runs_status", "status"),
    )


class SyncErrorLog(Base, UUIDPrimaryKeyMixin):
    """Detailed error and diagnostic context captured during telemetry synchronization."""

    __tablename__ = "sync_error_logs"

    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    error_code: Mapped[str] = mapped_column(String(64), nullable=False, default="GENERAL_ERROR")
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_data: Mapped[Dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    sync_run: Mapped["SyncRun"] = relationship(
        "SyncRun",
        back_populates="error_logs",
    )

    __table_args__ = (
        Index("ix_sync_error_logs_run_id", "sync_run_id"),
        Index("ix_sync_error_logs_occurred_at", "occurred_at"),
    )
