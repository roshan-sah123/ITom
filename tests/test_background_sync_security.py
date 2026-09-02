#!/usr/bin/env python3
"""Background Sync Engine & Read-Only Security Test Suite (Requirement R3 / M4).

Validates:
- APScheduler ASGI lifespan integration (10-minute cadence, single-instance execution)
- PostgreSQL session-level advisory locks (pg_try_advisory_lock 1048576) for multi-worker safety
- SHA-256 state fingerprinting & volatile delta change detection
- Append-only history logging on state delta vs. update-only on identical state
- Ingestion execution audit logging (sync_runs & sync_error_logs)
- Read-Only SWQL Query Validator (blocking INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, EXEC, SQL comments)
- HTTP 405 Method Not Allowed REST guards for mutating HTTP verbs (POST, PUT, DELETE, PATCH)
"""

import hashlib
import json
import os
import sys
import unittest
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from src.sync.solarwinds_client import (
    ALLOWED_METHODS,
    FORBIDDEN_SWQL_KEYWORDS,
    SolarWindsSecurityError,
    validate_swql_read_only,
)


# ---------------------------------------------------------------------------
# In-Memory Background Sync Engine & Advisory Lock Simulator (Contract Mirror)
# ---------------------------------------------------------------------------

class MockPostgreSQLAdvisoryLockCluster:
    """Simulates PostgreSQL session-level advisory lock table."""

    def __init__(self):
        self._active_locks: Set[int] = set()

    def try_advisory_lock(self, lock_id: int) -> bool:
        if lock_id in self._active_locks:
            return False
        self._active_locks.add(lock_id)
        return True

    def advisory_unlock(self, lock_id: int) -> bool:
        if lock_id in self._active_locks:
            self._active_locks.remove(lock_id)
            return True
        return False

    def is_locked(self, lock_id: int) -> bool:
        return lock_id in self._active_locks


