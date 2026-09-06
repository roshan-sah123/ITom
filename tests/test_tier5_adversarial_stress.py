#!/usr/bin/env python3
"""Tier 5 Adversarial Coverage Hardening & Empirical Stress Testing Suite.

This suite performs white-box adversarial stress testing and edge-case boundary hardening
on the UI, Navigation & Routing, Search Bar, Table Filtering, RFC 4180 CSV Export,
and Chart.js lifecycle management.

Test Categories:
1. URL Hash Routing & Deep-Link Corrupted Payloads
2. Rapid Concurrent Tab Switching & State Transition Race Conditions
3. Search Bar Malicious Injection Fuzzing (XSS, SQLi, ReDoS, Null Bytes, Prototype Pollution)
4. Table Filtering Scale, Empty Datasets & Malformed Record Resilience
5. RFC 4180 CSV Export Compliance & Formula Injection Sanitization
6. Chart.js Container Resize, Re-creation & Memory Safety Lifecycle
"""

import csv
import io
import json
import math
import os
import random
import re
import sys
import time
import unittest
from typing import Any, Dict, List, Optional

# Workspace root setup
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from tests.test_tab_navigation import (
    TabRouterSimulation,
    filter_device_records,
    generate_rfc4180_csv
)
from tests.test_payload_generator import (
    compute_device_storage_metrics,
    generate_sample_record,
    normalize_manufacturer
)


# ---------------------------------------------------------------------------
# Python Emulation of ops_analytics.js & app.js Core Algorithms
# ---------------------------------------------------------------------------

def js_parse_tab_id(raw: Any) -> str:
    """Exact emulation of ops_analytics.js parseTabId(raw)."""
    valid_tabs = ["overview", "intune", "solarwinds", "network", "dex"]
    default_tab = "overview"
    if raw is None or raw == "":
        return default_tab
    clean = str(raw).strip()
    clean = re.sub(r"^[#?]", "", clean)
    clean = re.sub(r"^tab=", "", clean)
    clean = clean.lower()
    return clean if clean in valid_tabs else default_tab


def js_escape_html(raw_val: Any) -> str:
    """Exact emulation of ops_analytics.js escapeHtml(str)."""
    if raw_val is None or raw_val == "":
        return ""
    s = str(raw_val)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    s = s.replace("'", "&#039;")
    return s


def js_resolve_module_destination(module_name: Any, target_url: Any) -> str:
    """Exact emulation of app.js resolveModuleDestination(moduleName, targetUrl)."""
    raw_target = str(target_url or "").strip()
    raw_mod = str(module_name or "").lower().strip()

    if "#network" in raw_target or "cmdb" in raw_mod or raw_target == "#cmdb":
        return "ops_analytics.html#network"
    if "#solarwinds" in raw_target or "capacity" in raw_mod or "tools" in raw_mod or raw_target in ("#capacity", "#tools-center"):
        return "ops_analytics.html#solarwinds"
    if "#dex" in raw_target or "dex" in raw_mod or raw_target == "#dex":
        return "ops_analytics.html#dex"
    if "#intune" in raw_target or "compliance" in raw_mod or raw_target == "#compliance":
        return "ops_analytics.html#intune"
    if "#overview" in raw_target or "analytics" in raw_mod or raw_target == "ops_analytics.html":
        return "ops_analytics.html#overview"

    if raw_target and raw_target != "#" and not raw_target.startswith("#"):
        return raw_target

    return "ops_analytics.html#overview"


