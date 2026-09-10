"""Cross-domain analytics endpoints — currently location/site reporting.

Separate from the per-domain routers because a location view spans source
systems: a site has both SolarWinds infrastructure and (potentially) Intune
endpoints, and an operations dashboard wants them together.

Data provenance for ``location``:
    SolarWinds  -> Orion custom property ``City``, selected by the SWQL in
                   ``solarwinds_client.fetch_nodes()`` and mapped to
                   ``ConfigurationItem.location`` during normalisation.
    Intune      -> Microsoft Graph ``managedDevices`` exposes no site field,
                   so Intune CIs currently have no location and are reported
                   under ``unlocated_cis``.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.summary_repository import SummaryRepository

router = APIRouter(prefix="/analytics", tags=["Analytics"])

ALLOWED_SORTS = {"total", "risk", "name"}


@router.get("/locations", status_code=status.HTTP_200_OK)
async def get_location_analytics(
    source_system: Optional[str] = Query(
        None, description="SOLARWINDS, INTUNE, or omit for all sources"
    ),
    sort_by: str = Query(
        "total", description="total (largest sites first) | risk (most unhealthy first) | name"
    ),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Per-site operational analytics: availability, health mix and risk.

    Returns HTTP 503 when the requested scope has no ingested data.

    Response shape::

        {
          "source_system": "SOLARWINDS",
          "data_source": "DATABASE",
          "generated_at": "2026-09-10T13:45:00+00:00",
          "sorted_by": "total",
          "total_cis": 1579,
          "located_cis": 1567,
          "unlocated_cis": 12,
          "location_coverage_pct": 99.24,
          "total_locations": 42,
          "locations": [
            {
              "location": "Mumbai",
              "total_cis": 210,
              "available_cis": 198,
              "unavailable_cis": 12,
              "availability_pct": 94.29,
              "high_health_count": 195,
              "medium_health_count": 8,
              "low_health_count": 7,
              "at_risk_cis": 15,
              "health_score_pct": 92.86,
              "status_breakdown": {"Up": 198, "Down": 5, "Critical": 7},
              "health_breakdown": {"High": 195, "Medium": 8, "Low": 7}
            }
          ]
        }

    Notes for consumers:
        * ``sort_by=risk`` orders sites by low-health count descending — the
          natural ordering for an operations triage view.
        * ``location_coverage_pct`` tells you what share of the estate actually
          carries a site. Do not present per-site totals as fleet totals unless
          coverage is 100%.
        * Every site's ``status_breakdown`` sums to its ``total_cis``.
    """
    normalised_sort = sort_by if sort_by in ALLOWED_SORTS else "total"
    repo = SummaryRepository(session)
    return await repo.get_location_analytics(
        source_system=source_system,
        sort_by=normalised_sort,
    )
