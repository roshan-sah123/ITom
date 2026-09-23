"""Read-only route guard and database-backed data freshness headers."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.freshness_repository import FreshnessRepository

# Compatibility helpers retained for integration tests and operational tooling.
# The authoritative value is still persisted by the sync repository; this
# in-process mirror is only a lightweight fallback for callers that need to
# seed or inspect a timestamp without opening a database session.
_last_sync_timestamp = None


def set_last_sync_timestamp(value):
    """Set the process-local last-sync timestamp used by legacy checks."""
    global _last_sync_timestamp
    _last_sync_timestamp = value


def get_last_sync_timestamp():
    """Return the process-local last-sync timestamp, if one was recorded."""
    return _last_sync_timestamp


class FreshnessHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        protected = ("/api/v1/cmdb", "/api/v1/solarwinds", "/api/v1/intune")
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith(protected):
            response = JSONResponse(status_code=405, content={"error": "Telemetry routes are read-only"},
                                    headers={"Allow": "GET, HEAD, OPTIONS"})
        else:
            response = await call_next(request)
        try:
            async with AsyncSessionLocal() as session:
                report = await FreshnessRepository(session, max(900, int(settings.SYNC_INTERVAL_SECONDS * 2.5))).get_freshness()
            response.headers["X-Sync-Status"] = report["overall_status"]
            if report["oldest_age_seconds"] is not None:
                response.headers["X-Data-Age-Seconds"] = str(report["oldest_age_seconds"])
            times = [s["last_synchronized_at"] for s in report["sources"].values() if s["last_synchronized_at"]]
            if len(times) == len(report["sources"]):
                response.headers["X-Last-Synchronized-At"] = min(times)
        except Exception:
            response.headers["X-Sync-Status"] = "UNAVAILABLE"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