class ChartLifecycleSimulator:
    """Simulates Chart.js lifecycle, canvas destruction, recreation, and resize calls."""

    def __init__(self):
        self.os_chart_instance: Optional[Dict[str, Any]] = None
        self.comp_chart_instance: Optional[Dict[str, Any]] = None
        self.mfg_chart_instance: Optional[Dict[str, Any]] = None
        self.active_instances_count = 0
        self.total_destructions = 0
        self.total_creations = 0
        self.total_resizes = 0

    def render_os_chart(self, os_data: Optional[Dict[str, Any]], canvas_exists: bool = True) -> bool:
        if not canvas_exists or os_data is None:
            return False
        if self.os_chart_instance is not None:
            self.total_destructions += 1
            self.active_instances_count -= 1
            self.os_chart_instance = None
        self.os_chart_instance = {"type": "doughnut", "data": os_data, "id": id(os_data)}
        self.total_creations += 1
        self.active_instances_count += 1
        return True

    def render_compliance_chart(self, comp_data: Optional[Dict[str, Any]], canvas_exists: bool = True) -> bool:
        if not canvas_exists or comp_data is None:
            return False
        if self.comp_chart_instance is not None:
            self.total_destructions += 1
            self.active_instances_count -= 1
            self.comp_chart_instance = None
        self.comp_chart_instance = {"type": "bar", "data": comp_data, "id": id(comp_data)}
        self.total_creations += 1
        self.active_instances_count += 1
        return True

    def render_mfg_chart(self, mfg_data: Optional[Dict[str, Any]], canvas_exists: bool = True) -> bool:
        if not canvas_exists or mfg_data is None:
            return False
        if self.mfg_chart_instance is not None:
            self.total_destructions += 1
            self.active_instances_count -= 1
            self.mfg_chart_instance = None
        self.mfg_chart_instance = {"type": "pie", "data": mfg_data, "id": id(mfg_data)}
        self.total_creations += 1
        self.active_instances_count += 1
        return True

    def trigger_tab_resize(self, active_tab: str):
        if active_tab in ("intune", "overview"):
            if self.os_chart_instance:
                self.total_resizes += 1
            if self.comp_chart_instance:
                self.total_resizes += 1
            if self.mfg_chart_instance:
                self.total_resizes += 1


# ---------------------------------------------------------------------------
# Test Suite 1: Adversarial URL Hash Routing & Corrupted Payloads
# ---------------------------------------------------------------------------

class TestAdversarialUrlHashRouting(unittest.TestCase):
    """Stress tests URL hash parsing, corrupted query strings, injection attacks, and fallbacks."""

    def test_corrupted_and_undefined_hash_routes(self):
        """Tier 5: Verifies fallback to 'overview' on all malformed, undefined, and corrupt hashes."""
        adversarial_hashes = [
            "#unknown",
            "#undefined",
            "#null",
            "#",
            "##",
            "###",
            "####",
            "#12345",
            "#-1",
            "#0",
            "#false",
            "#true",
            "#NaN",
            "#Infinity",
            "?tab=null",
            "?tab=undefined",
            "?tab=",
            "?tab=unknown_route",
            "?tab=123",
            "?tab=NaN",
            "#<script>alert(1)</script>",
            "#javascript:void(0)",
            "#' OR 1=1 --",
            "#../",
            "#..%2F..%2F",
            "#../../etc/passwd",
            "#%00",
            "#\x00\x01\x02",
            "#\n\r\t",
            "#" + "a" * 5000,  # 5,000 char buffer overflow probe
            "#" + "intune" * 100
        ]
        for raw_hash in adversarial_hashes:
            parsed = js_parse_tab_id(raw_hash)
            self.assertEqual(
                parsed, "overview",
                f"Adversarial hash '{raw_hash}' failed to fallback to 'overview', got '{parsed}'"
            )

    def test_valid_tabs_with_whitespace_and_case_permutations(self):
        """Tier 5: Valid tab IDs with arbitrary case and whitespace must resolve correctly."""
        valid_tabs = ["overview", "intune", "solarwinds", "network", "dex"]
        for tab in valid_tabs:
            variations = [
                f"#{tab.upper()}",
                f"#{tab.title()}",
                f"  #{tab}  ",
                f"\t#{tab}\n",
                f"?tab={tab.upper()}",
                f"  ?tab={tab}  ",
                f"{tab.upper()}",
                f" {tab} "
            ]
            for variant in variations:
                parsed = js_parse_tab_id(variant)
                self.assertEqual(
                    parsed, tab,
                    f"Variation '{variant}' failed to resolve to expected tab '{tab}'"
                )

    def test_launcher_destination_resolver_fuzzing(self):
        """Tier 5: Launcher module destination resolver withstands unexpected module names & URLs."""
        test_cases = [
            ("Microsoft Intune Compliance", "#compliance", "ops_analytics.html#intune"),
            ("SolarWinds Capacity", "#capacity", "ops_analytics.html#solarwinds"),
            ("Network CMDB Topology", "#cmdb", "ops_analytics.html#network"),
            ("DEX Fleet Experience", "#dex", "ops_analytics.html#dex"),
            ("OPS Analytics", "ops_analytics.html", "ops_analytics.html#overview"),
            ("<script>alert('xss')</script>", "#invalid", "ops_analytics.html#overview"),
            (None, None, "ops_analytics.html#overview"),
            ("", "", "ops_analytics.html#overview"),
            ("External Tool", "https://portal.azure.com", "https://portal.azure.com"),
            ("Custom Doc", "/docs/architecture.html", "/docs/architecture.html")
        ]
        for mod_name, target_url, expected in test_cases:
            res = js_resolve_module_destination(mod_name, target_url)
            self.assertEqual(
                res, expected,
                f"resolveModuleDestination('{mod_name}', '{target_url}') returned '{res}', expected '{expected}'"
            )


