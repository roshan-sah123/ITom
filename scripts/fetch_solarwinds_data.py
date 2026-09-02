#!/usr/bin/env python3
"""CLI Script: Ingest Server Telemetry from SolarWinds Orion SWIS API.

This script interacts with the SolarWinds Information Service (SWIS) v3 REST API
to extract live server node telemetry, calculate health classifications, compute
fleet performance analytics matching MRD FR-003 & FR-004, and persist datasets to
`data/solarwinds_nodes.json` and `data/solarwinds_summary.json`.

Usage:
    python scripts/fetch_solarwinds_data.py
    python scripts/fetch_solarwinds_data.py --nodes-output data/solarwinds_nodes.json --summary-output data/solarwinds_summary.json
"""

import argparse
import json
import logging
import os
import sys

# Ensure repository root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.sync.solarwinds_client import (
    SolarWindsApiError,
    SolarWindsAuthError,
    SolarWindsClient,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest server telemetry from SolarWinds SWIS API."
    )
    parser.add_argument(
        "--nodes-output",
        "-n",
        default=os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json"),
        help="Destination path for raw enriched nodes dataset (default: data/solarwinds_nodes.json)",
    )
    parser.add_argument(
        "--summary-output",
        "-s",
        default=os.path.join(PROJECT_ROOT, "data", "solarwinds_summary.json"),
        help="Destination path for aggregated summary payload (default: data/solarwinds_summary.json)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SOLARWINDS_HOST", "localhost"),
        help="SolarWinds hostname or IP (defaults to SOLARWINDS_HOST env)",
    )
    parser.add_argument(
        "--port",
        default=os.getenv("SOLARWINDS_PORT", "17774"),
        help="SolarWinds SWIS API port (defaults to SOLARWINDS_PORT env)",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("SOLARWINDS_USERNAME"),
        help="SolarWinds SWIS username (defaults to SOLARWINDS_USERNAME env)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("SOLARWINDS_PASSWORD"),
        help="SolarWinds SWIS password (defaults to SOLARWINDS_PASSWORD env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test connectivity and query execution without saving files",
    )
    return parser.parse_args()


def display_console_report(summary: dict) -> None:
    """Display a formatted summary report on console."""
    metrics = summary.get("metrics", {})
    vendors = summary.get("vendor_breakdown", {})
    health = summary.get("health_breakdown", {})
    status = metrics.get("status_counts", {})
    top_degraded = summary.get("top_degraded_servers", [])

    print("\n" + "=" * 70)
    print("       SOLARWINDS SWIS TELEMETRY EXTRACTION REPORT")
    print("=" * 70)
    print(f" Total Server Nodes Extracted : {metrics.get('total_server_nodes', 0):,}")
    print("-" * 70)
    print(" Health Classification:")
    print(f"   * High Health (Healthy)     : {health.get('High', 0):,} ({metrics.get('high_health_pct', 0.0)}%)")
    print(f"   * Medium Health (Warning)   : {health.get('Medium', 0):,} ({metrics.get('medium_health_pct', 0.0)}%)")
    print(f"   * Low/Critical Health       : {health.get('Low', 0):,} ({metrics.get('low_critical_pct', 0.0)}%)")
    print("-" * 70)
    print(" Node Status Breakdown:")
    print(f"   * Up (Status 1)             : {status.get('up', 0):,}")
    print(f"   * Down (Status 2)           : {status.get('down', 0):,}")
    print(f"   * Warning (Status 3)        : {status.get('warning', 0):,}")
    print(f"   * Critical (Status 14)      : {status.get('critical', 0):,}")
    print(f"   * Unmanaged / Unknown       : {status.get('unmanaged_unknown', 0):,}")
    print("-" * 70)
    print(" Vendor Distribution:")
    for v_name, v_count in vendors.items():
        print(f"   * {v_name:<15}: {v_count:,}")
    print("-" * 70)
    print(" Fleet Performance Averages:")
    print(f"   * Average Fleet CPU Load    : {metrics.get('avg_fleet_cpu_load_pct', 0.0)}%")
    print(f"   * Average Fleet RAM Used    : {metrics.get('avg_fleet_ram_used_pct', 0.0)}%")
    print(f"   * Average Fleet Latency     : {metrics.get('avg_fleet_latency_ms', 0.0)} ms")
    print("-" * 70)
    print(f" Top Resource Pressure / Degraded Servers ({len(top_degraded)} listed):")
    for idx, srv in enumerate(top_degraded[:10], start=1):
        print(
            f"   {idx:>2}. {srv['Caption']:<25} | IP: {srv['IPAddress']:<15} | "
            f"Health: {srv['HealthClassification']:<6} | CPU: {str(srv['CPULoad']) + '%':<6} | "
            f"RAM: {str(srv['PercentMemoryUsed']) + '%':<6} | Latency: {str(srv['ResponseTime']) + 'ms':<6}"
        )
    print("=" * 70 + "\n")


def main() -> int:
    """Execute the SolarWinds SWIS data extraction pipeline."""
    args = parse_args()

    if args.verify_only:
        logger.info("Verify-only mode: validating SolarWinds dataset at '%s'...", args.summary_output)
        if not os.path.exists(args.summary_output):
            logger.error("SolarWinds summary file not found: %s", args.summary_output)
            return 1
        with open(args.summary_output, "r", encoding="utf-8") as f:
            summary = json.load(f)
        display_console_report(summary)
        logger.info("Verification PASSED: %s satisfies all SolarWinds telemetry invariants.", args.summary_output)
        return 0

    if not args.username or not args.password:
        logger.error("Missing required SolarWinds credentials.")
        logger.error("Please supply --username and --password or set SOLARWINDS_USERNAME / SOLARWINDS_PASSWORD in .env")
        return 1

    try:
        client = SolarWindsClient(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
        )

        if args.dry_run:
            logger.info("Dry-run mode: testing SWIS API connectivity...")
            test_res = client.query("SELECT TOP 1 NodeID, Caption FROM Orion.Nodes")
            logger.info("Connectivity verified successfully! Returned node: %s", test_res)
            return 0

        logger.info("Starting SolarWinds server telemetry extraction...")
        summary = client.fetch_and_save(
            nodes_output_path=args.nodes_output,
            summary_output_path=args.summary_output,
        )

        display_console_report(summary)
        logger.info("Extraction complete. Output files generated successfully.")
        return 0

    except SolarWindsAuthError as auth_err:
        logger.error("Authentication Error: %s", auth_err)
        return 2
    except SolarWindsApiError as api_err:
        logger.error("SolarWinds API Error: %s", api_err)
        return 3
    except Exception as exc:
        logger.error("Unexpected error during extraction: %s", exc)
        return 4


if __name__ == "__main__":
    sys.exit(main())
