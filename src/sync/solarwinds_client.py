"""SolarWinds Orion SWIS API Client & Telemetry Extraction Engine.

This module provides enterprise-grade read-only access to SolarWinds Orion
Information Service (SWIS) v3 REST API, extracting node metrics, computing health
classifications, vendor distributions, and fleet telemetry aggregations matching
MRD FR-003 & FR-004 specifications.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests
import urllib3

# Suppress insecure HTTPS request warnings when connecting to internal servers with self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class SolarWindsApiError(Exception):
    """Exception raised for SWIS API query or response errors."""
    pass


class SolarWindsAuthError(Exception):
    """Exception raised for SWIS API authentication or permission errors."""
    pass


def normalize_solarwinds_vendor(vendor_str: Optional[str]) -> str:
    """Normalize raw vendor string into standard 5 categories: Windows, Cisco, Linux, SolarWinds, Other.

    Args:
        vendor_str: Raw vendor name from Orion.Nodes.

    Returns:
        Standard vendor category name.
    """
    if not vendor_str or not isinstance(vendor_str, str):
        return "Other"

    v_lower = vendor_str.strip().lower()
    if "windows" in v_lower or "microsoft" in v_lower:
        return "Windows"
    if "cisco" in v_lower:
        return "Cisco"
    if "linux" in v_lower or "ubuntu" in v_lower or "redhat" in v_lower or "centos" in v_lower or "debian" in v_lower or "net-snmp" in v_lower:
        return "Linux"
    if "solarwinds" in v_lower or "orion" in v_lower:
        return "SolarWinds"
    return "Other"


def classify_node_health(node: Dict[str, Any]) -> str:
    """Compute server health classification based on Status, CPU, and RAM thresholds.

    Rules:
        - Low/Critical: Status in [2 (Down), 14 (Critical), 0 (Unknown/Unmanaged)] OR CPULoad > 90 OR PercentMemoryUsed > 90
        - Medium: Status in [1, 3] AND (75 <= CPULoad <= 90 OR 80 <= PercentMemoryUsed <= 90 OR Status == 3 (Warning))
        - High: Status == 1 (Up) AND (CPULoad < 75 or CPULoad is None) AND (PercentMemoryUsed < 80 or PercentMemoryUsed is None)

    Args:
        node: Node dictionary containing Status, CPULoad, PercentMemoryUsed.

    Returns:
        'High', 'Medium', or 'Low' (Critical/Degraded).
    """
    status = node.get("Status")
    cpu = node.get("CPULoad")
    ram = node.get("PercentMemoryUsed")

    # Normalize negative or unmeasured values (e.g. -2 for ICMP-only devices)
    valid_cpu = cpu if (isinstance(cpu, (int, float)) and cpu >= 0) else None
    valid_ram = ram if (isinstance(ram, (int, float)) and ram >= 0) else None

    # Check Critical / Low Health conditions
    is_status_crit = status in [2, 14, 0] or status is None
    is_cpu_crit = valid_cpu is not None and valid_cpu > 90
    is_ram_crit = valid_ram is not None and valid_ram > 90

    if is_status_crit or is_cpu_crit or is_ram_crit:
        return "Low"

    # Check Warning / Medium Health conditions
    is_status_warn = (status == 3)
    is_cpu_warn = valid_cpu is not None and (75 <= valid_cpu <= 90)
    is_ram_warn = valid_ram is not None and (80 <= valid_ram <= 90)

    if is_status_warn or (status in [1, 3] and (is_cpu_warn or is_ram_warn)):
        return "Medium"

    # Default to High if Status == 1 (Up) with healthy resource metrics
    if status == 1:
        return "High"

    return "Medium"


class SolarWindsClient:
    """Production SWIS API client for Orion infrastructure telemetry extraction."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """Initialize the SolarWinds SWIS client with host and credentials.

        Args:
            host: SolarWinds hostname or IP (defaults to SOLARWINDS_HOST env).
            port: SWIS REST port (defaults to SOLARWINDS_PORT env or 17774).
            username: SWIS username (defaults to SOLARWINDS_USERNAME env).
            password: SWIS password (defaults to SOLARWINDS_PASSWORD env).
            timeout: HTTP request timeout in seconds.
        """
        self.host = host or os.getenv("SOLARWINDS_HOST", "localhost")
        self.port = str(port or os.getenv("SOLARWINDS_PORT", "17774"))
        self.username = username or os.getenv("SOLARWINDS_USERNAME")
        self.password = password or os.getenv("SOLARWINDS_PASSWORD")
        self.timeout = timeout

        if not self.username or not self.password:
            raise SolarWindsAuthError(
                "Missing SolarWinds credentials. Please supply username/password or set "
                "SOLARWINDS_USERNAME and SOLARWINDS_PASSWORD environment variables."
            )

        self.base_url = f"https://{self.host}:{self.port}/SolarWinds/InformationService/v3/Json/Query"

    def query(self, swql_query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a read-only SWQL query against the SWIS REST API.

        Args:
            swql_query: Valid SWQL query string.
            params: Optional parameter dictionary for parameterized queries.

        Returns:
            List of result row dictionaries.

        Raises:
            SolarWindsAuthError: If authentication/authorization fails (401/403).
            SolarWindsApiError: If query execution fails or returns non-200.
        """
        query_params = {"query": swql_query}
        if params:
            query_params.update(params)

        logger.info("Executing SWQL query against SWIS API (%s:%s)...", self.host, self.port)

        try:
            # First attempt with standard certificate verification
            try:
                response = requests.get(
                    self.base_url,
                    params=query_params,
                    auth=(self.username, self.password),
                    timeout=self.timeout,
                    verify=True,
                )
            except requests.exceptions.SSLError:
                logger.warning("Internal/self-signed SSL certificate detected; retrying with secure fallback verify=False...")
                response = requests.get(
                    self.base_url,
                    params=query_params,
                    auth=(self.username, self.password),
                    timeout=self.timeout,
                    verify=False,
                )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                logger.info("SWIS query succeeded. %d rows returned.", len(results))
                return results

            if response.status_code in (401, 403):
                raise SolarWindsAuthError(
                    f"Authentication failed ({response.status_code}): {response.text}"
                )

            raise SolarWindsApiError(
                f"SWIS API error HTTP {response.status_code}: {response.text}"
            )

        except requests.exceptions.Timeout as exc:
            raise SolarWindsApiError(f"SWIS API connection timed out ({self.timeout}s): {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise SolarWindsApiError(f"Failed to connect to SWIS API at {self.host}:{self.port}: {exc}") from exc

    def fetch_nodes(self) -> List[Dict[str, Any]]:
        """Query server nodes and required fields from Orion.Nodes.

        Returns:
            List of node telemetry dictionaries.
        """
        swql = """
            SELECT 
                n.NodeID, 
                n.Caption, 
                n.IPAddress, 
                n.Status, 
                n.StatusDescription, 
                n.CPULoad, 
                n.PercentMemoryUsed, 
                n.ResponseTime, 
                n.AvgResponseTime, 
                n.Vendor, 
                n.MachineType, 
                n.LastSync, 
                n.SystemUpTime, 
                n.NodeDescription, 
                n.CustomProperties.City AS City, 
                n.Contact 
            FROM Orion.Nodes n
            ORDER BY n.NodeID ASC
        """
        raw_nodes = self.query(swql)
        return raw_nodes

    def process_telemetry(self, raw_nodes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Process, clean, enrich with health classifications, and compute dashboard summary.

        Args:
            raw_nodes: Raw node records extracted from Orion.Nodes.

        Returns:
            Tuple of (enriched_nodes, dashboard_summary).
        """
        total_nodes = len(raw_nodes)
        enriched_nodes: List[Dict[str, Any]] = []

        high_health_count = 0
        medium_health_count = 0
        low_health_count = 0

        up_count = 0
        down_count = 0
        warning_count = 0
        critical_count = 0
        unmanaged_count = 0

        vendor_breakdown = {
            "Windows": 0,
            "Cisco": 0,
            "Linux": 0,
            "SolarWinds": 0,
            "Other": 0,
        }
        raw_vendor_counts: Dict[str, int] = {}

        valid_cpu_sum = 0.0
        valid_cpu_count = 0

        valid_ram_sum = 0.0
        valid_ram_count = 0

        valid_latency_sum = 0.0
        valid_latency_count = 0

        degraded_candidates: List[Dict[str, Any]] = []

        for node in raw_nodes:
            # Clean and sanitize fields
            node_id = node.get("NodeID")
            caption = node.get("Caption") or "Unknown"
            ip_address = node.get("IPAddress") or "N/A"
            status = node.get("Status")
            status_desc = node.get("StatusDescription") or ""
            cpu_load = node.get("CPULoad")
            ram_used = node.get("PercentMemoryUsed")
            resp_time = node.get("ResponseTime")
            avg_resp_time = node.get("AvgResponseTime")
            raw_vendor = node.get("Vendor") or "Unknown"
            machine_type = node.get("MachineType") or "Unknown"
            last_sync = node.get("LastSync")
            sys_uptime = node.get("SystemUpTime")
            node_desc = node.get("NodeDescription") or ""
            city = node.get("City") or ""
            contact = node.get("Contact") or ""

            # Health classification
            health = classify_node_health(node)
            if health == "High":
                high_health_count += 1
            elif health == "Medium":
                medium_health_count += 1
            else:
                low_health_count += 1

            # Status tracking
            if status == 1:
                up_count += 1
            elif status == 2:
                down_count += 1
            elif status == 3:
                warning_count += 1
            elif status == 14:
                critical_count += 1
            else:
                unmanaged_count += 1

            # Vendor aggregation
            norm_vendor = normalize_solarwinds_vendor(raw_vendor)
            vendor_breakdown[norm_vendor] = vendor_breakdown.get(norm_vendor, 0) + 1
            raw_vendor_counts[raw_vendor] = raw_vendor_counts.get(raw_vendor, 0) + 1

            # CPU metrics aggregation
            if isinstance(cpu_load, (int, float)) and cpu_load >= 0:
                valid_cpu_sum += cpu_load
                valid_cpu_count += 1

            # RAM metrics aggregation
            if isinstance(ram_used, (int, float)) and ram_used >= 0:
                valid_ram_sum += ram_used
                valid_ram_count += 1

            # Latency metrics aggregation
            latency_val = avg_resp_time if (isinstance(avg_resp_time, (int, float)) and avg_resp_time >= 0) else (
                resp_time if (isinstance(resp_time, (int, float)) and resp_time >= 0) else None
            )
            if latency_val is not None:
                valid_latency_sum += latency_val
                valid_latency_count += 1

            enriched_record = {
                "NodeID": node_id,
                "Caption": caption,
                "IPAddress": ip_address,
                "Status": status,
                "StatusDescription": status_desc,
                "CPULoad": cpu_load,
                "PercentMemoryUsed": ram_used,
                "ResponseTime": resp_time,
                "AvgResponseTime": avg_resp_time,
                "Vendor": raw_vendor,
                "NormalizedVendor": norm_vendor,
                "MachineType": machine_type,
                "LastSync": last_sync,
                "SystemUpTime": sys_uptime,
                "NodeDescription": node_desc,
                "City": city,
                "Contact": contact,
                "HealthClassification": health,
            }
            enriched_nodes.append(enriched_record)

            # Check if degraded / resource pressure candidate
            is_degraded = (
                health in ("Medium", "Low") or
                status in (2, 3, 14, 0) or
                (isinstance(cpu_load, (int, float)) and cpu_load >= 75) or
                (isinstance(ram_used, (int, float)) and ram_used >= 80)
            )
            if is_degraded:
                degraded_candidates.append(enriched_record)

        # Sort degraded candidates by severity (Low health first, then CPU desc, then RAM desc)
        def degraded_sort_key(item: Dict[str, Any]) -> Tuple[int, float, float]:
            h_rank = 0 if item["HealthClassification"] == "Low" else (1 if item["HealthClassification"] == "Medium" else 2)
            c_val = float(item["CPULoad"]) if isinstance(item["CPULoad"], (int, float)) and item["CPULoad"] >= 0 else 0.0
            r_val = float(item["PercentMemoryUsed"]) if isinstance(item["PercentMemoryUsed"], (int, float)) and item["PercentMemoryUsed"] >= 0 else 0.0
            return (h_rank, -c_val, -r_val)

        degraded_candidates.sort(key=degraded_sort_key)
        top_degraded = degraded_candidates[:25]

        # Calculate averages
        avg_cpu = round(valid_cpu_sum / valid_cpu_count, 1) if valid_cpu_count > 0 else 0.0
        avg_ram = round(valid_ram_sum / valid_ram_count, 1) if valid_ram_count > 0 else 0.0
        avg_latency = round(valid_latency_sum / valid_latency_count, 1) if valid_latency_count > 0 else 0.0

        high_pct = round((high_health_count / total_nodes) * 100, 2) if total_nodes > 0 else 0.0
        med_pct = round((medium_health_count / total_nodes) * 100, 2) if total_nodes > 0 else 0.0
        low_pct = round((low_health_count / total_nodes) * 100, 2) if total_nodes > 0 else 0.0

        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "total_server_nodes": total_nodes,
                "high_health_nodes": high_health_count,
                "medium_health_nodes": medium_health_count,
                "low_critical_nodes": low_health_count,
                "high_health_pct": high_pct,
                "medium_health_pct": med_pct,
                "low_critical_pct": low_pct,
                "status_counts": {
                    "up": up_count,
                    "down": down_count,
                    "warning": warning_count,
                    "critical": critical_count,
                    "unmanaged_unknown": unmanaged_count,
                },
                "avg_fleet_cpu_load_pct": avg_cpu,
                "avg_fleet_ram_used_pct": avg_ram,
                "avg_fleet_latency_ms": avg_latency,
            },
            "vendor_breakdown": vendor_breakdown,
            "raw_vendor_distribution": raw_vendor_counts,
            "health_breakdown": {
                "High": high_health_count,
                "Medium": medium_health_count,
                "Low": low_health_count,
            },
            "top_degraded_servers": top_degraded,
            "sample_nodes": enriched_nodes[:50],
        }

        return enriched_nodes, summary

    def fetch_and_save(
        self,
        nodes_output_path: Optional[str] = None,
        summary_output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute full extraction, enrichment, and write output files.

        Args:
            nodes_output_path: Destination path for raw enriched nodes JSON.
            summary_output_path: Destination path for summary payload JSON.

        Returns:
            The summary payload dictionary.
        """
        raw_nodes = self.fetch_nodes()
        enriched_nodes, summary = self.process_telemetry(raw_nodes)

        # Save enriched nodes dataset
        if nodes_output_path:
            os.makedirs(os.path.dirname(os.path.abspath(nodes_output_path)), exist_ok=True)
            with open(nodes_output_path, "w", encoding="utf-8") as f:
                json.dump({
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "total_nodes": len(enriched_nodes),
                    "nodes": enriched_nodes,
                }, f, indent=2)
            logger.info("Saved %d SolarWinds node records to: %s", len(enriched_nodes), nodes_output_path)

        # Save summary payload
        if summary_output_path:
            os.makedirs(os.path.dirname(os.path.abspath(summary_output_path)), exist_ok=True)
            with open(summary_output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            logger.info("Saved SolarWinds summary payload to: %s", summary_output_path)

        return summary