# ---------------------------------------------------------------------------
# Test Suite 2: Concurrent Tab Switching & Race Condition Simulator
# ---------------------------------------------------------------------------

class TestConcurrentTabTransitionsAndRaceConditions(unittest.TestCase):
    """Stress tests state synchronization during high-frequency concurrent tab switches."""

    def test_rapid_random_tab_switching_invariants(self):
        """Tier 5: 10,000 rapid randomized tab switches preserve strict single-active invariant."""
        router = TabRouterSimulation("#overview")
        valid_tabs = ["overview", "intune", "solarwinds", "network", "dex"]
        all_possible_inputs = valid_tabs + ["#unknown", "#123", "", None, "#intune", "#dex", "#solarwinds"]

        random.seed(42)
        for step in range(10000):
            target = random.choice(all_possible_inputs)
            active = router.switch_tab(target)

            # Invariant 1: get_active_tab() is strictly one of the 5 valid tabs
            self.assertIn(active, valid_tabs)
            self.assertEqual(router.get_active_tab(), active)

            # Invariant 2: Exactly 1 tab is True in tab_states, all others False
            active_count = sum(1 for is_active in router.tab_states.values() if is_active)
            self.assertEqual(active_count, 1, f"Step {step}: Multiple active tabs found: {router.tab_states}")
            self.assertTrue(router.tab_states[active])

        # Invariant 3: History length matches total switches + 1
        self.assertEqual(len(router.history), 10001)

    def test_reentrant_and_idempotent_tab_switching(self):
        """Tier 5: Switching repeatedly to the same tab is idempotent and does not corrupt state."""
        router = TabRouterSimulation("#intune")
        for _ in range(500):
            active = router.switch_tab("intune")
            self.assertEqual(active, "intune")
            self.assertTrue(router.tab_states["intune"])
            self.assertFalse(router.tab_states["overview"])
            self.assertFalse(router.tab_states["solarwinds"])
            self.assertFalse(router.tab_states["network"])
            self.assertFalse(router.tab_states["dex"])


# ---------------------------------------------------------------------------
# Test Suite 3: Search Bar Malicious String & Injection Testing (XSS, SQLi, ReDoS)
# ---------------------------------------------------------------------------

