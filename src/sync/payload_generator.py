"""Intune Telemetry Payload Aggregator and Normalization Engine.

This module processes raw Microsoft Intune device extraction datasets and computes
verified aggregation metrics, OS breakdowns, compliance summaries, case-insensitive
manufacturer distributions, and sample device records for high-performance dashboard consumption.
"""

import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def atomic_json_dump(data: Any, filepath: str, indent: Optional[int] = None) -> None:
    """Safely write JSON data to file using an atomic replace to prevent race conditions.

    Args:
        data: Serializable Python object.
        filepath: Target destination filepath.
        indent: Optional indentation level (default: None).
    """
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


def normalize_manufacturer(mfg: Optional[str], include_microsoft: bool = False) -> str:
    """Normalize raw hardware manufacturer string to a standardized vendor name.

    Performs case-insensitive pattern matching to accurately categorize OEM strings
    such as 'LENOVO', 'Dell Inc.', 'Hewlett-Packard', 'Apple', and others.

    Args:
        mfg: Raw manufacturer string from Intune device record.
        include_microsoft: Whether to normalize Microsoft as a distinct category.
            Defaults to False to match the standard 5-category dashboard schema.

    Returns:
        Standardized brand name ('Dell', 'HP', 'Lenovo', 'Apple', 'Microsoft', or 'Other').

    Examples:
        >>> normalize_manufacturer("LENOVO")
        'Lenovo'
        >>> normalize_manufacturer("Dell Inc.")
        'Dell'
        >>> normalize_manufacturer("Hewlett-Packard")
        'HP'
        >>> normalize_manufacturer("Apple")
        'Apple'
        >>> normalize_manufacturer("ASUSTeK COMPUTER INC.")
        'Other'
    """
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
    if include_microsoft and "microsoft" in mfg_lower:
        return "Microsoft"
    return "Other"


