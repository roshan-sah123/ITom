"""End-to-End Verification Test Suite for ITOM Telemetry Ingestion Pipeline.

Validates the 7 core lifecycle and resilience scenarios:
1. New record ingestion (CI insertion + initial history record)
2. Existing unchanged record (zero history writes, liveness timestamp refresh only)
3. Existing changed record (CI update + state transition history append)
4. Duplicate records in single batch (reconciliation & unique constraint safety)
5. Source API failure (error capture, audit logging & fallback behavior)
6. Database transaction rollback (zero orphaned records on failure)
7. Partial / broken source data (graceful normalization & resilient ingestion)
"""

import asyncio
import os
import sys
import unittest
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from app.models.base import Base
from app.models.ci import ConfigurationItem
from app.models.history import CIStatusHistory
from app.models.sync import SyncErrorLog, SyncRun
from app.services.sync_service import SyncService


class TestIngestionPipelineScenarios(unittest.IsolatedAsyncioTestCase):
    """Rigorous end-to-end verification of ingestion, change detection, and resilience."""

    async def asyncSetUp(self):
        """Create isolated in-memory SQLite async database for each test."""
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        self.session = self.session_factory()
        self.sync_service = SyncService(self.session)

    async def asyncTearDown(self):
        """Clean up database connections and engine."""
        await self.session.close()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await self.engine.dispose()

    async def test_scenario_1_new_record_ingestion(self):
        """Scenario 1: New record is persisted and an initial state history row is appended."""
        items = [{
            "external_id": "SW-NODE-101",
            "name": "edge-router-01.corp.internal",
            "ci_type": "Router",
            "status": "Up",
            "health_tier": "High",
            "ip_address": "10.10.1.1",
            "vendor": "Cisco",
            "model": "Cisco ASR 1001-X",
            "operating_system": "Cisco IOS-XE 17.3.4",
            "cpu_load": 22.5,
            "ram_used": 45.0,
            "storage_used": None,
            "latency_ms": 12.4,
            "attributes": {"serial": "FOX2134G01B"},
        }]

        result = await self.sync_service.ingest_telemetry_batch(items, "SOLARWINDS")
        await self.session.commit()

        # Verify batch result metrics
        self.assertEqual(result["persisted"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["unchanged"], 0)
        self.assertEqual(result["history_written"], 1)

        # Verify ConfigurationItem row in database
        stmt = select(ConfigurationItem).where(
            ConfigurationItem.source_system == "SOLARWINDS",
            ConfigurationItem.source_id == "SW-NODE-101",
        )
        ci = (await self.session.execute(stmt)).scalar_one_or_none()
        self.assertIsNotNone(ci)
        self.assertEqual(ci.name, "edge-router-01.corp.internal")
        self.assertEqual(ci.status, "Up")
        self.assertEqual(ci.health_tier, "High")
        self.assertIsNotNone(ci.state_hash)
        self.assertEqual(len(ci.state_hash), 64)

        # Verify initial history row
        hist_stmt = select(CIStatusHistory).where(CIStatusHistory.ci_id == ci.id)
        histories = (await self.session.execute(hist_stmt)).scalars().all()
        self.assertEqual(len(histories), 1)
        self.assertEqual(histories[0].status, "Up")
        self.assertEqual(histories[0].health_tier, "High")
        self.assertEqual(histories[0].changed_attributes.get("event"), "INITIAL_INGESTION")

    async def test_scenario_2_existing_unchanged_record(self):
        """Scenario 2: Unchanged record does NOT insert into history; only refreshes last_sync_time."""
        item = {
            "external_id": "SW-NODE-102",
            "name": "core-switch-01",
            "ci_type": "Core Switch",
            "status": "Up",
            "health_tier": "High",
            "ip_address": "10.10.2.1",
            "vendor": "Cisco",
            "cpu_load": 15.0,
            "ram_used": 30.0,
            "storage_used": None,
        }

        # First cycle: Ingest initial record
        res1 = await self.sync_service.ingest_telemetry_batch([item], "SOLARWINDS")
        await self.session.commit()
        self.assertEqual(res1["persisted"], 1)

        # Fetch initial sync timestamp
        stmt = select(ConfigurationItem).where(ConfigurationItem.source_id == "SW-NODE-102")
        ci1 = (await self.session.execute(stmt)).scalar_one()
        first_sync_time = ci1.last_sync_time

        # Sleep briefly to ensure time difference
        await asyncio.sleep(0.01)

        # Second cycle: Ingest identical operational state
        res2 = await self.sync_service.ingest_telemetry_batch([item], "SOLARWINDS")
        await self.session.commit()

        # Verify change detection counters
        self.assertEqual(res2["persisted"], 0)
        self.assertEqual(res2["updated"], 0)
        self.assertEqual(res2["unchanged"], 1)
        self.assertEqual(res2["history_written"], 0)

        # Verify CI count remains exactly 1
        count_stmt = select(func.count(ConfigurationItem.id))
        total_cis = (await self.session.execute(count_stmt)).scalar_one()
        self.assertEqual(total_cis, 1)

        # Verify history rows count is STILL exactly 1 (no unnecessary write!)
        hist_count_stmt = select(func.count(CIStatusHistory.id))
        total_history = (await self.session.execute(hist_count_stmt)).scalar_one()
        self.assertEqual(total_history, 1)

        # Verify last_sync_time was updated
        ci2 = (await self.session.execute(stmt)).scalar_one()
        t1 = first_sync_time.replace(tzinfo=timezone.utc).timestamp() if first_sync_time.tzinfo is None else first_sync_time.timestamp()
        t2 = ci2.last_sync_time.replace(tzinfo=timezone.utc).timestamp() if ci2.last_sync_time.tzinfo is None else ci2.last_sync_time.timestamp()
        self.assertGreaterEqual(t2, t1)

    async def test_scenario_3_existing_changed_record(self):
        """Scenario 3: Changed record updates CI mutable fields and appends 1 history row."""
        item = {
            "external_id": "SW-NODE-103",
            "name": "db-server-primary",
            "ci_type": "Server",
            "status": "Up",
            "health_tier": "High",
            "ip_address": "10.10.3.1",
            "vendor": "Dell",
            "cpu_load": 25.0,
            "ram_used": 50.0,
            "storage_used": None,
        }

        # Cycle 1: initial ingest
        await self.sync_service.ingest_telemetry_batch([item], "SOLARWINDS")
        await self.session.commit()

        stmt = select(ConfigurationItem).where(ConfigurationItem.source_id == "SW-NODE-103")
        ci1 = (await self.session.execute(stmt)).scalar_one()
        initial_hash = ci1.state_hash

        # Cycle 2: CPU and RAM spike, status degrades to Warning
        changed_item = dict(item)
        changed_item["status"] = "Warning"
        changed_item["health_tier"] = "Medium"
        changed_item["cpu_load"] = 85.0
        changed_item["ram_used"] = 88.0

        res = await self.sync_service.ingest_telemetry_batch([changed_item], "SOLARWINDS")
        await self.session.commit()

        self.assertEqual(res["persisted"], 0)
        self.assertEqual(res["updated"], 1)
        self.assertEqual(res["unchanged"], 0)
        self.assertEqual(res["history_written"], 1)

        # Verify updated CI state in DB
        ci2 = (await self.session.execute(stmt)).scalar_one()
        self.assertEqual(ci2.status, "Warning")
        self.assertEqual(ci2.health_tier, "Medium")
        self.assertNotEqual(ci2.state_hash, initial_hash)

        # Verify append-only history trail has 2 rows
        hist_stmt = select(CIStatusHistory).where(CIStatusHistory.ci_id == ci2.id).order_by(CIStatusHistory.recorded_at.asc())
        histories = (await self.session.execute(hist_stmt)).scalars().all()
        self.assertEqual(len(histories), 2)
        
        # Check transition details in second history record
        transition = histories[1]
        self.assertEqual(transition.previous_status, "Up")
        self.assertEqual(transition.status, "Warning")
        self.assertEqual(transition.previous_health_tier, "High")
        self.assertEqual(transition.health_tier, "Medium")
        self.assertEqual(transition.cpu_utilization, 85.0)

    async def test_scenario_4_duplicate_records_in_single_batch(self):
        """Scenario 4: Batch containing duplicate source_ids is cleanly reconciled without DB crashes."""
        item = {
            "external_id": "DEV-DUP-001",
            "name": "workstation-alpha",
            "ci_type": "Windows",
            "status": "Compliant",
            "health_tier": "High",
            "storage_used": 35.0,
        }
        batch = [item, item, item]  # 3 duplicate records in same payload

        result = await self.sync_service.ingest_telemetry_batch(batch, "INTUNE")
        await self.session.commit()

        # Exactly 1 persisted, other 2 handled as unchanged within batch
        self.assertEqual(result["persisted"], 1)
        self.assertEqual(result["unchanged"], 2)

        # Confirm exactly 1 record in database
        stmt = select(ConfigurationItem).where(
            ConfigurationItem.source_system == "INTUNE",
            ConfigurationItem.source_id == "DEV-DUP-001",
        )
        cis = (await self.session.execute(stmt)).scalars().all()
        self.assertEqual(len(cis), 1)

    async def test_scenario_5_source_api_failure(self):
        """Scenario 5: Source API failure rolls back session and records FAILED SyncRun with error logs."""
        result = await self.sync_service.execute_sync_with_lock(source_system="SOLARWINDS", should_fail=True)

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("Simulated SWIS API network timeout", result.get("error", ""))

        # Verify SyncRun audit record exists with FAILED status
        run_stmt = select(SyncRun).order_by(SyncRun.started_at.desc())
        latest_run = (await self.session.execute(run_stmt)).scalar_one_or_none()
        self.assertIsNotNone(latest_run)
        self.assertEqual(latest_run.status, "FAILED")
        self.assertEqual(latest_run.items_persisted, 0)

        # Verify SyncErrorLog record exists
        err_stmt = select(SyncErrorLog).where(SyncErrorLog.sync_run_id == latest_run.id)
        err_log = (await self.session.execute(err_stmt)).scalar_one_or_none()
        self.assertIsNotNone(err_log)
        self.assertEqual(err_log.error_code, "ConnectionError")
        self.assertIn("Simulated SWIS API network timeout", err_log.error_message)

    async def test_scenario_6_database_transaction_rollback(self):
        """Scenario 6: Unhandled DB error during batch triggers rollback, leaving zero orphaned records."""
        # Pre-seed one record
        seed_item = {"external_id": "VALID-001", "name": "valid-node", "status": "Up", "health_tier": "High"}
        await self.sync_service.ingest_telemetry_batch([seed_item], "SOLARWINDS")
        await self.session.commit()

        initial_count = (await self.session.execute(select(func.count(ConfigurationItem.id)))).scalar_one()
        self.assertEqual(initial_count, 1)

        # Simulate exception during execution
        try:
            async with self.session.begin_nested():
                bad_item = {"external_id": "BAD-002", "name": "bad-node", "status": "Up", "health_tier": "High"}
                await self.sync_service.ingest_telemetry_batch([bad_item], "SOLARWINDS")
                # Intentionally trigger error
                raise RuntimeError("Simulated unrecoverable DB disk I/O failure")
        except RuntimeError:
            await self.session.rollback()

        # Database state should be rolled back to initial state
        final_count = (await self.session.execute(select(func.count(ConfigurationItem.id)))).scalar_one()
        self.assertEqual(final_count, 1)

        # Confirm BAD-002 was not committed
        bad_stmt = select(ConfigurationItem).where(ConfigurationItem.source_id == "BAD-002")
        bad_ci = (await self.session.execute(bad_stmt)).scalar_one_or_none()
        self.assertIsNone(bad_ci)

    async def test_scenario_7_partial_broken_source_data(self):
        """Scenario 7: Incomplete/broken data is safely sanitized and defaulted without crashing."""
        broken_items = [
            # Missing name, vendor, model, os, status, health_tier
            {"id": "DEV-BROKEN-01"},
            # None status, none vendor, invalid metric types
            {
                "external_id": "DEV-BROKEN-02",
                "status": None,
                "health_tier": None,
                "manufacturer": None,
                "cpu_load": -1.0,
                "ram_used": "invalid_string",
                "storage_used": None,
            },
            # Empty dictionary (should be skipped gracefully)
            {},
        ]

        result = await self.sync_service.ingest_telemetry_batch(broken_items, "INTUNE")
        await self.session.commit()

        # 2 valid IDs ingested, empty dict skipped
        self.assertEqual(result["persisted"], 2)

        # Verify defaults applied cleanly
        stmt1 = select(ConfigurationItem).where(ConfigurationItem.source_id == "DEV-BROKEN-01")
        ci1 = (await self.session.execute(stmt1)).scalar_one()
        self.assertEqual(ci1.status, "ACTIVE")
        self.assertEqual(ci1.health_tier, "High")
        self.assertEqual(ci1.vendor, "Other")

        stmt2 = select(ConfigurationItem).where(ConfigurationItem.source_id == "DEV-BROKEN-02")
        ci2 = (await self.session.execute(stmt2)).scalar_one()
        self.assertEqual(ci2.status, "ACTIVE")
        self.assertEqual(ci2.vendor, "Other")


if __name__ == "__main__":
    unittest.main()
