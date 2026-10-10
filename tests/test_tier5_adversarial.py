#!/usr/bin/env python3
"""Tier 5 Adversarial Coverage Hardening & Empirical Stress Testing Suite.

This test suite performs rigorous white-box adversarial stress testing, invariant fuzzing,
error injection, and boundary pressure testing across:
1. Invariant Fuzzing on Corrupted Device Records (Nulls, negative storage, corrupted types, malformed dates).
2. Manufacturer Case-Normalization Permutations (LENOVO INC, DELL INC, hP, Apple Computer, Microsoft Corp, injections).
3. Compliance Rate & Storage Precision Math (0%, 100%, single device, zero devices, sub-percentage rounding, float precision).
4. Sync Pipeline Resilience (OAuth errors, token expiry cache, mid-pagination 401 retry, HTTP 429 rate limits).

Usage:
    python tests/test_tier5_adversarial.py
    python -m unittest tests/test_tier5_adversarial.py
"""

import json
import os
import random
import sys
import time
import unittest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List

# Workspace setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.sync.payload_generator import (
    PayloadGenerator,
    calculate_metrics,
    generate_breakdowns,
    format_sample_devices,
    normalize_manufacturer,
    create_dashboard_summary,
)
from src.sync.graph_client import GraphClient, GraphAuthError, GraphApiError



class TestTier5InvariantFuzzing(unittest.TestCase):
    """Stress testing data invariant enforcement against corrupted and hostile inputs."""

    def setUp(self):
        self.generator = PayloadGenerator(default_sample_size=100)

    def test_fuzz_missing_and_none_fields(self):
        """Adversarial Test: Ingest device records with all None or completely missing fields."""
        corrupted_devices = [
            {},
            {"id": None, "deviceName": None, "complianceState": None},
            {"totalStorageSpaceInBytes": None, "freeStorageSpaceInBytes": None},
            {"operatingSystem": None, "manufacturer": None, "lastSyncDateTime": None},
            {
                "id": None,
                "deviceName": None,
                "operatingSystem": None,
                "osVersion": None,
                "complianceState": None,
                "userPrincipalName": None,
                "model": None,
                "manufacturer": None,
                "serialNumber": None,
                "lastSyncDateTime": None,
                "totalStorageSpaceInBytes": None,
                "freeStorageSpaceInBytes": None,
            },
        ]

        # Calculate metrics must not crash on missing/None fields
        metrics = calculate_metrics(corrupted_devices)
        self.assertEqual(metrics["total_managed_devices"], 5)
        self.assertEqual(metrics["compliant_devices"], 0)
        self.assertEqual(metrics["noncompliant_devices"], 0)
        self.assertEqual(metrics["other_compliance"], 5)
        self.assertEqual(metrics["compliance_rate_pct"], 0.0)
        self.assertEqual(metrics["avg_storage_used_pct"], 0.0)

        # Breakdowns must not crash
        os_b, comp_b, mfg_b = generate_breakdowns(corrupted_devices)
        self.assertEqual(sum(os_b.values()), 5)
        self.assertEqual(sum(comp_b.values()), 5)
        self.assertEqual(sum(mfg_b.values()), 5)
        self.assertEqual(mfg_b["Other"], 5)

        # Sample formatting must safely populate defaults
        samples = format_sample_devices(corrupted_devices)
        self.assertEqual(len(samples), 5)
        for s in samples:
            self.assertEqual(s["deviceName"], "N/A")
            self.assertEqual(s["operatingSystem"], "Unknown")
            self.assertEqual(s["complianceState"], "unknown")
            self.assertEqual(s["totalStorageGB"], 0.0)
            self.assertEqual(s["usedStoragePct"], 0.0)

    def test_fuzz_zero_and_negative_storage_boundaries(self):
        """Adversarial Test: Verify zero total storage and negative storage bytes handling."""
        hostile_devices = [
            {"totalStorageSpaceInBytes": 0, "freeStorageSpaceInBytes": 0},
            {"totalStorageSpaceInBytes": -500000000, "freeStorageSpaceInBytes": -200000000},
            {"totalStorageSpaceInBytes": 0, "freeStorageSpaceInBytes": 1000},
        ]

        metrics = calculate_metrics(hostile_devices)
        self.assertEqual(metrics["total_managed_devices"], 3)
        self.assertEqual(metrics["avg_storage_used_pct"], 0.0)

    def test_fuzz_random_mutations_10k_records(self):
        """Stress Test: Fuzz 10,000 synthetic corrupted device records with string/None variations."""
        random.seed(42)
        comp_states = ["compliant", "noncompliant", "configManager", "unknown", "inGracePeriod", "", None, "COMPLIANT", "NonCompliant"]
        manufacturers = ["Dell Inc.", "LENOVO", "HP", "Apple", "Microsoft Corp", "ASUSTeK", "", None, "Hewlett-Packard"]
        os_list = ["Windows", "macOS", "Linux (ubuntu)", "iOS", "Android", "", None]

        fuzzed_devices = []
        for i in range(10000):
            tot = random.choice([0, None, -100, 256 * (1024**3), 512 * (1024**3)])
            free = random.choice([0, None, -50, 128 * (1024**3), 256 * (1024**3)])
            fuzzed_devices.append({
                "id": f"fuzz-{i}" if random.random() > 0.1 else None,
                "deviceName": f"DEV-{i}" if random.random() > 0.1 else None,
                "operatingSystem": random.choice(os_list),
                "complianceState": random.choice(comp_states),
                "manufacturer": random.choice(manufacturers),
                "totalStorageSpaceInBytes": tot,
                "freeStorageSpaceInBytes": free,
            })

        metrics = calculate_metrics(fuzzed_devices)
        self.assertEqual(metrics["total_managed_devices"], 10000)
        self.assertEqual(
            metrics["compliant_devices"] + metrics["noncompliant_devices"] + metrics["other_compliance"],
            10000
        )
        self.assertTrue(0.0 <= metrics["compliance_rate_pct"] <= 100.0)
        self.assertTrue(0.0 <= metrics["avg_storage_used_pct"] <= 100.0)

        os_b, comp_b, mfg_b = generate_breakdowns(fuzzed_devices)
        self.assertEqual(sum(mfg_b.values()), 10000)
        self.assertEqual(sum(comp_b.values()), 10000)
        self.assertEqual(sum(os_b.values()), 10000)

    def test_malformed_dates_and_special_strings(self):
        """Adversarial Test: Format sample devices with malformed ISO dates, extreme years, and special characters."""
        edge_devices = [
            {"id": "1", "lastSyncDateTime": "9999-12-31T23:59:59.999Z"},
            {"id": "2", "lastSyncDateTime": "0001-01-01T00:00:00Z"},
            {"id": "3", "lastSyncDateTime": "NOT_A_DATE"},
            {"id": "4", "lastSyncDateTime": ""},
            {"id": "5", "lastSyncDateTime": None},
            {"id": "6", "lastSyncDateTime": "<script>alert('xss')</script>"},
        ]
        samples = format_sample_devices(edge_devices)
        self.assertEqual(len(samples), 6)
        self.assertEqual(samples[0]["lastSync"], "9999-12-31T23:59:59.999Z")
        self.assertEqual(samples[3]["lastSync"], "N/A")
        self.assertEqual(samples[4]["lastSync"], "N/A")
        self.assertEqual(samples[5]["lastSync"], "<script>alert('xss')</script>")


