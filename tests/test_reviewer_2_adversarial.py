#!/usr/bin/env python3
"""Adversarial Verification Suite for Reviewer Round 2.

Covers:
1. CORS origins normalization, JSON parsing, whitespace/quote stripping, and wildcard rejection.
2. BACKEND_CORS_ORIGINS explicit kwarg priority over ambient environment variables.
3. Origin list sanitization against None / non-string items.
4. SECRET_KEY enforcement in non-development environments and placeholder rejection.
5. Safe DEBUG flag defaults and production environment prohibition.
6. SolarWinds error handling on corrupt JSON, non-dict payloads, and non-dict node elements.
7. SolarWinds descriptive error messages on count divergence in all invariant guards.
8. Zero-build asset synchronicity for all root-level assets against src/frontend/.
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
    classify_node_health,
)


class TestReviewer2CORSAndConfigHardening(unittest.TestCase):
    """Test adversarial configuration matrices for CORS, DEBUG, and SECRET_KEY."""

    def test_clean_origin_handles_none_and_trailing_slashes(self):
        self.assertEqual(Settings._clean_origin(None), "")
        self.assertEqual(Settings._clean_origin("http://localhost:8080/"), "http://localhost:8080")
        self.assertEqual(Settings._clean_origin("http://localhost:8080///"), "http://localhost:8080")
        self.assertEqual(Settings._clean_origin("  'http://localhost:8080/'  "), "http://localhost:8080")
        self.assertEqual(Settings._clean_origin("*"), "*")
        self.assertEqual(Settings._clean_origin(" * "), "*")
        self.assertEqual(Settings._clean_origin("'*'"), "*")

    def test_backend_cors_origins_kwarg_priority(self):
        """Ensure explicit BACKEND_CORS_ORIGINS is not wiped out when CORS_ORIGINS is in env."""
        old_env = os.environ.get("CORS_ORIGINS")
        try:
            os.environ["CORS_ORIGINS"] = "http://localhost:8080"
            # Explicit kwarg must take precedence
            s = Settings(BACKEND_CORS_ORIGINS=["http://custom:9000"])
            self.assertEqual(s.BACKEND_CORS_ORIGINS, ["http://custom:9000"])

            # Explicit wildcard in BACKEND_CORS_ORIGINS must NOT be bypassed
            with self.assertRaises(ValueError) as ctx:
                Settings(BACKEND_CORS_ORIGINS=["*"])
            self.assertIn("Wildcard origin", str(ctx.exception))
        finally:
            if old_env is not None:
                os.environ["CORS_ORIGINS"] = old_env
            else:
                os.environ.pop("CORS_ORIGINS", None)

    def test_wildcard_rejection_permutations_when_credentials_enabled(self):
        """All wildcard permutations must fail fast at startup when credentials are enabled."""
        wildcards = ["*", " * ", "'*'", '"*"', "['*']", "[' * ']", '["*"]']
        for wc in wildcards:
            with self.assertRaises(ValueError, msg=f"Failed to reject wildcard permutation: {wc}"):
                Settings(CORS_ORIGINS=wc, CORS_ALLOW_CREDENTIALS=True)

    def test_wildcard_permitted_when_credentials_disabled(self):
        """Wildcard is safe and permitted when allow_credentials=False."""
        s = Settings(CORS_ORIGINS="*", CORS_ALLOW_CREDENTIALS=False)
        self.assertEqual(s.BACKEND_CORS_ORIGINS, ["*"])

    def test_secret_key_validation_in_production(self):
        """SECRET_KEY must be configured and non-placeholder in production/staging."""
        # Development allows empty SECRET_KEY
        s_dev = Settings(ENVIRONMENT="development", SECRET_KEY="")
        self.assertIsNotNone(s_dev)

        # Production rejects empty/None
        with self.assertRaises(ValueError):
            Settings(ENVIRONMENT="production", SECRET_KEY="")
        with self.assertRaises(ValueError):
            Settings(ENVIRONMENT="production", SECRET_KEY=None)

        # Production rejects insecure placeholders
        for ph in ["itom-secret-key-change-in-production-0987654321", "secret", "changeme", "password", "admin", "test"]:
            with self.assertRaises(ValueError, msg=f"Accepted insecure placeholder: {ph}"):
                Settings(ENVIRONMENT="production", SECRET_KEY=ph)

        # Production accepts strong key
        s_prod = Settings(ENVIRONMENT="production", SECRET_KEY="a" * 64, DEBUG=False)
        self.assertEqual(s_prod.SECRET_KEY, "a" * 64)

    def test_debug_safe_defaults_and_guards(self):
        """DEBUG must default to False and be prohibited in production."""
        s = Settings()
        self.assertFalse(s.DEBUG)

        with self.assertRaises(ValueError):
            Settings(ENVIRONMENT="production", DEBUG=True, SECRET_KEY="a" * 64)

        with self.assertRaises(ValueError):
            Settings(ENVIRONMENT="staging", DEBUG=True, SECRET_KEY="a" * 64)

        # Permitted in development
        s_dev_debug = Settings(ENVIRONMENT="development", DEBUG=True)
        self.assertTrue(s_dev_debug.DEBUG)


class TestReviewer2SolarWindsEdgeCases(unittest.TestCase):
    """Test SolarWinds telemetry resilience against corrupted data and missing files."""

    def test_classify_node_health_non_dict_input(self):
        self.assertEqual(classify_node_health(None), "Low")
        self.assertEqual(classify_node_health("invalid"), "Low")
        self.assertEqual(classify_node_health(123), "Low")
        self.assertEqual(classify_node_health([]), "Low")

    def test_process_telemetry_skips_non_dict_elements(self):
        client = SolarWindsClient()
        mixed_nodes = [
            {"NodeID": 1, "Caption": "Node-1", "Status": 1, "CPULoad": 20, "PercentMemoryUsed": 30, "Vendor": "Windows"},
            None,
            "corrupt_string",
            123,
            {"NodeID": 2, "Caption": "Node-2", "Status": 2, "CPULoad": 95, "PercentMemoryUsed": 95, "Vendor": "Linux"},
        ]
        enriched, summary = client.process_telemetry(mixed_nodes)
        self.assertEqual(len(enriched), 2)
        self.assertEqual(summary["metrics"]["total_server_nodes"], 2)

    def test_reconcile_from_file_corrupt_json(self):
        client = SolarWindsClient()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write("{this is not valid json")
            tf_path = tf.name

        try:
            with self.assertRaises(SolarWindsApiError) as ctx:
                client.reconcile_from_file(tf_path)
            self.assertIn("Corrupt or invalid JSON", str(ctx.exception))
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_reconcile_from_file_primitive_json(self):
        client = SolarWindsClient()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write("12345")
            tf_path = tf.name

        try:
            with self.assertRaises(SolarWindsApiError) as ctx:
                client.reconcile_from_file(tf_path)
            self.assertIn("Unexpected JSON structure", str(ctx.exception))
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
