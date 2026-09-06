"""High-performance bulk database seeding service for Microsoft Intune and SolarWinds telemetry."""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ci import CIRelationship, ConfigurationItem
from app.models.history import CIStatusHistory
from app.models.sync import SyncRun

def _find_project_root() -> str:
    cur = os.path.abspath(__file__)
    while cur and os.path.dirname(cur) != cur:
        cur = os.path.dirname(cur)
        if os.path.exists(os.path.join(cur, "data")):
            return cur
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PROJECT_ROOT = _find_project_root()


def normalize_intune_manufacturer(mfg: Optional[str]) -> str:
    """Normalize Intune raw manufacturer string to standardized vendor name."""
    if not mfg or not isinstance(mfg, str):
        return "Other"
    mfg_lower = mfg.strip().lower()
    if "dell" in mfg_lower:
        return "Dell"
    if "hp" in mfg_lower or "hewlett" in mfg_lower:
        return "HP"
    if "lenovo" in mfg_lower:
        return "Lenovo"
    if "apple" in mfg_lower:
        return "Apple"
    if "microsoft" in mfg_lower:
        return "Microsoft"
    return "Other"


def normalize_solarwinds_vendor(vendor: Optional[str]) -> str:
    """Normalize SolarWinds vendor strings."""
    if not vendor or not isinstance(vendor, str):
        return "Other"
    v = vendor.strip().lower()
    if "cisco" in v:
        return "Cisco"
    if "windows" in v or "microsoft" in v:
        return "Windows"
    if "linux" in v or "ubuntu" in v or "redhat" in v or "centos" in v:
        return "Linux"
    if "solarwinds" in v:
        return "SolarWinds"
    if "juniper" in v:
        return "Juniper"
    if "fortinet" in v:
        return "Fortinet"
    if "palo" in v:
        return "Palo Alto"
    if "vmware" in v:
        return "VMware"
    return "Other"


def classify_device_role(technology: Optional[str], model: Optional[str], node_desc: Optional[str] = "") -> str:
    """Classify SolarWinds node into canonical architectural role."""
    tech_str = (str(technology) if technology is not None else "").lower()
    model_str = (str(model) if model is not None else "").lower()
    desc_str = (str(node_desc) if node_desc is not None else "").lower()
    combined = f"{tech_str} {model_str} {desc_str}"

    if any(k in combined for k in ["asa 55", "firepower", "palo alto", "pa-32", "fortinet", "fortigate", "firewall", "check point"]):
        return "Firewall"
    if any(k in combined for k in ["wlc", "3504 wireless", "5520", "controller", "c9800", "ctvm"]):
        return "Wireless Controller"
    if any(k in combined for k in ["3925", "892fsp", "c8300", "isr", "asr", "router", "voice-rtr", "cube"]):
        return "Router"
    if any(k in combined for k in ["versa", "cpe", "appliance", "nutanix", "broadcom", "mikrotik"]):
        return "Network Appliance"
    if any(k in combined for k in ["nexus", "n9k", "9500", "9600", "c9606", "9400", "c9407", "c9410", "4500", "4510", "core"]):
        return "Core Switch"
    if any(k in combined for k in ["3850", "38xx", "3650", "36xx", "9300", "c9300", "distribution"]):
        return "Distribution Switch"
    if any(k in combined for k in ["2960", "c9200", "9200", "3560", "3750", "switch", "catalyst", "juniper ex"]):
        return "Access Switch"
    if any(k in combined for k in ["windows", "server 20", "linux", "ubuntu", "redhat", "centos", "debian", "esx", "vmware", "hyper-v", "intel64"]):
        return "Server"
    return "Server" if "windows" in tech_str else "Access Switch"


