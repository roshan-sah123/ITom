"""Authoritative data-freshness lookup, computed from the database.

WHY THIS FILE EXISTS
--------------------
The freshness signal previously came from a module-level global in
``app/core/middleware.py``:

    _last_sync_time: datetime = datetime.now(timezone.utc)

That has two defects that make the signal untrustworthy:

1. It is initialised to *process start time*. The moment the server boots,
   every response claims ``X-Sync-Status: FRESH`` and ``X-Data-Age-Seconds: 0``
   even if no synchronization has ever run and the data is weeks old.

2. It is per-process. With more than one uvicorn worker, only the worker that
   happened to execute the sync knows the real timestamp; the others report
   their own boot time. The header becomes non-deterministic per request.

This module derives freshness from ``MAX(sync_runs.completed_at)`` where the
run succeeded, so every worker reports the same answer and "never synced"
is representable.

Status vocabulary returned to clients:

    FRESH    data age is within the freshness window
    STALE    a sync has succeeded before, but not recently enough
    UNKNOWN  no successful synchronization has ever been recorded
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync import SyncRun

logger = logging.getLogger("itom.freshness")

# Domains reported individually. A per-source view matters because SolarWinds
# succeeding must never make Intune look fresh.
TRACKED_SOURCES: List[str] = ["INTUNE", "SOLARWINDS"]

STATUS_FRESH = "FRESH"
STATUS_STALE = "STALE"
STATUS_UNKNOWN = "UNKNOWN"


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return a timezone-aware UTC datetime, tolerating naive DB values."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def classify(
    last_success: Optional[datetime],
    now: Optional[datetime] = None,
    freshness_window_seconds: int = 900,
) -> Dict[str, Any]:
    """Classify a last-success timestamp into a freshness verdict.

    Args:
        last_success: Timestamp of the most recent successful sync, or None.
        now: Reference time (defaults to current UTC).
        freshness_window_seconds: Age at or below which data counts as FRESH.

    Returns:
        Dict with ``last_synchronized_at``, ``age_seconds`` and ``status``.
    """
    reference = now or datetime.now(timezone.utc)
    normalised = _as_utc(last_success)

    if normalised is None:
        return {
            "last_synchronized_at": None,
            "age_seconds": None,
            "status": STATUS_UNKNOWN,
        }

    age = max(0, int((reference - normalised).total_seconds()))
    return {
        "last_synchronized_at": normalised.isoformat(),
        "age_seconds": age,
        "status": STATUS_FRESH if age <= freshness_window_seconds else STATUS_STALE,
    }


class FreshnessRepository:
    """Reads the authoritative last-successful-sync timestamps from the database."""

    def __init__(
        self,
        session: Optional[AsyncSession],
        freshness_window_seconds: int = 900,
    ) -> None:
        self.session = session
        self.freshness_window_seconds = freshness_window_seconds

    async def _last_success_per_source(self) -> Dict[str, Optional[datetime]]:
        """MAX(completed_at) for successful runs, grouped by source system.

        A run recorded against source ``ALL`` counts toward every tracked
        source, because that is what an all-domain sync actually refreshed.
        """
        results: Dict[str, Optional[datetime]] = {src: None for src in TRACKED_SOURCES}
        if self.session is None:
            return results

        try:
            stmt = (
                select(SyncRun.source_system, func.max(SyncRun.completed_at))
                .where(SyncRun.status == "SUCCESS")
                .group_by(SyncRun.source_system)
            )
            rows = (await self.session.execute(stmt)).all()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Freshness query failed: %s", exc)
            return results

        by_source: Dict[str, Optional[datetime]] = {}
        for source, completed in rows:
            if source:
                by_source[str(source).upper()] = _as_utc(completed)

        all_domains = by_source.get("ALL")
        for src in TRACKED_SOURCES:
            candidates = [t for t in (by_source.get(src), all_domains) if t is not None]
            results[src] = max(candidates) if candidates else None

        return results

    async def get_freshness(self) -> Dict[str, Any]:
        """Build the full freshness report for all tracked source systems.

        The overall status is the WORST status across sources: a dashboard is
        only as fresh as its least-fresh feed. UNKNOWN outranks STALE, because
        "never synced" is a stronger warning than "synced a while ago".
        """
        now = datetime.now(timezone.utc)
        per_source_times = await self._last_success_per_source()

        sources: Dict[str, Any] = {}
        for src, last_success in per_source_times.items():
            sources[src] = classify(
                last_success,
                now=now,
                freshness_window_seconds=self.freshness_window_seconds,
            )

        if self.session is not None:
            attempts = (await self.session.execute(
                select(SyncRun.source_system, SyncRun.status, SyncRun.started_at)
                .where(SyncRun.source_system.in_(TRACKED_SOURCES))
                .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            )).all()
            seen = set()
            for source, status, started_at in attempts:
                if source in sources and source not in seen:
                    seen.add(source)
                    sources[source]["last_attempt_status"] = status
                    sources[source]["last_attempt_at"] = _as_utc(started_at).isoformat() if started_at else None

        statuses = {entry["status"] for entry in sources.values()}
        if STATUS_UNKNOWN in statuses:
            overall = STATUS_UNKNOWN
        elif STATUS_STALE in statuses:
            overall = STATUS_STALE
        else:
            overall = STATUS_FRESH

        ages = [
            entry["age_seconds"]
            for entry in sources.values()
            if entry["age_seconds"] is not None
        ]

        return {
            "checked_at": now.isoformat(),
            "freshness_window_seconds": self.freshness_window_seconds,
            "overall_status": overall,
            "oldest_age_seconds": max(ages) if ages else None,
            "sources": sources,
        }