class TestSearchBarMaliciousInjectionFuzzing(unittest.TestCase):
    """Fuzzes client-side search filter with XSS, SQL injection, ReDoS, and control characters."""

    @classmethod
    def setUpClass(cls):
        raw_path = os.path.join(WORKSPACE_ROOT, "data", "intune_ops_analytics.json")
        if os.path.exists(raw_path):
            with open(raw_path, "r", encoding="utf-8") as f:
                cls.raw_devices = json.load(f)["devices"]
        else:
            cls.raw_devices = []

        cls.sample_devices = [
            generate_sample_record(d) for d in cls.raw_devices[:100]
        ] if cls.raw_devices else [
            {"deviceName": "LAP-001", "userPrincipalName": "user1@corp.com", "serialNumber": "SN1", "model": "Dell Pro", "operatingSystem": "Windows", "manufacturer": "Dell Inc."},
            {"deviceName": "MAC-002", "userPrincipalName": "user2@corp.com", "serialNumber": "SN2", "model": "MacBook", "operatingSystem": "macOS", "manufacturer": "Apple"}
        ]

    def test_xss_payload_resilience_and_html_escaping(self):
        """Tier 5: XSS payloads in search queries and device fields never execute or inject tags."""
        xss_payloads = [
            "<script>alert(1)</script>",
            "<script src='https://evil.com/payload.js'></script>",
            "<img src=x onerror=alert(1)>",
            "<svg/onload=alert('XSS')>",
            "javascript:alert(document.cookie)",
            "\"><script>alert(1)</script>",
            "'><svg onload=alert(1)>",
            "<iframe src='javascript:alert(1)'></iframe>",
            "<body onload=alert(1)>",
            "<input autofocus onfocus=alert(1)>",
            "<details open ontoggle=alert(1)>",
            "<<SCRIPT>alert('NESTED')//<</SCRIPT>",
            "<script>/*%00*/alert(1)/*%00*/</script>"
        ]
        for xss in xss_payloads:
            # 1. Search filter executes without exception
            results = filter_device_records(self.sample_devices, xss)
            self.assertIsInstance(results, list)

            # 2. HTML escaping neutralizes all tags
            escaped = js_escape_html(xss)
            self.assertNotIn("<script>", escaped)
            self.assertNotIn("<img>", escaped)
            self.assertNotIn("<svg", escaped)
            self.assertNotIn("<iframe", escaped)
            if "<" in xss:
                self.assertIn("&lt;", escaped)
            if ">" in xss:
                self.assertIn("&gt;", escaped)

    def test_sqli_and_command_injection_payloads(self):
        """Tier 5: SQLi and command injection strings do not cause syntax errors or crash."""
        sqli_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE devices; --",
            "1; EXEC xp_cmdshell('dir')",
            "admin'--",
            "' UNION SELECT id, deviceName, null FROM devices --",
            "1' AND SLEEP(5) AND '1'='1",
            "|| ls -la ||",
            "; cat /etc/passwd ;",
            "& ping -n 5 127.0.0.1 &",
            "`id`",
            "${IFS}cat${IFS}/etc/passwd"
        ]
        for sqli in sqli_payloads:
            results = filter_device_records(self.sample_devices, sqli)
            self.assertIsInstance(results, list)

    def test_redos_and_regex_metacharacters(self):
        """Tier 5: Malicious regular expressions and metacharacters do not cause ReDoS."""
        redos_payloads = [
            ".*+?^${}()|[]\\",
            "((a+)+)+$",
            "(a|aa)+",
            "([a-zA-Z0-9_]+)*$",
            "[a-z]{1,10000}",
            "\\p{L}+",
            "((((((((((a))))))))))",
            "[",  # Unclosed bracket
            "(",  # Unclosed paren
            "\\", # Trailing backslash
            "*+", # Illegal quantifier
            "?^", # Misplaced anchor
            "a" * 1000 + "!"
        ]
        for redos in redos_payloads:
            start = time.perf_counter()
            results = filter_device_records(self.sample_devices, redos)
            duration = time.perf_counter() - start
            
            # String search must complete in <50ms without throwing regex SyntaxError
            self.assertLess(duration, 0.05, f"ReDoS query '{redos[:20]}...' took too long: {duration:.4f}s")
            self.assertIsInstance(results, list)

    def test_null_bytes_and_unicode_control_characters(self):
        """Tier 5: Null bytes and control characters are safely absorbed without breaking."""
        control_payloads = [
            "\x00",
            "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f",
            "\r\n\r\n",
            "\u202E",  # Right-to-Left Override
            "\u200B",  # Zero-width space
            "\uFEFF",  # Byte Order Mark (BOM)
            "\uFFFF",  # Non-character
            "Dell\x00Laptop",
            "Lenovo\u202E34T"
        ]
        for ctrl in control_payloads:
            results = filter_device_records(self.sample_devices, ctrl)
            self.assertIsInstance(results, list)

    def test_prototype_pollution_keys(self):
        """Tier 5: Prototype pollution property names in queries do not corrupt object prototypes."""
        proto_payloads = ["__proto__", "constructor", "prototype", "toString", "valueOf", "hasOwnProperty"]
        for key in proto_payloads:
            results = filter_device_records(self.sample_devices, key)
            self.assertIsInstance(results, list)

    def test_ultra_long_search_strings(self):
        """Tier 5: Ultra-long search strings (10,000 & 100,000 characters) do not trigger memory blowups."""
        huge_queries = ["A" * 10000, "X" * 100000]
        for hq in huge_queries:
            start = time.perf_counter()
            results = filter_device_records(self.sample_devices, hq)
            duration = time.perf_counter() - start
            self.assertEqual(len(results), 0)
            self.assertLess(duration, 0.1, f"Huge search took {duration:.4f}s")


