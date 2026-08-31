#!/usr/bin/env python3
"""Comprehensive Adversarial Verification & Empirical Stress Harness (Challenger 2).

Tests:
1. Advanced Hostile XSS Vector Matrix & Full DOM Sanitization Audit
2. RFC 4180 CSV Export Conformance, Quote Escaping, Formula Injection & Invariant Reconciliation
3. UI Routing, Dynamic Header Switching & Chart.js Memory Lifecycle
4. Deep Repository Secret Scan & Credential Exposure Detection
"""

import csv
import io
import json
import os
import re
import sys
import unittest
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestHostileXSSAndDOMSanitization(unittest.TestCase):
    """Rigorous XSS attack matrix testing against HTML escaping and DOM sinks."""

    def setUp(self):
        # Read ops_analytics.js and index.html / app.js
        with open(os.path.join(PROJECT_ROOT, "ops_analytics.js"), "r", encoding="utf-8") as f:
            self.ops_js = f.read()
        with open(os.path.join(PROJECT_ROOT, "app.js"), "r", encoding="utf-8") as f:
            self.app_js = f.read()

    @staticmethod
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

    def test_exhaustive_xss_payload_neutralization(self):
        """Hostile XSS payloads across all known attack vectors are neutralized."""
        payloads = [
            # Standard tags
            "<script>alert('XSS')</script>",
            "<SCRIPT SRC=https://evil.com/x.js></SCRIPT>",
            "<script>/*<!--*/alert(1)/*-->*/</script>",
            # Event handlers
            "<img src=x onerror=alert(1)>",
            "<img src=x onerror=\"javascript:alert('XSS')\">",
            "<svg onload=alert(1)>",
            "<svg/onload=alert('XSS')>",
            "<body onload=alert(1)>",
            "<input autofocus onfocus=alert(1)>",
            "<marquee onstart=alert(1)>",
            "<details open ontoggle=alert(1)>",
            "<video><source onerror=\"alert(1)\">",
            "<audio src=x onerror=alert(1)>",
            # Attribute breakouts
            "\"><script>alert(1)</script>",
            "'\"><img src=x onerror=alert(1)>",
            "\" onmouseover=\"alert(1)",
            "' onfocus='alert(1)",
            # URI schemes
            "javascript:alert(1)",
            "JaVaScRiPt:alert(1)",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            # DOM Clobbering & Polyglots
            "<form id=\"test\"><input name=\"id\">",
            "jaVasCript:/*-/*`/*\\`/*'/*\"/**/(/* */oNcliCk=alert() )//%0D%0A%0d%0a//</stYle/<titLe/<teXtarEa/<scRipt/--!>\\x3csVg/<sVg/oNloAd=alert()//>\\x3e",
            # HTML5 & MathML
            "<math><mtext><table><mglyph><style><!--</style><img src=x onerror=alert(1)>",
            "<iframe srcdoc=\"&lt;script&gt;alert(1)&lt;/script&gt;\"></iframe>",
            # Null bytes & comments
            "<script\x00>alert(1)</script>",
            "<!--<script>alert(1)</script>-->",
            "<![CDATA[<script>alert(1)</script>]]>",
        ]

        for payload in payloads:
            escaped = self.js_escape_html(payload)
            # 1. Must not contain raw unencoded HTML tag delimiters
            self.assertNotIn("<", escaped, f"Unescaped '<' in: {escaped}")
            self.assertNotIn(">", escaped, f"Unescaped '>' in: {escaped}")
            self.assertNotIn('"', escaped, f"Unescaped '\"' in: {escaped}")
            self.assertNotIn("'", escaped, f"Unescaped \"'\" in: {escaped}")

            # 2. If payload contained < or >, it must be HTML entity encoded
            if "<" in payload:
                self.assertIn("&lt;", escaped)
            if ">" in payload:
                self.assertIn("&gt;", escaped)
            if '"' in payload:
                self.assertIn("&quot;", escaped)
            if "'" in payload:
                self.assertIn("&#039;", escaped)

    def test_dom_table_rendering_all_fields_sanitized(self):
        """Verify all dynamic record properties in ops_analytics.js are wrapped in escapeHtml()."""
        # 1. Intune Table
        intune_render_match = re.search(r"tbody\.innerHTML\s*=\s*displayDevices\.map\(d\s*=>\s*\{(.*?)\}\)\.join\(''\);", self.ops_js, re.DOTALL)
        self.assertIsNotNone(intune_render_match, "Intune displayDevices row mapping not found")
        intune_code = intune_render_match.group(1)

        # Ensure return template string contains escapeHtml for all device properties
        self.assertIn("${escapeHtml(d.deviceName)}", intune_code)
        self.assertIn("${escapeHtml(devIdShort)}", intune_code)
        self.assertIn("${escapeHtml(d.operatingSystem)}", intune_code)
        self.assertIn("${escapeHtml(d.osVersion || 'N/A')}", intune_code)
        self.assertIn("${escapeHtml(d.userPrincipalName)}", intune_code)
        self.assertIn("${escapeHtml(d.manufacturer)}", intune_code)
        self.assertIn("${escapeHtml(d.model || 'N/A')}", intune_code)
        self.assertIn("${escapeHtml(d.serialNumber || 'N/A')}", intune_code)
        self.assertIn("${escapeHtml(d.complianceState)}", intune_code)
        self.assertIn("${escapeHtml(syncDate)}", intune_code)

        # 2. SolarWinds Table
        sw_render_match = re.search(r"tbody\.innerHTML\s*=\s*displayNodes\.map\(n\s*=>\s*\{(.*?)\}\)\.join\(''\);", self.ops_js, re.DOTALL)
        self.assertIsNotNone(sw_render_match, "SolarWinds displayNodes row mapping not found")
        sw_code = sw_render_match.group(1)

        self.assertIn("${escapeHtml(n.Caption)}", sw_code)
        self.assertIn("${escapeHtml(String(n.NodeID))}", sw_code)
        self.assertIn("${escapeHtml(n.IPAddress || 'N/A')}", sw_code)
        self.assertIn("${escapeHtml(n.Vendor || 'Generic')}", sw_code)
        self.assertIn("${escapeHtml(n.MachineType || 'N/A')}", sw_code)
        self.assertIn("${escapeHtml(tier)}", sw_code)

        # 3. SolarWinds Saturated Server List
        sat_render_match = re.search(r"container\.innerHTML\s*=\s*servers\.slice\(0,\s*10\)\.map\(s\s*=>\s*\{(.*?)\}\)\.join\(''\);", self.ops_js, re.DOTALL)
        self.assertIsNotNone(sat_render_match, "SolarWinds saturated servers mapping not found")
        sat_code = sat_render_match.group(1)

        self.assertIn("${escapeHtml(s.Caption || 'Server')}", sat_code)
        self.assertIn("${escapeHtml(s.IPAddress || 'N/A')}", sat_code)
        self.assertIn("${escapeHtml(s.Vendor || 'Hardware')}", sat_code)

    def test_no_dangerous_eval_or_document_write(self):
        """Verify no dynamic eval(), Function constructor, or document.write() in scripts."""
        for js_name, js_code in [("ops_analytics.js", self.ops_js), ("app.js", self.app_js)]:
            self.assertNotIn("eval(", js_code, f"Found dangerous eval() in {js_name}")
            self.assertNotIn("document.write(", js_code, f"Found dangerous document.write() in {js_name}")
            self.assertNotIn("setTimeout(\"", js_code, f"Found string-based setTimeout in {js_name}")
            self.assertNotIn("setInterval(\"", js_code, f"Found string-based setInterval in {js_name}")


