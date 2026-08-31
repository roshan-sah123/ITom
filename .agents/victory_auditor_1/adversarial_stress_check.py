"""Adversarial Stress Test Script by Victory Auditor.
Tests edge cases, hostile injection, boundary arithmetic, and degradation paths.
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.sync.payload_generator import normalize_manufacturer, calculate_metrics
from src.sync.solarwinds_client import classify_node_health, normalize_solarwinds_vendor

print("=== ADVERSARIAL STRESS TESTING ===")

# Test 1: OEM Normalization Stress
assert normalize_manufacturer("   lEnOvO   ") == "Lenovo"
assert normalize_manufacturer("DELL CORP INC") == "Dell"
assert normalize_manufacturer("HEWLETT PACKARD ENTERPRISE") == "HP"
assert normalize_manufacturer("Apple Computer Inc.") == "Apple"
assert normalize_manufacturer("MICROSOFT CORPORATION", include_microsoft=True) == "Microsoft"
assert normalize_manufacturer("MICROSOFT CORPORATION", include_microsoft=False) == "Other"
assert normalize_manufacturer(None) == "Other"
assert normalize_manufacturer("") == "Other"
assert normalize_manufacturer("   ") == "Other"
assert normalize_manufacturer(12345) == "Other"
print("1. OEM Normalization Stress: PASSED")

# Test 2: SolarWinds Vendor Normalization Stress
assert normalize_solarwinds_vendor("Cisco Systems IOS XR") == "Cisco"
assert normalize_solarwinds_vendor("Microsoft Windows Server 2022") == "Windows"
assert normalize_solarwinds_vendor("Ubuntu Linux 22.04 LTS") == "Linux"
assert normalize_solarwinds_vendor("SolarWinds Agent") == "SolarWinds"
assert normalize_solarwinds_vendor("Palo Alto Networks PA-5200") == "Other"
assert normalize_solarwinds_vendor(None) == "Other"
assert normalize_solarwinds_vendor("") == "Other"
print("2. SolarWinds Vendor Normalization Stress: PASSED")

# Test 3: SolarWinds Health Classification Boundary Stress
# Status 1 (Up) with healthy metrics -> High
assert classify_node_health({"Status": 1, "CPULoad": 74.9, "PercentMemoryUsed": 79.9}) == "High"
# Status 1 with CPU at 75% -> Medium
assert classify_node_health({"Status": 1, "CPULoad": 75.0, "PercentMemoryUsed": 50.0}) == "Medium"
# Status 1 with RAM at 80% -> Medium
assert classify_node_health({"Status": 1, "CPULoad": 50.0, "PercentMemoryUsed": 80.0}) == "Medium"
# Status 3 (Warning) with low CPU/RAM -> Medium
assert classify_node_health({"Status": 3, "CPULoad": 10.0, "PercentMemoryUsed": 10.0}) == "Medium"
# Status 1 with CPU > 90% -> Low/Critical
assert classify_node_health({"Status": 1, "CPULoad": 90.1, "PercentMemoryUsed": 50.0}) == "Low"
# Status 1 with RAM > 90% -> Low/Critical
assert classify_node_health({"Status": 1, "CPULoad": 50.0, "PercentMemoryUsed": 90.1}) == "Low"
# Status 2 (Down) -> Low/Critical
assert classify_node_health({"Status": 2, "CPULoad": 0.0, "PercentMemoryUsed": 0.0}) == "Low"
# Status 14 (Critical) -> Low/Critical
assert classify_node_health({"Status": 14, "CPULoad": 10.0, "PercentMemoryUsed": 10.0}) == "Low"
# Unpolled node (-2 CPU/RAM) with Status 1 -> High
assert classify_node_health({"Status": 1, "CPULoad": -2.0, "PercentMemoryUsed": -2.0}) == "High"
# None node -> Low
assert classify_node_health({"Status": None, "CPULoad": None, "PercentMemoryUsed": None}) == "Low"
print("3. SolarWinds Health Classification Stress: PASSED")

# Test 4: Empty & Degraded Device Collections
empty_metrics = calculate_metrics([])
assert empty_metrics["total_managed_devices"] == 0
assert empty_metrics["compliance_rate_pct"] == 0.0
assert empty_metrics["avg_storage_used_pct"] == 0.0

zero_storage_devs = [
    {"complianceState": "compliant", "totalStorageSpaceInBytes": 0, "freeStorageSpaceInBytes": 0},
    {"complianceState": "noncompliant", "totalStorageSpaceInBytes": None, "freeStorageSpaceInBytes": None},
]
z_metrics = calculate_metrics(zero_storage_devs)
assert z_metrics["total_managed_devices"] == 2
assert z_metrics["compliant_devices"] == 1
assert z_metrics["compliance_rate_pct"] == 50.0
assert z_metrics["avg_storage_used_pct"] == 0.0
print("4. Empty & Edge Payload Aggregation Stress: PASSED")

print("\nALL ADVERSARIAL STRESS TESTS COMPLETED SUCCESSFULLY!")
