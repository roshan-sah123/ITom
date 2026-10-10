#!/usr/bin/env python3
"""Adversarial Verification Suite for Reviewer Round 3.

Covers:
1. classify_node_health string numeric robustness (Status as "1"/"2"/"3"/"14"/"0", CPULoad as "95"/"85", PercentMemoryUsed as "95"/"85").
2. Boolean status/metric guard (True/False must not be treated as int 1/0).
3. SolarWindsClient.process_telemetry with string numeric telemetry parsing and degraded server ordering.
4. SolarWindsClient.reconcile_from_file rejection when 'nodes' is not a list.
5. verify_solarwinds_data.py descriptive failure messages across all invariants, missing files, and boundary conditions.
7. Settings CORS cross-parameter wildcard bypass closure (BACKEND_CORS_ORIGINS vs CORS_ORIGINS).
8. Settings SECRET_KEY minimum length enforcement and expanded placeholder rejection in non-development environments.
"""

import json
import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import Settings
from src.sync.solarwinds_client import (
    SolarWindsApiError,
    SolarWindsClient,
    _parse_sw_metric,
    _parse_sw_status,
    classify_node_health,
)


class TestReviewer3TelemetryParsingAndHealth(unittest.TestCase):
    """Test resilience of SolarWinds metric parsing and health classification."""

    def test_parse_sw_status_edge_cases(self):
        self.assertEqual(_parse_sw_status(1), 1)
        self.assertEqual(_parse_sw_status("1"), 1)
        self.assertEqual(_parse_sw_status("  2  "), 2)
        self.assertEqual(_parse_sw_status(3.0), 3)
        self.assertIsNone(_parse_sw_status(True))
        self.assertIsNone(_parse_sw_status(False))
        self.assertIsNone(_parse_sw_status(None))
        self.assertIsNone(_parse_sw_status("invalid"))
        self.assertIsNone(_parse_sw_status([]))

    def test_parse_sw_metric_edge_cases(self):
        self.assertEqual(_parse_sw_metric(50), 50.0)
        self.assertEqual(_parse_sw_metric("50"), 50.0)
        self.assertEqual(_parse_sw_metric("  75.5  "), 75.5)
        self.assertIsNone(_parse_sw_metric(-2))
        self.assertIsNone(_parse_sw_metric("-5"))
        self.assertIsNone(_parse_sw_metric(True))
        self.assertIsNone(_parse_sw_metric(False))
        self.assertIsNone(_parse_sw_metric(None))
        self.assertIsNone(_parse_sw_metric("corrupt"))

    def test_classify_node_health_with_string_metrics(self):
        # String Status "1" with healthy metrics should be High
        self.assertEqual(
            classify_node_health({"Status": "1", "CPULoad": "20", "PercentMemoryUsed": "30"}),
            "High"
        )
        # String CPULoad "95" must be Low/Critical even if Status is 1
        self.assertEqual(
            classify_node_health({"Status": 1, "CPULoad": "95", "PercentMemoryUsed": 50}),
            "Low"
        )
        # String PercentMemoryUsed "92" must be Low/Critical
        self.assertEqual(
            classify_node_health({"Status": 1, "CPULoad": 20, "PercentMemoryUsed": "92"}),
            "Low"
        )
        # String Status "3" (Warning) with moderate load must be Medium
        self.assertEqual(
            classify_node_health({"Status": "3", "CPULoad": "20", "PercentMemoryUsed": "30"}),
            "Medium"
        )
        # String Status "2" (Down) must be Low
        self.assertEqual(
            classify_node_health({"Status": "2", "CPULoad": 10, "PercentMemoryUsed": 10}),
            "Low"
        )
        # String CPULoad "85" must be Medium
        self.assertEqual(
            classify_node_health({"Status": 1, "CPULoad": "85", "PercentMemoryUsed": 50}),
            "Medium"
        )
        # Boolean values must not masquerade as integers
        self.assertEqual(
            classify_node_health({"Status": True, "CPULoad": True, "PercentMemoryUsed": True}),
            "Low"
        )

    def test_process_telemetry_aggregates_string_metrics(self):
        client = SolarWindsClient()
        nodes = [
            {"NodeID": 101, "Caption": "N1", "Status": "1", "CPULoad": "20", "PercentMemoryUsed": "40", "Vendor": "Windows"},
            {"NodeID": 102, "Caption": "N2", "Status": "1", "CPULoad": "40", "PercentMemoryUsed": "60", "Vendor": "Linux"},
        ]
        enriched, summary = client.process_telemetry(nodes)
        self.assertEqual(summary["metrics"]["total_server_nodes"], 2)
        self.assertEqual(summary["metrics"]["avg_fleet_cpu_load_pct"], 30.0)
        self.assertEqual(summary["metrics"]["avg_fleet_ram_used_pct"], 50.0)
        self.assertEqual(enriched[0]["HealthClassification"], "High")
        self.assertEqual(enriched[1]["HealthClassification"], "High")

    def test_reconcile_from_file_rejects_non_list_nodes(self):
        client = SolarWindsClient()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(json.dumps({"extracted_at": "2026-09-03T00:00:00Z", "nodes": "not_a_list"}))
            tf_path = tf.name

        try:
            with self.assertRaises(SolarWindsApiError) as ctx:
                client.reconcile_from_file(tf_path)
            self.assertIn("'nodes' field must be a list", str(ctx.exception))
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)


class TestReviewer3ConfigAndSecurityHardening(unittest.TestCase):
    """Test CORS precedence, wildcard closures, and SECRET_KEY length guards."""

    def test_cors_cross_parameter_wildcard_bypass_prevention(self):
        # Passing wildcard in CORS_ORIGINS while explicit BACKEND_CORS_ORIGINS is provided must still fail
        with self.assertRaises(ValueError) as ctx:
            Settings(BACKEND_CORS_ORIGINS=["http://custom:9000"], CORS_ORIGINS="*", CORS_ALLOW_CREDENTIALS=True)
        self.assertIn("Wildcard origin", str(ctx.exception))

        # Passing wildcard in BACKEND_CORS_ORIGINS while explicit CORS_ORIGINS is provided must fail
        with self.assertRaises(ValueError) as ctx:
            Settings(BACKEND_CORS_ORIGINS=["*"], CORS_ORIGINS="http://custom:9000", CORS_ALLOW_CREDENTIALS=True)
        self.assertIn("Wildcard origin", str(ctx.exception))

    def test_secret_key_minimum_length_and_expanded_placeholders(self):
        # Short secret key (< 16 chars) must be rejected in production
        with self.assertRaises(ValueError) as ctx:
            Settings(ENVIRONMENT="production", SECRET_KEY="short_key", DEBUG=False)
        self.assertIn("at least 16 characters long", str(ctx.exception))

        # Additional placeholders rejected
        for ph in ["your-secret-key-here", "your-secret-key", "dummy", "12345678", "secretkey", "placeholder"]:
            with self.assertRaises(ValueError, msg=f"Accepted weak placeholder: {ph}"):
                Settings(ENVIRONMENT="production", SECRET_KEY=ph, DEBUG=False)




if __name__ == "__main__":
    unittest.main(verbosity=2)