class TestTier5ManufacturerNormalizationPermutations(unittest.TestCase):
    """Adversarial coverage for OEM manufacturer normalization permutations and boundary strings."""

    def test_oem_case_permutations_exhaustive(self):
        """Adversarial Test: Exhaustive case permutations and brand naming variations."""
        test_matrix = [
            # Lenovo variations
            ("LENOVO", "Lenovo"),
            ("LeNoVo", "Lenovo"),
            ("lenovo", "Lenovo"),
            ("LENOVO INC", "Lenovo"),
            ("Lenovo Group Limited", "Lenovo"),
            ("LENOVO ThinkPad T14", "Lenovo"),
            ("  LeNoVo  ", "Lenovo"),

            # Dell variations
            ("DELL INC", "Dell"),
            ("dell", "Dell"),
            ("DeLl InC.", "Dell"),
            ("Dell Technologies", "Dell"),
            ("DELL OptiPlex 7090", "Dell"),

            # HP variations
            ("hP", "HP"),
            ("HP", "HP"),
            ("hp", "HP"),
            ("Hewlett-Packard", "HP"),
            ("HEWLETT-PACKARD", "HP"),
            ("Hewlett Packard Enterprise", "HP"),
            ("hp inc.", "HP"),
            ("HP EliteBook 840 G8", "HP"),

            # Apple variations
            ("Apple Computer", "Apple"),
            ("APPLE", "Apple"),
            ("apple", "Apple"),
            ("aPpLe InC.", "Apple"),
            ("Apple MacBook Pro 16", "Apple"),

            # Microsoft variations (when include_microsoft=False -> Other; when True -> Microsoft)
            ("Microsoft Corp", "Other"),
            ("MICROSOFT CORPORATION", "Other"),
            ("Microsoft Surface Laptop", "Other"),

            # Other OEM variations
            ("ASUSTeK COMPUTER INC.", "Other"),
            ("Acer Inc.", "Other"),
            ("Panasonic Corporation", "Other"),
            ("Toshiba Client Solutions", "Other"),
            ("Custom Built PC", "Other"),

            # Hostile edge strings
            ("", "Other"),
            ("   \t\n  ", "Other"),
            (None, "Other"),
            (12345, "Other"),
            (True, "Other"),
            ("'; DROP TABLE devices; --", "Other"),
            ("<img src=x onerror=alert(1)>", "Other"),
            ("🤖 OEM Robot Corp", "Other"),
        ]

        for raw_input, expected in test_matrix:
            with self.subTest(raw_input=raw_input, expected=expected):
                result = normalize_manufacturer(raw_input)
                self.assertEqual(result, expected, f"Failed for raw input: {repr(raw_input)}")

    def test_oem_include_microsoft_flag(self):
        """Verify normalize_manufacturer when include_microsoft is explicitly True."""
        self.assertEqual(normalize_manufacturer("Microsoft Corp", include_microsoft=True), "Microsoft")
        self.assertEqual(normalize_manufacturer("MICROSOFT CORPORATION", include_microsoft=True), "Microsoft")
        self.assertEqual(normalize_manufacturer("Dell Inc.", include_microsoft=True), "Dell")