def classify_node_health(node: Dict[str, Any]) -> str:
    """Classify SolarWinds node health tier (High, Medium, Low)."""
    status = node.get("Status", 0)
    cpu = node.get("CPULoad")
    ram = node.get("PercentMemoryUsed")

    cpu_val = float(cpu) if cpu is not None and float(cpu) >= 0 else 0.0
    ram_val = float(ram) if ram is not None and float(ram) >= 0 else 0.0

    if status in [2, 14, 0] or cpu_val > 90.0 or ram_val > 90.0:
        return "Low"
    if status == 3 or (75.0 <= cpu_val <= 90.0) or (80.0 <= ram_val <= 90.0):
        return "Medium"
    if status == 1 and cpu_val < 75.0 and ram_val < 80.0:
        return "High"
    return "Medium"


def map_node_status_string(status_code: Optional[int]) -> str:
    """Map numeric SolarWinds status code to string."""
    status_map = {
        1: "Up",
        2: "Down",
        3: "Warning",
        9: "Unmanaged",
        14: "Critical",
        0: "Unknown",
    }
    return status_map.get(status_code, "Unknown")


def parse_clean_os(machine_type: Optional[str], node_desc: Optional[str], vendor: Optional[str]) -> str:
    """Extract clean operating system name."""
    desc = node_desc or ""
    mt = machine_type or ""

    if "Windows Version" in desc:
        if "17763" in desc:
            return "Windows Server 2019"
        if "20348" in desc:
            return "Windows Server 2022"
        if "14393" in desc:
            return "Windows Server 2016"
        return "Windows Server"
    if "Windows 2019" in mt:
        return "Windows Server 2019"
    if "Windows 2022" in mt:
        return "Windows Server 2022"
    if "Hyper-V" in mt:
        return "Microsoft Hyper-V Server"
    if "ESX" in mt or "VMware" in mt:
        return "VMware ESXi"
    if "Cisco IOS Software" in desc:
        if "Version " in desc:
            ver_part = desc.split("Version ")[1].split(",")[0].split(" ")[0].strip()
            return f"Cisco IOS {ver_part}"
        return "Cisco IOS-XE"
    if "Adaptive Security Appliance" in desc or "ASA Version" in desc:
        return "Cisco ASA OS"
    if "Palo Alto" in desc or "PA-" in mt:
        return "PAN-OS"
    if "Versa" in desc or "Versa" in mt:
        return "Versa Operating System (VOS)"
    if "Fortinet" in (vendor or ""):
        return "FortiOS"
    return mt if mt and mt != "Unknown" else "Proprietary Firmware"


def parse_iso_datetime(dt_str: Optional[str]) -> datetime:
    """Parse ISO 8601 string or return current UTC timestamp."""
    if not dt_str:
        return datetime.now(timezone.utc)
    try:
        clean_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except Exception:
        return datetime.now(timezone.utc)


