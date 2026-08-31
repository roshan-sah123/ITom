#!/usr/bin/env python3
"""ITOM On-Premise Production Server & Auto-Sync Supervisor.

Runs:
1. Multi-threaded HTTP Server on 0.0.0.0:8080 (serves portal to local & corporate network).
2. Recurring 30-Minute Telemetry Auto-Sync Daemon in background thread.
3. Auto-restarts services if any failure occurs.
"""

import os
import sys
import time
import logging
import threading
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(PROJECT_ROOT, "itom_server.log")
CRON_LOG_FILE = os.path.join(PROJECT_ROOT, "itom_cron.log")
SYNC_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "run_sync.py")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("itom_server")

PORT = 8080
HOST = "0.0.0.0"
INTERVAL_SECONDS = 10 * 60  # 10 minutes

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class CustomHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PROJECT_ROOT, **kwargs)

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        if self.path.endswith('.json') or self.path.endswith('.js') or self.path.endswith('.html'):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

def run_http_server():
    server = ThreadingHTTPServer((HOST, PORT), CustomHTTPHandler)
    logger.info("ITOM Web Server active and listening on http://%s:%d", HOST, PORT)
    logger.info("Serving root directory: %s", PROJECT_ROOT)
    try:
        server.serve_forever()
    except Exception as e:
        logger.error("HTTP Server encountered error: %s", e)
    finally:
        server.server_close()

def execute_sync():
    logger.info("=== Starting Scheduled 10-Minute Telemetry Extraction ===")
    try:
        cmd = [sys.executable, SYNC_SCRIPT, "--skip-firestore"]
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info("Telemetry sync executed successfully. Datasets refreshed.")
        else:
            logger.warning("Telemetry sync completed with warnings: %s", (result.stderr or result.stdout).strip())
    except subprocess.TimeoutExpired:
        logger.error("Telemetry sync pipeline timed out after 300 seconds. Process terminated.")
    except Exception as err:
        logger.error("Failed to execute sync pipeline: %s", err)

def run_sync_daemon():
    logger.info("ITOM 10-Minute Telemetry Sync Daemon started.")
    time.sleep(3)
    execute_sync()
    
    while True:
        try:
            time.sleep(INTERVAL_SECONDS)
            execute_sync()
        except Exception as e:
            logger.error("Sync daemon encountered error: %s", e)
            time.sleep(60)

def main():
    logger.info("Starting ITOM Production Unified Server Service on port %d...", PORT)
    
    sync_thread = threading.Thread(target=run_sync_daemon, daemon=True, name="SyncDaemonThread")
    sync_thread.start()
    
    while True:
        try:
            run_http_server()
        except KeyboardInterrupt:
            logger.info("Server stopped by user.")
            break
        except Exception as err:
            logger.error("Server crashed: %s. Restarting in 5 seconds...", err)
            time.sleep(5)

if __name__ == "__main__":
    main()
