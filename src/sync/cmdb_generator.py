"""SolarWinds Live CMDB Telemetry Extraction & Normalization Engine.

This module provides a strictly READ-ONLY integration between SolarWinds Orion
and the ITOM CMDB platform, extracting live Configuration Items (CIs), normalizing
device roles (Servers, Core/Distribution/Access Switches, Routers, Firewalls, WLCs),
discovering architectural relationships, and generating verified telemetry payloads.
"""

import csv
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.sync.solarwinds_client import (
    SolarWindsClient,
    SolarWindsApiError,
    SolarWindsAuthError,
    SolarWindsSecurityError,
    classify_node_health,
    normalize_solarwinds_vendor,
)

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_RAW_NODES_PATH = os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json")
DEFAULT_SUMMARY_PATH = os.path.join(PROJECT_ROOT, "data", "cmdb_summary.json")
DEFAULT_CSV_PATH = os.path.join(PROJECT_ROOT, "exports", "cmdb_network_cis_complete.csv")
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "data", "analytics.db")


def atomic_json_dump(data: Any, filepath: str, indent: Optional[int] = 2) -> None:
    """Safely write JSON data to file using an atomic rename operation."""
    target_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(target_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def atomic_csv_dump(rows: List[Dict[str, Any]], fieldnames: List[str], filepath: str) -> None:
    """Safely write tabular records to CSV using an atomic rename operation."""
    target_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(target_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def classify_device_role(technology: Optional[str], model: Optional[str], node_desc: Optional[str] = "") -> str:
    """Classify an infrastructure configuration item into its canonical architectural role.
    
    Categories:
        - Firewall: Security gateways and ASA appliances
        - Router: Edge, branch, and aggregation routers (ISR, ASR, 39xx, 89xx, 8300)
        - Wireless Controller: WLC appliances and virtual wireless controllers
        - Core Switch: Modular chassis, datacenter Nexus, and core switches
        - Distribution Switch: Multi-layer aggregation switches (C9300, 3850, 3650)
        - Access Switch: Edge access layer switches (C9200, 2960, 3560, etc.)
        - Server: Windows Server, Linux, Hyper-V, VMware ESXi hosts
        - Network Appliance: SD-WAN CPEs, Nutanix, Broadcom
    """
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


def classify_hardware_vendor(technology: Optional[str], model: Optional[str]) -> str:
    """Normalize hardware vendor into canonical OEM vendor categories."""
    tech_str = (str(technology) if technology is not None else "").lower()
    model_str = (str(model) if model is not None else "").lower()
    combined = f"{tech_str} {model_str}"

    if "juniper" in combined:
        return "Juniper"
    if "fortinet" in combined or "fortigate" in combined:
        return "Fortinet"
    if "palo" in combined or "pan-os" in combined:
        return "Palo Alto"
    if "arista" in combined:
        return "Arista"
    if "versa" in combined:
        return "Versa Networks"
    if "windows" in combined or "microsoft" in combined:
        return "Windows"
    if "vmware" in combined:
        return "VMware"
    if any(k in combined for k in ["cisco", "catalyst", "nexus", "c9200", "c9300", "c9500", "c9600", "c9400", "ws-c", "asa", "isr", "wlc", "c892", "c8300"]):
        return "Cisco"
    return "Other"


def parse_clean_os(machine_type: Optional[str], node_desc: Optional[str], vendor: Optional[str]) -> str:
    """Extract clean, human-readable Operating System / Firmware version."""
    desc = node_desc or ""
    mt = machine_type or ""

    if "Windows Version" in desc:
        if "17763" in desc: return "Windows Server 2019"
        if "20348" in desc: return "Windows Server 2022"
        if "14393" in desc: return "Windows Server 2016"
        return "Windows Server"
    if "Windows 2019" in mt: return "Windows Server 2019"
    if "Windows 2022" in mt: return "Windows Server 2022"
    if "Hyper-V" in mt: return "Microsoft Hyper-V Server"
    if "ESX" in mt or "VMware" in mt: return "VMware ESXi"
    if "Cisco IOS Software" in desc:
        if "Version " in desc:
            ver_part = desc.split("Version ")[1].split(",")[0].split(" ")[0].strip()
            return f"Cisco IOS {ver_part}"
        return "Cisco IOS-XE"
    if "Adaptive Security Appliance" in desc or "ASA Version" in desc:
        return "Cisco ASA OS"
    if "Palo Alto" in desc or "PA-" in mt: return "PAN-OS"
    if "Versa" in desc or "Versa" in mt: return "Versa Operating System (VOS)"
    if "Fortinet" in (vendor or ""): return "FortiOS"
    return mt if mt and mt != "Unknown" else "Proprietary Firmware"


def classify_compliance_state(action_category: Optional[str]) -> str:
    """Map operational action category into standardized 4-state compliance classification."""
    if not action_category:
        return "Under Review"
    cat = str(action_category).lower()
    if "no immediate" in cat or "compliant" in cat:
        return "Compliant"
    if "missing serial" in cat:
        return "Missing Serial"
    if "schedule" in cat or "review" in cat:
        return "Under Review"
    return "Action Required"


def map_node_status_string(status_code: Optional[int]) -> str:
    """Map SolarWinds numeric status code to human-readable status string."""
    status_map = {
        1: "Up",
        2: "Down",
        3: "Warning",
        9: "Unmanaged",
        14: "Critical",
        0: "Unknown"
    }
    return status_map.get(status_code, "Unknown")


class CMDBService:
    """Enterprise Live CMDB Ingestion & Telemetry Service."""

    def __init__(self, client: Optional[SolarWindsClient] = None) -> None:
        self.client = client or SolarWindsClient()

    def fetch_live_nodes(self) -> Tuple[List[Dict[str, Any]], str, str]:
        """Fetch live nodes from SolarWinds with resilient fallback to cached snapshot if unavailable.

        Returns:
            Tuple of (raw_nodes_list, mode, connection_status)
        """
        try:
            logger.info("Querying live SolarWinds SWIS API for CMDB CIs...")
            raw_nodes = self.client.fetch_nodes()
            if raw_nodes and len(raw_nodes) > 0:
                logger.info("Live SWIS query returned %d nodes. Caching snapshot...", len(raw_nodes))
                atomic_json_dump(
                    {
                        "extracted_at": datetime.now(timezone.utc).isoformat(),
                        "total_nodes": len(raw_nodes),
                        "nodes": raw_nodes
                    },
                    DEFAULT_RAW_NODES_PATH
                )
                return raw_nodes, "live", "Connected (Live SWIS API v3)"
        except Exception as exc:
            logger.warning("SolarWinds live query failed (%s). Falling back to cached snapshot...", exc)

        # Fallback to verified cached snapshot
        if os.path.exists(DEFAULT_RAW_NODES_PATH):
            try:
                with open(DEFAULT_RAW_NODES_PATH, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    nodes = cached.get("nodes", [])
                    logger.info("Loaded %d nodes from cached snapshot (%s).", len(nodes), cached.get("extracted_at"))
                    return nodes, "cached", "Unavailable (Serving Verified Cached Snapshot)"
            except Exception as e:
                logger.error("Failed to read cached nodes snapshot: %s", e)

        return [], "unavailable", "Unavailable (No data available)"

    def normalize_nodes_to_cis(self, raw_nodes: List[Dict[str, Any]], mode: str = "live") -> List[Dict[str, Any]]:
        """Normalize raw SolarWinds nodes into canonical Configuration Items."""
        cis: List[Dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for n in raw_nodes:
            node_id = str(n.get("NodeID", ""))
            caption = str(n.get("Caption", f"Node-{node_id}")).strip()
            ip = str(n.get("IPAddress", "")).strip()
            vendor = str(n.get("Vendor", "Unknown")).strip()
            machine_type = str(n.get("MachineType", "Unknown")).strip()
            desc = str(n.get("NodeDescription", "")).strip()
            city = str(n.get("City", "")).strip() or "Default Location"
            contact = str(n.get("Contact", "")).strip()
            status_code = n.get("Status", 0)
            cpu = n.get("CPULoad")
            ram = n.get("PercentMemoryUsed")
            latency = n.get("AvgResponseTime") or n.get("ResponseTime")
            uptime_s = n.get("SystemUpTime")
            uptime_h = round(float(uptime_s) / 3600.0, 1) if uptime_s is not None and float(uptime_s) > 0 else None

            ci_type = classify_device_role(vendor, machine_type, desc)
            health_tier = classify_node_health(n)
            status_str = map_node_status_string(status_code)
            os_clean = parse_clean_os(machine_type, desc, vendor)

            relationships = [
                {
                    "source_ci_id": f"SW-NODE-{node_id}",
                    "target_ci_id": f"SITE-{city.upper().replace(' ', '-')}",
                    "relationship_type": "located_at",
                    "target_name": city,
                    "target_type": "Facility / Location",
                    "description": f"Hardware physically provisioned at site {city}"
                }
            ]

            ci_record = {
                "ci_id": f"SW-NODE-{node_id}",
                "device_id": f"SW-NODE-{node_id}",
                "device_token": caption,
                "name": caption,
                "caption": caption,
                "ci_type": ci_type,
                "role": ci_type,
                "device_role": ci_type,
                "hostname": caption,
                "ip_address": ip,
                "vendor": normalize_solarwinds_vendor(vendor),
                "hardware_vendor": normalize_solarwinds_vendor(vendor),
                "technology": machine_type if machine_type != "Unknown" else ci_type,
                "model": machine_type if machine_type != "Unknown" else ci_type,
                "operating_system": os_clean,
                "status": status_str,
                "scan_status": "Monitored" if status_str in ["Up", "Warning", "Critical"] else "Unmanaged",
                "compliance_state": "Compliant" if health_tier == "High" else "Action Required" if health_tier == "Low" else "Under Review",
                "health_tier": health_tier,
                "priority": "High" if health_tier == "Low" else "Normal" if health_tier == "Medium" else "Low",
                "location": city,
                "source": "SolarWinds",
                "mode": mode,
                "last_updated": now_iso,
                "cpu_load": float(cpu) if cpu is not None and float(cpu) >= 0 else None,
                "memory_used": float(ram) if ram is not None and float(ram) >= 0 else None,
                "latency_ms": float(latency) if latency is not None and float(latency) >= 0 else None,
                "uptime_hours": uptime_h,
                "contact": contact,
                "description": desc,
                "relationships": relationships
            }
            cis.append(ci_record)

        return cis

    def generate_cmdb_summary(
        self,
        cis: List[Dict[str, Any]],
        mode: str = "live",
        connection_status: str = "Connected"
    ) -> Dict[str, Any]:
        """Compute mathematical aggregations and build standard CMDB summary payload."""
        total_cis = len(cis)
        active_monitored = sum(1 for c in cis if c["status"] in ["Up", "Warning", "Critical", "Down"])
        unmanaged = sum(1 for c in cis if c["status"] in ["Unmanaged", "Unknown"])

        # 1. CI Type Distribution
        type_dist: Dict[str, int] = {}
        for c in cis:
            type_dist[c["ci_type"]] = type_dist.get(c["ci_type"], 0) + 1

        # 2. Hardware Vendor Distribution
        vendor_dist: Dict[str, int] = {}
        for c in cis:
            vendor_dist[c["vendor"]] = vendor_dist.get(c["vendor"], 0) + 1

        # 3. Status Distribution
        status_dist: Dict[str, int] = {}
        for c in cis:
            status_dist[c["status"]] = status_dist.get(c["status"], 0) + 1

        # 4. Health Tier Distribution
        health_dist: Dict[str, int] = {}
        for c in cis:
            health_dist[c["health_tier"]] = health_dist.get(c["health_tier"], 0) + 1

        # 5. Location Distribution (Top 10)
        loc_counts: Dict[str, int] = {}
        for c in cis:
            loc_counts[c["location"]] = loc_counts.get(c["location"], 0) + 1
        top_locations = [
            {"location": loc, "count": cnt, "share_pct": round((cnt / total_cis) * 100.0, 2) if total_cis > 0 else 0}
            for loc, cnt in sorted(loc_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        # 6. Top Resource Pressure CIs
        pressure_cis = sorted(
            cis,
            key=lambda x: (1 if x["health_tier"] == 'Low' else 2 if x["health_tier"] == 'Medium' else 3, -(x.get("cpu_load") or 0), -(x.get("memory_used") or 0))
        )[:10]

        summary_payload = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "SolarWinds",
                "source_api": "SolarWinds Information Service (SWIS) v3",
                "mode": mode,
                "connection_status": connection_status,
                "total_configuration_items": total_cis,
                "active_monitored_cis": active_monitored,
                "unmanaged_cis": unmanaged,
            },
            "metrics": {
                "total_network_cis": total_cis,
                "total_servers": type_dist.get("Server", 0),
                "total_network_devices": sum(type_dist.get(k, 0) for k in ["Access Switch", "Distribution Switch", "Core Switch", "Router", "Firewall", "Wireless Controller", "Network Appliance"]),
                "high_health_cis": health_dist.get("High", 0),
                "medium_health_cis": health_dist.get("Medium", 0),
                "low_health_cis": health_dist.get("Low", 0),
                "up_cis": status_dist.get("Up", 0),
                "critical_cis": status_dist.get("Critical", 0),
                "warning_cis": status_dist.get("Warning", 0),
                "down_cis": status_dist.get("Down", 0),
                "control_compliance_rate": round((health_dist.get("High", 0) / total_cis) * 100.0, 2) if total_cis > 0 else 0.0,
            },
            "ci_type_distribution": type_dist,
            "role_breakdown": type_dist,  # UI backward compatibility
            "detailed_role_breakdown": type_dist,
            "compliance_breakdown": {
                "Compliant": health_dist.get("High", 0),
                "Action Required": health_dist.get("Low", 0),
                "Missing Serial": status_dist.get("Unmanaged", 0),
                "Under Review": health_dist.get("Medium", 0)
            },
            "hardware_breakdown": vendor_dist,
            "status_breakdown": status_dist,
            "health_tier_breakdown": health_dist,
            "top_locations": top_locations,
            "ip_distribution": {
                "total_ips": total_cis,
                "top_sites": [{"site": l["location"], "device_count": l["count"]} for l in top_locations[:5]]
            },
            "top_risk_assets": pressure_cis,
            "sample_devices": cis,
        }
        return summary_payload

    def sync_and_save(
        self,
        json_output_path: str = DEFAULT_SUMMARY_PATH,
        csv_output_path: str = DEFAULT_CSV_PATH
    ) -> Dict[str, Any]:
        """Execute end-to-end sync, CI normalization, and atomic disk writes."""
        raw_nodes, mode, status = self.fetch_live_nodes()
        cis = self.normalize_nodes_to_cis(raw_nodes, mode=mode)
        summary = self.generate_cmdb_summary(cis, mode=mode, connection_status=status)

        # Atomic JSON dump
        atomic_json_dump(summary, json_output_path)
        logger.info("Saved CMDB summary payload (%d CIs) to %s", len(cis), json_output_path)

        # Atomic CSV export
        fieldnames = [
            "ci_id", "name", "ci_type", "hostname", "ip_address", "vendor", "model",
            "operating_system", "status", "health_tier", "location", "cpu_load",
            "memory_used", "latency_ms", "uptime_hours", "source", "mode", "last_updated"
        ]
        csv_rows = [
            {
                "ci_id": c["ci_id"],
                "name": c["name"],
                "ci_type": c["ci_type"],
                "hostname": c["hostname"],
                "ip_address": c["ip_address"],
                "vendor": c["vendor"],
                "model": c["model"],
                "operating_system": c["operating_system"],
                "status": c["status"],
                "health_tier": c["health_tier"],
                "location": c["location"],
                "cpu_load": c["cpu_load"] if c["cpu_load"] is not None else "",
                "memory_used": c["memory_used"] if c["memory_used"] is not None else "",
                "latency_ms": c["latency_ms"] if c["latency_ms"] is not None else "",
                "uptime_hours": c["uptime_hours"] if c["uptime_hours"] is not None else "",
                "source": c["source"],
                "mode": c["mode"],
                "last_updated": c["last_updated"]
            }
            for c in cis
        ]
        atomic_csv_dump(csv_rows, fieldnames, csv_output_path)
        logger.info("Saved complete CMDB CSV export (%d rows) to %s", len(csv_rows), csv_output_path)

        return summary


# Backward compatibility wrapper
class CMDBDataExtractor:
    """Wrapper providing backward compatibility for existing callers."""

    def __init__(self, db_path: Optional[str] = None):
        self.service = CMDBService()

    def extract_all(self) -> Dict[str, Any]:
        raw_nodes, mode, status = self.service.fetch_live_nodes()
        cis = self.service.normalize_nodes_to_cis(raw_nodes, mode=mode)
        summary = self.service.generate_cmdb_summary(cis, mode=mode, connection_status=status)
        return {
            "summary_payload": summary,
            "devices_list": cis
        }


def generate_cmdb_artifacts(
    db_path: Optional[str] = None,
    json_output_path: str = DEFAULT_SUMMARY_PATH,
    csv_output_path: str = DEFAULT_CSV_PATH
) -> Tuple[str, str]:
    """Execute live CMDB telemetry generation and artifact write."""
    service = CMDBService()
    service.sync_and_save(json_output_path=json_output_path, csv_output_path=csv_output_path)
    return json_output_path, csv_output_path

