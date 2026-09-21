"""Shared concurrency guard for Intune remediation-cache updates."""

import asyncio

# SQLite permits only one writer. Endpoint and scheduled-sync cache writes must
# share this guard so a large worklist update cannot race another update.
remediation_cache_write_lock = asyncio.Lock()
