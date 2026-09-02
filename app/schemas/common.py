"""Common Pydantic v2 schemas for pagination, freshness, and response envelopes."""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Standardized pagination and search query parameters."""

    page: int = Field(1, ge=1, description="1-based page number")
    page_size: int = Field(25, ge=1, le=100, description="Items per page (allowed: 10, 25, 50, 100)")
    search: Optional[str] = Field(None, description="Debounced full-text search string")
    sort_by: Optional[str] = Field(None, description="Column name to sort results by")
    sort_order: Optional[str] = Field("asc", description="Sort order: 'asc' or 'desc'")


class PaginationMeta(BaseModel):
    """Pagination metadata included in collection envelopes."""

    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """Authoritative paginated collection response envelope."""

    model_config = ConfigDict(from_attributes=True)

    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class FreshnessMetadata(BaseModel):
    """Authoritative freshness metadata tracking sync intervals."""

    last_synchronized_at: Optional[datetime] = None
    data_age_seconds: int = 0
    sync_status: str = "FRESH"  # "FRESH" if age <= 900s, else "STALE"
    source_mode: str = "LIVE_MIRROR"


class HealthResponse(BaseModel):
    """System liveness and readiness probe payload."""

    status: str = "ok"
    version: str = "2.0.0"
    database: str = "connected"
    timestamp: datetime


class ReadOnlyErrorResponse(BaseModel):
    """HTTP 405 Method Not Allowed error payload for read-only integrations."""

    error: str = "Forbidden: SolarWinds/Intune Telemetry API is strictly READ-ONLY."
    allowed_methods: List[str] = ["GET"]


class ErrorResponse(BaseModel):
    """Generic error envelope."""

    error: str
    detail: Optional[Any] = None
