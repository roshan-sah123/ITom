import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.sync.solarwinds_client import (
    ALLOWED_METHODS,
    SolarWindsClient,
    SolarWindsSecurityError,
    validate_swql_read_only,
    classify_node_health,
    normalize_solarwinds_vendor,
)
from src.sync.cmdb_generator import (
    CMDBService,
    classify_device_role,
    classify_hardware_vendor,
    parse_clean_os,
    map_node_status_string,
)


class TestSolarWindsSecurityGuards(unittest.TestCase):
    def test_allowed_methods_strictly_get(self):
        self.assertEqual(ALLOWED_METHODS, ["GET"])

    def test_validate_swql_read_only_valid_select(self):
        valid_queries = [
            "SELECT NodeID, Caption FROM Orion.Nodes",
            "  SELECT TOP 10 * FROM Orion.NPM.Interfaces WHERE Status = 1",
        ]
        for q in valid_queries:
            validate_swql_read_only(q)

    def test_validate_swql_read_only_blocks_mutations(self):
        forbidden_queries = [
            "INSERT INTO Orion.Nodes (Caption) VALUES ('hacked')",
            "UPDATE Orion.Nodes SET Caption = 'changed' WHERE NodeID = 1",
            "DELETE FROM Orion.Nodes WHERE NodeID = 1",
            "DROP TABLE Orion.Nodes",
            "ALTER TABLE Orion.Nodes ADD Column test",
            "EXEC Orion.Nodes.AcknowledgeAlert 123",
            "TRUNCATE TABLE Orion.Alerts",
            "SELECT NodeID FROM Orion.Nodes; DELETE FROM Orion.Nodes",
            "SELECT NodeID FROM Orion.Nodes WHERE 1=1; DROP TABLETest",
        ]
        for q in forbidden_queries:
            with self.assertRaises(SolarWindsSecurityError):
                validate_swql_read_only(q)

    def test_client_query_blocks_non_get_methods(self):
        client = SolarWindsClient(host="localhost", port=17774, username="test", password="test")
        with self.assertRaises(SolarWindsSecurityError):
            client.query("SELECT 1 FROM Orion.Nodes", method="POST")
        with self.assertRaises(SolarWindsSecurityError):
            client.query("SELECT 1 FROM Orion.Nodes", method="PUT")
        with self.assertRaises(SolarWindsSecurityError):
            client.query("SELECT 1 FROM Orion.Nodes", method="DELETE")


class TestCIClassification(unittest.TestCase):
    def test_firewalls(self):
        self.assertEqual(classify_device_role("Cisco", "Cisco ASA 5515", "Adaptive Security Appliance"), "Firewall")
        self.assertEqual(classify_device_role("Palo Alto Networks", "PA-3220", "PAs-3200 Series"), "Firewall")
        self.assertEqual(classify_device_role("Fortinet, Inc.", "FortiGate-100F", "FortiOS"), "Firewall")

    def test_wireless_controllers(self):
        self.assertEqual(classify_device_role("Cisco", "WLC 5520", "Cisco Controller"), "Wireless Controller")
        self.assertEqual(classify_device_role("Cisco", "Cisco 3504 Wireless LAN Controller", "Cisco Controller"), "Wireless Controller")

    def test_routers(self):
        self.assertEqual(classify_device_role("Cisco", "Cisco 3925K9", "C3900 Software"), "Router")
        self.assertEqual(classify_device_role("Cisco", "C892FSP", "Integrated Services Router"), "Router")
        self.assertEqual(classify_device_role("Cisco", "C8300-1N1S-6T", "Catalyst 8300 Router"), "Router")

    def test_core_switches(self):
        self.assertEqual(classify_device_role("Cisco", "Nexus 9000", "NX-OS Chassis"), "Core Switch")
        self.assertEqual(classify_device_role("Cisco", "C9500-48Y4C", "Catalyst Core Switch"), "Core Switch")

    def test_distribution_switches(self):
        self.assertEqual(classify_device_role("Cisco", "C9300L", "Catalyst L3 Switch"), "Distribution Switch")
        self.assertEqual(classify_device_role("Cisco", "Catalyst 3850", "Multi-layer Aggregation Switch"), "Distribution Switch")

    def test_access_switches(self):
        self.assertEqual(classify_device_role("Cisco", "Cisco C9200L", "Catalyst 9200 Switch"), "Access Switch")
        self.assertEqual(classify_device_role("Cisco", "Cisco Catalyst 29xxStack", "C2960X "), "Access Switch")

    def test_servers(self):
        self.assertEqual(classify_device_role("Windows", "Windows 2019 Server", "Intel64 AT"), "Server")
        self.assertEqual(classify_device_role("Windows", "Windows 2022 Server", "Intel64"), "Server")
        self.assertEqual(classify_device_role("Windows", "Hyper-V Server", "Hyper-V Host"), "Server")
        self.assertEqual(classify_device_role("VMware Inc.", "VMware ESX ", "ESXi Host"), "Server")


class TestCMDBServiceMathematicalInvariants(unittest.TestCase):
    def setUp(self):
        self.service = CMDBService()

    def test_sync_and_save_invariants(self):
        summary = self.service.sync_and_save()
        meta = summary["metadata"]
        metrics = summary["metrics"]
        type_dist = summary["ci_type_distribution"]
        vendor_dist = summary["hardware_breakdown"]
        status_dist = summary["status_breakdown"]
        health_dist = summary["health_tier_breakdown"]
        sample_devices = summary["sample_devices"]

        total_cis = meta["total_configuration_items"]
        self.assertGreaterEqual(total_cis, 1000, "Total CIs should be at least 1000")
        self.assertEqual(len(sample_devices), total_cis)

        # Invariant 1: Sum of CI types equals total
        self.assertEqual(sum(type_dist.values()), total_cis)

        # Invariant 2: Sum of vendors equals total
        self.assertEqual(sum(vendor_dist.values()), total_cis)

        # Invariant 3: Sum of statuses equals total
        self.assertEqual(sum(status_dist.values()), total_cis)

        # Invariant 4: Sum of health tiers equals total
        self.assertEqual(sum(health_dist.values()), total_cis)

        # Invariant 5: Servers + Network devices equals total
        self.assertEqual(metrics["total_servers"] + metrics["total_network_devices"], total_cis)

        # Invariant 6: High health rate
        expected_rate = round((health_dist.get("High", 0) / total_cis) * 100.0, 2)
        self.assertEqual(metrics["control_compliance_rate"], expected_rate)


if __name__ == "__main__":
    unittest.main()

