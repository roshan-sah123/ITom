"""Telemetry source adapters - the bridge between live APIs and the CMDB.

WHY THIS FILE EXISTS
--------------------
``sync_service`` previously read ``data/*.json`` from disk on every cycle:

    intune_file = os.path.join(PROJECT_ROOT, "data", "intune_ops_analytics.json")
    sw_file     = os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json")

Three consequences:

1. The 10-minute scheduler re-ingested the *same static file* forever, so the
   data never actually refreshed no matter how long the server ran.
2. ``intune_file`` was assigned but never used - there was no Intune branch at
   all, so ``source_system="INTUNE"`` reported SUCCESS having done nothing.
3. A sync could not fail. Reading a local file always works, so the freshness
   clock advanced even when Graph and SolarWinds were unreachable.

This module wires the real clients in. Each source exposes ``fetch()`` returning
normalised CI dictionaries ready for ``ingest_telemetry_batch``.

FIELD MAPPING PARITY
--------------------
The normalisation below mirrors ``app/services/seed_service.py`` exactly, so a
live sync and a seed produce identical rows for the same device. If you change
one, change the other.

OFFLINE MODE
------------
``FixtureSource`` reproduces the old file-reading behaviour. It is retained
deliberately for tests and air-gapped demos, but it is never the default -
production must fail loudly rather than silently serve a stale file.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger("itom.sources")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --------------------------------------------------------------------------- #
# SolarWinds Orion status vocabulary
# --------------------------------------------------------------------------- #
# The previous mapping collapsed everything that was not 1 or 3 into "Down":
#
#     "status": "Up" if Status == 1 else ("Warning" if Status == 3 else "Down")
#
# That turned Critical (14) and Unmanaged (9) into Down. Against the documented
# fleet - Up 1370, Warning 25, Critical 35, Down 6, Unmanaged 112 - the database
# would have shown Down = 153 instead of 6. An unmanaged node is not down; it is
# simply not being watched, and paging someone at 3am on that difference matters.
ORION_STATUS_MAP: Dict[int, str] = {
    0: "Unknown",
    1: "Up",
    2: "Down",
    3: "Warning",
    4: "Shutdown",
    9: "Unmanaged",
    14: "Critical",
    17: "Undefined",
    19: "Unreachable",
    22: "Inactive",
}

# The old mapping only ever emitted "High" or "Medium", so health_tier="Low"
# was unreachable and the documented "Low/Critical 41 nodes" could never be
# reproduced from the database.
ORION_HEALTH_MAP: Dict[str, str] = {
    "Up": "High",
    "Warning": "Medium",
    "Shutdown": "Medium",
    "Unmanaged": "Medium",
    "Inactive": "Medium",
    "Unknown": "Medium",
    "Undefined": "Medium",
    "Down": "Low",
    "Critical": "Low",
    "Unreachable": "Low",
}

# Resource thresholds that downgrade an otherwise-healthy node.
CPU_CRITICAL_PCT = 90.0
RAM_CRITICAL_PCT = 90.0
CPU_WARNING_PCT = 75.0
RAM_WARNING_PCT = 80.0


class SourceUnavailableError(RuntimeError):
    """Raised when a telemetry source cannot be reached or authenticated.

    This must propagate. The sync run is then recorded as FAILED and the
    freshness clock does not advance - which is the entire point.
    """


def validated_snapshot(raw, normalizer):
    """Reject incomplete/malformed identity sets before authorizing retirement."""
    if not isinstance(raw, list) or not raw:
        raise SourceUnavailableError("Empty or invalid source snapshot")
    items = []
    seen = set()
    for row in raw:
        if not isinstance(row, dict):
            raise SourceUnavailableError("Malformed source row")
        item = normalizer(row)
        if not item or not item.get("external_id"):
            raise SourceUnavailableError("Source record lacks a valid identifier")
        if item["external_id"] in seen:
            raise SourceUnavailableError("Duplicate source identifier")
        seen.add(item["external_id"])
        items.append(item)
    return items


def _num(value: Any) -> Optional[float]:
    """Coerce to a non-negative float, or None if the value is unusable."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value >= 0 else None


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp defensively, returning None on failure."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def normalize_vendor(raw: Optional[str]) -> str:
    """Normalise an OEM string to a canonical vendor bucket.

    ``include_microsoft`` was False by default in the old payload generator, so
    every Surface device silently became "Other". Microsoft is a real bucket here.
    """
    if not raw or not isinstance(raw, str):
        return "Other"
    text = raw.strip().lower()
    if "dell" in text:
        return "Dell"
    if text.startswith("hp") or "hewlett" in text or "hpe" in text:
        return "HP"
    if "lenovo" in text:
        return "Lenovo"
    if "apple" in text:
        return "Apple"
    if "microsoft" in text:
        return "Microsoft"
    if "cisco" in text:
        return "Cisco"
    if "vmware" in text:
        return "VMware"
    return "Other"


