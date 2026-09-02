"""Starlette middleware for Freshness Headers and Strict Read-Only 405 Guards."""

import json
from datetime import datetime, timezone
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Module-level sync timestamp state (updated by SyncService)
_last_sync_time: datetime = datetime.now(timezone.utc)


def get_last_sync_timestamp() -> datetime:
    """Get the authoritative last sync timestamp."""
    global _last_sync_time
    return _last_sync_time


def set_last_sync_timestamp(dt: datetime) -> None:
    """Set the authoritative last sync timestamp."""
    global _last_sync_time
    _last_sync_time = dt


class FreshnessHeadersMiddleware(BaseHTTPMiddleware):
    """Adds X-Last-Synchronized-At, X-Data-Age-Seconds, and X-Sync-Status headers to responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check for mutating methods on read-only endpoints first
        method = request.method.upper()
        path = request.url.path

        # Read-only guard: POST, PUT, DELETE, PATCH on telemetry & CMDB endpoints
        read_only_prefixes = (
            "/api/v1/cmdb",
            "/api/v1/solarwinds",
            "/api/v1/intune",
        )

        if method in ("POST", "PUT", "DELETE", "PATCH"):
            # Check if targeting read-only CMDB or telemetry endpoints (or all /api/v1 except sync triggers)
            if any(path.startswith(prefix) for prefix in read_only_prefixes) or (
                path.startswith("/api/v1/") and not path.startswith("/api/v1/sync")
            ):
                now = datetime.now(timezone.utc)
                last_sync = get_last_sync_timestamp()
                age_seconds = max(0, int((now - last_sync).total_seconds()))
                sync_status = "FRESH" if age_seconds <= 900 else "STALE"

                headers = {
                    "Allow": "GET, HEAD, OPTIONS",
                    "X-Last-Synchronized-At": last_sync.isoformat(),
                    "X-Data-Age-Seconds": str(age_seconds),
                    "X-Sync-Status": sync_status,
                }
                return JSONResponse(
                    status_code=405,
                    content={
                        "error": "Forbidden: SolarWinds/Intune Telemetry API is strictly READ-ONLY.",
                        "allowed_methods": ["GET"],
                    },
                    headers=headers,
                )

        # Call endpoint handler
        response = await call_next(request)

        # Compute freshness headers
        now = datetime.now(timezone.utc)
        last_sync = get_last_sync_timestamp()
        age_seconds = max(0, int((now - last_sync).total_seconds()))
        sync_status = "FRESH" if age_seconds <= 900 else "STALE"

        response.headers["X-Last-Synchronized-At"] = last_sync.isoformat()
        response.headers["X-Data-Age-Seconds"] = str(age_seconds)
        response.headers["X-Sync-Status"] = sync_status

        return response