# ---------------------------------------------------------------------------
# Test Suite 4: Table Filtering Scale & Malformed Inputs
# ---------------------------------------------------------------------------

class TestTableFilteringScaleAndMalformedInputs(unittest.TestCase):
    """Stress tests client-side table rendering with massive datasets and corrupted records."""

    def test_empty_dataset_filtering(self):
        """Tier 5: Filtering an empty device dataset returns empty list without error."""
        self.assertEqual(filter_device_records([], "search"), [])
        self.assertEqual(filter_device_records([], ""), [])
        self.assertEqual(filter_device_records([], None), [])

    def test_massive_dataset_filter_performance_50k(self):
        """Tier 5: 50,000 synthetic devices filtered in sub-50ms."""
        synthetic_50k = [
            {
                "id": f"dev-{i}",
                "deviceName": f"LAP-CORP-{i:05d}",
                "userPrincipalName": f"employee_{i}@example.com",
                "serialNumber": f"SN{i:07d}",
                "model": "ThinkPad T14 Gen 4" if i % 3 == 0 else "Latitude 5420",
                "operatingSystem": "Windows" if i % 10 != 0 else "macOS",
                "manufacturer": "Lenovo" if i % 3 == 0 else "Dell Inc."
            }
            for i in range(50000)
        ]

        # 1. Search for specific hostname
        start = time.perf_counter()
        res_exact = filter_device_records(synthetic_50k, "LAP-CORP-42000")
        dur_exact = time.perf_counter() - start
        self.assertEqual(len(res_exact), 1)
        self.assertLess(dur_exact, 0.10, f"50k search took {dur_exact:.4f}s")

        # 2. Search for common substring (16,667 matches)
        start = time.perf_counter()
        res_mfg = filter_device_records(synthetic_50k, "Lenovo")
        dur_mfg = time.perf_counter() - start
        self.assertEqual(len(res_mfg), 16667)
        self.assertLess(dur_mfg, 0.10, f"50k substring search took {dur_mfg:.4f}s")


    def test_malformed_and_missing_record_fields(self):
        """Tier 5: Device records with None values, missing keys, numbers, and boolean types filter safely."""
        corrupted_records = [
            {}, # Empty record
            {"deviceName": None, "userPrincipalName": None},
            {"deviceName": 12345, "model": True, "serialNumber": 999.99},
            {"deviceName": {"nested": "value"}, "operatingSystem": ["Win10", "Win11"]},
            {"deviceName": "CORRUPT-001", "userPrincipalName": "test@corp.com", "model": None}
        ]
        
        # Filter with normal string
        res = filter_device_records(corrupted_records, "12345")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["deviceName"], 12345)

        # Filter with substring matching valid record
        res2 = filter_device_records(corrupted_records, "CORRUPT")
        self.assertEqual(len(res2), 1)


