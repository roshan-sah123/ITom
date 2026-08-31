#!/usr/bin/env python3
"""Local Server 30-Minute Telemetry Auto-Sync Daemon.

Runs continuously in the background on the local server. Every 30 minutes, it:
1. Calls Microsoft Graph API (Intune) & SolarWinds SWIS API.
2. Recalculates metrics, health tiers, and disk storage invariants.
3. Updates data/intune_summary.json and data/solarwinds_summary.json.
4. Logs execution status to itom_cron.log.
"""

import os
import sys
import time
import subprocess
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "itom_cron.log"), encoding="utf-8")
    ]
)
logger = logging.getLogger("itom_daemon")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNC_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "run_sync.py")

INTERVAL_SECONDS = 10 * 60  # 10 Minutes

def execute_sync():
    logger.info("=== Starting Scheduled 10-Minute Telemetry Extraction ===")
    try:
        cmd = [sys.executable, SYNC_SCRIPT, "--skip-firestore"]
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info("Telemetry sync executed successfully. Dashboard datasets refreshed.")
        else:
            logger.warning("Telemetry sync completed with warnings: %s", result.stderr.strip() or result.stdout.strip())
    except subprocess.TimeoutExpired:
        logger.error("Telemetry sync pipeline timed out after 300 seconds.")
    except Exception as err:
        logger.error("Failed to execute sync pipeline: %s", err)

def main():
    logger.info("ITOM 10-Minute Auto-Sync Daemon started (Interval: 600s).")
    execute_sync() # Initial sync immediately upon daemon start
    
    while True:
        try:
            time.sleep(INTERVAL_SECONDS)
            execute_sync()
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")
            break
        except Exception as e:
            logger.error("Daemon loop error: %s", e)
            time.sleep(60)

if __name__ == "__main__":
    main()
