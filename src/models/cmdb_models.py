from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

@dataclass
class Relationship:
    source_ci_id: str
    target_ci_id: str
    relationship_type: str
    target_name: str
    target_type: str
    description: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ConfigurationItem:
    ci_id: str
    name: str
    ci_type: str
    hostname: str
    ip_address: str
    vendor: str
    model: str
    operating_system: str
    status: str
    health_tier: str
    location: str
    source: str = 'SolarWinds'
    mode: str = 'live'
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cpu_load: Optional[float] = None
    memory_used: Optional[float] = None
    latency_ms: Optional[float] = None
    uptime_hours: Optional[float] = None
    contact: str = ''
    description: str = ''
    relationships: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CMDBSummary:
    total_configuration_items: int
    active_monitored_cis: int
    unmanaged_cis: int
    source: str = 'SolarWinds'
    mode: str = 'live'
    last_refreshed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    connection_status: str = 'Connected'
    ci_type_distribution: Dict[str, int] = field(default_factory=dict)
    hardware_vendor_distribution: Dict[str, int] = field(default_factory=dict)
    status_distribution: Dict[str, int] = field(default_factory=dict)
    health_tier_distribution: Dict[str, int] = field(default_factory=dict)
    top_locations: List[Dict[str, Any]] = field(default_factory=list)
    top_resource_pressure_cis: List[Dict[str, Any]] = field(default_factory=list)
    sample_cis: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