def classify_solarwinds_health(status_label: str, cpu: Optional[float], ram: Optional[float]) -> str:
    """Derive a health tier from an Orion status plus resource pressure."""
    base = ORION_HEALTH_MAP.get(status_label, "Medium")
    if base == "Low":
        return "Low"

    if (cpu is not None and cpu > CPU_CRITICAL_PCT) or (ram is not None and ram > RAM_CRITICAL_PCT):
        return "Low"
    if (cpu is not None and cpu >= CPU_WARNING_PCT) or (ram is not None and ram >= RAM_WARNING_PCT):
        return "Medium"
    return base


# --------------------------------------------------------------------------- #
# Normalisation - shared by live and fixture sources
# --------------------------------------------------------------------------- #

def normalize_intune_device(dev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map a Microsoft Graph managed device into a CI dictionary.

    Mirrors ``seed_service`` field-for-field so live and seeded rows match.
    """
    device_id = str(dev.get("id") or "").strip()
    if not device_id:
        return None

    raw_os = str(dev.get("operatingSystem") or "Endpoint")
    raw_compliance = str(dev.get("complianceState") or "unknown").lower()
    manufacturer = str(dev.get("manufacturer") or "Other")
    os_version = dev.get("osVersion")

    if raw_compliance == "compliant":
        status, health = "Compliant", "High"
    elif raw_compliance == "noncompliant":
        status, health = "Noncompliant", "Low"
    else:
        status, health = raw_compliance.capitalize(), "Medium"

    total_storage = dev.get("totalStorageSpaceInBytes")
    free_storage = dev.get("freeStorageSpaceInBytes")

    return {
        "external_id": device_id,
        "name": str(dev.get("deviceName") or f"Device-{device_id[:8]}"),
        "ci_type": raw_os or "Endpoint",
        "status": status,
        "health_tier": health,
        "ip_address": None,
        "vendor": normalize_vendor(manufacturer),
        "model": dev.get("model"),
        "serial_number": dev.get("serialNumber"),
        "operating_system": f"{raw_os} {os_version}".strip() if os_version else raw_os,
        "storage_used": None,
        "attributes": {
            "user_principal_name": dev.get("userPrincipalName"),
            "total_storage_bytes": total_storage,
            "free_storage_bytes": free_storage,
            "raw_compliance_state": dev.get("complianceState"),
            "raw_manufacturer": manufacturer,
            "os_version": os_version,
            "last_sync_date_time": dev.get("lastSyncDateTime"),
        },
    }


def normalize_solarwinds_node(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map an Orion.Nodes row into a CI dictionary, preserving every status."""
    node_id = node.get("NodeID")
    if node_id is None:
        return None

    raw_status = node.get("Status")
    status_code = raw_status if isinstance(raw_status, int) and not isinstance(raw_status, bool) else 0
    status_label = ORION_STATUS_MAP.get(status_code, "Unknown")

    cpu = _num(node.get("CPULoad"))
    ram = _num(node.get("PercentMemoryUsed"))
    latency = _num(node.get("AvgResponseTime"))
    city = str(node.get("City") or "").strip()
    itsm_location = str(node.get("ITSM_Location") or "").strip()
    location = city or itsm_location or None

    return {
        "external_id": f"SW-NODE-{node_id}",
        "name": str(node.get("Caption") or f"Node-{node_id}"),
        "ci_type": str(node.get("MachineType") or "Server"),
        "status": status_label,
        "health_tier": classify_solarwinds_health(status_label, cpu, ram),
        "ip_address": node.get("IPAddress"),
        "vendor": normalize_vendor(node.get("Vendor")),
        "model": node.get("MachineType"),
        "serial_number": None,
        "operating_system": node.get("MachineType"),
        "cpu_load": cpu,
        "ram_used": ram,
        "latency_ms": latency,
        "location": location,
        "attributes": {
            "orion_status_code": status_code,
            "status_description": node.get("StatusDescription"),
            "cpu_load": cpu,
            "memory_used": ram,
            "latency_ms": latency,
            "system_uptime": node.get("SystemUpTime"),
            "node_description": node.get("NodeDescription"),
            "contact": node.get("Contact"),
            "city": city or None,
            "itsm_location": itsm_location or None,
        },
    }


# --------------------------------------------------------------------------- #
# Source adapters
# --------------------------------------------------------------------------- #

class TelemetrySource(Protocol):
    """A named provider of normalised CI records."""

    name: str

    def fetch(self) -> List[Dict[str, Any]]:
        """Return normalised CI dictionaries, or raise SourceUnavailableError."""
        ...


class IntuneSource:
    """Live Microsoft Intune devices via Microsoft Graph.

    Note: ``GraphClient`` is synchronous (requests-based), so callers must run
    ``fetch()`` in a thread executor to avoid blocking the event loop.
    """

    name = "INTUNE"

    def __init__(self, client: Any = None, max_devices: Optional[int] = None) -> None:
        self._client = client
        self.max_devices = max_devices

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from src.sync.graph_client import GraphClient
        except ImportError as exc:  # pragma: no cover - defensive
            raise SourceUnavailableError(f"GraphClient import failed: {exc}") from exc
        self._client = GraphClient()
        return self._client

    def fetch(self) -> List[Dict[str, Any]]:
        client = self._resolve_client()
        self.snapshot_complete = False
        try:
            devices = client.fetch_managed_devices(max_devices=self.max_devices)
        except Exception as exc:
            # Auth failures, network errors and Graph errors all land here and
            # must surface - a failed extraction is never a successful sync.
            raise SourceUnavailableError(f"Intune extraction failed: {exc}") from exc

        self.fetched_count = len(devices)
        items = validated_snapshot(devices, normalize_intune_device)
        self.snapshot_complete = self.max_devices is None
        logger.info("Intune source produced %d CI records from %d raw devices.",
                    len(items), len(devices or []))
        return items


class SolarWindsSource:
    """Live SolarWinds Orion nodes via the read-only SWIS v3 REST API."""

    name = "SOLARWINDS"

    def __init__(self, client: Any = None) -> None:
        self._client = client

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from src.sync.solarwinds_client import SolarWindsClient
        except ImportError as exc:  # pragma: no cover - defensive
            raise SourceUnavailableError(f"SolarWindsClient import failed: {exc}") from exc
        self._client = SolarWindsClient()
        return self._client

    def fetch(self) -> List[Dict[str, Any]]:
        client = self._resolve_client()
        self.snapshot_complete = False
        try:
            nodes = client.fetch_nodes()
        except Exception as exc:
            raise SourceUnavailableError(f"SolarWinds extraction failed: {exc}") from exc

        self.fetched_count = len(nodes)
        items = validated_snapshot(nodes, normalize_solarwinds_node)
        self.snapshot_complete = True
        logger.info("SolarWinds source produced %d CI records from %d raw nodes.",
                    len(items), len(nodes or []))
        return items


class FixtureSource:
    """Reads a local JSON snapshot. FOR TESTS AND AIR-GAPPED DEMOS ONLY.

    This reproduces the old production behaviour deliberately, so it is easy to
    see the difference: a FixtureSource sync can never fail and never refreshes,
    which is precisely why it must not be the production default.
    """

    def __init__(self, source_system: str, file_path: Optional[str] = None) -> None:
        self.name = source_system.upper()
        if file_path:
            self.file_path = file_path
        elif self.name == "INTUNE":
            self.file_path = os.path.join(PROJECT_ROOT, "data", "intune_ops_analytics.json")
        else:
            self.file_path = os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json")

    def fetch(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.file_path):
            raise SourceUnavailableError(f"Fixture file not found: {self.file_path}")

        logger.warning(
            "FixtureSource is serving %s from a local file (%s). "
            "This data does NOT refresh - use live sources in production.",
            self.name, self.file_path,
        )
        with open(self.file_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if self.name == "INTUNE":
            raw = payload.get("devices", []) if isinstance(payload, dict) else payload
            normalised = [normalize_intune_device(d) for d in raw or []]
        else:
            raw = payload.get("nodes", []) if isinstance(payload, dict) else payload
            normalised = [normalize_solarwinds_node(n) for n in raw or []]

        return [item for item in normalised if item is not None]


def build_sources(source_system: str = "ALL", offline: bool = False) -> List[TelemetrySource]:
    """Construct the source adapters for a requested sync scope.

    Args:
        source_system: ``INTUNE``, ``SOLARWINDS`` or ``ALL``.
        offline: When True, use local fixtures instead of live APIs.
    """
    scope = (source_system or "ALL").upper()
    wanted = ["INTUNE", "SOLARWINDS"] if scope == "ALL" else [scope]

    sources: List[TelemetrySource] = []
    for name in wanted:
        if offline:
            sources.append(FixtureSource(name))
        elif name == "INTUNE":
            sources.append(IntuneSource())
        elif name == "SOLARWINDS":
            sources.append(SolarWindsSource())
        else:
            raise ValueError(f"Unknown source system: {name}")
    return sources
