"""Pydantic v2 schemas for Sync Runs and Sync Error Logs."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """Make SQLite-naive persisted UTC timestamps explicit for JSON output."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SyncRunBase(BaseModel):
    """Base schema for sync execution run."""

    source_system: str = Field(..., description="SOLARWINDS, INTUNE, or ALL")
    status: str = Field("RUNNING", description="SUCCESS, FAILED, PARTIAL, or RUNNING")
    records_processed: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    records_retired: int = 0
    records_failed: int = 0
    items_normalized: int = 0
    items_extracted: int = 0
    items_persisted: int = 0
    duration_ms: int = 0


class SyncRunCreate(SyncRunBase):
    """Schema for initializing a sync run."""

    started_at: Optional[datetime] = None


class SyncRunUpdate(BaseModel):
    """Schema for completing or updating a sync run."""

    status: Optional[str] = None
    records_processed: Optional[int] = None
    records_updated: Optional[int] = None
    records_unchanged: Optional[int] = None
    items_extracted: Optional[int] = None
    items_persisted: Optional[int] = None
    duration_ms: Optional[int] = None
    completed_at: Optional[datetime] = None


class SyncErrorLogBase(BaseModel):
    """Base schema for sync error diagnostic records."""

    error_code: str = "GENERAL_ERROR"
    error_message: str
    stack_trace: Optional[str] = None
    context_data: Dict[str, Any] = Field(default_factory=dict)


class SyncErrorLogCreate(SyncErrorLogBase):
    """Schema for creating a sync error log."""

    sync_run_id: uuid.UUID


class SyncErrorLogRead(SyncErrorLogBase):
    """Output schema for a sync error log."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sync_run_id: uuid.UUID
    occurred_at: datetime

    # Stored diagnostics can contain connection details, including old records.
    @field_serializer("error_message")
    def public_error_message(self, value: str) -> str:
        return "Synchronization failed. Contact the administrator with the sync run ID."

    @field_serializer("stack_trace")
    def private_stack_trace(self, value: Optional[str]) -> None:
        return None

    @field_serializer("context_data")
    def private_context(self, value: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    @field_serializer("occurred_at")
    def serialize_occurred_at(self, value: datetime) -> str:
        return _utc_datetime(value).isoformat()


class SyncRunRead(SyncRunBase):
    """Authoritative output schema for a sync run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_logs: List[SyncErrorLogRead] = Field(default_factory=list)

    @field_serializer("started_at", "completed_at")
    def serialize_run_time(self, value: Optional[datetime]) -> Optional[str]:
        normalized = _utc_datetime(value)
        return normalized.isoformat() if normalized else None


class SyncTriggerResponse(BaseModel):
    """Response returned when triggering an asynchronous background sync."""

    message: str
    run_id: Optional[uuid.UUID] = None
    status: str
    timestamp: datetime