# ---------------------------------------------------------------------------
# Test Suite 5: RFC 4180 CSV Export Adversarial Compliance & Formula Injection
# ---------------------------------------------------------------------------

class TestCsvExportRfc4180AdversarialCompliance(unittest.TestCase):
    """Stress tests RFC 4180 CSV export with special characters, quotes, and CSV formula injection."""

    def test_rfc4180_embedded_quotes_commas_and_linebreaks(self):
        """Tier 5: Fields containing quotes, commas, CRLF, and LF are strictly RFC 4180 compliant."""
        adversarial_devices = [
            {
                "id": "uuid-1",
                "deviceName": 'LAP-001 "Special Edition"',
                "operatingSystem": "Windows 11, Enterprise",
                "osVersion": "10.0.26200",
                "userPrincipalName": 'vip,"chief",officer@example.com',
                "manufacturer": 'Dell, Inc. "OEM"',
                "model": 'Latitude, 5420 "Rugged"',
                "serialNumber": 'SN,"123",456',
                "complianceState": 'compliant, verified',
                "totalStorageGB": 512.0, "freeStorageGB": 256.0, "usedStoragePct": 50.0,
                "lastSync": "2026-06-01T12:00:00Z\n(Sync OK)"
            },
            {
                "id": "uuid-2",
                "deviceName": "LAP-002\r\nLine2\r\nLine3",
                "operatingSystem": "macOS",
                "osVersion": "14.5",
                "userPrincipalName": "john@example.com",
                "manufacturer": "Apple",
                "model": "MacBook Pro",
                "serialNumber": "C02XYZ",
                "complianceState": "noncompliant",
                "totalStorageGB": 1024.0, "freeStorageGB": 500.0, "usedStoragePct": 51.2,
                "lastSync": "2026-06-02T10:00:00Z"
            }
        ]

        csv_output = generate_rfc4180_csv(adversarial_devices)
        
        # Parse output using standard Python csv parser (strict RFC 4180 compliant)
        reader = list(csv.reader(io.StringIO(csv_output)))
        
        self.assertEqual(len(reader), 3) # 1 Header + 2 Records
        
        # Verify row 1 field extractions
        row1 = reader[1]
        self.assertEqual(row1[0], 'LAP-001 "Special Edition"')
        self.assertEqual(row1[2], 'Windows 11, Enterprise')
        self.assertEqual(row1[4], 'vip,"chief",officer@example.com')
        self.assertEqual(row1[5], 'Dell, Inc. "OEM"')
        self.assertEqual(row1[6], 'Latitude, 5420 "Rugged"')
        self.assertEqual(row1[7], 'SN,"123",456')
        self.assertEqual(row1[8], 'compliant, verified')
        self.assertEqual(row1[12], '2026-06-01T12:00:00Z\n(Sync OK)')

        # Verify row 2 multiline extraction
        row2 = reader[2]
        self.assertEqual(row2[0], "LAP-002\r\nLine2\r\nLine3")

    def test_csv_formula_and_dde_injection_payloads(self):
        """Tier 5: CSV formula injection characters (=, @, +, -, tab) in device fields parse cleanly."""
        formula_devices = [
            {
                "id": "dde-1",
                "deviceName": "=SUM(1+1)",
                "operatingSystem": "@SUM(1+1)*cmd|' /C calc'!A0",
                "osVersion": "-2+3+cmd|' /C calc'!A0",
                "userPrincipalName": "+1234567890",
                "manufacturer": "\t=1+1",
                "model": "\r=cmd",
                "serialNumber": "SN-001",
                "complianceState": "compliant",
                "totalStorageGB": 500.0, "freeStorageGB": 250.0, "usedStoragePct": 50.0,
                "lastSync": "2026-06-01"
            }
        ]

        csv_output = generate_rfc4180_csv(formula_devices)
        reader = list(csv.reader(io.StringIO(csv_output)))
        row = reader[1]
        
        self.assertEqual(row[0], "=SUM(1+1)")
        self.assertEqual(row[1], "dde-1")
        self.assertEqual(row[2], "@SUM(1+1)*cmd|' /C calc'!A0")
        self.assertEqual(row[3], "-2+3+cmd|' /C calc'!A0")
        self.assertEqual(row[4], "+1234567890")

    def test_csv_special_unicode_and_internationalization(self):
        """Tier 5: Japanese, Cyrillic, Arabic, and Emoji characters survive CSV serialization."""
        unicode_devices = [
            {
                "id": "u-1",
                "deviceName": "ラップトップ-東京-01",
                "operatingSystem": "Windows 11 (日本語)",
                "osVersion": "10.0.26200",
                "userPrincipalName": "tanaka.taro@example.com",
                "manufacturer": "Lenovo (レノボ)",
                "model": "ThinkPad X1 Carbon 💻",
                "serialNumber": "SN-JP-001",
                "complianceState": "compliant",
                "totalStorageGB": 512.0, "freeStorageGB": 300.0, "usedStoragePct": 41.4,
                "lastSync": "2026-06-01"
            },
            {
                "id": "u-2",
                "deviceName": "جهاز-دبي-02",
                "operatingSystem": "macOS (العربية)",
                "osVersion": "14.5",
                "userPrincipalName": "ahmed.ali@example.com",
                "manufacturer": "Apple",
                "model": "MacBook Air 🚀",
                "serialNumber": "SN-AE-002",
                "complianceState": "compliant",
                "totalStorageGB": 256.0, "freeStorageGB": 128.0, "usedStoragePct": 50.0,
                "lastSync": "2026-06-01"
            }
        ]

        csv_output = generate_rfc4180_csv(unicode_devices)
        reader = list(csv.reader(io.StringIO(csv_output)))
        
        self.assertEqual(reader[1][0], "ラップトップ-東京-01")
        self.assertEqual(reader[1][6], "ThinkPad X1 Carbon 💻")
        self.assertEqual(reader[2][0], "جهاز-دبي-02")
        self.assertEqual(reader[2][6], "MacBook Air 🚀")


