#!/usr/bin/env python3
"""Database Seeding Script for ITOM Operations Platform.

Ingests all 25,987 Microsoft Intune managed devices and 1,543 SolarWinds Orion server nodes
into the persistent PostgreSQL/SQLite database with 100% zero data loss and historical tracking.

Usage:
    python scripts/seed_database.py [--db-url DATABASE_URL] [--clean] [--batch-size 1000]
"""

import argparse
import asyncio
import logging
import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings
from app.core.database import create_db_and_tables, create_engine_for_url, get_sessionmaker
from app.services.seed_service import seed_database

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed_database")


async def main_async(db_url: str, data_dir: str, batch_size: int, clean: bool) -> int:
    """Async main entrypoint for database seeding."""
    logger.info("Initializing engine for database URL: %s", db_url.split("@")[-1] if "@" in db_url else db_url)
    target_engine = create_engine_for_url(db_url)
    sessionmaker_cls = get_sessionmaker(target_engine)

    logger.info("Ensuring all database tables and schema structures exist...")
    await create_db_and_tables(target_engine)

    async with sessionmaker_cls() as session:
        result = await seed_database(
            session=session,
            data_dir=data_dir,
            batch_size=batch_size,
            clean_existing=clean,
        )

    await target_engine.dispose()

    print("\n" + "=" * 70)
    print(" ITOM TELEMETRY DATABASE SEEDING REPORT")
    print("=" * 70)
    print(f" Status:                    {result['status'].upper()}")
    print(f" Intune Devices Seeded:     {result['intune_cis_seeded']:,}")
    print(f" SolarWinds Nodes Seeded:   {result['solarwinds_cis_seeded']:,}")
    print(f" Total CIs Persisted:       {result['total_cis_seeded']:,}")
    print(f" Status History Records:    {result['history_records_created']:,}")
    print(f" Execution Duration:        {result['duration_ms']} ms")
    print(f" Initial Sync Run ID:       {result['sync_run_id']}")
    print("=" * 70 + "\n")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed ITOM database from raw JSON telemetry datasets.")
    parser.add_argument(
        "--db-url",
        type=str,
        default=settings.async_database_url,
        help="Target database async URL (defaults to DATABASE_URL from .env)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=os.path.join(PROJECT_ROOT, "data"),
        help="Directory containing JSON datasets",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for bulk inserts (default: 1000)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=True,
        help="Clean existing CI records before seeding (default: True)",
    )

    args = parser.parse_args()
    return asyncio.run(
        main_async(
            db_url=args.db_url,
            data_dir=args.data_dir,
            batch_size=args.batch_size,
            clean=args.clean,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
