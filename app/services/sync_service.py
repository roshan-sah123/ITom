"""Resilient telemetry synchronization with live extraction, delta detection and locking.

WHAT CHANGED IN STEP 4
----------------------
1. LIVE EXTRACTION. Data now comes from Microsoft Graph and SolarWinds SWIS via
   ``telemetry_sources``, not from ``data/*.json`` on disk. The old code
   re-read the same static file every 10 minutes forever.

2. INTUNE ACTUALLY RUNS. The previous version assigned ``intune_file`` and
   never used it - there was no Intune branch, so ``source_system="INTUNE"``
   returned SUCCESS with ``items_extracted: 0``. A silent no-op reporting
   success is worse than a failure.

3. ONE SyncRun PER SOURCE. Previously a single run covered "ALL", so a
   SolarWinds success masked an Intune that never executed. Each source now
   gets its own audited run, which is what makes per-source freshness possible.

4. FAILURES ARE REAL. If Graph returns 401 or SolarWinds is unreachable, the
   run is recorded FAILED and the freshness clock does not advance. Under the
   old design a sync literally could not fail, because reading a local file
   always succeeds.

5. TRANSACTION-SCOPED ADVISORY LOCK. ``pg_try_advisory_lock`` is *session*
   scoped - it binds to the connection. The old code committed first and then
   released, by which point SQLAlchemy had returned the connection to the pool,
   so the unlock ran on a different connection and silently returned false. The
   original lock stayed held and every later sync returned SKIPPED - sync death
   with a still-green freshness header. ``pg_advisory_xact_lock`` releases
   automatically at commit, which is the correct primitive here.

6. FINGERPRINT ON STATE, NOT LOAD. The hash previously included CPU and RAM,
   which change on essentially every poll, so ~1,548 nodes x 144 cycles wrote
   roughly 223,000 history rows per day (~81M/year) into an unpartitioned table.
   The fingerprint now covers ``status:health_tier`` only, so history records
   genuine transitions. Live resource metrics still land on each history row.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ci import ConfigurationItem
from app.models.history import CIStatusHistory
from app.models.sync import SyncErrorLog, SyncRun
from app.repositories.ci_repository import CIRepository
from app.repositories.sync_repository import SyncRepository
from app.services.summary_cache import invalidate_summaries_for_sources
from app.services.location_service import LocationService
from app.services.telemetry_sources import (
    SourceUnavailableError,
    TelemetrySource,
    build_sources,
)

logger = logging.getLogger("itom.sync")

# Fallback lock for non-PostgreSQL engines (SQLite in tests).
_in_memory_locked = False


def _safe_float(value: Any) -> Optional[float]:
    """Coerce a telemetry metric to a float, or None if it is unusable.

    Upstream sources are not trustworthy. SolarWinds can return -1 for an
    unpolled counter, Graph can return a string, and a malformed record can
    carry anything at all. Passing such a value straight into a Float column
    raises ``StatementError`` mid-flush, which aborts the transaction and loses
    the ENTIRE batch - one bad row taking down 27,000 good ones.

    Unusable metrics become NULL so ingestion continues. The CI row itself is
    still persisted; only the unreadable metric is dropped.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        try:
            numeric = float(value.strip())
        except (ValueError, AttributeError):
            return None
    else:
        return None

    # Reject sentinels and non-finite values that would poison an average.
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        return None
    if numeric < 0:
        return None
    return numeric


