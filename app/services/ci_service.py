"""Business logic service for Configuration Items, CMDB analytics, and domain telemetry.

STEP 1 CHANGE
-------------
``get_intune_summary()`` and ``get_solarwinds_summary()`` previously returned
hardcoded dictionaries. They now delegate to :class:`SummaryRepository`, which
computes every figure with a SQL aggregate against ``configuration_items``.

STEP 2 CHANGE
-------------
Every endpoint that returns Configuration Items, status history, or
relationships now converts SQLAlchemy ORM rows into plain JSON-safe dicts
before handing them to FastAPI. Without this, ``GET /api/v1/cmdb/cis``,
``/intune/devices`` and ``/solarwinds/nodes`` all fail with:

    PydanticSerializationError: Unable to serialize unknown type:
    <class 'app.models.ci.ConfigurationItem'>

These are the three list endpoints the frontend relies on for tables and
pagination, so they must return valid JSON.
"""

import os
import uuid
from typing import Any, Dict, List, Optional

from app.models.ci import CIRelationship, ConfigurationItem
from app.models.history import CIStatusHistory
from app.repositories.ci_repository import CIRepository
from app.repositories.summary_repository import EmptyDatasetError, SummaryRepository
from app.schemas.serializers import orm_list_to_dicts, orm_to_dict
from app.services.summary_cache import summary_cache, summary_cache_key

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

__all__ = ["CIService", "EmptyDatasetError"]


class CIService:
    """Service orchestrating CMDB records, search/filtering, and multi-domain summary metrics."""

    def __init__(self, ci_repo: CIRepository) -> None:
        self.ci_repo = ci_repo
        # The summary repository shares the request-scoped session already bound
        # to the CI repository, so no additional dependency wiring is required.
        self.summary_repo = SummaryRepository(getattr(ci_repo, "session", None))

    async def get_cis_paginated(
        self,
        page: int = 1,
        page_size: int = 25,
        search: Optional[str] = None,
        source_system: Optional[str] = None,
        ci_type: Optional[str] = None,
        vendor: Optional[str] = None,
        health_tier: Optional[str] = None,
        status: Optional[str] = None,
        location: Optional[str] = None,
        sort_by: Optional[str] = "name",
        sort_order: Optional[str] = "asc",
    ) -> Dict[str, Any]:
        """Fetch paginated CIs wrapped in the standard response envelope.

        Items are serialised to plain dicts so the response is valid JSON.
        """
        items, total = await self.ci_repo.get_cis_paginated(
            page=page,
            page_size=page_size,
            search=search,
            source_system=source_system,
            ci_type=ci_type,
            vendor=vendor,
            health_tier=health_tier,
            status=status,
            location=location,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_pages = max(1, (total + page_size - 1) // page_size)

        return {
            "items": orm_list_to_dicts(items),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    async def get_network_devices(
        self, page: int = 1, page_size: int = 25, search: Optional[str] = None,
        ci_type: Optional[str] = None, vendor: Optional[str] = None,
        health_tier: Optional[str] = None, status: Optional[str] = None,
        location: Optional[str] = None, sort_by: Optional[str] = "name",
        sort_order: Optional[str] = "asc",
    ) -> Dict[str, Any]:
        """Return source-backed SolarWinds network-device inventory."""
        items, total = await self.ci_repo.get_network_devices(
            page=page, page_size=page_size, search=search, ci_type=ci_type,
            vendor=vendor, health_tier=health_tier, status=status,
            location=location, sort_by=sort_by, sort_order=sort_order,
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": orm_list_to_dicts(items), "total": total, "page": page,
            "page_size": page_size, "total_pages": total_pages,
            "has_next": page < total_pages, "has_prev": page > 1,
            "data_lineage": "SOLARWINDS_NODES",
            "classification": "vendor_and_machine_type",
        }

    async def get_ci_by_id(self, ci_id: str | uuid.UUID) -> Optional[Any]:
        """Fetch a specific CI record by UUID, serialised to a plain dict."""
        record = await self.ci_repo.get_by_id(ci_id)
        return orm_to_dict(record) if record is not None else None

    async def get_cmdb_summary(self) -> Dict[str, Any]:
        """Retrieve aggregated CMDB health and inventory metrics."""
        return await summary_cache.get_or_load(
            summary_cache_key(getattr(self.ci_repo, "session", None), "cmdb"),
            self.ci_repo.get_cmdb_summary,
        )

    async def get_intune_summary(self) -> Dict[str, Any]:
        """Microsoft Intune telemetry and compliance metrics, computed from the database.

        Raises:
            EmptyDatasetError: If no Intune CIs have been ingested. The API layer
                translates this into HTTP 503 rather than serving placeholder data.
        """
        return await summary_cache.get_or_load(
            summary_cache_key(getattr(self.ci_repo, "session", None), "intune"),
            self.summary_repo.get_intune_summary,
        )

    async def get_intune_device_count_forecast(self) -> Dict[str, Any]:
        """Return the short-term Intune inventory trend estimate."""
        return await self.summary_repo.get_intune_device_count_forecast()

    async def get_solarwinds_summary(self) -> Dict[str, Any]:
        """SolarWinds Orion node telemetry and health metrics, computed from the database.

        Raises:
            EmptyDatasetError: If no SolarWinds CIs have been ingested.
        """
        return await summary_cache.get_or_load(
            summary_cache_key(getattr(self.ci_repo, "session", None), "solarwinds"),
            self.summary_repo.get_solarwinds_summary,
        )

    async def get_solarwinds_sites(self) -> List[Dict[str, Any]]:
        """Return the site catalog used by the infrastructure dashboard."""
        return await self.ci_repo.get_solarwinds_sites()

    async def get_solarwinds_site_trend(
        self, site_id: str, hours: int = 24
    ) -> Dict[str, Any]:
        """Return the requested availability trend for an infrastructure site."""
        return await self.ci_repo.get_solarwinds_site_trend(site_id, hours=hours)

    async def get_ci_history(
        self, ci_id: str | uuid.UUID, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve time-series state history for a specific CI, as plain dicts."""
        records = await self.ci_repo.get_history_by_ci_id(ci_id, limit=limit)
        return orm_list_to_dicts(records)

    async def get_ci_relationships(self, ci_id: str | uuid.UUID) -> List[Dict[str, Any]]:
        """Retrieve graph relationships for a specific CI, as plain dicts."""
        records = await self.ci_repo.get_relationships_by_ci_id(ci_id)
        return orm_list_to_dicts(records)
