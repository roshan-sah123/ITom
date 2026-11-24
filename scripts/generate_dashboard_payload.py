#!/usr/bin/env python3
"""CLI Script: Generate Dashboard Aggregation Payload from Intune Telemetry.

This script parses raw Intune device records from `data/intune_ops_analytics.json`,
normalizes manufacturer information case-insensitively, computes verified fleet metrics
(compliance totals, compliance rate, disk storage utilization), formats sample records,
and outputs the optimized `data/intune_summary.json` payload.

Usage:
    python scripts/generate_dashboard_payload.py [--input data/intune_ops_analytics.json] [--output data/intune_summary.json]
"""

import argparse
import logging
import os
import sys

# Ensure repository root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.sync.payload_generator import PayloadGenerator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Aggregate Intune device telemetry into precomputed dashboard summary payload."
    )
    parser.add_argument(
        "--input",
        "-i",
        default=os.path.join(PROJECT_ROOT, "data", "intune_ops_analytics.json"),
        help="Path to raw telemetry JSON file (default: data/intune_ops_analytics.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=os.path.join(PROJECT_ROOT, "data", "intune_summary.json"),
        help="Destination path for aggregated summary payload (default: data/intune_summary.json)",
    )
    parser.add_argument(
        "--sample-size",
        "-s",
        type=int,
        default=100,
        help="Number of recent device records for sample table (default: 100)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing data/intune_summary.json without writing changes",
    )
    return parser.parse_args()


def main() -> int:
    """Execute the dashboard payload generation."""
    args = parse_args()
    generator = PayloadGenerator(default_sample_size=args.sample_size)

    try:
        if args.verify_only:
            logger.info("Verifying payload at: %s", args.output)
            import json
            with open(args.output, "r", encoding="utf-8") as f:
                payload = json.load(f)
            generator.validate_payload(payload)
            logger.info("Verification PASSED: %s satisfies all mathematical invariants.", args.output)
            return 0

        logger.info("Generating dashboard payload from '%s' -> '%s'", args.input, args.output)
        payload = generator.generate(
            input_file=args.input,
            output_file=args.output,
            sample_size=args.sample_size,
        )

        metrics = payload.get("metrics", {})
        mfg = payload.get("manufacturer_breakdown", {})
        logger.info("Successfully generated payload:")
        logger.info("  - Total Managed Devices : %d", metrics.get("total_managed_devices", 0))
        logger.info("  - Compliant Devices     : %d", metrics.get("compliant_devices", 0))
        logger.info("  - Non-Compliant Devices : %d", metrics.get("noncompliant_devices", 0))
        logger.info("  - Compliance Rate       : %.2f%%", metrics.get("compliance_rate_pct", 0.0))
        logger.info("  - Avg Storage Used      : %.1f%%", metrics.get("avg_storage_used_pct", 0.0))
        logger.info("  - Manufacturer Counts   : Dell=%d, HP=%d, Lenovo=%d, Apple=%d, Other=%d",
                    mfg.get("Dell", 0), mfg.get("HP", 0), mfg.get("Lenovo", 0), mfg.get("Apple", 0), mfg.get("Other", 0))

        return 0

    except Exception as err:
        logger.error("Failed to generate dashboard payload: %s", err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