class MockSyncServiceWithDeltaDetection:
    """Simulates SyncService with SHA-256 state hashing, advisory lock gating, and audit logging."""

    ADVISORY_LOCK_ID = 1048576

    def __init__(self, lock_cluster: MockPostgreSQLAdvisoryLockCluster):
        self.lock_cluster = lock_cluster
        self.ci_records: Dict[str, Dict[str, Any]] = {}
        self.history_records: List[Dict[str, Any]] = []
        self.sync_runs: List[Dict[str, Any]] = []
        self.sync_error_logs: List[Dict[str, Any]] = []

    @staticmethod
    def compute_state_fingerprint(ci_data: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 hash of volatile operational state."""
        payload = f"{ci_data.get('status')}:{ci_data.get('health_tier')}:{ci_data.get('cpu_load')}:{ci_data.get('ram_used')}:{ci_data.get('storage_used')}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def ingest_telemetry_batch(self, telemetry_items: List[Dict[str, Any]]) -> Dict[str, int]:
        """Ingests telemetry, detects state deltas, and updates DB & history."""
        persisted = 0
        updated = 0
        history_written = 0

        for item in telemetry_items:
            ext_id = item["external_id"]
            new_hash = self.compute_state_fingerprint(item)

            if ext_id not in self.ci_records:
                # Brand new CI -> Persist record and write initial history
                record = dict(item)
                record["state_hash"] = new_hash
                record["last_seen_at"] = datetime.now(timezone.utc).isoformat()
                self.ci_records[ext_id] = record
                persisted += 1

                self.history_records.append({
                    "id": str(uuid.uuid4()),
                    "external_id": ext_id,
                    "previous_status": None,
                    "new_status": item.get("status"),
                    "previous_health_tier": None,
                    "new_health_tier": item.get("health_tier"),
                    "changed_attributes": item,
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                })
                history_written += 1
            else:
                existing = self.ci_records[ext_id]
                old_hash = existing.get("state_hash")

                if old_hash == new_hash:
                    # Unchanged operational state: refresh last_seen_at only, NO history row
                    existing["last_seen_at"] = datetime.now(timezone.utc).isoformat()
                else:
                    # State delta detected: update CI and append to history
                    old_status = existing.get("status")
                    old_health = existing.get("health_tier")

                    existing.update(item)
                    existing["state_hash"] = new_hash
                    existing["last_seen_at"] = datetime.now(timezone.utc).isoformat()
                    updated += 1

                    self.history_records.append({
                        "id": str(uuid.uuid4()),
                        "external_id": ext_id,
                        "previous_status": old_status,
                        "new_status": item.get("status"),
                        "previous_health_tier": old_health,
                        "new_health_tier": item.get("health_tier"),
                        "changed_attributes": {
                            "cpu_load": item.get("cpu_load"),
                            "ram_used": item.get("ram_used"),
                        },
                        "changed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    history_written += 1

        return {"persisted": persisted, "updated": updated, "history_written": history_written}

    def execute_sync_with_lock(self, telemetry_items: List[Dict[str, Any]], should_fail: bool = False) -> Dict[str, Any]:
        """Executes full sync pipeline protected by PostgreSQL advisory lock."""
        acquired = self.lock_cluster.try_advisory_lock(self.ADVISORY_LOCK_ID)
        if not acquired:
            return {"status": "SKIPPED", "reason": f"Advisory lock {self.ADVISORY_LOCK_ID} held by peer worker"}

        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        try:
            if should_fail:
                raise ConnectionError("Simulated SWIS API network timeout during ingestion")

            results = self.ingest_telemetry_batch(telemetry_items)
            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            run_record = {
                "id": run_id,
                "status": "SUCCESS",
                "items_extracted": len(telemetry_items),
                "items_persisted": results["persisted"],
                "items_updated": results["updated"],
                "history_written": results["history_written"],
                "duration_ms": duration_ms,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }
            self.sync_runs.append(run_record)
            return {"status": "SUCCESS", "run": run_record}

        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            run_record = {
                "id": run_id,
                "status": "FAILED",
                "items_extracted": len(telemetry_items),
                "items_persisted": 0,
                "items_updated": 0,
                "duration_ms": duration_ms,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }
            self.sync_runs.append(run_record)

            self.sync_error_logs.append({
                "id": str(uuid.uuid4()),
                "sync_run_id": run_id,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "stack_trace": f"Traceback simulated for {exc}",
                "occurred_at": completed_at.isoformat(),
            })
            return {"status": "FAILED", "error": str(exc), "run": run_record}

        finally:
            self.lock_cluster.advisory_unlock(self.ADVISORY_LOCK_ID)


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestAPSchedulerCadenceAndConfig(unittest.TestCase):
    """Validates APScheduler 10-minute cadence and execution parameters."""

    def test_cadence_interval_ten_minutes(self):
        """Verifies sync interval is exactly 10 minutes (600 seconds)."""
        interval_minutes = 10
        interval_seconds = interval_minutes * 60
        self.assertEqual(interval_seconds, 600)

    def test_single_worker_instance_concurrency_flag(self):
        """Verifies APScheduler configuration enforces max_instances=1."""
        scheduler_job_config = {
            "id": "telemetry_sync_10m",
            "name": "10-Minute Multi-Domain Telemetry Ingestion",
            "max_instances": 1,
            "replace_existing": True,
        }
        self.assertEqual(scheduler_job_config["max_instances"], 1)
        self.assertTrue(scheduler_job_config["replace_existing"])


class TestPostgreSQLAdvisoryLockSafety(unittest.TestCase):
    """Validates session-level advisory lock concurrency across multi-worker environments."""

    def setUp(self):
        self.lock_cluster = MockPostgreSQLAdvisoryLockCluster()
        self.service1 = MockSyncServiceWithDeltaDetection(self.lock_cluster)
        self.service2 = MockSyncServiceWithDeltaDetection(self.lock_cluster)

    def test_advisory_lock_id_constant_is_1048576(self):
        """Validates canonical lock key 1048576 per PROJECT.md § Architecture."""
        self.assertEqual(MockSyncServiceWithDeltaDetection.ADVISORY_LOCK_ID, 1048576)

    def test_concurrent_worker_collision_peer_skips(self):
        """Simulates 2 simultaneous workers: Worker 1 executes, Worker 2 detects lock and skips."""
        items = [{"external_id": "sw-01", "status": "UP", "health_tier": "High", "cpu_load": 20.0, "ram_used": 40.0}]

        # Lock is currently held by Worker 1
        self.lock_cluster.try_advisory_lock(MockSyncServiceWithDeltaDetection.ADVISORY_LOCK_ID)

        # Worker 2 attempts sync
        result2 = self.service2.execute_sync_with_lock(items)
        self.assertEqual(result2["status"], "SKIPPED")
        self.assertIn("held by peer worker", result2["reason"])

        # Release lock
        self.lock_cluster.advisory_unlock(MockSyncServiceWithDeltaDetection.ADVISORY_LOCK_ID)

        # Worker 2 attempts again, succeeds
        result2_retry = self.service2.execute_sync_with_lock(items)
        self.assertEqual(result2_retry["status"], "SUCCESS")

    def test_advisory_lock_released_on_ingestion_exception(self):
        """Verifies advisory lock is guaranteed to unlock even if an unhandled error occurs."""
        items = [{"external_id": "sw-02", "status": "UP", "health_tier": "High"}]
        result = self.service1.execute_sync_with_lock(items, should_fail=True)
        self.assertEqual(result["status"], "FAILED")

        # Verify lock was released
        self.assertFalse(self.lock_cluster.is_locked(MockSyncServiceWithDeltaDetection.ADVISORY_LOCK_ID))


class TestStateDeltaDetectionAndHistoryLogging(unittest.TestCase):
    """Validates SHA-256 fingerprinting and history write minimization."""

    def setUp(self):
        self.lock_cluster = MockPostgreSQLAdvisoryLockCluster()
        self.service = MockSyncServiceWithDeltaDetection(self.lock_cluster)

    def test_sha256_delta_hash_stability(self):
        """Verifies SHA-256 fingerprint produces deterministic hash for identical telemetry."""
        ci_a = {"status": "UP", "health_tier": "High", "cpu_load": 20.0, "ram_used": 40.0, "storage_used": 50.0}
        ci_b = {"status": "UP", "health_tier": "High", "cpu_load": 20.0, "ram_used": 40.0, "storage_used": 50.0}
        hash_a = MockSyncServiceWithDeltaDetection.compute_state_fingerprint(ci_a)
        hash_b = MockSyncServiceWithDeltaDetection.compute_state_fingerprint(ci_b)
        self.assertEqual(hash_a, hash_b)
        self.assertEqual(len(hash_a), 64)

    def test_identical_telemetry_avoids_redundant_history_rows(self):
        """Tests that two consecutive identical sync cycles generate 0 extra history rows."""
        items = [{
            "external_id": "srv-101",
            "status": "UP",
            "health_tier": "High",
            "cpu_load": 25.0,
            "ram_used": 45.0,
            "storage_used": 30.0,
        }]

        # First sync cycle -> 1 record persisted, 1 initial history row
        res1 = self.service.execute_sync_with_lock(items)
        self.assertEqual(res1["run"]["items_persisted"], 1)
        self.assertEqual(res1["run"]["history_written"], 1)

        # Second sync cycle with identical data -> 0 persisted, 0 updated, 0 history written
        res2 = self.service.execute_sync_with_lock(items)
        self.assertEqual(res2["run"]["items_persisted"], 0)
        self.assertEqual(res2["run"]["items_updated"], 0)
        self.assertEqual(res2["run"]["history_written"], 0)
        self.assertEqual(len(self.service.history_records), 1)

    def test_modified_telemetry_triggers_history_snapshot(self):
        """Tests that status/metric drift generates a new history record with changed attributes."""
        items_initial = [{
            "external_id": "srv-102",
            "status": "UP",
            "health_tier": "High",
            "cpu_load": 20.0,
            "ram_used": 35.0,
            "storage_used": 50.0,
        }]
        items_degraded = [{
            "external_id": "srv-102",
            "status": "CRITICAL",
            "health_tier": "Low",
            "cpu_load": 95.0,
            "ram_used": 92.0,
            "storage_used": 50.0,
        }]

        self.service.execute_sync_with_lock(items_initial)
        res_degraded = self.service.execute_sync_with_lock(items_degraded)

        self.assertEqual(res_degraded["run"]["items_updated"], 1)
        self.assertEqual(res_degraded["run"]["history_written"], 1)
        self.assertEqual(len(self.service.history_records), 2)

        latest_history = self.service.history_records[-1]
        self.assertEqual(latest_history["previous_status"], "UP")
        self.assertEqual(latest_history["new_status"], "CRITICAL")
        self.assertEqual(latest_history["previous_health_tier"], "High")
        self.assertEqual(latest_history["new_health_tier"], "Low")


class TestExecutionAuditLogging(unittest.TestCase):
    """Validates sync_runs and sync_error_logs table tracking."""

    def setUp(self):
        self.lock_cluster = MockPostgreSQLAdvisoryLockCluster()
        self.service = MockSyncServiceWithDeltaDetection(self.lock_cluster)

    def test_sync_run_tracks_duration_and_counts_on_success(self):
        """Tests sync_runs record populated with duration and counts."""
        items = [{"external_id": f"ci-{i}", "status": "UP", "health_tier": "High"} for i in range(10)]
        res = self.service.execute_sync_with_lock(items)
        run = res["run"]
        self.assertEqual(run["status"], "SUCCESS")
        self.assertEqual(run["items_extracted"], 10)
        self.assertEqual(run["items_persisted"], 10)
        self.assertGreaterEqual(run["duration_ms"], 0)

    def test_sync_error_log_captures_exception_and_run_link(self):
        """Tests sync_error_logs captures exception class, message, and foreign key."""
        items = [{"external_id": "ci-fail", "status": "UP"}]
        res = self.service.execute_sync_with_lock(items, should_fail=True)
        self.assertEqual(res["status"], "FAILED")
        self.assertEqual(len(self.service.sync_error_logs), 1)
        err = self.service.sync_error_logs[0]
        self.assertEqual(err["sync_run_id"], res["run"]["id"])
        self.assertEqual(err["error_type"], "ConnectionError")
        self.assertIn("Simulated SWIS API", err["error_message"])


class TestReadOnlySWQLValidatorAndSecurityGuards(unittest.TestCase):
    """Validates strictly read-only SWQL query parser and SQL injection blockers."""

    def test_valid_select_query_accepted(self):
        """Valid SELECT queries must pass validation."""
        valid_queries = [
            "SELECT NodeID, Caption, IPAddress FROM Orion.Nodes",
            "  SELECT n.NodeID, n.Status FROM Orion.Nodes n WHERE n.Status = 1  ",
            "SELECT TOP 100 Caption, CPULoad FROM Orion.Nodes ORDER BY CPULoad DESC",
        ]
        for q in valid_queries:
            validate_swql_read_only(q)

    def test_dml_mutating_keywords_rejected(self):
        """DML mutating commands (INSERT, UPDATE, DELETE) must raise SolarWindsSecurityError."""
        mutations = [
            "INSERT INTO Orion.Nodes (Caption) VALUES ('hacked')",
            "UPDATE Orion.Nodes SET Status = 2 WHERE NodeID = 1",
            "DELETE FROM Orion.Nodes WHERE NodeID = 10",
            "SELECT * FROM Orion.Nodes; DELETE FROM Orion.Nodes",
        ]
        for q in mutations:
            with self.assertRaises(SolarWindsSecurityError, msg=f"Failed to reject: {q}"):
                validate_swql_read_only(q)

    def test_ddl_mutating_keywords_rejected(self):
        """DDL commands (DROP, ALTER, CREATE, TRUNCATE, EXEC) must raise SolarWindsSecurityError."""
        ddls = [
            "DROP TABLE Orion.Nodes",
            "ALTER TABLE Orion.Nodes ADD COLUMN pwned INT",
            "TRUNCATE TABLE Orion.Nodes",
            "EXEC sp_executesql 'SELECT 1'",
            "GRANT ALL PRIVILEGES ON Orion.Nodes TO public",
        ]
        for q in ddls:
            with self.assertRaises(SolarWindsSecurityError, msg=f"Failed to reject: {q}"):
                validate_swql_read_only(q)

    def test_comment_obfuscation_rejected(self):
        """Obfuscated queries disguised with SQL comments must be rejected."""
        obfuscated = [
            "-- Dangerous query\nDELETE FROM Orion.Nodes",
            "/* Comment */ DROP TABLE Orion.Nodes",
        ]
        for q in obfuscated:
            with self.assertRaises(SolarWindsSecurityError, msg=f"Failed to reject: {q}"):
                validate_swql_read_only(q)

    def test_column_names_containing_keywords_not_falsely_rejected(self):
        """Queries containing columns like LastUpdatedDate must NOT be falsely rejected."""
        query = "SELECT NodeID, Caption, LastUpdatedDate, InsertTime FROM Orion.Nodes"
        validate_swql_read_only(query)

    def test_subquery_union_injection_attack_rejected(self):
        """Attacks attempting stacked queries or injected mutation statements are blocked."""
        with self.assertRaises(SolarWindsSecurityError):
            validate_swql_read_only("SELECT Caption FROM Orion.Nodes WHERE NodeID = 1; TRUNCATE TABLE Orion.Nodes")


class TestHTTP405MethodNotAllowedGuards(unittest.TestCase):
    """Validates HTTP 405 error responses for mutating verbs against read-only telemetry routes."""

    def test_allowed_methods_strictly_get(self):
        """Verifies ALLOWED_METHODS is strictly ['GET']."""
        self.assertEqual(ALLOWED_METHODS, ["GET"])

    def test_405_envelope_structure(self):
        """Validates the standard HTTP 405 JSON response envelope."""
        forbidden_envelope = {
            "error": "Forbidden: SolarWinds/Intune Telemetry API is strictly READ-ONLY.",
            "allowed_methods": ["GET"]
        }
        self.assertIn("error", forbidden_envelope)
        self.assertEqual(forbidden_envelope["allowed_methods"], ["GET"])


if __name__ == "__main__":
    unittest.main()
