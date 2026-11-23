"""Keep geographic contributing inventory only for each location's latest capture.

Score history in geographic_score_snapshots is untouched. The latest device list
per location is copied aside, the table is truncated (releasing disk space
immediately and writing little WAL, unlike a large DELETE), and the kept rows are
restored, all in one transaction holding an exclusive lock. Dry run by default.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

LATEST = """
    SELECT DISTINCT ON (location_id) id FROM geographic_score_snapshots
    ORDER BY location_id, recorded_at DESC, id DESC
"""


async def run(apply):
    if not settings.async_database_url.startswith("postgresql+asyncpg://"):
        raise SystemExit("This maintenance script targets the PostgreSQL deployment.")
    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET LOCAL lock_timeout = '120s'"))
                await connection.execute(text("LOCK TABLE geographic_score_inventory IN ACCESS EXCLUSIVE MODE"))
                before = (await connection.execute(text(
                    "SELECT pg_total_relation_size('geographic_score_inventory')"))).scalar_one()
                await connection.execute(text(
                    f"CREATE TEMP TABLE keep_inventory ON COMMIT DROP AS SELECT * FROM geographic_score_inventory "
                    f"WHERE snapshot_id IN ({LATEST})"))
                kept = (await connection.execute(text("SELECT count(*) FROM keep_inventory"))).scalar_one()
                print(f"latest captures keep {kept} rows; table currently uses {before / 1024 ** 3:.1f} GB")
                if not apply:
                    await transaction.rollback()
                    print("Dry run only; nothing was changed.")
                    return
                await connection.execute(text("TRUNCATE geographic_score_inventory"))
                await connection.execute(text("INSERT INTO geographic_score_inventory SELECT * FROM keep_inventory"))
                restored = (await connection.execute(text(
                    "SELECT count(*) FROM geographic_score_inventory"))).scalar_one()
                if restored != kept:
                    raise RuntimeError(f"restored {restored} rows, expected {kept}; rolling back")
                await transaction.commit()
            except BaseException:
                if transaction.is_active:
                    await transaction.rollback()
                raise
        async with engine.connect() as connection:
            after = (await connection.execute(text(
                "SELECT pg_total_relation_size('geographic_score_inventory')"))).scalar_one()
        print(f"Pruned. Table now uses {after / 1024 ** 2:.1f} MB.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="truncate and restore (default is a dry run)")
    asyncio.run(run(parser.parse_args().apply))
