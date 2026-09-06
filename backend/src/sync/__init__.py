"""ITOM Microsoft Intune Telemetry Ingestion and Synchronization Subsystem.

This package provides enterprise data extraction, aggregation, normalization,
and synchronization services connecting Microsoft Graph API Intune telemetry
to the ITOM Operations Analytics dashboard and persistence stores.
"""

from src.sync.firestore_sync import FirestoreSyncService
from src.sync.graph_client import GraphApiError, GraphAuthError, GraphClient
from src.sync.payload_generator import (
    PayloadGenerator,
    calculate_metrics,
    create_dashboard_summary,
    format_sample_devices,
    generate_breakdowns,
    normalize_manufacturer,
)
from src.sync.solarwinds_client import (
    SolarWindsApiError,
    SolarWindsAuthError,
    SolarWindsClient,
    classify_node_health,
    normalize_solarwinds_vendor,
)
from src.sync.cmdb_generator import (
    CMDBDataExtractor,
    CMDBService,
    classify_compliance_state,
    classify_device_role,
    classify_hardware_vendor,
    generate_cmdb_artifacts,
)

__version__ = "1.0.0"
__all__ = [
    "GraphClient",
    "GraphAuthError",
    "GraphApiError",
    "PayloadGenerator",
    "FirestoreSyncService",
    "SolarWindsClient",
    "SolarWindsAuthError",
    "SolarWindsApiError",
    "classify_node_health",
    "normalize_solarwinds_vendor",
    "normalize_manufacturer",
    "calculate_metrics",
    "generate_breakdowns",
    "format_sample_devices",
    "create_dashboard_summary",
    "CMDBService",
    "CMDBDataExtractor",
    "classify_device_role",
    "classify_hardware_vendor",
    "classify_compliance_state",
    "generate_cmdb_artifacts",
]