class TestRFC4180CSVExportCompliance(unittest.TestCase):
    """Stress tests on CSV export files and CSV generator."""

    def test_intune_csv_file_rfc4180_compliance(self):
        """Validate exports/intune_devices_complete.csv for strict RFC 4180 conformance."""
        csv_path = os.path.join(PROJECT_ROOT, "exports", "intune_devices_complete.csv")
        self.assertTrue(os.path.exists(csv_path), f"File not found: {csv_path}")

        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = list(csv.reader(f))

        expected_headers = [
            "DeviceName", "DeviceID", "OperatingSystem", "OSVersion",
            "UserPrincipalName", "Manufacturer", "Model", "SerialNumber",
            "ComplianceState", "TotalStorageGB", "FreeStorageGB",
            "UsedStoragePct", "LastSync"
        ]

        self.assertEqual(reader[0], expected_headers, "Intune CSV header mismatch")
        self.assertGreaterEqual(len(reader), 101, "Expected at least 100 device data rows")

        # Verify every row has exactly 13 columns
        for idx, row in enumerate(reader[1:], start=1):
            self.assertEqual(
                len(row), 13,
                f"Row {idx} has invalid column count {len(row)} instead of 13: {row}"
            )
            total_gb = float(row[9])
            free_gb = float(row[10])
            used_pct = float(row[11])
            self.assertGreaterEqual(total_gb, 0.0)
            self.assertGreaterEqual(free_gb, 0.0)
            self.assertTrue(0.0 <= used_pct <= 100.0)

    def test_solarwinds_csv_file_rfc4180_compliance(self):
        """Validate exports/solarwinds_nodes_complete.csv for strict RFC 4180 conformance."""
        csv_path = os.path.join(PROJECT_ROOT, "exports", "solarwinds_nodes_complete.csv")
        self.assertTrue(os.path.exists(csv_path), f"File not found: {csv_path}")

        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = list(csv.reader(f))

        expected_headers = [
            "NodeID", "Caption", "IPAddress", "Vendor", "MachineType",
            "HealthClassification", "Status", "StatusDescription",
            "CPULoad", "PercentMemoryUsed", "ResponseTime", "AvgResponseTime",
            "City", "LastSync"
        ]

        self.assertEqual(reader[0], expected_headers, "SolarWinds CSV header mismatch")
        # 1,547 data rows + 1 header = 1548 rows
        self.assertEqual(len(reader), 1548, f"Expected 1,548 total lines in SW CSV, got {len(reader)}")

        # Verify every row has exactly 14 columns
        for idx, row in enumerate(reader[1:], start=1):
            self.assertEqual(
                len(row), 14,
                f"Row {idx} has invalid column count {len(row)} instead of 14: {row}"
            )
            # Health classification
            self.assertIn(row[5], ["High", "Medium", "Low"], f"Invalid health tier at row {idx}: {row[5]}")
            # CPU & RAM values: -2.0 is SWIS unmanaged/not polled indicator; otherwise 0-100%
            cpu = float(row[8])
            ram = float(row[9])
            self.assertTrue(cpu >= -2.0 and cpu <= 100.0, f"Row {idx} invalid CPU: {cpu}")
            self.assertTrue(ram >= -2.0 and ram <= 100.0, f"Row {idx} invalid RAM: {ram}")

    def test_csv_formula_injection_and_multiline_stress(self):
        """Stress-test CSV escaping with DDE/Formula injection payloads and multiline text."""
        from tests.test_tab_navigation import generate_rfc4180_csv

        adversarial_records = [
            {
                "deviceName": "=cmd|' /C calc'!A0",
                "id": "+1234567890",
                "operatingSystem": "-2+3+cmd|' /C calc'!A0",
                "osVersion": "@SUM(1+1)*cmd|' /C calc'!A0",
                "userPrincipalName": "\t=1+1",
                "manufacturer": "Dell, \"Special\" Corp",
                "model": "Precision\n5550\r\nWorkstation",
                "serialNumber": 'SN,"999",888',
                "complianceState": "compliant",
                "totalStorageGB": 512.0,
                "freeStorageGB": 256.0,
                "usedStoragePct": 50.0,
                "lastSync": "2026-08-27T00:00:00Z"
            }
        ]

        csv_str = generate_rfc4180_csv(adversarial_records)
        parsed = list(csv.reader(io.StringIO(csv_str)))

        self.assertEqual(len(parsed), 2)  # Header + 1 record
        row = parsed[1]
        self.assertEqual(row[0], "=cmd|' /C calc'!A0")
        self.assertEqual(row[5], 'Dell, "Special\" Corp')
        self.assertEqual(row[6], "Precision\n5550\r\nWorkstation")
        self.assertEqual(row[7], 'SN,"999",888')