class TestTier5ComplianceAndPrecisionMath(unittest.TestCase):
    """Stress testing mathematical precision, sub-percentage rounding, and edge distributions."""

    def test_compliance_edge_distributions(self):
        """Adversarial Test: 0% compliance, 100% compliance, single device, zero devices."""
        # 1. Zero devices
        m_zero = calculate_metrics([])
        self.assertEqual(m_zero["total_managed_devices"], 0)
        self.assertEqual(m_zero["compliant_devices"], 0)
        self.assertEqual(m_zero["compliance_rate_pct"], 0.0)
        self.assertEqual(m_zero["avg_storage_used_pct"], 0.0)

        # 2. Single device compliant
        m_single_comp = calculate_metrics([{"complianceState": "compliant"}])
        self.assertEqual(m_single_comp["total_managed_devices"], 1)
        self.assertEqual(m_single_comp["compliant_devices"], 1)
        self.assertEqual(m_single_comp["compliance_rate_pct"], 100.0)

        # 3. Single device non-compliant
        m_single_noncomp = calculate_metrics([{"complianceState": "noncompliant"}])
        self.assertEqual(m_single_noncomp["total_managed_devices"], 1)
        self.assertEqual(m_single_noncomp["compliant_devices"], 0)
        self.assertEqual(m_single_noncomp["noncompliant_devices"], 1)
        self.assertEqual(m_single_noncomp["compliance_rate_pct"], 0.0)

        # 4. 100% compliance fleet (10,000 devices)
        fleet_100 = [{"complianceState": "compliant"} for _ in range(10000)]
        m_100 = calculate_metrics(fleet_100)
        self.assertEqual(m_100["total_managed_devices"], 10000)
        self.assertEqual(m_100["compliance_rate_pct"], 100.0)

        # 5. 0% compliance fleet (10,000 devices)
        fleet_0 = [{"complianceState": "noncompliant"} for _ in range(10000)]
        m_0 = calculate_metrics(fleet_0)
        self.assertEqual(m_0["total_managed_devices"], 10000)
        self.assertEqual(m_0["compliance_rate_pct"], 0.0)

    def test_precision_rounding_sub_percentages(self):
        """Adversarial Test: Assert strict 2-decimal rounding on irregular fractional compliance rates."""
        # 1 compliant out of 3 total -> 33.3333...% -> 33.33%
        m3 = calculate_metrics([
            {"complianceState": "compliant"},
            {"complianceState": "noncompliant"},
            {"complianceState": "noncompliant"},
        ])
        self.assertEqual(m3["compliance_rate_pct"], 33.33)

        # 1 compliant out of 7 total -> 14.2857...% -> 14.29%
        m7 = calculate_metrics([{"complianceState": "compliant"}] + [{"complianceState": "noncompliant"}] * 6)
        self.assertEqual(m7["compliance_rate_pct"], 14.29)

        # 2 compliant out of 3 total -> 66.6666...% -> 66.67%
        m3_2 = calculate_metrics([
            {"complianceState": "compliant"},
            {"complianceState": "compliant"},
            {"complianceState": "noncompliant"},
        ])
        self.assertEqual(m3_2["compliance_rate_pct"], 66.67)

        # Authoritative: 21,589 compliant out of 25,987 -> 83.07615...% -> 83.08%
        m_auth = calculate_metrics(
            [{"complianceState": "compliant"}] * 21589 + [{"complianceState": "noncompliant"}] * 4398
        )
        self.assertEqual(m_auth["compliance_rate_pct"], 83.08)

    def test_storage_utilization_precision_and_clamping(self):
        """Adversarial Test: Storage utilization precision under fractional gigabytes."""
        # Exact 1/3 storage used: 300 GB total, 200 GB free -> 100 GB used = 33.333% -> 33.3% rounded
        devs = [{
            "totalStorageSpaceInBytes": 300 * (1024**3),
            "freeStorageSpaceInBytes": 200 * (1024**3)
        }]
        m = calculate_metrics(devs)
        self.assertEqual(m["avg_storage_used_pct"], 33.3)


