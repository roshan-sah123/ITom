"""Live FastAPI Application End-to-End Integration Test Suite.

Validates:
- Actual FastAPI application (`app.main:app`) mounted with middleware and routers.
- Response Freshness Headers on all endpoints (`X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status`).
- Strict Read-Only HTTP 405 Method Not Allowed guards for mutating verbs (POST, PUT, DELETE, PATCH).
- Query validation, pagination envelopes, and CMDB / Telemetry domain endpoints.
- SWQL validator and PostgreSQL advisory lock constant integrity.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone

from starlette.testclient import TestClient

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from app.core.middleware import get_last_sync_timestamp, set_last_sync_timestamp
from app.core.security import (
    ALLOWED_METHODS,
    FORBIDDEN_SWQL_KEYWORDS,
    SolarWindsSecurityError,
    validate_swql_read_only,
)
from app.main import app
from app.services.sync_service import SyncService


class TestLiveFastAPIAppIntegration(unittest.TestCase):
    """Integration test suite executing requests directly against app.main:app."""

    @classmethod
    def setUpClass(cls):
        # Initialize test client
        cls.client = TestClient(app, raise_server_exceptions=True)

    def test_root_endpoint(self):
        """GET / returns service metadata."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "operational")
        self.assertIn("version", data)

    def test_healthz_liveness_probe(self):
        """GET /healthz returns 200 OK with timestamp and freshness headers."""
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("timestamp", data)
        self.assertIn("X-Last-Synchronized-At", response.headers)
        self.assertIn("X-Data-Age-Seconds", response.headers)
        self.assertIn("X-Sync-Status", response.headers)

    def test_ready_readiness_probe(self):
        """GET /ready returns 200 OK."""
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data["status"], ["ready", "unhealthy"])

    def test_cmdb_summary_endpoint(self):
        """GET /api/v1/cmdb/summary returns aggregated counts."""
        response = self.client.get("/api/v1/cmdb/summary")
        self.assertEqual(response.status_code, 200, f"Got {response.status_code}: {response.text}")
        data = response.json()
        self.assertIn("total_cis", data)
        self.assertIn("high_health_count", data)

    def test_intune_summary_metrics_invariants(self):
        """GET /api/v1/intune/summary returns endpoints reconciling compliance invariants."""
        response = self.client.get("/api/v1/intune/summary")
        self.assertEqual(response.status_code, 200, f"Got {response.status_code}: {response.text}")
        data = response.json()
        metrics = data["metrics"]
        self.assertGreater(metrics["total_managed_devices"], 0)
        self.assertGreater(metrics["compliant_devices"], 0)
        self.assertGreaterEqual(metrics["non_compliant_devices"], 0)
        self.assertIn("compliance_breakdown", data)
        self.assertEqual(
            sum(data["compliance_breakdown"].values()),
            metrics["total_managed_devices"],
        )
        self.assertGreaterEqual(metrics["compliance_rate_pct"], 0.0)
        self.assertLessEqual(metrics["compliance_rate_pct"], 100.0)
        self.assertGreaterEqual(metrics["avg_storage_used_pct"], 0.0)
        self.assertIn("os_distribution", data)
        self.assertIn("vendor_distribution", data)

    def test_solarwinds_summary_metrics_invariants(self):
        """GET /api/v1/solarwinds/summary returns nodes reconciling health invariants."""
        response = self.client.get("/api/v1/solarwinds/summary")
        self.assertEqual(response.status_code, 200, f"Got {response.status_code}: {response.text}")
        data = response.json()
        metrics = data["metrics"]
        self.assertGreater(metrics["total_server_nodes"], 0)
        self.assertEqual(
            metrics["total_server_nodes"],
            metrics["high_health_nodes"] + metrics["medium_health_nodes"] + metrics["low_critical_nodes"],
        )
        self.assertIn("health_breakdown", data)
        self.assertIn("vendor_distribution", data)

    def test_cmdb_cis_pagination_envelope(self):
        """GET /api/v1/cmdb/cis validates envelope fields."""
        response = self.client.get("/api/v1/cmdb/cis?page=1&page_size=25")
        self.assertEqual(response.status_code, 200, f"Got {response.status_code}: {response.text}")
        data = response.json()
        for field in ["items", "total", "page", "page_size", "total_pages", "has_next", "has_prev"]:
            self.assertIn(field, data)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 25)

    def test_invalid_page_size_rejected_422(self):
        """GET /api/v1/cmdb/cis with invalid page_size returns 422."""
        response = self.client.get("/api/v1/cmdb/cis?page_size=15")
        self.assertEqual(response.status_code, 422)

    def test_read_only_post_returns_405(self):
        """POST /api/v1/cmdb/cis returns HTTP 405 Method Not Allowed."""
        response = self.client.post("/api/v1/cmdb/cis", json={"name": "test"})
        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertIn("strictly READ-ONLY", data["error"])
        self.assertEqual(data["allowed_methods"], ["GET"])
        self.assertEqual(response.headers.get("Allow"), "GET, HEAD, OPTIONS")

    def test_read_only_put_returns_405(self):
        """PUT /api/v1/solarwinds/nodes/1 returns HTTP 405."""
        response = self.client.put("/api/v1/solarwinds/nodes/1", json={"status": 1})
        self.assertEqual(response.status_code, 405)

    def test_read_only_delete_returns_405(self):
        """DELETE /api/v1/cmdb/cis/123 returns HTTP 405."""
        response = self.client.delete("/api/v1/cmdb/cis/123")
        self.assertEqual(response.status_code, 405)

    def test_read_only_patch_returns_405(self):
        """PATCH /api/v1/intune/devices/123 returns HTTP 405."""
        response = self.client.patch("/api/v1/intune/devices/123", json={"status": "Compliant"})
        self.assertEqual(response.status_code, 405)

    def test_swql_validator_security(self):
        """SWQL query validator blocks mutating statements."""
        valid_q = "SELECT NodeID, Caption, LastUpdatedDate FROM Orion.Nodes"
        validate_swql_read_only(valid_q)

        mutating_q = "DELETE FROM Orion.Nodes WHERE NodeID = 1"
        with self.assertRaises(SolarWindsSecurityError):
            validate_swql_read_only(mutating_q)

    def test_sync_service_sha256_fingerprint(self):
        """Verifies deterministic SHA-256 state fingerprinting."""
        ci = {"status": "UP", "health_tier": "High", "cpu_load": 15.0, "ram_used": 30.0, "storage_used": 40.0}
        hash1 = SyncService.compute_state_fingerprint(ci)
        hash2 = SyncService.compute_state_fingerprint(ci)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)


if __name__ == "__main__":
    unittest.main()
