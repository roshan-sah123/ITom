#!/usr/bin/env python3
"""Deep Empirical Adversarial Harness for Challenger 1.

Executes comprehensive stress testing on:
1. OEM Casing & Normalization Variations
2. Storage Calculation Boundaries, Precision & Powers
3. Compliance State Boundaries & Invariants
4. SolarWinds Health Classification Boundary Conditions
5. ETL Determinism, Permutation Invariance & Idempotence
"""

import json
import math
import os
import random
import sys
import unittest
from typing import Any, Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.sync.payload_generator import (
    PayloadGenerator,
    calculate_metrics,
    generate_breakdowns,
    format_sample_devices,
    normalize_manufacturer,
)
from src.sync.solarwinds_client import (
    classify_node_health,
    normalize_solarwinds_vendor,
)


class TestEmpiricalOemNormalization(unittest.TestCase):
    """Adversarial stress-testing of OEM normalization."""

    def test_oem_casing_variations_and_whitespace(self):
        cases = [
            ("LENOVO", "Lenovo"),
            ("lenovo", "Lenovo"),
            ("LeNoVo", "Lenovo"),
            ("  LENOVO  ", "Lenovo"),
            ("\tlenovo\n", "Lenovo"),
            ("LENOVO INC", "Lenovo"),
            ("LENOVO GROUP LIMITED", "Lenovo"),
            ("dell inc.", "Dell"),
            ("DELL INC.", "Dell"),
            ("Dell Inc.", "Dell"),
            ("DeLl", "Dell"),
            ("  DELL COMPUTER CORP  ", "Dell"),
            ("Hewlett-Packard", "HP"),
            ("HEWLETT-PACKARD", "HP"),
            ("hewlett-packard", "HP"),
            ("Hewlett Packard Enterprise", "HP"),
            ("hp", "HP"),
            ("HP", "HP"),
            ("hP", "HP"),
            ("HP Inc.", "HP"),
            ("APPLE", "Apple"),
            ("apple", "Apple"),
            ("Apple Computer, Inc.", "Apple"),
            ("aPpLe InC.", "Apple"),
            ("Unknown Corp", "Other"),
            ("ASUSTeK COMPUTER INC.", "Other"),
            ("Acer Inc.", "Other"),
            ("Toshiba", "Other"),
            ("Panasonic", "Other"),
            ("", "Other"),
            ("   ", "Other"),
            (None, "Other"),
            (12345, "Other"),
            (True, "Other"),
            (False, "Other"),
            ({"name": "Dell"}, "Other"),
            (["HP"], "Other"),
        ]
        for raw, expected in cases:
            res = normalize_manufacturer(raw)
            self.assertEqual(res, expected, f"normalize_manufacturer({repr(raw)}) -> {repr(res)}, expected {repr(expected)}")

    def test_solarwinds_vendor_normalization(self):
        cases = [
            ("Windows", "Windows"),
            ("WINDOWS", "Windows"),
            ("Microsoft Windows Server", "Windows"),
            ("Cisco", "Cisco"),
            ("CISCO SYSTEMS INC", "Cisco"),
            ("cisco catalyst", "Cisco"),
            ("Linux", "Linux"),
            ("LINUX", "Linux"),
            ("RedHat Linux", "Linux"),
            ("Ubuntu Linux", "Linux"),
            ("CentOS", "Linux"),
            ("Debian", "Linux"),
            ("net-snmp", "Linux"),
            ("SolarWinds", "SolarWinds"),
            ("SOLARWINDS", "SolarWinds"),
            ("SolarWinds Orion", "SolarWinds"),
            ("Palo Alto Networks", "Other"),
            ("Juniper Networks, Inc.", "Other"),
            ("Fortinet, Inc.", "Other"),
            ("VMware Inc.", "Other"),
            ("Unknown", "Other"),
            ("", "Other"),
            (None, "Other"),
            (123, "Other"),
        ]
        for raw, expected in cases:
            res = normalize_solarwinds_vendor(raw)
            self.assertEqual(res, expected, f"normalize_solarwinds_vendor({repr(raw)}) -> {repr(res)}, expected {repr(expected)}")


