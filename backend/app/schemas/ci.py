"""Pydantic v2 schemas for Configuration Items, Relationships, and CMDB Summaries."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ConfigurationItemBase(BaseModel):
    """Base schema for Configuration Item properties."""

    source_id: str = Field(..., description="Unique ID within source system")
    source_system: str = Field(..., description="Origin system: SOLARWINDS or INTUNE")
    name: str = Field(..., description="Host name, device caption, or asset tag")
    ci_type: str = Field(..., description="CI Type classification")
    status: str = Field(..., description="Operational status: Up, Down, Compliant, etc.")
    health_tier: str = Field(..., description="Health category: High, Medium, Low")
    ip_address: Optional[str] = Field(None, description="Primary IPv4 or IPv6 address")
    mac_address: Optional[str] = Field(None, description="MAC address")
    vendor: str = Field("Other", description="Hardware or software vendor")
    model: Optional[str] = Field(None, description="Hardware model or OS edition")
    serial_number: Optional[str] = Field(None, description="Hardware serial number")
    operating_system: Optional[str] = Field(None, description="Operating system version")
    location: Optional[str] = Field(None, description="Data center, site, or city location")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Domain-specific dynamic attributes")


class ConfigurationItemCreate(ConfigurationItemBase):
    """Schema for creating a new Configuration Item."""

    last_sync_time: Optional[datetime] = None
    state_hash: Optional[str] = None


class ConfigurationItemUpdate(BaseModel):
    """Schema for updating an existing Configuration Item."""

    name: Optional[str] = None
    ci_type: Optional[str] = None
    status: Optional[str] = None
    health_tier: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    operating_system: Optional[str] = None
    location: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    last_sync_time: Optional[datetime] = None
    state_hash: Optional[str] = None


class ConfigurationItemRead(ConfigurationItemBase):
    """Authoritative output schema for a Configuration Item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    last_sync_time: datetime
    state_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CIRelationshipBase(BaseModel):
    """Base schema for CI relationships."""

    source_ci_id: uuid.UUID
    target_ci_id: uuid.UUID
    relationship_type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class CIRelationshipCreate(CIRelationshipBase):
    """Schema for creating a CI relationship."""
    pass


class CIRelationshipRead(CIRelationshipBase):
    """Output schema for a CI relationship."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class CIStatusHistoryRead(BaseModel):
    """Output schema for historical CI status transitions."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ci_id: uuid.UUID
    status: str
    health_tier: str
    previous_status: Optional[str] = None
    previous_health_tier: Optional[str] = None
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    storage_used_pct: Optional[float] = None
    latency_ms: Optional[float] = None
    changed_attributes: Dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime


class CMDBSummaryRead(BaseModel):
    """Fleet-wide CMDB summary and breakdown schema."""

    total_cis: int
    total_servers: int
    total_network_devices: int
    total_endpoints: int
    health_breakdown: Dict[str, int]
    status_breakdown: Dict[str, int]
    ci_type_distribution: Dict[str, int]
    vendor_distribution: Dict[str, int]
    compliance_rate_pct: float
