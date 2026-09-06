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

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "source_system": self.source_system,
            "status": self.status,
            "records_processed": self.records_processed,
            "records_updated": self.records_updated,
            "records_unchanged": self.records_unchanged,
            "items_extracted": self.items_extracted,
            "items_persisted": self.items_persisted,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_logs": [log.to_dict() for log in self.error_logs] if self.error_logs else [],
        }


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

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "sync_run_id": str(self.sync_run_id),
            "error_code": self.error_code,
            "error_type": self.error_code,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "context_data": self.context_data or {},
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }

