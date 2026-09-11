"""Cross-domain analytics endpoints — location reporting and stale-asset visibility.

Separate from the per-domain routers because these views span source systems:
a site holds both SolarWinds infrastructure and Intune endpoints, and an asset
that stopped reporting is interesting regardless of where it came from.

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

    Notes for consumers:
        * ``sort_by=risk`` orders sites by low-health count descending — the
          natural ordering for an operations triage view.
        * ``location_coverage_pct`` tells you what share of the estate actually
          carries a site. Do not present per-site totals as fleet totals unless
          coverage is 100%.
        * Every site's ``status_breakdown`` sums to its own ``total_cis``.
    """
    normalised_sort = sort_by if sort_by in ALLOWED_SORTS else "total"
    repo = SummaryRepository(session)
    return await repo.get_location_analytics(
        source_system=source_system,
        sort_by=normalised_sort,
    )


@router.get("/stale-assets", status_code=status.HTTP_200_OK)
async def get_stale_assets(
    source_system: Optional[str] = Query(
        None, description="INTUNE, SOLARWINDS, or omit for all sources"
    ),
    limit: int = Query(
        100, ge=0, le=1000, description="How many individual asset records to return"
    ),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Assets on the books that the source system has stopped reporting.

    This is a **decision-support view, not a data-quality warning**. Each entry
    is an asset the organisation still holds a record for but which no longer
    appears in Intune or SolarWinds. Common explanations, all worth knowing:

    ============================  ==================================================
    Pattern                       Likely meaning
    ============================  ==================================================
    Stopped 1-7 days ago          Investigate now: failure, theft, network change
    Stopped 8-30 days ago         Probably decommissioned without a CMDB update
    Stopped 90+ days ago          Records cleanup; check for lingering licences
    Clustered at one site         Site-wide event: office closure, agent rollout
    Clustered on one vendor       Fleet refresh or a bad agent version
    Last known status Noncompliant  Left the estate carrying an unresolved risk
    ============================  ==================================================

    How staleness is determined: every sync stamps ``last_sync_time`` on every
    CI the source returned, including unchanged ones. An asset whose
    ``last_sync_time`` predates the start of the last successful sync was not
    in that extraction.

    Response shape::

        {
          "definition": "Assets present in the CMDB that were absent from ...",
          "reference_sync_started_at": { "INTUNE": "2026-09-10T13:34:56+00:00" },
          "total_cis": 30773,
          "active_cis": 30196,
          "stale_cis": 577,
          "stale_pct": 1.87,
          "stale_by_source":   { "INTUNE": 574, "SOLARWINDS": 3 },
          "stale_by_age":      { "0-1 days": 4, "2-7 days": 22, "8-30 days": 380, ... },
          "stale_by_location": { "Unknown": 574, "Gr.Noida-T-AB": 2, ... },
          "stale_by_vendor":   { "Dell": 320, "HP": 190, ... },
          "stale_by_last_known_status": { "Compliant": 402, "Noncompliant": 175 },
          "assets": [ { "name": "...", "days_since_last_seen": 12.4, ... } ]
        }

    Notes for consumers:
        * ``active_cis`` is the figure to use if you want compliance rates that
          exclude assets no longer in the estate. The main summary endpoints
          still report over everything, so both views remain available.
        * ``reference_sync_started_at`` is null for a source that has never
          synced successfully. In that case staleness is not measurable and
          ``stale_cis`` is reported as 0 rather than guessed.
        * Set ``limit=0`` for counts only — much faster for a KPI tile.
    """
    repo = SummaryRepository(session)
    return await repo.get_stale_assets(source_system=source_system, limit=limit)
