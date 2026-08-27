#!/usr/bin/env python3
"""SolarWinds Orion SWIS API Connectivity & Verification Script.

This script tests read-only connectivity to SolarWinds Orion SWIS API (port 17774)
by executing a minimal verification query:
    SELECT TOP 1 NodeID, Caption FROM Orion.Nodes

Credentials are read securely from the local .env configuration.
"""

import os
import sys
import json
import logging
import requests
from dotenv import load_dotenv

# Ensure secure TLS warnings are logged cleanly
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_solarwinds_connection():
    load_dotenv()

    host = os.getenv("SOLARWINDS_HOST", "localhost")
    port = os.getenv("SOLARWINDS_PORT", "17774")
    username = os.getenv("SOLARWINDS_USERNAME")
    password = os.getenv("SOLARWINDS_PASSWORD")

    if not username or not password:
        logger.error("Missing SOLARWINDS_USERNAME or SOLARWINDS_PASSWORD in .env")
        return False

    url = f"https://{host}:{port}/SolarWinds/InformationService/v3/Json/Query"
    query = "SELECT TOP 1 NodeID, Caption FROM Orion.Nodes"
    params = {"query": query}

    logger.info("Initiating read-only test query to SolarWinds SWIS API at %s:%s ...", host, port)

    try:
        # First attempt with standard certificate verification
        try:
            response = requests.get(
                url,
                params=params,
                auth=(username, password),
                timeout=10,
                verify=True
            )
        except requests.exceptions.SSLError as ssl_err:
            logger.warning("Standard CA TLS verification returned: %s", ssl_err)
            logger.info("Retrying with internal/self-signed certificate verification bypass (-k equivalent for testing)...")
            response = requests.get(
                url,
                params=params,
                auth=(username, password),
                timeout=10,
                verify=False
            )

        logger.info("HTTP Status Code: %d", response.status_code)

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            logger.info(" SolarWinds SWIS Query SUCCESSFUL!")
            logger.info("Results Retrieved: %s", json.dumps(results, indent=2))
            return True
        elif response.status_code == 401 or response.status_code == 403:
            logger.error("Authentication / Authorization Failed. HTTP Status: %d", response.status_code)
            logger.error("Response Details: %s", response.text)
            return False
        else:
            logger.error("SolarWinds SWIS API returned unexpected status %d: %s", response.status_code, response.text)
            return False

    except requests.exceptions.ConnectTimeout:
        logger.error("Connection Timeout: Unable to reach %s on port %s within 10s.", host, port)
        return False
    except requests.exceptions.ConnectionError as conn_err:
        logger.error("Connection Error: %s", conn_err)
        return False
    except Exception as exc:
        logger.error("Unexpected error occurred while querying SolarWinds: %s", exc)
        return False


if __name__ == "__main__":
    success = test_solarwinds_connection()
    sys.exit(0 if success else 1)
