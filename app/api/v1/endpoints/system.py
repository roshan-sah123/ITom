"""System-level endpoints: data freshness reporting for dashboard clients.

``GET /api/v1/system/freshness`` is the single call a frontend makes to answer
"can I trust the numbers I am about to render?".

It is intentionally separate from ``/healthz`` and ``/ready``:

    /healthz              is the process alive?
    /ready                can the process reach its database?
    /system/freshness     is the DATA recent enough to display?

A server can be perfectly healthy and ready while serving three-week-old
telemetry. Only this endpoint distinguishes those cases.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.repositories.freshness_repository import FreshnessRepository

router = APIRouter(prefix="/system", tags=["System"])

# Data older than this is reported as STALE. Derived from the sync cadence with
# headroom for one missed cycle, rather than a bare magic number.
FRESHNESS_WINDOW_SECONDS = max(900, int(getattr(settings, "SYNC_INTERVAL_SECONDS", 600) * 2.5))


@router.get("/freshness", status_code=status.HTTP_200_OK)
async def get_data_freshness(
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Report how recently each telemetry domain was successfully synchronized.

    Always returns HTTP 200 - staleness is data the client renders, not a
    transport failure. Branch on ``overall_status`` in the response body.

    Response shape::

        {
          "checked_at": "2026-09-10T12:00:00+00:00",
          "freshness_window_seconds": 1500,
          "overall_status": "FRESH",          // FRESH | STALE | UNKNOWN
          "oldest_age_seconds": 412,
          "sources": {
            "INTUNE":     {"last_synchronized_at": "...", "age_seconds": 412, "status": "FRESH"},
            "SOLARWINDS": {"last_synchronized_at": "...", "age_seconds": 380, "status": "FRESH"}
          }
        }

    ``status`` values:
        FRESH    - synchronized within the freshness window
        STALE    - synchronized before, but too long ago to trust
        UNKNOWN  - no successful synchronization has ever been recorded
    """
    repo = FreshnessRepository(session, freshness_window_seconds=FRESHNESS_WINDOW_SECONDS)
    report = await repo.get_freshness()

    # Mirror the verdict into headers so a client can check freshness without
    # parsing the body (useful for cheap polling).
    response.headers["X-Sync-Status"] = report["overall_status"]
    if report["oldest_age_seconds"] is not None:
        response.headers["X-Data-Age-Seconds"] = str(report["oldest_age_seconds"])

    return report