class SyncService:
    """Orchestrates live telemetry ingestion, delta detection, and execution audits."""

    ADVISORY_LOCK_ID: int = settings.ADVISORY_LOCK_ID

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ci_repo = CIRepository(session)
        self.sync_repo = SyncRepository(session)

    # ------------------------------------------------------------------ #
    # Delta detection
    # ------------------------------------------------------------------ #

    @staticmethod
    def compute_state_fingerprint(ci_data: Dict[str, Any]) -> str:
        """SHA-256 over the *stable* operational state of a CI.

        Deliberately excludes CPU/RAM/storage: those fluctuate on every poll and
        including them defeated the purpose of delta detection entirely.
        """
        payload = f"{ci_data.get('status')}:{ci_data.get('health_tier')}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ #
    # Locking
    # ------------------------------------------------------------------ #

    async def _acquire_lock(self) -> bool:
        """Take the ingestion lock for the current transaction.

        On PostgreSQL this uses ``pg_advisory_xact_lock``, which the database
        releases automatically at COMMIT or ROLLBACK - no leak is possible.
        """
        global _in_memory_locked
        bind = self.session.bind
        dialect = bind.dialect.name if bind is not None else "postgresql"

        if dialect == "postgresql":
            try:
                return bool((await self.session.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": self.ADVISORY_LOCK_ID},
                )).scalar())
            except Exception as exc:
                raise RuntimeError("PostgreSQL sync lock unavailable") from exc

        if _in_memory_locked:
            return False
        _in_memory_locked = True
        return True

    @staticmethod
    def _release_in_memory_lock() -> None:
        global _in_memory_locked
        _in_memory_locked = False

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #

    async def ingest_telemetry_batch(
        self, telemetry_items: List[Dict[str, Any]], source_system: str
    ) -> Dict[str, int]:
        """Persist a batch of CI records, writing history only on real change."""
        persisted = updated = unchanged = history_written = 0
        now = datetime.now(timezone.utc)

        # Load database location rules once for this batch, not once per device.
        location_resolver = await LocationService(self.session).resolver(bootstrap=True)

        for item in telemetry_items:
            source_id = str(
                item.get("external_id") or item.get("source_id") or item.get("id") or ""
            ).strip()
            if not source_id:
                continue

            new_hash = self.compute_state_fingerprint(item)
            existing = await self.ci_repo.get_by_source_key(source_system, source_id)

            # Fallback defaults for records that bypass normalisation (direct
            # API injection, malformed source rows). The live adapters in
            # telemetry_sources.py always set status and health explicitly, so
            # these values never apply to real Graph or SWIS ingestion - they
            # exist only so a malformed record still produces a valid row
            # instead of failing the NOT NULL constraint and killing the batch.
            status = item.get("status") or "Unknown"
            health = item.get("health_tier") or "Medium"
            name = item.get("name") or "Unknown"
            ci_type = item.get("ci_type") or "Unknown"
            ip = item.get("ip_address")
            vendor = item.get("vendor") or item.get("manufacturer") or "Unknown"
            model = item.get("model")
            serial = item.get("serial_number")
            os_ver = item.get("operating_system")
            location = item.get("location")
            attrs = item.get("attributes") or {}
            assignment = location_resolver.resolve(source_system, name, location, attrs)

            # Metrics are coerced defensively: a single malformed value must
            # never abort the flush and discard the whole batch.
            cpu_val = _safe_float(item.get("cpu_load"))
            ram_val = _safe_float(item.get("ram_used"))
            storage_val = _safe_float(item.get("storage_used"))
            latency_val = _safe_float(item.get("latency_ms"))

            if not existing:
                ci = ConfigurationItem(
                    id=uuid.uuid4(),
                    source_id=source_id,
                    source_system=source_system.upper(),
                    name=name,
                    ci_type=ci_type,
                    status=status,
                    health_tier=health,
                    ip_address=ip,
                    vendor=vendor,
                    model=model,
                    serial_number=serial,
                    operating_system=os_ver,
                    location=location,
                    last_sync_time=now,
                    state_hash=new_hash,
                    attributes=attrs,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(ci)
                LocationService.assign(ci, assignment)
                await self.session.flush()

                self.session.add(
                    CIStatusHistory(
                        id=uuid.uuid4(),
                        ci_id=ci.id,
                        status=status,
                        health_tier=health,
                        previous_status=None,
                        previous_health_tier=None,
                        cpu_utilization=cpu_val,
                        memory_utilization=ram_val,
                        storage_used_pct=storage_val,
                        latency_ms=latency_val,
                        changed_attributes={"event": "INITIAL_INGESTION"},
                        recorded_at=now,
                    )
                )
                persisted += 1
                history_written += 1
                continue

            if existing.state_hash == new_hash and existing.is_active:
                LocationService.assign(existing, assignment)
                # A stable health state does not imply stable inventory fields.
                current = {
                    "name": name, "ci_type": ci_type, "ip_address": ip,
                    "vendor": vendor, "model": model, "serial_number": serial,
                    "operating_system": os_ver, "location": location,
                    "attributes": attrs,
                }
                changed = any(getattr(existing, key) != value for key, value in current.items())
                for key, value in current.items():
                    setattr(existing, key, value)
                if changed:
                    existing.updated_at = now
                    updated += 1
                else:
                    unchanged += 1
                existing.last_sync_time = now
                continue

            old_status = existing.status
            old_health = existing.health_tier

            existing.status = status
            existing.is_active = True
            existing.retired_at = None
            existing.health_tier = health
            existing.name = name
            existing.ci_type = ci_type or existing.ci_type
            existing.ip_address = ip
            existing.vendor = vendor or existing.vendor
            existing.model = model or existing.model
            existing.serial_number = serial or existing.serial_number
            existing.operating_system = os_ver or existing.operating_system
            existing.location = location
            LocationService.assign(existing, assignment)
            existing.state_hash = new_hash
            existing.last_sync_time = now
            existing.updated_at = now

            if attrs:
                # Reassign rather than mutate in place: SQLAlchemy does not track
                # in-place dict mutation unless the column is a MutableDict, so
                # the old `existing.attributes.update(attrs)` was silently lost.
                merged = dict(existing.attributes or {})
                merged.update(attrs)
                existing.attributes = merged

            self.session.add(
                CIStatusHistory(
                    id=uuid.uuid4(),
                    ci_id=existing.id,
                    status=status,
                    health_tier=health,
                    previous_status=old_status,
                    previous_health_tier=old_health,
                    cpu_utilization=cpu_val,
                    memory_utilization=ram_val,
                    storage_used_pct=storage_val,
                    latency_ms=latency_val,
                    changed_attributes={
                        "previous_status": old_status,
                        "new_status": status,
                        "previous_health_tier": old_health,
                        "new_health_tier": health,
                    },
                    recorded_at=now,
                )
            )
            updated += 1
            history_written += 1

        await self.session.flush()
        return {
            "persisted": persisted,
            "updated": updated,
            "unchanged": unchanged,
            "history_written": history_written,
        }

    # ------------------------------------------------------------------ #
    # Per-source execution
    # ------------------------------------------------------------------ #

    async def _fetch_source(self, source: TelemetrySource) -> List[Dict[str, Any]]:
        """Run a synchronous client in a worker thread so the loop stays free."""
        return await asyncio.to_thread(source.fetch)

    async def retire_missing(self, source_name, items):
        """Soft retire only after the caller validates a complete source snapshot."""
        seen = {str(item["external_id"]) for item in items}
        rows = (await self.session.execute(
            select(ConfigurationItem).where(ConfigurationItem.source_system == source_name)
        )).scalars().all()
        now = datetime.now(timezone.utc)
        retired = 0
        for ci in rows:
            if ci.source_id not in seen and ci.is_active:
                ci.is_active = False
                ci.retired_at = now
                ci.updated_at = now
                self.session.add(CIStatusHistory(
                    id=uuid.uuid4(), ci_id=ci.id, status=ci.status,
                    health_tier=ci.health_tier, previous_status=ci.status,
                    previous_health_tier=ci.health_tier, recorded_at=now,
                    changed_attributes={"event": "RETIRED", "reason": "Absent from complete snapshot"},
                ))
                retired += 1
        await self.session.flush()
        return retired

    async def sync_single_source(
        self,
        source: TelemetrySource,
        telemetry_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Execute and audit one source's ingestion cycle.

        Records a SyncRun per source, so one domain failing never lets another
        domain look fresh.
        """
        run_id = uuid.uuid4()
        started_at = datetime.now(timezone.utc)

        sync_run = SyncRun(
            id=run_id,
            source_system=source.name.upper(),
            status="RUNNING",
            started_at=started_at,
        )
        self.session.add(sync_run)
        await self.session.flush()

        try:
            items = telemetry_items if telemetry_items is not None else await self._fetch_source(source)
            extracted_count = len(items or [])

            if not items:
                raise SourceUnavailableError(
                    f"{source.name} returned zero records - treating as a failed "
                    f"extraction rather than an empty fleet."
                )

            keys = [str(item.get("external_id") or item.get("source_id") or item.get("id") or "").strip() for item in items]
            if any(not key for key in keys) or len(set(keys)) != len(keys):
                raise SourceUnavailableError("Missing or duplicate normalized source identifiers")
            # Inventory, retirement, source success and score observations are
            # one atomic unit. A derived-history failure must not advance CIs
            # while the audit claims the source failed and was rolled back.
            async with self.session.begin_nested():
                results = await self.ingest_telemetry_batch(items, source.name)
                retired = 0
                if telemetry_items is None and getattr(source, "snapshot_complete", False):
                    retired = await self.retire_missing(source.name, items)

                completed_at = datetime.now(timezone.utc)
                sync_run.status = "SUCCESS"
                sync_run.items_extracted = getattr(source, "fetched_count", len(items))
                sync_run.items_normalized = len(items)
                sync_run.items_rejected = max(0, sync_run.items_extracted - sync_run.items_normalized)
                sync_run.records_retired = retired
                sync_run.records_failed = 0
                sync_run.items_persisted = results["persisted"]
                sync_run.records_updated = results["updated"]
                sync_run.records_unchanged = results["unchanged"]
                sync_run.records_processed = len(items)
                sync_run.duration_ms = int((completed_at - started_at).total_seconds() * 1000)
                sync_run.completed_at = completed_at

                # Observations begin here; change-only CI history is not a site trend.
                await LocationService(self.session).capture(sync_run.id)

            logger.info(
                "%s sync SUCCESS: %d extracted, %d new, %d updated, %d unchanged (%d ms).",
                source.name, len(items), results["persisted"],
                results["updated"], results["unchanged"], sync_run.duration_ms,
            )

            return {
                "source_system": source.name.upper(),
                "status": "SUCCESS",
                "run_id": str(run_id),
                "items_extracted": getattr(source, "fetched_count", len(items)),
                "items_normalized": len(items),
                "items_retired": retired,
                "items_failed": 0,
                "items_persisted": results["persisted"],
                "items_updated": results["updated"],
                "items_unchanged": results["unchanged"],
                "history_written": results["history_written"],
                "duration_ms": sync_run.duration_ms,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }

        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            sync_run.status = "FAILED"
            raw_count = getattr(source, "fetched_count", 0)
            sync_run.items_extracted = raw_count or locals().get("extracted_count", 0)
            sync_run.items_normalized = 0
            sync_run.items_rejected = raw_count or locals().get("extracted_count", 0)
            sync_run.items_persisted = 0
            sync_run.records_updated = 0
            sync_run.records_unchanged = 0
            sync_run.records_retired = 0
            sync_run.records_processed = 0
            sync_run.duration_ms = duration_ms
            sync_run.completed_at = completed_at

            self.session.add(
                SyncErrorLog(
                    id=uuid.uuid4(),
                    sync_run_id=run_id,
                    error_code=exc.__class__.__name__,
                    error_message=f"{type(exc).__name__}: source synchronization failed; inventory changes rolled back.",
                    stack_trace=None,
                    context_data={"source_system": source.name.upper()},
                    occurred_at=completed_at,
                )
            )
            await self.session.flush()

            logger.error("%s sync FAILED after %d ms: %s", source.name, duration_ms, exc)

            return {
                "source_system": source.name.upper(),
                "status": "FAILED",
                "run_id": str(run_id),
                "error": str(exc),
                "items_extracted": raw_count or locals().get("extracted_count", 0),
                "duration_ms": duration_ms,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    async def execute_sync_with_lock(
        self,
        telemetry_items: Optional[List[Dict[str, Any]]] = None,
        source_system: str = "ALL",
        should_fail: bool = False,
        offline: bool = False,
    ) -> Dict[str, Any]:
        """Run the full ingestion pipeline under the advisory lock.

        Args:
            telemetry_items: Pre-built records (tests bypass live extraction).
            source_system: ``INTUNE``, ``SOLARWINDS`` or ``ALL``.
            should_fail: Test hook that forces a failure path.
            offline: Read local fixtures instead of live APIs. Never the default.

        Returns:
            Overall status plus a per-source result list. Overall status is:
            ``SUCCESS`` if every source succeeded, ``PARTIAL`` if some did, and
            ``FAILED`` if none did.
        """
        acquired = await self._acquire_lock()
        if not acquired:
            logger.info("Sync skipped: ingestion lock %s held by a peer worker.", self.ADVISORY_LOCK_ID)
            return {
                "status": "SKIPPED",
                "reason": f"Advisory lock {self.ADVISORY_LOCK_ID} held by peer worker",
                "sources": [],
            }

        try:
            if should_fail:
                raise ConnectionError("Simulated SWIS API network timeout during ingestion")

            sources = build_sources(source_system, offline=offline)

            results: List[Dict[str, Any]] = []
            for source in sources:
                # Explicit test injection applies only to a single-source run.
                injected = telemetry_items if (telemetry_items is not None and len(sources) == 1) else None
                results.append(await self.sync_single_source(source, telemetry_items=injected))

            successes = [r for r in results if r["status"] == "SUCCESS"]
            await self.session.commit()  # releases pg_advisory_xact_lock
            if successes:
                invalidate_summaries_for_sources(
                    (result["source_system"] for result in successes),
                    session=self.session,
                )

            if len(successes) == len(results):
                overall = "SUCCESS"
            elif successes:
                overall = "PARTIAL"
            else:
                overall = "FAILED"

            return {
                "status": overall,
                "sources": results,
                "total_extracted": sum(r.get("items_extracted", 0) for r in results),
                # Retained for callers written against the single-run shape.
                "run": results[0] if results else None,
            }

        except Exception as exc:
            await self.session.rollback()
            logger.error("Sync pipeline aborted: %s", exc, exc_info=True)

            failed_at = datetime.now(timezone.utc)
            run_id = uuid.uuid4()
            self.session.add(
                SyncRun(
                    id=run_id,
                    source_system=(source_system or "ALL").upper(),
                    status="FAILED",
                    items_extracted=0,
                    items_persisted=0,
                    records_updated=0,
                    records_unchanged=0,
                    records_processed=0,
                    duration_ms=0,
                    started_at=failed_at,
                    completed_at=failed_at,
                )
            )
            self.session.add(
                SyncErrorLog(
                    id=uuid.uuid4(),
                    sync_run_id=run_id,
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                    stack_trace=traceback.format_exc(),
                    context_data={"source_system": source_system},
                    occurred_at=failed_at,
                )
            )
            await self.session.commit()

            return {
                "status": "FAILED",
                "error": str(exc),
                "sources": [],
                "run": {
                    "id": str(run_id),
                    "status": "FAILED",
                    "items_extracted": 0,
                    "started_at": failed_at.isoformat(),
                    "completed_at": failed_at.isoformat(),
                },
            }

        finally:
            self._release_in_memory_lock()