def calculate_metrics(devices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute top-level summary metrics across a collection of Intune managed devices.

    Args:
        devices: List of raw Intune device dictionaries.

    Returns:
        Dictionary containing verified mathematical metrics:
            - total_managed_devices (int)
            - compliant_devices (int)
            - noncompliant_devices (int)
            - other_compliance (int)
            - compliance_rate_pct (float rounded to 2 decimal places)
            - avg_storage_used_pct (float rounded to 1 decimal place)
    """
    total_devices = len(devices)
    compliant_count = 0
    noncompliant_count = 0
    other_compliance = 0

    storage_total_gb = 0.0
    storage_free_gb = 0.0

    for dev in devices:
        comp = (dev.get("complianceState") or "").strip().lower()
        if comp == "compliant":
            compliant_count += 1
        elif comp == "noncompliant":
            noncompliant_count += 1
        else:
            other_compliance += 1

        tot_bytes = dev.get("totalStorageSpaceInBytes") or 0
        free_bytes = dev.get("freeStorageSpaceInBytes") or 0
        if isinstance(tot_bytes, (int, float)) and not isinstance(tot_bytes, bool) and tot_bytes > 0:
            tot_num = float(tot_bytes)
            free_num = float(free_bytes) if (isinstance(free_bytes, (int, float)) and not isinstance(free_bytes, bool) and free_bytes >= 0) else 0.0
            free_clamped = max(0.0, min(free_num, tot_num))
            tot_gb = tot_num / (1024 ** 3)
            free_gb = free_clamped / (1024 ** 3)
            storage_total_gb += tot_gb
            storage_free_gb += free_gb

    compliance_rate = round((compliant_count / total_devices) * 100, 2) if total_devices > 0 else 0.0
    if storage_total_gb > 0:
        used_storage_gb = storage_total_gb - storage_free_gb
        avg_storage_used = round((used_storage_gb / storage_total_gb) * 100, 1)
    else:
        avg_storage_used = 0.0

    return {
        "total_managed_devices": total_devices,
        "compliant_devices": compliant_count,
        "noncompliant_devices": noncompliant_count,
        "other_compliance": other_compliance,
        "compliance_rate_pct": compliance_rate,
        "avg_storage_used_pct": avg_storage_used,
    }


def generate_breakdowns(
    devices: List[Dict[str, Any]],
    raw_summary: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
    """Generate OS, compliance, and normalized manufacturer distribution maps.

    Args:
        devices: List of raw Intune device dictionaries.
        raw_summary: Optional raw summary metadata dictionary if available.

    Returns:
        Tuple of (os_breakdown, compliance_breakdown, manufacturer_breakdown).
    """
    os_breakdown: Dict[str, int] = {}
    compliance_breakdown: Dict[str, int] = {}
    manufacturer_breakdown: Dict[str, int] = {
        "Dell": 0,
        "HP": 0,
        "Lenovo": 0,
        "Apple": 0,
        "Other": 0,
    }

    # If raw summary has breakdowns, use them or compute from devices
    if raw_summary and "os_breakdown" in raw_summary and raw_summary["os_breakdown"]:
        os_breakdown = dict(raw_summary["os_breakdown"])
    else:
        for dev in devices:
            os_name = dev.get("operatingSystem") or ""
            os_breakdown[os_name] = os_breakdown.get(os_name, 0) + 1

    if raw_summary and "compliance_breakdown" in raw_summary and raw_summary["compliance_breakdown"]:
        compliance_breakdown = dict(raw_summary["compliance_breakdown"])
    else:
        for dev in devices:
            comp_state = dev.get("complianceState") or "unknown"
            compliance_breakdown[comp_state] = compliance_breakdown.get(comp_state, 0) + 1

    # Manufacturer breakdown is always normalized case-insensitively
    for dev in devices:
        raw_mfg = dev.get("manufacturer")
        normalized_mfg = normalize_manufacturer(raw_mfg)
        manufacturer_breakdown[normalized_mfg] = manufacturer_breakdown.get(normalized_mfg, 0) + 1

    return os_breakdown, compliance_breakdown, manufacturer_breakdown


def format_sample_devices(devices: List[Dict[str, Any]], limit: int = 100) -> List[Dict[str, Any]]:
    """Format sample device records for instant dashboard table rendering.

    Args:
        devices: List of raw Intune device dictionaries.
        limit: Maximum number of sample records to extract (default: 100).

    Returns:
        List of formatted sample device dictionaries with storage metrics.
    """
    sample_records: List[Dict[str, Any]] = []

    for dev in devices[:limit]:
        raw_tot = dev.get("totalStorageSpaceInBytes")
        raw_free = dev.get("freeStorageSpaceInBytes")
        
        tot_bytes = float(raw_tot) if (isinstance(raw_tot, (int, float)) and not isinstance(raw_tot, bool) and raw_tot > 0) else 0.0
        free_bytes = float(raw_free) if (isinstance(raw_free, (int, float)) and not isinstance(raw_free, bool) and raw_free >= 0) else 0.0
        free_clamped = min(free_bytes, tot_bytes) if tot_bytes > 0 else 0.0

        tot_gb = round(tot_bytes / (1024 ** 3), 1) if tot_bytes > 0 else 0.0
        free_gb = round(free_clamped / (1024 ** 3), 1) if tot_bytes > 0 else 0.0
        used_pct = round(((tot_bytes - free_clamped) / tot_bytes) * 100, 1) if tot_bytes > 0 else 0.0

        sample_records.append({
            "id": dev.get("id") or "",
            "deviceName": dev.get("deviceName") or "N/A",
            "operatingSystem": dev.get("operatingSystem") or "Unknown",
            "osVersion": dev.get("osVersion") or "N/A",
            "complianceState": dev.get("complianceState") or "unknown",
            "userPrincipalName": dev.get("userPrincipalName") or "N/A",
            "model": dev.get("model") or "N/A",
            "manufacturer": dev.get("manufacturer") or "N/A",
            "serialNumber": dev.get("serialNumber") or "N/A",
            "lastSync": dev.get("lastSyncDateTime") or "N/A",
            "totalStorageGB": tot_gb,
            "freeStorageGB": free_gb,
            "usedStoragePct": used_pct,
        })

    return sample_records


class PayloadGenerator:
    """Production aggregator service for building verified Intune dashboard payloads."""

    def __init__(self, default_sample_size: int = 100) -> None:
        """Initialize the PayloadGenerator.

        Args:
            default_sample_size: Default number of sample device records to include.
        """
        self.default_sample_size = default_sample_size

    def generate(
        self,
        input_file: Optional[str] = None,
        output_file: Optional[str] = None,
        sample_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Load raw Intune extraction data, compute aggregations, and generate summary payload.

        Args:
            input_file: Path to `intune_ops_analytics.json` raw dataset.
            output_file: Target path to write `intune_summary.json`.
            sample_size: Number of sample records to include.

        Returns:
            The complete generated dashboard payload dictionary.

        Raises:
            FileNotFoundError: If input_file does not exist.
            ValueError: If input payload is invalid or empty.
        """
        resolved_input = input_file or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "intune_ops_analytics.json",
        )
        resolved_output = output_file or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "intune_summary.json",
        )
        limit = sample_size or self.default_sample_size

        if not os.path.exists(resolved_input):
            raise FileNotFoundError(f"Raw Intune dataset not found at: {resolved_input}")

        logger.info("Reading raw Intune dataset from: %s", resolved_input)
        with open(resolved_input, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_summary = data.get("summary", {})
        devices = data.get("devices", [])

        if not devices:
            raise ValueError("Raw Intune dataset contains 0 devices.")

        metrics = calculate_metrics(devices)
        os_breakdown, compliance_breakdown, mfg_breakdown = generate_breakdowns(devices, raw_summary)
        sample_devices = format_sample_devices(devices, limit=limit)

        dashboard_payload = {
            "metrics": metrics,
            "os_breakdown": os_breakdown,
            "compliance_breakdown": compliance_breakdown,
            "manufacturer_breakdown": mfg_breakdown,
            "sample_devices": sample_devices,
        }

        # Validate mathematical invariants before saving
        self.validate_payload(dashboard_payload)

        if resolved_output:
            atomic_json_dump(dashboard_payload, resolved_output, indent=2)
            logger.info("Saved verified dashboard payload to: %s", resolved_output)

        return dashboard_payload

    def generate_and_save(
        self,
        devices: List[Dict[str, Any]],
        output_file: str,
        sample_size: int = 500,
    ) -> Dict[str, Any]:
        """Generate summary payload directly from device list and write atomically.

        Args:
            devices: List of raw Intune device records.
            output_file: Target output JSON file.
            sample_size: Number of sample records to preserve.

        Returns:
            The complete dashboard payload dictionary.
        """
        metrics = calculate_metrics(devices)
        os_breakdown, compliance_breakdown, mfg_breakdown = generate_breakdowns(devices)
        sample_devices = format_sample_devices(devices, limit=sample_size)

        dashboard_payload = {
            "metrics": metrics,
            "os_breakdown": os_breakdown,
            "compliance_breakdown": compliance_breakdown,
            "manufacturer_breakdown": mfg_breakdown,
            "sample_devices": sample_devices,
        }

        self.validate_payload(dashboard_payload)
        atomic_json_dump(dashboard_payload, output_file, indent=2)
        logger.info("Directly serialized %d devices to summary payload: %s", len(devices), output_file)
        return dashboard_payload

    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate mathematical invariants across the generated summary payload.

        Args:
            payload: Generated dashboard payload dictionary.

        Returns:
            True if all assertions pass.

        Raises:
            AssertionError: If any mathematical invariant fails.
        """
        metrics = payload.get("metrics", {})
        total = metrics.get("total_managed_devices", 0)
        compliant = metrics.get("compliant_devices", 0)
        noncompliant = metrics.get("noncompliant_devices", 0)
        other = metrics.get("other_compliance", 0)
        rate = metrics.get("compliance_rate_pct", 0.0)
        storage_pct = metrics.get("avg_storage_used_pct", 0.0)

        # Invariant 1: Compliance sum matches total
        assert compliant + noncompliant + other == total, (
            f"Compliance sum mismatch: {compliant} + {noncompliant} + {other} != {total}"
        )

        # Invariant 2: Compliance rate calculation
        expected_rate = round((compliant / total) * 100, 2) if total > 0 else 0.0
        assert abs(rate - expected_rate) < 0.01, f"Compliance rate mismatch: {rate} != {expected_rate}"

        # Invariant 3: Manufacturer breakdown sum matches total
        mfg = payload.get("manufacturer_breakdown", {})
        mfg_sum = sum(mfg.values())
        assert mfg_sum == total, f"Manufacturer breakdown sum mismatch: {mfg_sum} != {total}"

        # Invariant 4: OS breakdown sum matches total
        os_breakdown = payload.get("os_breakdown", {})
        os_sum = sum(os_breakdown.values())
        assert os_sum == total, f"OS breakdown sum mismatch: {os_sum} != {total}"

        # Invariant 5: Storage percentage is within valid bounds
        assert 0.0 <= storage_pct <= 100.0, f"Storage percentage out of bounds: {storage_pct}"

        # Invariant 6: Sample devices length is within expected bounds
        samples = payload.get("sample_devices", [])
        assert len(samples) <= max(500, total), f"Sample devices count exceeds limit: {len(samples)}"

        logger.info("All mathematical invariants validated successfully.")
        return True


def create_dashboard_summary(
    input_file: Optional[str] = None,
    output_file: Optional[str] = None,
    sample_size: int = 100,
) -> Dict[str, Any]:
    """Convenience function to generate dashboard summary payload.

    Args:
        input_file: Optional raw dataset input path.
        output_file: Optional output summary path.
        sample_size: Number of sample records to include.

    Returns:
        Generated dashboard payload dictionary.
    """
    generator = PayloadGenerator(default_sample_size=sample_size)
    return generator.generate(input_file=input_file, output_file=output_file, sample_size=sample_size)
