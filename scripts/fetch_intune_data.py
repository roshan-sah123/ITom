#!/usr/bin/env python3
"""CLI Script: Ingest Managed Device Telemetry from Microsoft Intune.

This script interacts with Microsoft Graph API using OAuth 2.0 Client Credentials Grant
to extract live managed device telemetry and save raw snapshots into `data/intune_ops_analytics.json`.

Usage:
    python scripts/fetch_intune_data.py [--output data/intune_ops_analytics.json] [--max-devices 1000]
"""

import argparse
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

from src.sync.graph_client import GraphAuthError, GraphApiError, GraphClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest managed endpoint telemetry from Microsoft Intune Graph API."
    )
    parser.add_argument(
        "--output",
        "-o",
        default=os.path.join(PROJECT_ROOT, "data", "intune_ops_analytics.json"),
        help="Destination path for raw telemetry JSON (default: data/intune_ops_analytics.json)",
    )
    parser.add_argument(
        "--tenant-id",
        default=os.getenv("AZURE_TENANT_ID"),
        help="Azure AD Tenant ID (defaults to AZURE_TENANT_ID env)",
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("AZURE_CLIENT_ID"),
        help="Azure AD Client ID (defaults to AZURE_CLIENT_ID env)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("AZURE_CLIENT_SECRET"),
        help="Azure AD Client Secret (defaults to AZURE_CLIENT_SECRET env)",
    )
    parser.add_argument(
        "--max-devices",
        type=int,
        default=None,
        help="Optional limit on total devices to fetch (for testing/dry runs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate credentials and token acquisition without writing data",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing Intune datasets without network connection or credentials",
    )
    return parser.parse_args()


def main() -> int:
    """Execute the extraction pipeline."""
    args = parse_args()

    if args.verify_only:
        logger.info("Verify-only mode: validating Intune dataset at '%s'...", args.output)
        if not os.path.exists(args.output):
            logger.error("Intune dataset not found: %s", args.output)
            return 1
        import json
        with open(args.output, "r", encoding="utf-8") as f:
            data = json.load(f)
        total = data.get("summary", {}).get("total_devices", len(data.get("devices", [])))
        logger.info("Verification PASSED: %s contains %d verified Intune endpoint records.", args.output, total)
        return 0

    if not args.tenant_id or not args.client_id or not args.client_secret:
        logger.error("Missing required Azure AD credentials.")
        logger.error("Please supply --tenant-id, --client-id, --client-secret or set .env variables.")
        return 1

    try:
        client = GraphClient(
            tenant_id=args.tenant_id,
            client_id=args.client_id,
            client_secret=args.client_secret,
        )

        if args.dry_run:
            logger.info("Dry-run requested. Verifying Azure AD OAuth 2.0 token acquisition...")
            token = client.get_access_token()
            logger.info("OAuth token acquired successfully. Token length: %d chars.", len(token))
            return 0

        logger.info("Starting live Microsoft Intune device extraction...")
        raw_data = client.fetch_and_save(
            output_path=args.output,
            max_devices=args.max_devices,
        )
        total_fetched = raw_data.get("summary", {}).get("total_devices", 0)
        logger.info("Successfully extracted %d devices to '%s'", total_fetched, args.output)
        return 0

    except GraphAuthError as err:
        logger.error("Authentication Error: %s", err)
        return 2
    except GraphApiError as err:
        logger.error("Graph API Error: %s", err)
        return 3
    except Exception as err:
        logger.error("Unexpected error during extraction: %s", err)
        return 4


if __name__ == "__main__":
    sys.exit(main())
