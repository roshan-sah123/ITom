"""Pydantic v2 validation and serialization schemas for ITOM Portal."""

from app.schemas.ci import (
    CIRelationshipBase,
    CIRelationshipCreate,
    CIRelationshipRead,
    CIStatusHistoryRead,
    CMDBSummaryRead,
    ConfigurationItemBase,
    ConfigurationItemCreate,
    ConfigurationItemRead,
    ConfigurationItemUpdate,
)
from app.schemas.common import (
    ErrorResponse,
    FreshnessMetadata,
    HealthResponse,
    PaginatedResponse,
    PaginationMeta,
    PaginationParams,
    ReadOnlyErrorResponse,
)
from app.schemas.sync import (
    SyncErrorLogBase,
    SyncErrorLogCreate,
    SyncErrorLogRead,
    SyncRunBase,
    SyncRunCreate,
    SyncRunRead,
    SyncRunUpdate,
    SyncTriggerResponse,
)

__all__ = [
    "PaginationParams",
    "PaginationMeta",
    "PaginatedResponse",
    "FreshnessMetadata",
    "HealthResponse",
    "ReadOnlyErrorResponse",
    "ErrorResponse",
    "ConfigurationItemBase",
    "ConfigurationItemCreate",
    "ConfigurationItemUpdate",
    "ConfigurationItemRead",
    "CIRelationshipBase",
    "CIRelationshipCreate",
    "CIRelationshipRead",
    "CIStatusHistoryRead",
    "CMDBSummaryRead",
    "SyncRunBase",
    "SyncRunCreate",
    "SyncRunUpdate",
    "SyncRunRead",
    "SyncErrorLogBase",
    "SyncErrorLogCreate",
    "SyncErrorLogRead",
    "SyncTriggerResponse",
]