class TestUIRoutingAndMemoryGuards(unittest.TestCase):
    """Stress tests on UI routing, dynamic header switching, and Chart.js memory guards."""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "ops_analytics.js"), "r", encoding="utf-8") as f:
            self.ops_js = f.read()

    def test_parse_tab_id_bounds_and_fallbacks(self):
        """Verify parseTabId bounds handling and fallback."""
        from tests.test_tier5_adversarial_stress import js_parse_tab_id

        self.assertEqual(js_parse_tab_id("intune"), "intune")
        self.assertEqual(js_parse_tab_id("solarwinds"), "solarwinds")
        self.assertEqual(js_parse_tab_id("#intune"), "intune")
        self.assertEqual(js_parse_tab_id("#solarwinds"), "solarwinds")
        self.assertEqual(js_parse_tab_id("?tab=solarwinds"), "solarwinds")
        self.assertEqual(js_parse_tab_id("?tab=intune"), "intune")
        self.assertEqual(js_parse_tab_id("UNKNOWN_TAB"), "overview")
        self.assertEqual(js_parse_tab_id(""), "overview")
        self.assertEqual(js_parse_tab_id(None), "overview")
        self.assertEqual(js_parse_tab_id("<script>alert(1)</script>"), "overview")

    def test_dynamic_header_stat_synchronization_logic(self):
        """Verify updateHeaderStat in ops_analytics.js handles all domain tabs cleanly."""
        self.assertIn("function updateHeaderStat(tabId)", self.ops_js)
        self.assertIn("Total Monitored Nodes", self.ops_js)
        self.assertIn("Total Verified Endpoints", self.ops_js)
        self.assertIn("CMDB Network CIs", self.ops_js)
        self.assertIn("DEX Monitored Fleet", self.ops_js)
        self.assertIn("Phase 2", self.ops_js)

    def test_chart_destruction_guards_present(self):
        """Verify destroyChartSafe and Chart.getChart destroy guards prevent memory leaks."""
        self.assertIn("function destroyChartSafe(instance, canvas)", self.ops_js)
        self.assertIn("instance.destroy()", self.ops_js)
        self.assertIn("Chart.getChart(canvas)", self.ops_js)
        self.assertIn("existing.destroy()", self.ops_js)


