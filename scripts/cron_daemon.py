#!/usr/bin/env python3
"""[DEPRECATED] Redundant standalone cron daemon.

Background telemetry synchronization is natively managed by the multi-threaded
background sync daemon in `scripts/start_server.py` or via the master CLI `scripts/run_sync.py`.
This script is retained as a thin shim for backward compatibility.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.run_sync import main

if __name__ == "__main__":
    print("[DEPRECATED] scripts/cron_daemon.py is superseded by scripts/start_server.py background daemon.")
    sys.exit(main())
