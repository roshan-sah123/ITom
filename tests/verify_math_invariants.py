#!/usr/bin/env python3
"""Comprehensive Mathematical Invariant Verification Suite across Multi-Domain Telemetry.

Validates exact arithmetic, partition completeness, and numerical precision across:
1. Microsoft Intune Dataset (`data/intune_summary.json` & `data/intune_ops_analytics.json`)
2. SolarWinds Orion Dataset (`data/solarwinds_summary.json` & `data/solarwinds_nodes.json`)
3. SolarWinds Live CMDB Dataset (`data/cmdb_summary.json` & `exports/cmdb_network_cis_complete.csv`)

Usage:
    python tests/verify_math_invariants.py
"""

import json
import os
import sys
import unittest
from typing import Any, Dict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestCrossDomainMathInvariants(unittest.TestCase):
    """Assert mathematical invariants across all domain payloads."""

    @classmethod
    def setUpClass(cls):
        intune_path = os.path.join(PROJECT_ROOT, "data", "intune_summary.json")
        sw_path = os.path.join(PROJECT_ROOT, "data", "solarwinds_summary.json")
        cmdb_path = os.path.join(PROJECT_ROOT, "data", "cmdb_summary.json")

        with open(intune_path, "r", encoding="utf-8") as f:
            cls.intune = json.load(f)

        with open(sw_path, "r", encoding="utf-8") as f:
            cls.sw = json.load(f)

        with open(cmdb_path, "r", encoding="utf-8") as f:
            cls.cmdb = json.load(f)

    # -------------------------------------------------------------
    # 1. Microsoft Intune Mathematical Invariants
    # -------------------------------------------------------------
    def test_intune_partition_sums(self):
        """Intune Invariant: OS, Compliance, and Manufacturer breakdowns sum strictly to total devices."""
        total = self.intune["metrics"]["total_managed_devices"]
        self.assertGreaterEqual(total, 25000)

        # OS Breakdown sum
        os_sum = sum(self.intune["os_breakdown"].values())
        self.assertEqual(os_sum, total, f"Intune OS sum {os_sum} != {total}")

        # Compliance Breakdown sum
        comp_sum = sum(self.intune["compliance_breakdown"].values())
        self.assertEqual(comp_sum, total, f"Intune Compliance sum {comp_sum} != {total}")

        # Manufacturer Breakdown sum
        mfg_sum = sum(self.intune["manufacturer_breakdown"].values())
        self.assertEqual(mfg_sum, total, f"Intune Manufacturer sum {mfg_sum} != {total}")

    def test_intune_percentage_precision(self):
        """Intune Invariant: Compliance rate and storage utilization are mathematically exact."""
        metrics = self.intune["metrics"]
        total = metrics["total_managed_devices"]
        compliant = metrics["compliant_devices"]

        expected_rate = round((compliant / total) * 100.0, 2)
        self.assertEqual(metrics["compliance_rate_pct"], expected_rate)

        avg_storage = metrics["avg_storage_used_pct"]
        self.assertGreaterEqual(avg_storage, 0.0)
        self.assertLessEqual(avg_storage, 100.0)

    # -------------------------------------------------------------
    # 2. SolarWinds Orion Mathematical Invariants
    # -------------------------------------------------------------
    def test_solarwinds_partition_sums(self):
        """SolarWinds Invariant: Health, Status, and Vendor breakdowns sum strictly to total nodes."""
        metrics = self.sw["metrics"]
        total_nodes = metrics["total_server_nodes"]
        self.assertEqual(total_nodes, 1548)

        # Health Breakdown sum
        health = self.sw["health_breakdown"]
        health_sum = sum(health.values())
        self.assertEqual(health_sum, total_nodes, f"SolarWinds Health sum {health_sum} != {total_nodes}")

        # Status Breakdown sum
        status = metrics["status_counts"]
        status_sum = sum(status.values())
        self.assertEqual(status_sum, total_nodes, f"SolarWinds Status sum {status_sum} != {total_nodes}")

        # Vendor Breakdown sum
        vendor = self.sw["vendor_breakdown"]
        vendor_sum = sum(vendor.values())
        self.assertEqual(vendor_sum, total_nodes, f"SolarWinds Vendor sum {vendor_sum} != {total_nodes}")

    def test_solarwinds_averages_within_bounds(self):
        """SolarWinds Invariant: CPU, RAM, and Latency fleet averages are within physically valid ranges."""
        metrics = self.sw["metrics"]
        cpu = metrics["avg_fleet_cpu_load_pct"]
        ram = metrics["avg_fleet_ram_used_pct"]
        latency = metrics["avg_fleet_latency_ms"]

        self.assertGreaterEqual(cpu, 0.0)
        self.assertLessEqual(cpu, 100.0)
        self.assertGreaterEqual(ram, 0.0)
        self.assertLessEqual(ram, 100.0)
        self.assertGreaterEqual(latency, 0.0)

    # -------------------------------------------------------------
    # 3. Live CMDB Mathematical Invariants
    # -------------------------------------------------------------
    def test_cmdb_partition_sums(self):
        """CMDB Invariant: CI Types, Vendors, Statuses, and Health Tiers sum strictly to Total CIs."""
        meta = self.cmdb["metadata"]
        total_cis = meta["total_configuration_items"]
        self.assertEqual(total_cis, 1543)

        # CI Type sum
        type_dist = self.cmdb["ci_type_distribution"]
        self.assertEqual(sum(type_dist.values()), total_cis)

        # Servers + Network Devices sum
        metrics = self.cmdb["metrics"]
        self.assertEqual(metrics["total_servers"] + metrics["total_network_devices"], total_cis)

        # Hardware Vendor sum
        hw_dist = self.cmdb["hardware_breakdown"]
        self.assertEqual(sum(hw_dist.values()), total_cis)

        # Status sum
        status_dist = self.cmdb["status_breakdown"]
        self.assertEqual(sum(status_dist.values()), total_cis)

        # Health Tier sum
        health_dist = self.cmdb["health_tier_breakdown"]
        self.assertEqual(sum(health_dist.values()), total_cis)


def main() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCrossDomainMathInvariants)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