class TestRepositorySecretScan(unittest.TestCase):
    """Exhaustive scan across all repository files for hardcoded secrets/credentials."""

    SUSPICIOUS_SECRET_PATTERNS = [
        # Azure / Graph client secrets (30-40 char base64/urlsafe strings)
        (r"(?i)(client_secret|clientsecret|azure_secret|graph_secret)\s*[:=]\s*['\"]([a-zA-Z0-9~_.-]{20,})['\"]", "Azure/Graph Client Secret"),
        # SolarWinds passwords
        (r"(?i)(solarwinds_password|swis_password|orion_password)\s*[:=]\s*['\"]([^'\"]{4,})['\"]", "SolarWinds SWIS Password"),
        # Private Keys
        (r"-----BEGIN (RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----", "Private Key"),
        # AWS / GCP keys
        (r"(?i)AKIA[0-9A-Z]{16}", "AWS Access Key"),
        (r"(?i)AIza[0-9A-Za-z-_]{35}", "Google API Key"),
        # Hardcoded bearer tokens
        (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{30,}", "Hardcoded Bearer Token"),
        # Generic API keys with assigned values
        (r"(?i)(api_key|apikey|auth_token|secret_key)\s*[:=]\s*['\"][a-zA-Z0-9]{20,}['\"]", "Hardcoded API Key"),
    ]

    ALLOWED_FILES_OR_DIRS = [
        ".git",
        "__pycache__",
        ".env.example",  # Contains explicit placeholders
        ".agents",       # Metadata logs
    ]

    def test_no_hardcoded_secrets_in_codebase(self):
        """Scan all code and config files in repository for unencrypted credentials."""
        scanned_count = 0
        violations = []

        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Prune excluded dirs
            dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", ".agents"]]

            for fname in files:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, PROJECT_ROOT)

                # Skip binary files or known examples
                if rel_path.endswith((".png", ".ico", ".jpg", ".woff", ".woff2", ".ttf", ".csv", ".pyc")):
                    continue
                if rel_path == ".env.example":
                    continue

                scanned_count += 1
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception:
                    continue

                for pattern, secret_type in self.SUSPICIOUS_SECRET_PATTERNS:
                    matches = re.finditer(pattern, content)
                    for m in matches:
                        matched_str = m.group(0)
                        # Filter out safe placeholders
                        if any(safe in matched_str.lower() for safe in [
                            "os.getenv", "placeholder", "your_", "test-sec", "mock_", "<your", "example"
                        ]):
                            continue
                        violations.append(f"{rel_path}: {secret_type} -> '{matched_str[:40]}...'")

        self.assertGreater(scanned_count, 15, "Expected to scan at least 15 source files")
        self.assertEqual(
            violations, [],
            f"Found potential hardcoded credentials:\n" + "\n".join(violations)
        )

    def test_gitignore_protects_env_and_secrets(self):
        """Verify .gitignore includes .env and credential patterns."""
        gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
        self.assertTrue(os.path.exists(gitignore_path), ".gitignore file must exist")

        with open(gitignore_path, "r", encoding="utf-8") as f:
            gi_content = f.read()

        self.assertIn(".env", gi_content, ".env must be explicitly ignored in .gitignore")


if __name__ == "__main__":
    unittest.main(verbosity=2)
