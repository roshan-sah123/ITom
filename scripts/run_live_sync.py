"""LIVE SYNC RUNNER — fetch real telemetry, persist it, and report reconciliation.

This runs the production ingestion path directly, with its own database session,
and prints a full before/after reconciliation so the result is verifiable rather
than merely asserted.

Why a script rather than POST /api/v1/sync/trigger:
    That endpoint schedules the work as a FastAPI BackgroundTask using a session
    obtained via Depends(get_db). Since FastAPI 0.106, yield-dependencies are
    torn down BEFORE background tasks execute, so the session may already be
    closed when the sync runs. This script owns its session for the whole
    operation, which removes that ambiguity and gives you immediate output.

Usage:
    python scripts/run_live_sync.py --source solarwinds
    python scripts/run_live_sync.py --source intune
    python scripts/run_live_sync.py --source all
    python scripts/run_live_sync.py --source intune --dry-run    # fetch only, no writes
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

from sqlalchemy import func, select  # noqa: E402

from app.core.database import AsyncSessionLocal, create_db_and_tables, engine  # noqa: E402
from app.models.ci import ConfigurationItem  # noqa: E402
from app.models.history import CIStatusHistory  # noqa: E402
from app.models.sync import SyncRun  # noqa: E402
from app.services.sync_service import SyncService  # noqa: E402
from app.services.telemetry_sources import build_sources  # noqa: E402


def banner(text: str) -> None:
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


async def snapshot(session) -> dict:
    """Capture current row counts per source system."""
    result = await session.execute(
        select(ConfigurationItem.source_system, func.count(ConfigurationItem.id))
        .group_by(ConfigurationItem.source_system)
    )
    by_source = {row[0]: int(row[1]) for row in result.all()}

    history = await session.execute(select(func.count(CIStatusHistory.id)))
    runs = await session.execute(select(func.count(SyncRun.id)))

    return {
        "by_source": by_source,
        "total_cis": sum(by_source.values()),
        "history_rows": int(history.scalar_one()),
        "sync_runs": int(runs.scalar_one()),
    }


def print_snapshot(label: str, snap: dict) -> None:
    print(f"\n  {label}")
    for source, count in sorted(snap["by_source"].items()):
        print(f"    {source:14} {count:>8,} CIs")
    print(f"    {'TOTAL':14} {snap['total_cis']:>8,} CIs")
    print(f"    {'history rows':14} {snap['history_rows']:>8,}")
    print(f"    {'sync runs':14} {snap['sync_runs']:>8,}")


async def dry_run(source_name: str) -> int:
    """Fetch from the live source and report, without touching the database."""
    banner(f"DRY RUN — {source_name.upper()} (no database writes)")

    sources = build_sources(source_name.upper(), offline=False)
    for source in sources:
        print(f"\n  Fetching from {source.name} ...")
        started = time.time()
        try:
            items = await asyncio.to_thread(source.fetch)
        except Exception as exc:
            print(f"  [FAIL] {source.name}: {exc}")
            return 1

        elapsed = time.time() - started
        print(f"  [OK ] {len(items):,} records in {elapsed:.1f}s "
              f"({len(items)/elapsed:.0f}/s)" if elapsed > 0 else "")

        if items:
            statuses: dict[str, int] = {}
            health: dict[str, int] = {}
            for item in items:
                statuses[item["status"]] = statuses.get(item["status"], 0) + 1
                health[item["health_tier"]] = health.get(item["health_tier"], 0) + 1

            print("\n    Status distribution (as it WOULD be stored):")
            for key, count in sorted(statuses.items(), key=lambda kv: -kv[1]):
                print(f"      {key:20} {count:>8,}")

            print("\n    Health tier distribution:")
            for key in ("High", "Medium", "Low"):
                print(f"      {key:20} {health.get(key, 0):>8,}")

            total = sum(statuses.values())
            print(f"\n    Reconciliation: status sum {total:,} == record count "
                  f"{len(items):,} -> {'OK' if total == len(items) else 'MISMATCH'}")

            print("\n    First record:")
            first = items[0]
            for field in ("external_id", "name", "ci_type", "status", "health_tier", "vendor"):
                print(f"      {field:14} = {str(first.get(field))[:44]}")

    print("\n  Dry run complete. Nothing was written.")
    return 0


async def live_sync(source_name: str) -> int:
    """Execute the real ingestion path and report reconciliation."""
    banner(f"LIVE SYNC — {source_name.upper()}")

    if AsyncSessionLocal is None:
        print("  [FAIL] No database session factory. Check DATABASE_URL.")
        return 1

    try:
        await create_db_and_tables(engine)
    except Exception as exc:
        print(f"  [warn] Table creation notice: {exc}")

    async with AsyncSessionLocal() as session:
        before = await snapshot(session)
        print_snapshot("BEFORE", before)

        print(f"\n  Starting ingestion for {source_name.upper()} ...")
        print("  (this calls the live API and may take a while for a full fleet)")

        started = time.time()
        service = SyncService(session)
        result = await service.execute_sync_with_lock(source_system=source_name.upper())
        elapsed = time.time() - started

        banner("SYNC RESULT")
        print(f"  Overall status : {result.get('status')}")
        print(f"  Wall clock     : {elapsed:.1f}s")
        print(f"  Total extracted: {result.get('total_extracted', 0):,}")

        for entry in result.get("sources", []):
            print(f"\n  --- {entry['source_system']} ---")
            print(f"    status          : {entry['status']}")
            if entry["status"] == "SUCCESS":
                print(f"    extracted       : {entry.get('items_extracted', 0):,}")
                print(f"    new records     : {entry.get('items_persisted', 0):,}")
                print(f"    updated         : {entry.get('items_updated', 0):,}")
                print(f"    unchanged       : {entry.get('items_unchanged', 0):,}")
                print(f"    history written : {entry.get('history_written', 0):,}")
                print(f"    duration        : {entry.get('duration_ms', 0):,} ms")
            else:
                print(f"    error           : {entry.get('error')}")

        if result.get("status") == "SKIPPED":
            print(f"\n  Reason: {result.get('reason')}")

    # Re-open a session so we read committed state.
    async with AsyncSessionLocal() as session:
        after = await snapshot(session)
        print_snapshot("AFTER", after)

        banner("RECONCILIATION")
        print(f"  {'metric':16} {'before':>10} {'after':>10} {'delta':>10}")
        print("  " + "-" * 48)
        for key in sorted(set(before["by_source"]) | set(after["by_source"])):
            b = before["by_source"].get(key, 0)
            a = after["by_source"].get(key, 0)
            print(f"  {key:16} {b:>10,} {a:>10,} {a - b:>+10,}")
        for key in ("total_cis", "history_rows", "sync_runs"):
            b, a = before[key], after[key]
            print(f"  {key:16} {b:>10,} {a:>10,} {a - b:>+10,}")

        latest = await session.execute(
            select(SyncRun).order_by(SyncRun.started_at.desc()).limit(3)
        )
        print("\n  Most recent sync runs:")
        for run in latest.scalars().all():
            completed = run.completed_at.isoformat() if run.completed_at else "-"
            print(f"    {run.source_system:12} {run.status:8} "
                  f"extracted={run.items_extracted:>7,} {completed}")

    print("\n  Next: check the freshness endpoint")
    print("    curl.exe http://localhost:8000/api/v1/system/freshness")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live telemetry sync")
    parser.add_argument("--source", choices=["intune", "solarwinds", "all"], required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch from the live API but write nothing")
    args = parser.parse_args()

    print("\nITOM PORTAL — LIVE TELEMETRY SYNC")
    print(f"Started {datetime.now(timezone.utc).isoformat()}")
    print(f"Source: {args.source.upper()}   Mode: {'DRY RUN' if args.dry_run else 'WRITE'}")

    if args.dry_run:
        return asyncio.run(dry_run(args.source))
    return asyncio.run(live_sync(args.source))


if __name__ == "__main__":
    sys.exit(main())
