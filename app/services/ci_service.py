"""Business logic service for Configuration Items, CMDB analytics, and domain telemetry."""

import os
import uuid
from typing import Any, Dict, List, Optional

from app.models.ci import CIRelationship, ConfigurationItem
from app.models.history import CIStatusHistory
from app.repositories.ci_repository import CIRepository

from app.schemas.ci import (
    CIRelationshipRead,
    CIStatusHistoryRead,
    ConfigurationItemRead,
)

def _find_project_root() -> str:
    cur = os.path.abspath(__file__)
    while cur and os.path.dirname(cur) != cur:
        cur = os.path.dirname(cur)
        if os.path.exists(os.path.join(cur, "data")):
            return cur
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PROJECT_ROOT = _find_project_root()


class CIService:
    """Service orchestrating CMDB records, search/filtering, and multi-domain summary metrics."""

    def __init__(self, ci_repo: CIRepository) -> None:
        self.ci_repo = ci_repo

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
        sort_by: Optional[str] = "name",
        sort_order: Optional[str] = "asc",
    ) -> Dict[str, Any]:
        """Fetch paginated CIs wrapped in the standard response envelope."""
        items, total = await self.ci_repo.get_cis_paginated(
            page=page,
            page_size=page_size,
            search=search,
            source_system=source_system,
            ci_type=ci_type,
            vendor=vendor,
            health_tier=health_tier,
            status=status,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_pages = max(1, (total + page_size - 1) // page_size)

        serialized_items = []
        for it in items:
            if hasattr(it, "__table__"):
                serialized_items.append(ConfigurationItemRead.model_validate(it).model_dump(mode="json"))
            else:
                serialized_items.append(it)

        return {
            "items": serialized_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    async def get_ci_by_id(self, ci_id: str | uuid.UUID) -> Optional[Any]:
        """Fetch a specific CI record by UUID."""
        ci = await self.ci_repo.get_by_id(ci_id)
        if ci is not None and hasattr(ci, "__table__"):
            return ConfigurationItemRead.model_validate(ci).model_dump(mode="json")
        return ci

    async def get_cmdb_summary(self) -> Dict[str, Any]:
        """Retrieve aggregated CMDB health and inventory metrics."""
        return await self.ci_repo.get_cmdb_summary()

    async def get_intune_summary(self) -> Dict[str, Any]:
        """Retrieve live Microsoft Intune telemetry and compliance metrics aggregated from persisted CIs."""
        return await self.ci_repo.get_intune_summary()

    async def get_solarwinds_summary(self) -> Dict[str, Any]:
        """Retrieve live SolarWinds Orion server node telemetry and health metrics aggregated from persisted CIs."""
        return await self.ci_repo.get_solarwinds_summary()

    async def get_ci_history(self, ci_id: str | uuid.UUID, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve time-series state history for a specific CI."""
        records = await self.ci_repo.get_history_by_ci_id(ci_id, limit=limit)
        serialized = []
        for r in records:
            if hasattr(r, "__table__"):
                serialized.append(CIStatusHistoryRead.model_validate(r).model_dump(mode="json"))
            elif hasattr(r, "to_dict"):
                serialized.append(r.to_dict())
            else:
                serialized.append(r)
        return serialized

    async def get_ci_relationships(self, ci_id: str | uuid.UUID) -> List[Dict[str, Any]]:
        """Retrieve graph relationships for a specific CI."""
        records = await self.ci_repo.get_relationships_by_ci_id(ci_id)
        serialized = []
        for r in records:
            if hasattr(r, "__table__"):
                serialized.append(CIRelationshipRead.model_validate(r).model_dump(mode="json"))
            elif hasattr(r, "to_dict"):
                serialized.append(r.to_dict())
            else:
                serialized.append(r)
        return serialized

    async def get_solarwinds_sites(self) -> List[Dict[str, Any]]:
        """Retrieve 60-campus location breakdown with health status and sparkline trends."""
        return await self.ci_repo.get_solarwinds_sites()

    async def get_solarwinds_site_trend(self, site_id: str, hours: int = 24) -> Dict[str, Any]:
        """Retrieve 24h historical availability and performance trends for a specific campus facility."""
        return await self.ci_repo.get_solarwinds_site_trend(site_id, hours=hours)