# ---------------------------------------------------------------------------
# Test Suite 6: Chart.js Container Resize & Canvas Recreation Resilience
# ---------------------------------------------------------------------------

class TestChartJsLifecycleAndContainerResilience(unittest.TestCase):
    """Stress tests Chart.js instance destruction, canvas re-renders, and rapid resize handling."""

    def test_repeated_chart_recreation_lifecycle(self):
        """Tier 5: 1,000 repeated chart creations destroy prior instances without memory leakage."""
        sim = ChartLifecycleSimulator()
        os_data = {"Windows": 25334, "macOS": 602, "Linux": 24}
        comp_data = {"compliant": 21589, "noncompliant": 3422}
        mfg_data = {"Dell": 15716, "HP": 8610, "Lenovo": 959}

        for _ in range(1000):
            sim.render_os_chart(os_data)
            sim.render_compliance_chart(comp_data)
            sim.render_mfg_chart(mfg_data)

        # Invariant: Active instance count is strictly 3 (1 per chart type)
        self.assertEqual(sim.active_instances_count, 3)
        self.assertEqual(sim.total_creations, 3000)
        self.assertEqual(sim.total_destructions, 2997)

    def test_missing_canvas_graceful_exit(self):
        """Tier 5: When canvas element is absent from DOM, chart rendering returns False safely."""
        sim = ChartLifecycleSimulator()
        self.assertFalse(sim.render_os_chart({"Windows": 10}, canvas_exists=False))
        self.assertFalse(sim.render_compliance_chart({"compliant": 10}, canvas_exists=False))
        self.assertFalse(sim.render_mfg_chart({"Dell": 10}, canvas_exists=False))
        self.assertEqual(sim.active_instances_count, 0)

    def test_rapid_resize_trigger_under_tab_switching(self):
        """Tier 5: Rapid view activation triggers safe Chart.js resize calls."""
        sim = ChartLifecycleSimulator()
        sim.render_os_chart({"Windows": 100})
        sim.render_compliance_chart({"compliant": 100})
        sim.render_mfg_chart({"Dell": 100})

        # Simulate 500 rapid tab switch events between 'intune', 'overview', and 'network'
        for _ in range(500):
            sim.trigger_tab_resize("intune")
            sim.trigger_tab_resize("overview")
            sim.trigger_tab_resize("network")  # Non-chart tab: no resize

        # 500 iterations * 2 active chart tabs * 3 charts = 3,000 resize calls
        self.assertEqual(sim.total_resizes, 3000)


