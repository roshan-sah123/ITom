"""Automated ITOM Executive Operational Telemetry Digest.

Compiles high-impact health metrics, fleet compliance rates, critical bottleneck servers,
and stale asset statistics into structured JSON and executive markdown formats.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_executive_digest(
    intune_summary_path: Optional[str] = None,
    solarwinds_summary_path: Optional[str] = None,
    output_digest_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate structured executive digest from current precomputed telemetry summaries.

    Args:
        intune_summary_path: Path to intune_summary.json.
        solarwinds_summary_path: Path to solarwinds_summary.json.
        output_digest_path: Target path for executive_digest.json.

    Returns:
        Structured executive digest dictionary.
    """
    i_path = intune_summary_path or os.path.join(PROJECT_ROOT, "data", "intune_summary.json")
    s_path = solarwinds_summary_path or os.path.join(PROJECT_ROOT, "data", "solarwinds_summary.json")
    out_path = output_digest_path or os.path.join(PROJECT_ROOT, "data", "executive_digest.json")

    intune_data = {}
    if os.path.exists(i_path):
        with open(i_path, "r", encoding="utf-8") as f:
            intune_data = json.load(f)

    solarwinds_data = {}
    if os.path.exists(s_path):
        with open(s_path, "r", encoding="utf-8") as f:
            solarwinds_data = json.load(f)

    i_metrics = intune_data.get("metrics", {})
    s_metrics = solarwinds_data.get("metrics", {})

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": {
            "total_managed_fleet_size": i_metrics.get("total_managed_devices", 0) + s_metrics.get("total_server_nodes", 0),
            "endpoint_compliance_rate_pct": i_metrics.get("compliance_rate_pct", 0.0),
            "infrastructure_high_health_pct": s_metrics.get("high_health_pct", 0.0),
            "critical_nodes_requiring_triage": s_metrics.get("low_critical_nodes", 0),
            "fleet_average_disk_used_pct": i_metrics.get("avg_storage_used_pct", 0.0),
            "fleet_average_cpu_load_pct": s_metrics.get("avg_fleet_cpu_load_pct", 0.0),
            "fleet_average_ram_used_pct": s_metrics.get("avg_fleet_ram_used_pct", 0.0),
        },
        "critical_infrastructure_bottlenecks": solarwinds_data.get("top_degraded_servers", [])[:5],
        "compliance_risk_summary": {
            "non_compliant_devices": i_metrics.get("noncompliant_devices", 0),
            "stale_inactive_devices_count": len([d for d in intune_data.get("sample_devices", []) if "stale" in (d.get("complianceState") or "").lower()]),
        }
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(digest, f, indent=2)

    return digest


if __name__ == "__main__":
    d = generate_executive_digest()
    print(f"Generated Executive Digest: Fleet Size = {d['executive_summary']['total_managed_fleet_size']}, Compliance = {d['executive_summary']['endpoint_compliance_rate_pct']}%")
