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
from app.models.compliance_cache import IntuneComplianceReasonCache
from app.models.history import CIStatusHistory
from app.models.sync import SyncErrorLog, SyncRun
from app.repositories.ci_repository import CIRepository
from app.repositories.sync_repository import SyncRepository
from app.services.remediation_cache import remediation_cache_write_lock
from app.services.seed_service import (
    classify_device_role,
    classify_node_health,
    map_node_status_string,
    normalize_intune_manufacturer,
    normalize_solarwinds_vendor,
    parse_clean_os,
)

logger = logging.getLogger("itom.sync")

def _find_project_root() -> str:
    cur = os.path.abspath(__file__)
    while cur and os.path.dirname(cur) != cur:
        cur = os.path.dirname(cur)
        if os.path.exists(os.path.join(cur, "data")):
            return cur
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PROJECT_ROOT = _find_project_root()

# In-memory concurrency fallback lock for non-Postgres engines (e.g. SQLite / in-memory tests)
_in_memory_lock = asyncio.Lock()
_in_memory_locked = False


def _safe_float(val: Any) -> Optional[float]:
    """Safely parse resource metric (CPU, RAM, latency) from numeric or string, guarding against negatives and non-numbers."""
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        return f if f >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


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
        cpu = _safe_float(ci_data.get("cpu_load"))
        ram = _safe_float(ci_data.get("ram_used"))
        storage = _safe_float(ci_data.get("storage_used"))
        payload = f"{status}:{health}:{cpu}:{ram}:{storage}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def _refresh_cached_intune_remediation_worklists(
        self, graph_client: Any
    ) -> None:
        """Refresh cached Intune reason/worklist evidence during the scheduled sync."""
        now = datetime.now(timezone.utc)
        reasons = await asyncio.to_thread(
            graph_client.get_noncompliance_reason_summaries
        )
        existing = list(
            (
                await self.session.execute(select(IntuneComplianceReasonCache))
            ).scalars().all()
        )
        cached_worklist_ids = [
            record.summary_id
            for record in existing
            if record.is_active and record.worklist_refreshed_at is not None
        ]
        # Release the read transaction before remote calls. SQLite otherwise
        # retains a transaction while waiting for Graph responses.
        await self.session.rollback()

        refreshed_worklists: Dict[str, List[Dict[str, Any]]] = {}
        for summary_id in cached_worklist_ids:
            try:
                refreshed_worklists[summary_id] = await asyncio.to_thread(
                    graph_client.get_noncompliant_devices_for_reason,
                    summary_id,
                )
            except Exception as exc:
                logger.warning(
                    "Intune remediation cache refresh skipped for %s: %s",
                    summary_id,
                    exc,
                )

        # Only one cache update may write at a time in SQLite. All Graph calls
        # above are complete before this short protected database update.
        async with remediation_cache_write_lock:
            existing = list(
                (
                    await self.session.execute(select(IntuneComplianceReasonCache))
                ).scalars().all()
            )
            by_id = {record.summary_id: record for record in existing}
            cached_worklists = [
                record
                for record in existing
                if record.is_active and record.worklist_refreshed_at is not None
            ]
            for record in existing:
                record.is_active = False

            for reason in reasons:
                summary_id = str(reason.get("id") or "")
                if not summary_id:
                    continue
                record = by_id.get(summary_id)
                if record is None:
                    record = IntuneComplianceReasonCache(
                        summary_id=summary_id,
                        setting_name=str(reason.get("setting_name") or "Unnamed setting"),
                        platform=str(reason.get("platform") or "unknown"),
                        devices=[],
                        catalog_refreshed_at=now,
                        is_active=True,
                    )
                    self.session.add(record)
                record.setting_name = str(reason.get("setting_name") or "Unnamed setting")
                record.platform = str(reason.get("platform") or "unknown")
                record.noncompliant_count = int(reason.get("noncompliant_count") or 0)
                record.error_count = int(reason.get("error_count") or 0)
                record.conflict_count = int(reason.get("conflict_count") or 0)
                record.affected_count = int(reason.get("affected_count") or 0)
                record.catalog_refreshed_at = now
                record.is_active = True

            active_ids = {str(reason.get("id") or "") for reason in reasons}
            for record in cached_worklists:
                if record.summary_id not in active_ids or record.summary_id not in refreshed_worklists:
                    continue
                record.devices = refreshed_worklists[record.summary_id]
                record.worklist_refreshed_at = now

            await self.session.flush()

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

        # Filter items with valid source_id
        valid_items: List[Dict[str, Any]] = []
        for item in telemetry_items:
            source_id = str(item.get("external_id") or item.get("source_id") or item.get("id") or "")
            if source_id:
                valid_items.append(item)

        CHUNK_SIZE = 500
        for i in range(0, len(valid_items), CHUNK_SIZE):
            chunk = valid_items[i : i + CHUNK_SIZE]
            chunk_ids = [str(it.get("external_id") or it.get("source_id") or it.get("id") or "") for it in chunk]

            # Fast chunked pre-fetch of existing CIs
            existing_map: Dict[str, ConfigurationItem] = {}
            if self.session is not None and hasattr(self.session, "execute"):
                try:
                    stmt = select(ConfigurationItem).where(
                        ConfigurationItem.source_system == source_system.upper(),
                        ConfigurationItem.source_id.in_(chunk_ids),
                    )
                    res = await self.session.execute(stmt)
                    for ci in res.scalars().all():
                        existing_map[ci.source_id] = ci
                except Exception as exc:
                    logger.debug("Chunk lookup fallback: %s", exc)

            for item in chunk:
                source_id = str(item.get("external_id") or item.get("source_id") or item.get("id") or "")
                new_hash = self.compute_state_fingerprint(item)
                existing = existing_map.get(source_id)
                if not existing and not existing_map:
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
                location = item.get("location")
                attrs = item.get("attributes") or {}

                cpu_load = _safe_float(item.get("cpu_load"))
                ram_used = _safe_float(item.get("ram_used"))
                storage_used = _safe_float(item.get("storage_used"))
                latency_ms = _safe_float(item.get("latency_ms"))

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
                        location=location,
                        last_sync_time=now,
                        state_hash=new_hash,
                        attributes=attrs,
                        created_at=now,
                        updated_at=now,
                    )
                    self.session.add(ci)
                    existing_map[source_id] = ci  # In-batch duplicate guard

                    hist = CIStatusHistory(
                        id=uuid.uuid4(),
                        ci_id=ci.id,
                        status=status,
                        health_tier=health,
                        previous_status=None,
                        previous_health_tier=None,
                        cpu_utilization=cpu_load,
                        memory_utilization=ram_used,
                        storage_used_pct=storage_used,
                        latency_ms=latency_ms,
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
                        existing.location = location or existing.location
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
                            cpu_utilization=cpu_load,
                            memory_utilization=ram_used,
                            storage_used_pct=storage_used,
                            latency_ms=latency_ms,
                            changed_attributes={
                                "cpu_load": cpu_load,
                                "ram_used": ram_used,
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
        # Commit the short audit write before any long source request. This
        # prevents a SQLite write transaction from blocking dashboard reads
        # while Microsoft Graph or SolarWinds is being queried.
        await self.session.commit()

        try:
            if should_fail:
                raise ConnectionError("Simulated SWIS API network timeout during ingestion")

            total_extracted = 0
            total_persisted = 0
            total_updated = 0
            total_unchanged = 0
            total_history = 0
            intune_remediation_client = None

            # If external telemetry items provided (e.g. test invocation), process them directly
            if telemetry_items is not None:
                results = await self.ingest_telemetry_batch(telemetry_items, source_system)
                total_extracted = len(telemetry_items)
                total_persisted = results["persisted"]
                total_updated = results["updated"]
                total_unchanged = results["unchanged"]
                total_history = results["history_written"]
            else:
                # Load baseline verified data files or fetch live from APIs
                intune_file = os.path.join(PROJECT_ROOT, "data", "intune_ops_analytics.json")
                sw_file = os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json")

                # 1. Ingest Microsoft Intune Telemetry (27,412 Devices)
                if source_system in ("ALL", "INTUNE"):
                    intune_devices = None
                    intune_graph_client = None
                    # Settings loads the approved .env file; os.getenv() does
                    # not see values parsed by Pydantic Settings.
                    tenant_id = settings.AZURE_TENANT_ID
                    client_id = settings.AZURE_CLIENT_ID
                    client_sec = settings.AZURE_CLIENT_SECRET
                    if tenant_id and client_id and client_sec:
                        try:
                            from src.sync.graph_client import GraphClient
                            gc = GraphClient(tenant_id=tenant_id, client_id=client_id, client_secret=client_sec)
                            intune_graph_client = gc
                            intune_devices = await asyncio.to_thread(
                                gc.fetch_managed_devices
                            )
                            logger.info("Live Graph API fetch extracted %d Intune devices.", len(intune_devices))
                        except Exception as exc:
                            logger.warning("Live Graph API fetch failed: %s; falling back to staged file", exc)

                    if intune_devices is None and os.path.exists(intune_file):
                        try:
                            with open(intune_file, "r", encoding="utf-8") as f:
                                intune_devices = json.load(f).get("devices", [])
                        except Exception as exc:
                            logger.error("Failed to read Intune file %s: %s", intune_file, exc)

                    if intune_devices:
                        intune_items = []
                        for dev in intune_devices:
                            dev_id = str(dev.get("id", ""))
                            if not dev_id:
                                continue
                            raw_comp = str(dev.get("complianceState") or "unknown").lower()
                            if raw_comp == "compliant":
                                st = "Compliant"
                                ht = "High"
                            elif raw_comp == "noncompliant":
                                st = "Noncompliant"
                                ht = "Low"
                            else:
                                st = raw_comp.capitalize()
                                ht = "Medium"

                            mfg = str(dev.get("manufacturer") or "Other")
                            tot = dev.get("totalStorageSpaceInBytes")
                            free = dev.get("freeStorageSpaceInBytes")
                            st_pct = round(((tot - free) / tot) * 100.0, 1) if tot and free and tot > 0 else None

                            intune_items.append({
                                "external_id": dev_id,
                                "name": dev.get("deviceName") or f"Device-{dev_id[:8]}",
                                "ci_type": dev.get("operatingSystem") or "Endpoint",
                                "status": st,
                                "health_tier": ht,
                                "ip_address": None,
                                "vendor": normalize_intune_manufacturer(mfg),
                                "model": dev.get("model"),
                                "serial_number": dev.get("serialNumber"),
                                "operating_system": f"{dev.get('operatingSystem', '')} {dev.get('osVersion', '')}".strip() or "Endpoint",
                                "storage_used": st_pct,
                                "attributes": dev,
                            })

                        res_intune = await self.ingest_telemetry_batch(intune_items, "INTUNE")
                        total_extracted += len(intune_items)
                        total_persisted += res_intune["persisted"]
                        total_updated += res_intune["updated"]
                        total_unchanged += res_intune["unchanged"]
                        total_history += res_intune["history_written"]
                        intune_remediation_client = intune_graph_client

                # 2. Ingest SolarWinds Server Nodes (1,572 Nodes)
                if source_system in ("ALL", "SOLARWINDS"):
                    sw_nodes = None
                    sw_host = settings.SOLARWINDS_HOST
                    sw_user = settings.SOLARWINDS_USERNAME
                    sw_pwd = settings.SOLARWINDS_PASSWORD
                    if sw_host and sw_user and sw_pwd:
                        try:
                            from src.sync.solarwinds_client import SolarWindsClient
                            sw_c = SolarWindsClient(host=sw_host, username=sw_user, password=sw_pwd)
                            sw_nodes = await asyncio.to_thread(sw_c.fetch_nodes)
                            logger.info("Live SolarWinds SWIS API fetch extracted %d nodes.", len(sw_nodes))
                        except Exception as exc:
                            logger.warning("Live SolarWinds fetch failed: %s; falling back to staged file", exc)

                    if sw_nodes is None and os.path.exists(sw_file):
                        try:
                            with open(sw_file, "r", encoding="utf-8") as f:
                                sw_nodes = json.load(f).get("nodes", [])
                        except Exception as exc:
                            logger.error("Failed to read SolarWinds file %s: %s", sw_file, exc)

                    if sw_nodes:
                        sw_items = []
                        for n in sw_nodes:
                            node_id = str(n.get("NodeID", ""))
                            if not node_id:
                                continue
                            vendor = str(n.get("Vendor", "Unknown")).strip()
                            machine_type = str(n.get("MachineType", "Unknown")).strip()
                            desc = str(n.get("NodeDescription", "")).strip()
                            status_code = n.get("Status", 0)

                            sw_items.append({
                                "external_id": f"SW-NODE-{node_id}",
                                "name": n.get("Caption", f"Node-{node_id}"),
                                "ci_type": classify_device_role(vendor, machine_type, desc),
                                "status": map_node_status_string(status_code),
                                "health_tier": classify_node_health(n),
                                "ip_address": n.get("IPAddress"),
                                "vendor": normalize_solarwinds_vendor(vendor),
                                "model": machine_type,
                                "operating_system": parse_clean_os(machine_type, desc, vendor),
                                "location": n.get("City") or n.get("ITSM_Location") or "Other",
                                "cpu_load": float(n["CPULoad"]) if n.get("CPULoad") is not None and float(n["CPULoad"]) >= 0 else None,
                                "ram_used": float(n["PercentMemoryUsed"]) if n.get("PercentMemoryUsed") is not None and float(n["PercentMemoryUsed"]) >= 0 else None,
                                "latency_ms": float(n.get("AvgResponseTime") or n.get("ResponseTime") or 0.0) if (n.get("AvgResponseTime") or n.get("ResponseTime")) is not None else None,
                                "attributes": n,
                            })

                        res_sw = await self.ingest_telemetry_batch(sw_items, "SOLARWINDS")
                        total_extracted += len(sw_items)
                        total_persisted += res_sw["persisted"]
                        total_updated += res_sw["updated"]
                        total_unchanged += res_sw["unchanged"]
                        total_history += res_sw["history_written"]

            if intune_remediation_client is not None:
                # Persist main telemetry before the optional cache refresh.
                # The main dashboard remains available even if cache refresh
                # needs more time or encounters a Graph permission issue.
                await self.session.commit()
                try:
                    await self._refresh_cached_intune_remediation_worklists(
                        intune_remediation_client
                    )
                except Exception as exc:
                    logger.warning(
                        "Intune remediation cache refresh skipped: %s",
                        exc,
                    )

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
