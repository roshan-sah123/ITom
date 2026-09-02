#!/usr/bin/env python3
"""CLI Script: Extract and Aggregate CMDB Configuration Items from SolarWinds Telemetry.

Usage:
    python scripts/fetch_cmdb_data.py [--json-output PATH] [--csv-output PATH]
"""

import argparse
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.sync.cmdb_generator import (
    DEFAULT_SUMMARY_PATH,
    DEFAULT_CSV_PATH,
    CMDBDataExtractor,
    generate_cmdb_artifacts,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract and aggregate CMDB Configuration Items from SolarWinds telemetry."
    )
    parser.add_argument(
        "--json-output",
        default=DEFAULT_SUMMARY_PATH,
        help="Path to output data/cmdb_summary.json",
    )
    parser.add_argument(
        "--csv-output",
        default=DEFAULT_CSV_PATH,
        help="Path to output exports/cmdb_network_cis_complete.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info("Extracting CMDB data from live SolarWinds SWIS / cached snapshot...")
    try:
        json_path, csv_path = generate_cmdb_artifacts(
            json_output_path=args.json_output,
            csv_output_path=args.csv_output,
        )
        logger.info("Successfully generated CMDB artifacts:")
        logger.info("  - Summary JSON : %s", json_path)
        logger.info("  - Export CSV   : %s", csv_path)
        return 0
    except Exception as e:
        logger.error("Failed to generate CMDB artifacts: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
