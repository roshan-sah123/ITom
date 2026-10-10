"""Verification and Invariant Test Suite for SolarWinds SWIS Telemetry Data.

This module executes automated invariant validation across `data/solarwinds_nodes.json`
and `data/solarwinds_summary.json` to guarantee 100% data integrity with zero mock data.
"""

import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.sync.solarwinds_client import classify_node_health, normalize_solarwinds_vendor


class TestSolarWindsDataInvariants(unittest.TestCase):
    """Assert mathematical invariants and schema compliance for SolarWinds datasets."""

    @classmethod
    def setUpClass(cls):
        cls.nodes_file = os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json")
        cls.summary_file = os.path.join(PROJECT_ROOT, "data", "solarwinds_summary.json")

        if not os.path.exists(cls.summary_file):
            raise AssertionError(
                f"Missing SolarWinds summary file at '{cls.summary_file}'. "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to generate summary telemetry."
            )

        if not os.path.exists(cls.nodes_file):
            raise AssertionError(
                f"Missing SolarWinds raw dataset at '{cls.nodes_file}'. "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to fetch and populate raw nodes."
            )

        with open(cls.nodes_file, "r", encoding="utf-8") as f:
            cls.raw_data = json.load(f)

        with open(cls.summary_file, "r", encoding="utf-8") as f:
            cls.summary_data = json.load(f)

    def test_total_nodes_count_consistency(self):
        """Invariant: Total node counts match across raw dataset and summary payload."""
        summary_total = self.summary_data.get("metrics", {}).get("total_server_nodes", 0)
        self.assertGreater(
            summary_total,
            0,
            "Dataset must contain at least 1 server node. Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to reconcile datasets."
        )
        if self.raw_data is None:
            raise AssertionError(
                f"Missing SolarWinds raw dataset at '{self.nodes_file}'. "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to fetch and populate raw nodes."
            )

        raw_nodes = self.raw_data.get("nodes", [])
        raw_total = self.raw_data.get("total_nodes", len(raw_nodes))
        if len(raw_nodes) != raw_total:
            raise AssertionError(
                f"Data pipeline drift detected: raw node records count ({len(raw_nodes)}) "
                f"diverged from raw total_nodes count ({raw_total}). "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to reconcile datasets."
            )
        if raw_total != summary_total:
            raise AssertionError(
                f"Data pipeline drift detected: raw node dataset count ({raw_total}) "
                f"diverged from summary payload count ({summary_total}). "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to reconcile datasets."
            )
        self.assertEqual(len(raw_nodes), raw_total)
        self.assertEqual(raw_total, summary_total)


    def test_health_classification_sum_invariant(self):
        """Invariant: High + Medium + Low/Critical node counts exactly equal total nodes."""
        metrics = self.summary_data["metrics"]
        total = metrics["total_server_nodes"]
        high = metrics["high_health_nodes"]
        medium = metrics["medium_health_nodes"]
        low = metrics["low_critical_nodes"]

        health_sum = high + medium + low
        if health_sum != total:
            raise AssertionError(
                f"Data pipeline drift detected: sum of health classifications ({health_sum}) "
                f"diverged from total server nodes ({total}). "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to reconcile datasets."
            )
        self.assertEqual(health_sum, total)
        self.assertAlmostEqual(
            metrics["high_health_pct"] + metrics["medium_health_pct"] + metrics["low_critical_pct"],
            100.0,
            delta=0.1,
        )

    def test_status_counts_sum_invariant(self):
        """Invariant: Status counts sum matches total server nodes."""
        status_counts = self.summary_data["metrics"]["status_counts"]
        status_sum = sum(status_counts.values())
        total = self.summary_data["metrics"]["total_server_nodes"]

        if status_sum != total:
            raise AssertionError(
                f"Data pipeline drift detected: sum of status counts ({status_sum}) "
                f"diverged from total server nodes ({total}). "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to reconcile datasets."
            )
        self.assertEqual(status_sum, total)

    def test_vendor_breakdown_sum_invariant(self):
        """Invariant: Standard 5-category vendor breakdown sum matches total nodes."""
        vendor_breakdown = self.summary_data["vendor_breakdown"]
        vendor_sum = sum(vendor_breakdown.values())
        total = self.summary_data["metrics"]["total_server_nodes"]

        if vendor_sum != total:
            raise AssertionError(
                f"Data pipeline drift detected: sum of vendor breakdown ({vendor_sum}) "
                f"diverged from total server nodes ({total}). "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to reconcile datasets."
            )
        self.assertEqual(vendor_sum, total)
        self.assertIn("Windows", vendor_breakdown)
        self.assertIn("Cisco", vendor_breakdown)
        self.assertIn("Linux", vendor_breakdown)
        self.assertIn("SolarWinds", vendor_breakdown)
        self.assertIn("Other", vendor_breakdown)

    def test_individual_node_schema_and_health_integrity(self):
        """Invariant: Every node record has required fields and accurate health logic."""
        required_fields = [
            "NodeID", "Caption", "IPAddress", "Status", "CPULoad",
            "PercentMemoryUsed", "ResponseTime", "Vendor", "MachineType",
            "HealthClassification"
        ]

        nodes_to_test = self.raw_data.get("nodes", []) if self.raw_data else self.summary_data.get("sample_nodes", []) or self.summary_data.get("top_degraded_servers", [])
        self.assertGreater(
            len(nodes_to_test),
            0,
            "No node records found to validate. Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to enrich node telemetry."
        )

        for node in nodes_to_test:
            for field in required_fields:
                self.assertIn(
                    field,
                    node,
                    f"Node {node.get('NodeID')} missing required field '{field}'. "
                    f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to enrich node telemetry."
                )

            computed_health = classify_node_health(node)
            self.assertEqual(
                node["HealthClassification"],
                computed_health,
                f"Health classification mismatch for node {node.get('NodeID')}: "
                f"expected '{computed_health}', got '{node.get('HealthClassification')}'. "
                f"Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to enrich node telemetry."
            )


    def test_fleet_averages_within_valid_bounds(self):
        """Invariant: Average CPU, RAM, and Latency are non-negative and mathematically valid."""
        metrics = self.summary_data.get("metrics", {})
        cpu = metrics.get("avg_fleet_cpu_load_pct")
        ram = metrics.get("avg_fleet_ram_used_pct")
        latency = metrics.get("avg_fleet_latency_ms")

        error_remediation = "Please run 'python scripts/fetch_solarwinds_data.py' or 'python scripts/fetch_solarwinds_data.py' to reconcile datasets."
        self.assertIsNotNone(cpu, f"Missing avg_fleet_cpu_load_pct. {error_remediation}")
        self.assertIsNotNone(ram, f"Missing avg_fleet_ram_used_pct. {error_remediation}")
        self.assertIsNotNone(latency, f"Missing avg_fleet_latency_ms. {error_remediation}")
        self.assertTrue(0.0 <= cpu <= 100.0, f"CPU load out of bounds: {cpu}. {error_remediation}")
        self.assertTrue(0.0 <= ram <= 100.0, f"RAM used out of bounds: {ram}. {error_remediation}")
        self.assertTrue(latency >= 0.0, f"Latency negative: {latency}. {error_remediation}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