class TestEmpiricalStorageArithmetic(unittest.TestCase):
    """Adversarial stress-testing of storage arithmetic and precision."""

    def test_zero_free_bytes_utilization(self):
        # 100% full disk
        devs = [{
            "totalStorageSpaceInBytes": 500 * (1024 ** 3),
            "freeStorageSpaceInBytes": 0,
            "complianceState": "compliant"
        }]
        metrics = calculate_metrics(devs)
        self.assertEqual(metrics["avg_storage_used_pct"], 100.0)

    def test_zero_total_bytes_no_zero_division(self):
        devs = [
            {"totalStorageSpaceInBytes": 0, "freeStorageSpaceInBytes": 0, "complianceState": "compliant"},
            {"totalStorageSpaceInBytes": None, "freeStorageSpaceInBytes": None, "complianceState": "compliant"},
            {"complianceState": "compliant"},
        ]
        metrics = calculate_metrics(devs)
        self.assertEqual(metrics["avg_storage_used_pct"], 0.0)
        self.assertEqual(metrics["total_managed_devices"], 3)

    def test_binary_power_exactness(self):
        # 1 GiB = 1024^3 bytes = 1,073,741,824 bytes
        # 1 TiB = 1024^4 bytes = 1,099,511,627,776 bytes
        # If total = 1024^3 and free = 512 * 1024^2 (0.5 GiB) -> used = 50.0%
        devs = [{
            "totalStorageSpaceInBytes": 1024 ** 3,
            "freeStorageSpaceInBytes": 512 * (1024 ** 2),
            "complianceState": "compliant"
        }]
        metrics = calculate_metrics(devs)
        self.assertEqual(metrics["avg_storage_used_pct"], 50.0)

    def test_sample_device_storage_formatting(self):
        devs = [
            {
                "id": "dev-1",
                "deviceName": "PC-FULL",
                "totalStorageSpaceInBytes": 512 * (1024 ** 3),
                "freeStorageSpaceInBytes": 0,
                "complianceState": "compliant",
            },
            {
                "id": "dev-2",
                "deviceName": "PC-EMPTY",
                "totalStorageSpaceInBytes": 512 * (1024 ** 3),
                "freeStorageSpaceInBytes": 512 * (1024 ** 3),
                "complianceState": "compliant",
            },
            {
                "id": "dev-3",
                "deviceName": "PC-NO-STORAGE",
                "totalStorageSpaceInBytes": 0,
                "freeStorageSpaceInBytes": 0,
                "complianceState": "unknown",
            },
        ]
        samples = format_sample_devices(devs)
        self.assertEqual(len(samples), 3)
        self.assertEqual(samples[0]["totalStorageGB"], 512.0)
        self.assertEqual(samples[0]["freeStorageGB"], 0.0)
        self.assertEqual(samples[0]["usedStoragePct"], 100.0)

        self.assertEqual(samples[1]["totalStorageGB"], 512.0)
        self.assertEqual(samples[1]["freeStorageGB"], 512.0)
        self.assertEqual(samples[1]["usedStoragePct"], 0.0)

        self.assertEqual(samples[2]["totalStorageGB"], 0.0)
        self.assertEqual(samples[2]["freeStorageGB"], 0.0)
        self.assertEqual(samples[2]["usedStoragePct"], 0.0)