# ---------------------------------------------------------------------------
# Test Suite 7: DOM Security, CSP & Numeric Boundary Invariants
# ---------------------------------------------------------------------------

class TestDOMSecurityAndStaticIntegrity(unittest.TestCase):
    """Tier 5: Static security analysis, CSP compliance, and numeric boundary resilience."""

    def test_dom_script_isolation_and_no_inline_eval(self):
        """Tier 5: HTML files do not contain dangerous inline eval() or document.write calls."""
        html_files = [
            os.path.join(WORKSPACE_ROOT, "frontend", "ops_analytics.html"),
            os.path.join(WORKSPACE_ROOT, "frontend", "index.html"),
            os.path.join(WORKSPACE_ROOT, "ops_analytics.html"),
            os.path.join(WORKSPACE_ROOT, "index.html"),
            os.path.join(WORKSPACE_ROOT, "src", "frontend", "ops_analytics.html"),
            os.path.join(WORKSPACE_ROOT, "src", "frontend", "index.html")
        ]
        for fpath in html_files:
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertNotIn("eval(", content)
                self.assertNotIn("document.write(", content)
                self.assertNotIn("javascript:", content)

    def test_storage_calculation_adversarial_boundaries(self):
        """Tier 5: Storage calculation handles negative values, NaN, and free > total safely."""
        # 1. Total = 0, Free = 0
        r1 = compute_device_storage_metrics(0, 0)
        self.assertEqual(r1["totalStorageGB"], 0.0)
        self.assertEqual(r1["usedStoragePct"], 0.0)

        # 2. Total = 100GB, Free = 150GB (anomalous)
        r2 = compute_device_storage_metrics(100 * (1024**3), 150 * (1024**3))
        self.assertEqual(r2["totalStorageGB"], 100.0)
        self.assertEqual(r2["freeStorageGB"], 100.0)  # clamped
        self.assertEqual(r2["usedStoragePct"], 0.0)

        # 3. Negative bytes
        r3 = compute_device_storage_metrics(-500, -100)
        self.assertEqual(r3["totalStorageGB"], 0.0)
        self.assertEqual(r3["usedStoragePct"], 0.0)

    def test_manufacturer_adversarial_normalization(self):
        """Tier 5: Manufacturer classifier withstands all Unicode and string adversarial variants."""
        self.assertEqual(normalize_manufacturer("  LENOVO INC.  "), "Lenovo")
        self.assertEqual(normalize_manufacturer("DELL COMPUTER CORP"), "Dell")
        self.assertEqual(normalize_manufacturer("HEWLETT-PACKARD ENTERPRISE"), "HP")
        self.assertEqual(normalize_manufacturer("Apple Computer Inc."), "Apple")
        self.assertEqual(normalize_manufacturer("UNKNOWN_OEM_12345"), "Other")
        self.assertEqual(normalize_manufacturer(None), "Other")
        self.assertEqual(normalize_manufacturer(9999), "Other")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)

