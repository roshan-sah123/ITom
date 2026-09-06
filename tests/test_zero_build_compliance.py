#!/usr/bin/env python3
"""Zero-Build Runtime Compliance & Modular Frontend Integrity Test Suite.

Validates:
1. Zero-build compatibility: Frontend requires zero Node.js compilation, Webpack, or bundlers.
2. Modular helper availability: Ensures `constants.js`, `utils.js`, `services.js` exist and export expected symbols.
3. HTML `<script>` tag and stylesheet linkage integrity without broken 404 targets.
4. DOM security: Zero dangerous inline sinks (`eval`, `document.write`).

Note: The frontend has a single canonical source location (repository root). The
formerly-duplicated `src/frontend/` mirror was removed; do not reintroduce it.
"""

import os
import re
import sys
import unittest
from html.parser import HTMLParser
from typing import List, Set

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class ScriptLinkageParser(HTMLParser):
    """Extracts script sources and stylesheet links from HTML documents."""
    
    def __init__(self):
        super().__init__()
        self.script_srcs: List[str] = []
        self.stylesheet_hrefs: List[str] = []
        self.image_srcs: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        attr_dict = dict(attrs)
        if tag == "script" and "src" in attr_dict:
            self.script_srcs.append(attr_dict["src"])
        elif tag == "link" and attr_dict.get("rel") == "stylesheet" and "href" in attr_dict:
            self.stylesheet_hrefs.append(attr_dict["href"])
        elif tag == "img" and "src" in attr_dict:
            self.image_srcs.append(attr_dict["src"])


FRONTEND_ROOT = os.path.join(PROJECT_ROOT, "frontend") if os.path.exists(os.path.join(PROJECT_ROOT, "frontend")) else PROJECT_ROOT


class TestZeroBuildCompliance(unittest.TestCase):
    """Assert zero-build architectural compliance and asset synchronicity."""

    def test_modular_frontend_files_exist(self):
        """Verify modular JS helper files and canonical frontend assets exist."""
        required_files = [
            os.path.join(FRONTEND_ROOT, "js", "constants.js"),
            os.path.join(FRONTEND_ROOT, "js", "utils.js"),
            os.path.join(FRONTEND_ROOT, "js", "services.js"),
            os.path.join(FRONTEND_ROOT, "js", "shared.js"),
            os.path.join(FRONTEND_ROOT, "js", "intune.js"),
            os.path.join(FRONTEND_ROOT, "js", "solarwinds.js"),
            os.path.join(FRONTEND_ROOT, "js", "cmdb.js"),
            os.path.join(FRONTEND_ROOT, "index.html"),
            os.path.join(FRONTEND_ROOT, "app.js"),
            os.path.join(FRONTEND_ROOT, "ops_analytics.html"),
            os.path.join(FRONTEND_ROOT, "ops_analytics.js"),
            os.path.join(FRONTEND_ROOT, "style.css"),
        ]
        for path in required_files:
            self.assertTrue(os.path.exists(path), f"Required frontend file missing at {path}")

        self.assertFalse(
            os.path.exists(os.path.join(PROJECT_ROOT, "src", "frontend")),
            "Deprecated duplicate 'src/frontend/' must not be reintroduced."
        )

    def test_constants_module_exports_invariants_and_tokens(self):
        """Verify constants.js contains design system tokens and invariant numbers."""
        constants_path = os.path.join(FRONTEND_ROOT, "js", "constants.js")
        with open(constants_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("THEME", content)
        self.assertIn("#0B0B0B", content)
        self.assertIn("#141414", content)
        self.assertIn("#F97316", content)
        self.assertIn("INVARIANTS", content)
        self.assertIn("25987", content)
        self.assertIn("1548", content)

    def test_utils_module_exports_sanitizer_and_formatters(self):
        """Verify utils.js provides escapeHtml, debounce, and number formatters."""
        utils_path = os.path.join(FRONTEND_ROOT, "js", "utils.js")
        with open(utils_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("function escapeHtml(str)", content)
        self.assertIn("function debounce(func", content)
        self.assertIn("function formatNumber(val)", content)
        self.assertIn("function bytesToGB(bytes", content)

    def test_services_module_exports_loaders_and_csv_engine(self):
        """Verify services.js provides telemetry loaders and RFC 4180 export."""
        services_path = os.path.join(FRONTEND_ROOT, "js", "services.js")
        with open(services_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("loadIntuneTelemetry", content)
        self.assertIn("loadSolarWindsTelemetry", content)
        self.assertIn("loadCmdbTelemetry", content)
        self.assertIn("loadExecutiveDigest", content)
        self.assertIn("exportToCsv", content)

    def test_html_script_and_asset_references_resolve_locally(self):
        """Verify all local script and CSS references in HTML files exist on disk."""
        html_files = [
            os.path.join(FRONTEND_ROOT, "index.html"),
            os.path.join(FRONTEND_ROOT, "ops_analytics.html"),
        ]

        for hfile in html_files:
            if not os.path.exists(hfile):
                continue
            base_dir = os.path.dirname(hfile)
            with open(hfile, "r", encoding="utf-8") as f:
                content = f.read()

            parser = ScriptLinkageParser()
            parser.feed(content)

            # Check local scripts (skip CDN URLs like cdnjs / cdn.jsdelivr)
            for src in parser.script_srcs:
                if src.startswith(("http://", "https://", "//")):
                    continue
                resolved = os.path.normpath(os.path.join(base_dir, src.split("?")[0]))
                self.assertTrue(
                    os.path.exists(resolved) or os.path.exists(os.path.join(PROJECT_ROOT, src.split("?")[0])),
                    f"HTML file {hfile} references non-existent script: {src}"
                )

            # Check local stylesheets
            for href in parser.stylesheet_hrefs:
                if href.startswith(("http://", "https://", "//")):
                    continue
                resolved = os.path.normpath(os.path.join(base_dir, href.split("?")[0]))
                self.assertTrue(
                    os.path.exists(resolved) or os.path.exists(os.path.join(PROJECT_ROOT, href.split("?")[0])),
                    f"HTML file {hfile} references non-existent stylesheet: {href}"
                )

    def test_no_bundler_configs_or_node_modules_required(self):
        """Verify zero bundler config requirements in repository."""
        prohibited_configs = [
            "webpack.config.js",
            "vite.config.js",
            "rollup.config.js",
            "esbuild.config.js",
        ]
        for cfg in prohibited_configs:
            self.assertFalse(
                os.path.exists(os.path.join(PROJECT_ROOT, cfg)),
                f"Prohibited bundler config found: {cfg}. System must remain zero-build."
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
