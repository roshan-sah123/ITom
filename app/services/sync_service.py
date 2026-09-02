"""Resilient background telemetry synchronization service with delta detection and advisory locks."""

import asyncio
import hashlib
import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.middleware import set_last_sync_timestamp
from app.models.ci import ConfigurationItem
from app.models.history import CIStatusHistory
from app.models.sync import SyncErrorLog, SyncRun
from app.repositories.ci_repository import CIRepository
from app.repositories.sync_repository import SyncRepository

logger = logging.getLogger("itom.sync")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# In-memory concurrency fallback lock for non-Postgres engines (e.g. SQLite / in-memory tests)
_in_memory_lock = asyncio.Lock()
_in_memory_locked = False


class SyncService:
    """Orchestrates multi-domain telemetry ingestion, SHA-256 delta detection, and execution audits."""

    ADVISORY_LOCK_ID: int = settings.ADVISORY_LOCK_ID

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ci_repo = CIRepository(session)
        self.sync_repo = SyncRepository(session)

    @staticmethod
    def compute_state_fingerprint(ci_data: Dict[str, Any]) -> str:
        """Compute deterministic SHA-256 fingerprint of volatile operational metrics."""
        status = ci_data.get("status")
        health = ci_data.get("health_tier")
        cpu = ci_data.get("cpu_load")
        ram = ci_data.get("ram_used")
        storage = ci_data.get("storage_used")
        payload = f"{status}:{health}:{cpu}:{ram}:{storage}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def _try_acquire_advisory_lock(self) -> bool:
        """Attempt to acquire session-level advisory lock 1048576."""
        global _in_memory_locked
        bind = self.session.bind
        dialect = bind.dialect.name if bind else "postgresql"

        if dialect == "postgresql":
            try:
                res = await self.session.execute(
                    text(f"SELECT pg_try_advisory_lock({self.ADVISORY_LOCK_ID})")
                )
                acquired = res.scalar_one_or_none()
                return bool(acquired)
            except Exception as exc:
                logger.warning("PostgreSQL advisory lock check failed: %s; falling back to in-memory lock", exc)

        # Fallback for SQLite / test environments
        if _in_memory_locked:
            return False
        _in_memory_locked = True
        return True

    async def _release_advisory_lock(self) -> None:
        """Release session-level advisory lock 1048576."""
        global _in_memory_locked
        bind = self.session.bind
        dialect = bind.dialect.name if bind else "postgresql"

        if dialect == "postgresql":
            try:
                await self.session.execute(
                    text(f"SELECT pg_advisory_unlock({self.ADVISORY_LOCK_ID})")
                )
            except Exception as exc:
                logger.warning("Failed to release PostgreSQL advisory lock: %s", exc)

        _in_memory_locked = False

    async def ingest_telemetry_batch(
        self, telemetry_items: List[Dict[str, Any]], source_system: str
    ) -> Dict[str, int]:
        """Ingest telemetry batch, apply delta detection, and write state history on change."""
        persisted = 0
        updated = 0
        unchanged = 0
        history_written = 0
        now = datetime.now(timezone.utc)

        for item in telemetry_items:
            source_id = str(item.get("external_id") or item.get("source_id") or item.get("id") or "")
            if not source_id:
                continue

            new_hash = self.compute_state_fingerprint(item)
            existing = await self.ci_repo.get_by_source_key(source_system, source_id)

            status = item.get("status") or "ACTIVE"
            health = item.get("health_tier") or "High"
            name = item.get("name") or f"Node-{source_id}"
            ci_type = item.get("ci_type") or "Server"
            ip = item.get("ip_address")
            vendor = item.get("manufacturer") or item.get("vendor") or "Other"
            model = item.get("model")
            serial = item.get("serial_number")
            os_ver = item.get("operating_system")
            attrs = item.get("attributes") or {}

            if not existing:
                # Brand new CI -> Persist record and write initial history
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
                    last_sync_time=now,
                    state_hash=new_hash,
                    attributes=attrs,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(ci)
                await self.session.flush()

                hist = CIStatusHistory(
                    id=uuid.uuid4(),
                    ci_id=ci.id,
                    status=status,
                    health_tier=health,
                    previous_status=None,
                    previous_health_tier=None,
                    cpu_utilization=item.get("cpu_load"),
                    memory_utilization=item.get("ram_used"),
                    storage_used_pct=item.get("storage_used"),
                    latency_ms=item.get("latency_ms"),
                    changed_attributes={"event": "INITIAL_INGESTION"},
                    recorded_at=now,
                )
                self.session.add(hist)
                persisted += 1
                history_written += 1
            else:
                old_hash = existing.state_hash
                if old_hash == new_hash:
                    # Unchanged operational state: refresh last_sync_time only, NO history row
                    existing.last_sync_time = now
                    unchanged += 1
                else:
                    # Delta detected: update CI and append to time-series history
                    old_status = existing.status
                    old_health = existing.health_tier

                    existing.status = status
                    existing.health_tier = health
                    existing.name = name
                    existing.ip_address = ip or existing.ip_address
                    existing.vendor = vendor or existing.vendor
                    existing.model = model or existing.model
                    existing.serial_number = serial or existing.serial_number
                    existing.operating_system = os_ver or existing.operating_system
                    existing.state_hash = new_hash
                    existing.last_sync_time = now
                    existing.updated_at = now
                    if attrs:
                        existing.attributes.update(attrs)

                    hist = CIStatusHistory(
                        id=uuid.uuid4(),
                        ci_id=existing.id,
                        status=status,
                        health_tier=health,
                        previous_status=old_status,
                        previous_health_tier=old_health,
                        cpu_utilization=item.get("cpu_load"),
                        memory_utilization=item.get("ram_used"),
                        storage_used_pct=item.get("storage_used"),
                        latency_ms=item.get("latency_ms"),
                        changed_attributes={
                            "cpu_load": item.get("cpu_load"),
                            "ram_used": item.get("ram_used"),
                            "previous_status": old_status,
                            "new_status": status,
                        },
                        recorded_at=now,
                    )
                    self.session.add(hist)
                    updated += 1
                    history_written += 1

        await self.session.flush()
        return {
            "persisted": persisted,
            "updated": updated,
            "unchanged": unchanged,
            "history_written": history_written,
        }

    async def execute_sync_with_lock(
        self,
        telemetry_items: Optional[List[Dict[str, Any]]] = None,
        source_system: str = "ALL",
        should_fail: bool = False,
    ) -> Dict[str, Any]:
        """Execute full synchronization pipeline protected by advisory lock."""
        acquired = await self._try_acquire_advisory_lock()
        if not acquired:
            logger.info("Sync skipped: Advisory lock %s is held by another worker.", self.ADVISORY_LOCK_ID)
            return {
                "status": "SKIPPED",
                "reason": f"Advisory lock {self.ADVISORY_LOCK_ID} held by peer worker",
            }

        run_id = uuid.uuid4()
        started_at = datetime.now(timezone.utc)
        sync_run = SyncRun(
            id=run_id,
            source_system=source_system.upper(),
            status="RUNNING",
            started_at=started_at,
        )
        self.session.add(sync_run)
        await self.session.flush()

        try:
            if should_fail:
                raise ConnectionError("Simulated SWIS API network timeout during ingestion")

            total_extracted = 0
            total_persisted = 0
            total_updated = 0
            total_unchanged = 0
            total_history = 0

            # If external telemetry items provided (e.g. test invocation), process them directly
            if telemetry_items is not None:
                results = await self.ingest_telemetry_batch(telemetry_items, source_system)
                total_extracted = len(telemetry_items)
                total_persisted = results["persisted"]
                total_updated = results["updated"]
                total_unchanged = results["unchanged"]
                total_history = results["history_written"]
            else:
                # Load baseline verified data files
                intune_file = os.path.join(PROJECT_ROOT, "data", "intune_ops_analytics.json")
                sw_file = os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json")

                if os.path.exists(sw_file) and source_system in ("ALL", "SOLARWINDS"):
                    with open(sw_file, "r", encoding="utf-8") as f:
                        sw_data = json.load(f)
                    nodes = sw_data.get("nodes", [])
                    sw_items = []
                    for n in nodes:
                        sw_items.append({
                            "external_id": f"SW-NODE-{n.get('NodeID')}",
                            "name": n.get("Caption", f"Node-{n.get('NodeID')}"),
                            "ci_type": "Server",
                            "status": "Up" if n.get("Status") == 1 else ("Warning" if n.get("Status") == 3 else "Down"),
                            "health_tier": "High" if n.get("Status") == 1 else "Medium",
                            "ip_address": n.get("IPAddress"),
                            "vendor": n.get("Vendor", "Other"),
                            "model": n.get("MachineType"),
                            "operating_system": n.get("MachineType"),
                            "cpu_load": n.get("CPULoad"),
                            "ram_used": n.get("PercentMemoryUsed"),
                            "latency_ms": n.get("AvgResponseTime"),
                            "attributes": n,
                        })
                    res = await self.ingest_telemetry_batch(sw_items, "SOLARWINDS")
                    total_extracted += len(sw_items)
                    total_persisted += res["persisted"]
                    total_updated += res["updated"]
                    total_unchanged += res["unchanged"]
                    total_history += res["history_written"]

            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            sync_run.status = "SUCCESS"
            sync_run.items_extracted = total_extracted
            sync_run.items_persisted = total_persisted
            sync_run.records_updated = total_updated
            sync_run.records_unchanged = total_unchanged
            sync_run.records_processed = total_extracted
            sync_run.duration_ms = duration_ms
            sync_run.completed_at = completed_at
            await self.session.commit()

            set_last_sync_timestamp(completed_at)

            run_dict = {
                "id": str(run_id),
                "status": "SUCCESS",
                "items_extracted": total_extracted,
                "items_persisted": total_persisted,
                "items_updated": total_updated,
                "history_written": total_history,
                "duration_ms": duration_ms,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }
            logger.info("Sync execution %s completed successfully in %d ms.", run_id, duration_ms)
            return {"status": "SUCCESS", "run": run_dict}

        except Exception as exc:
            await self.session.rollback()
            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            # Record failed sync run
            fail_run = SyncRun(
                id=run_id,
                source_system=source_system.upper(),
                status="FAILED",
                items_extracted=0,
                items_persisted=0,
                records_updated=0,
                records_unchanged=0,
                records_processed=0,
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=completed_at,
            )
            self.session.add(fail_run)

            # Record error diagnostic
            err_log = SyncErrorLog(
                id=uuid.uuid4(),
                sync_run_id=run_id,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                stack_trace=traceback.format_exc(),
                context_data={"source_system": source_system},
                occurred_at=completed_at,
            )
            self.session.add(err_log)
            await self.session.commit()

            run_dict = {
                "id": str(run_id),
                "status": "FAILED",
                "items_extracted": 0,
                "items_persisted": 0,
                "items_updated": 0,
                "duration_ms": duration_ms,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }
            logger.error("Sync execution %s failed: %s", run_id, exc)
            return {"status": "FAILED", "error": str(exc), "run": run_dict}

        finally:
            await self._release_advisory_lock()