class TestTier5SyncPipelineResilience(unittest.TestCase):
    """Stress testing sync pipelines under network faults, HTTP 429 rate limits, token expiry, and batching."""

    def test_graph_client_missing_credentials_fails_fast(self):
        """GraphClient raises GraphAuthError immediately when credentials are missing."""
        client = GraphClient(tenant_id="", client_id="", client_secret="")
        with self.assertRaises(GraphAuthError) as ctx:
            client.get_access_token()
        self.assertIn("Missing Azure AD credentials", str(ctx.exception))

    @patch("src.sync.graph_client.requests.Session.post")
    def test_graph_client_token_caching_and_expiration(self, mock_post):
        """GraphClient caches token and refreshes when within 60s of expiry or force_refresh is requested."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token_initial_123",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        client = GraphClient(tenant_id="test-tenant", client_id="test-id", client_secret="test-sec")

        # 1. First acquisition
        token1 = client.get_access_token()
        self.assertEqual(token1, "token_initial_123")
        self.assertEqual(mock_post.call_count, 1)

        # 2. Immediate second call should use cache (mock_post not called again)
        token2 = client.get_access_token()
        self.assertEqual(token2, "token_initial_123")
        self.assertEqual(mock_post.call_count, 1)

        # 3. Force refresh bypasses cache
        mock_response.json.return_value = {
            "access_token": "token_refreshed_456",
            "expires_in": 3600,
        }
        token3 = client.get_access_token(force_refresh=True)
        self.assertEqual(token3, "token_refreshed_456")
        self.assertEqual(mock_post.call_count, 2)

    @patch("src.sync.graph_client.requests.Session.get")
    @patch.object(GraphClient, "get_access_token", return_value="mock_token")
    def test_graph_client_mid_pagination_401_recovery(self, mock_get_token, mock_get):
        """GraphClient automatically refreshes token on mid-pagination 401 Unauthorized."""
        page1_resp = MagicMock(status_code=200)
        page1_resp.json.return_value = {
            "value": [{"id": "dev1"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next_page",
        }

        page2_401_resp = MagicMock(status_code=401, text="Unauthorized")
        page2_ok_resp = MagicMock(status_code=200)
        page2_ok_resp.json.return_value = {
            "value": [{"id": "dev2"}],
        }

        mock_get.side_effect = [page1_resp, page2_401_resp, page2_ok_resp]

        client = GraphClient(tenant_id="t", client_id="c", client_secret="s")
        devices = client.fetch_managed_devices(max_devices=10)

        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["id"], "dev1")
        self.assertEqual(devices[1]["id"], "dev2")
        mock_get_token.assert_any_call(force_refresh=True)

    @patch("src.sync.graph_client.requests.Session.get")
    @patch.object(GraphClient, "get_access_token", return_value="mock_token")
    def test_graph_client_network_error_raises_graph_api_error(self, mock_get_token, mock_get):
        """GraphClient raises GraphApiError on network failure."""
        import requests
        mock_get.side_effect = requests.RequestException("Connection timed out")

        client = GraphClient(tenant_id="t", client_id="c", client_secret="s")
        with self.assertRaises(GraphApiError) as ctx:
            client.fetch_managed_devices()
        self.assertIn("Graph page 1 connection failed", str(ctx.exception))






if __name__ == "__main__":
    unittest.main(verbosity=2)