async def seed_database(
    session: AsyncSession,
    data_dir: Optional[str] = None,
    batch_size: int = 1000,
    clean_existing: bool = True,
) -> Dict[str, Any]:
    """Incorporate all 25,987 Intune CIs and 1,543 SolarWinds CIs into PostgreSQL/SQLite."""
    start_time = time.time()
    started_at = datetime.now(timezone.utc)
    target_data_dir = data_dir or os.path.join(PROJECT_ROOT, "data")

    intune_file = os.path.join(target_data_dir, "intune_ops_analytics.json")
    sw_file = os.path.join(target_data_dir, "solarwinds_nodes.json")

    from app.services.sync_service import SyncService

    logger.info("Starting database seeding from %s...", target_data_dir)

    if clean_existing:
        logger.info("Cleaning existing ConfigurationItem records...")
        await session.execute(delete(CIStatusHistory))
        await session.execute(delete(CIRelationship))
        await session.execute(delete(ConfigurationItem))
        await session.flush()

    ci_records: List[Dict[str, Any]] = []
    history_records: List[Dict[str, Any]] = []

    # -------------------------------------------------------------
    # 1. Ingest Microsoft Intune Devices (25,987 Endpoints)
    # -------------------------------------------------------------
    intune_count = 0
    if os.path.exists(intune_file):
        with open(intune_file, "r", encoding="utf-8") as f:
            intune_data = json.load(f)
        devices = intune_data.get("devices", [])
        logger.info("Loaded %d Intune devices from JSON.", len(devices))

        for dev in devices:
            ci_id = uuid.uuid4()
            dev_id = str(dev.get("id", ""))
            dev_name = str(dev.get("deviceName") or f"Device-{dev_id[:8]}")
            raw_os = str(dev.get("operatingSystem") or "Endpoint")
            raw_comp = str(dev.get("complianceState") or "unknown").lower()
            mfg = str(dev.get("manufacturer") or "Other")
            model = dev.get("model")
            serial = dev.get("serialNumber")
            os_ver = dev.get("osVersion")
            sync_dt = parse_iso_datetime(dev.get("lastSyncDateTime"))

            # Determine compliance status string
            if raw_comp == "compliant":
                status = "Compliant"
                health_tier = "High"
            elif raw_comp == "noncompliant":
                status = "Noncompliant"
                health_tier = "Low"
            else:
                status = raw_comp.capitalize()
                health_tier = "Medium"

            total_storage = dev.get("totalStorageSpaceInBytes")
            free_storage = dev.get("freeStorageSpaceInBytes")
            storage_pct = None
            if total_storage and free_storage and total_storage > 0:
                storage_pct = round(((total_storage - free_storage) / total_storage) * 100.0, 1)

            attributes = {
                "user_principal_name": dev.get("userPrincipalName"),
                "total_storage_bytes": total_storage,
                "free_storage_bytes": free_storage,
                "raw_compliance_state": dev.get("complianceState"),
                "raw_manufacturer": mfg,
                "os_version": os_ver,
            }

            ci_records.append({
                "id": ci_id,
                "source_id": dev_id,
                "source_system": "INTUNE",
                "name": dev_name,
                "ci_type": raw_os if raw_os else "Endpoint",
                "status": status,
                "health_tier": health_tier,
                "ip_address": None,
                "mac_address": None,
                "vendor": normalize_intune_manufacturer(mfg),
                "model": model,
                "serial_number": serial,
                "operating_system": f"{raw_os} {os_ver}".strip() if os_ver else raw_os,
                "location": None,
                "last_sync_time": sync_dt,
                "state_hash": SyncService.compute_state_fingerprint({
                    "status": status,
                    "health_tier": health_tier,
                    "cpu_load": None,
                    "ram_used": None,
                    "storage_used": storage_pct,
                }),
                "attributes": attributes,
                "created_at": started_at,
                "updated_at": started_at,
            })

            history_records.append({
                "id": uuid.uuid4(),
                "ci_id": ci_id,
                "status": status,
                "health_tier": health_tier,
                "previous_status": None,
                "previous_health_tier": None,
                "cpu_utilization": None,
                "memory_utilization": None,
                "storage_used_pct": storage_pct,
                "latency_ms": None,
                "changed_attributes": {"event": "INITIAL_SEED_INGESTION"},
                "recorded_at": sync_dt,
            })
            intune_count += 1
    else:
        logger.warning("Intune dataset not found at %s", intune_file)

    # -------------------------------------------------------------
    # 2. Ingest SolarWinds Orion Server Nodes (1,543 CIs)
    # -------------------------------------------------------------
    sw_count = 0
    if os.path.exists(sw_file):
        with open(sw_file, "r", encoding="utf-8") as f:
            sw_data = json.load(f)
        nodes = sw_data.get("nodes", [])
        logger.info("Loaded %d SolarWinds nodes from JSON.", len(nodes))

        for n in nodes:
            ci_id = uuid.uuid4()
            node_id = str(n.get("NodeID", ""))
            caption = str(n.get("Caption", f"Node-{node_id}")).strip()
            ip = str(n.get("IPAddress", "")).strip() or None
            vendor = str(n.get("Vendor", "Unknown")).strip()
            machine_type = str(n.get("MachineType", "Unknown")).strip()
            desc = str(n.get("NodeDescription", "")).strip()
            city = str(n.get("City", "")).strip() or "Default Location"
            status_code = n.get("Status", 0)
            cpu = n.get("CPULoad")
            ram = n.get("PercentMemoryUsed")
            latency = n.get("AvgResponseTime") or n.get("ResponseTime")
            uptime_s = n.get("SystemUpTime")
            sync_dt = parse_iso_datetime(n.get("LastSync"))

            ci_type = classify_device_role(vendor, machine_type, desc)
            health_tier = classify_node_health(n)
            status_str = map_node_status_string(status_code)
            clean_os = parse_clean_os(machine_type, desc, vendor)

            cpu_val = float(cpu) if cpu is not None and float(cpu) >= 0 else None
            ram_val = float(ram) if ram is not None and float(ram) >= 0 else None
            latency_val = float(latency) if latency is not None and float(latency) >= 0 else None

            attributes = {
                "cpu_load": cpu_val,
                "memory_used": ram_val,
                "latency_ms": latency_val,
                "uptime_seconds": float(uptime_s) if uptime_s is not None else None,
                "description": desc,
                "contact": n.get("Contact", ""),
                "status_code": status_code,
                "status_description": n.get("StatusDescription", ""),
            }

            ci_records.append({
                "id": ci_id,
                "source_id": f"SW-NODE-{node_id}",
                "source_system": "SOLARWINDS",
                "name": caption,
                "ci_type": ci_type,
                "status": status_str,
                "health_tier": health_tier,
                "ip_address": ip,
                "mac_address": None,
                "vendor": normalize_solarwinds_vendor(vendor),
                "model": machine_type if machine_type != "Unknown" else ci_type,
                "serial_number": None,
                "operating_system": clean_os,
                "location": city,
                "last_sync_time": sync_dt,
                "state_hash": SyncService.compute_state_fingerprint({
                    "status": status_str,
                    "health_tier": health_tier,
                    "cpu_load": cpu_val,
                    "ram_used": ram_val,
                    "storage_used": None,
                }),
                "attributes": attributes,
                "created_at": started_at,
                "updated_at": started_at,
            })

            history_records.append({
                "id": uuid.uuid4(),
                "ci_id": ci_id,
                "status": status_str,
                "health_tier": health_tier,
                "previous_status": None,
                "previous_health_tier": None,
                "cpu_utilization": cpu_val,
                "memory_utilization": ram_val,
                "storage_used_pct": None,
                "latency_ms": latency_val,
                "changed_attributes": {"event": "INITIAL_SEED_INGESTION"},
                "recorded_at": sync_dt,
            })
            sw_count += 1
    else:
        logger.warning("SolarWinds dataset not found at %s", sw_file)

    total_records = len(ci_records)
    logger.info("Executing bulk insert of %d CIs in batches of %d...", total_records, batch_size)

    # Bulk insert ConfigurationItems
    for i in range(0, len(ci_records), batch_size):
        chunk = ci_records[i : i + batch_size]
        await session.execute(insert(ConfigurationItem), chunk)

    # Bulk insert CIStatusHistory
    for i in range(0, len(history_records), batch_size):
        chunk = history_records[i : i + batch_size]
        await session.execute(insert(CIStatusHistory), chunk)

    elapsed_ms = int((time.time() - start_time) * 1000)
    completed_at = datetime.now(timezone.utc)

    # Record authoritative baseline SyncRun
    sync_run = SyncRun(
        id=uuid.uuid4(),
        source_system="ALL",
        status="SUCCESS",
        records_processed=total_records,
        records_updated=0,
        records_unchanged=total_records,
        items_extracted=total_records,
        items_persisted=total_records,
        duration_ms=elapsed_ms,
        started_at=started_at,
        completed_at=completed_at,
    )
    session.add(sync_run)
    await session.commit()

    logger.info(
        "Successfully seeded database: %d Intune CIs + %d SolarWinds CIs = %d Total CIs in %d ms.",
        intune_count,
        sw_count,
        total_records,
        elapsed_ms,
    )

    return {
        "status": "success",
        "intune_cis_seeded": intune_count,
        "solarwinds_cis_seeded": sw_count,
        "total_cis_seeded": total_records,
        "history_records_created": len(history_records),
        "duration_ms": elapsed_ms,
        "sync_run_id": str(sync_run.id),
    }