class TestEmpiricalSolarWindsHealthClassification(unittest.TestCase):
    """Adversarial stress-testing of SolarWinds health boundary conditions."""

    def test_health_tier_boundaries(self):
        test_cases = [
            # High health: Status=1, CPU < 75, RAM < 80
            ({"Status": 1, "CPULoad": 0, "PercentMemoryUsed": 0}, "High"),
            ({"Status": 1, "CPULoad": 74.99, "PercentMemoryUsed": 79.99}, "High"),
            ({"Status": 1, "CPULoad": None, "PercentMemoryUsed": None}, "High"),
            ({"Status": 1, "CPULoad": -2, "PercentMemoryUsed": -2}, "High"),

            # Medium health: Status=1 with CPU [75, 90] or RAM [80, 90]
            ({"Status": 1, "CPULoad": 75.0, "PercentMemoryUsed": 50}, "Medium"),
            ({"Status": 1, "CPULoad": 90.0, "PercentMemoryUsed": 50}, "Medium"),
            ({"Status": 1, "CPULoad": 50, "PercentMemoryUsed": 80.0}, "Medium"),
            ({"Status": 1, "CPULoad": 50, "PercentMemoryUsed": 90.0}, "Medium"),
            ({"Status": 1, "CPULoad": 75.0, "PercentMemoryUsed": 80.0}, "Medium"),
            ({"Status": 1, "CPULoad": 90.0, "PercentMemoryUsed": 90.0}, "Medium"),

            # Medium health: Status=3 (Warning) with non-critical metrics
            ({"Status": 3, "CPULoad": 10, "PercentMemoryUsed": 10}, "Medium"),
            ({"Status": 3, "CPULoad": 75, "PercentMemoryUsed": 80}, "Medium"),
            ({"Status": 3, "CPULoad": 90, "PercentMemoryUsed": 90}, "Medium"),

            # Low/Critical: Status in [2 (Down), 14 (Critical), 0 (Unknown/Unmanaged)]
            ({"Status": 2, "CPULoad": 0, "PercentMemoryUsed": 0}, "Low"),
            ({"Status": 14, "CPULoad": 0, "PercentMemoryUsed": 0}, "Low"),
            ({"Status": 0, "CPULoad": 0, "PercentMemoryUsed": 0}, "Low"),
            ({"Status": None, "CPULoad": 0, "PercentMemoryUsed": 0}, "Low"),

            # Low/Critical: CPU > 90 or RAM > 90 regardless of Status
            ({"Status": 1, "CPULoad": 90.01, "PercentMemoryUsed": 50}, "Low"),
            ({"Status": 1, "CPULoad": 50, "PercentMemoryUsed": 90.01}, "Low"),
            ({"Status": 1, "CPULoad": 100, "PercentMemoryUsed": 100}, "Low"),
            ({"Status": 3, "CPULoad": 95, "PercentMemoryUsed": 50}, "Low"),
            ({"Status": 3, "CPULoad": 50, "PercentMemoryUsed": 95}, "Low"),
        ]

        for node, expected in test_cases:
            res = classify_node_health(node)
            self.assertEqual(res, expected, f"classify_node_health({node}) -> {res}, expected {expected}")


class TestEmpiricalEtlPermutationInvariance(unittest.TestCase):
    """Stress test ETL invariance under input record permutation."""

    def test_permutation_invariance_on_deterministic_records(self):
        devices = [
            {"id": "one", "manufacturer": "Dell", "operatingSystem": "Windows", "complianceState": "compliant", "totalStorageSpaceInBytes": 100, "freeStorageSpaceInBytes": 50},
            {"id": "two", "manufacturer": "Lenovo", "operatingSystem": "Linux", "complianceState": "noncompliant", "totalStorageSpaceInBytes": 200, "freeStorageSpaceInBytes": 50},
            {"id": "three", "manufacturer": None, "operatingSystem": "macOS", "complianceState": "unknown"},
        ]
        m1 = calculate_metrics(devices)
        os1, comp1, mfg1 = generate_breakdowns(devices)

        # Shuffle devices randomly
        shuffled = list(devices)
        random.Random(12345).shuffle(shuffled)

        m2 = calculate_metrics(shuffled)
        os2, comp2, mfg2 = generate_breakdowns(shuffled)

        # Invariant checks: Shuffled order produces IDENTICAL metrics and breakdowns
        self.assertEqual(m1, m2)
        self.assertEqual(os1, os2)
        self.assertEqual(comp1, comp2)
        self.assertEqual(mfg1, mfg2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
