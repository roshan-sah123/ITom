"""Asynchronous repository for ConfigurationItem querying, filtering, and CMDB analytics."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, desc, false, func, not_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ci import CIRelationship, ConfigurationItem
from app.models.history import CIStatusHistory
from app.models.location import Location
from app.repositories.base import BaseRepository
from app.repositories.solarwinds_categories import category_counts
from app.repositories.decision_metrics import resources, above_resource_thresholds

logger = logging.getLogger("itom.ci_repo")

NETWORK_VENDORS = {
    "Cisco", "Juniper", "Arista", "Fortinet", "Palo Alto", "Check Point",
    "Extreme", "HPE Aruba", "Ubiquiti", "F5", "MikroTik",
}
NETWORK_TYPE_TERMS = (
    "switch", "router", "firewall", "wireless", "wlc", "access point",
    "network", "catalyst", "asa", "nexus", "fortigate", "palo alto",
)
SERVER_TYPE_TERMS = ("server", "linux", "ubuntu", "redhat", "centos", "esx", "hyper-v", "nutanix", "freebsd")
SORTABLE_CI_COLUMNS = {
    "name", "source_system", "ci_type", "status", "health_tier", "vendor",
    "location", "last_sync_time", "updated_at",
}


class InventoryUnavailableError(RuntimeError):
    """Inventory could not be read from its datastore."""


class CIRepository(BaseRepository[ConfigurationItem]):
    """High-performance repository for Configuration Items and CMDB metadata."""

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        super().__init__(ConfigurationItem, session)

    async def get_by_id(self, id: uuid.UUID | str) -> Optional[Any]:
        """Fetch a single record by primary key."""
        if self.session is None:
            return None

        try:
            target_id = uuid.UUID(str(id)) if isinstance(id, str) else id
            statement = select(self.model).where(self.model.id == target_id)
            result = await self.session.execute(statement)
            ci = result.scalars().first()
            if ci:
                return ci
        except Exception:
            pass

        return None

    async def get_by_source_key(
        self, source_system: str, source_id: str
    ) -> Optional[ConfigurationItem]:
        """Find CI by composite natural key (source_system, source_id)."""
        if self.session is None:
            return None

        try:
            stmt = select(ConfigurationItem).where(
                ConfigurationItem.source_system == source_system.upper(),
                ConfigurationItem.source_id == source_id,
            ).execution_options(include_retired=True)
            result = await self.session.execute(stmt)
            return result.scalars().first()
        except Exception:
            raise

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
        location_id: Optional[str] = None,
        network_only: bool = False,
        server_only: bool = False,
        category: Optional[str] = None,
        category_missing: bool = False,
        source_type: Optional[str] = None,
        resource_pressure: bool = False,
        ci_type_exact: bool = False,
        sort_by: Optional[str] = "name",
        sort_order: Optional[str] = "asc",
    ) -> Tuple[List[Any], int]:
        """Execute sub-20ms paginated query with multi-column filtering and indexing."""
        if self.session is None:
            return [], 0

        try:
            stmt = select(ConfigurationItem)
            count_stmt = select(func.count()).select_from(ConfigurationItem)

            # Filters
            filters = []
            if resource_pressure:
                # Reuse the summary's validated readings, including legacy JSON
                # aliases and malformed-value handling, before count/pagination.
                readings = (await self.session.execute(select(
                    ConfigurationItem.id, ConfigurationItem.attributes
                ).where(ConfigurationItem.source_system == 'SOLARWINDS',
                        ConfigurationItem.is_active.is_(True)))).all()
                pressure_ids = [row.id for row in readings
                                if above_resource_thresholds(*resources(row.attributes))]
                filters.append(ConfigurationItem.id.in_(pressure_ids))
            if source_system:
                filters.append(ConfigurationItem.source_system == source_system.upper())
            if category is not None:
                filters.append(ConfigurationItem.attributes['node_category'].as_string() == category)
            if source_type is not None:
                filters.append(ConfigurationItem.attributes['node_type'].as_string() == source_type)
            if category_missing:
                filters.append(or_(ConfigurationItem.attributes['node_category'].as_string().is_(None),
                                   func.trim(ConfigurationItem.attributes['node_category'].as_string()) == ''))
            if ci_type:
                filters.append(ConfigurationItem.ci_type == ci_type if ci_type_exact
                               else ConfigurationItem.ci_type.ilike(f"%{ci_type}%"))
            if vendor:
                filters.append(ConfigurationItem.vendor.ilike(f"%{vendor}%"))
            if health_tier:
                filters.append(ConfigurationItem.health_tier.ilike(health_tier))
            if status:
                filters.append(ConfigurationItem.status.ilike(status))
            if location_id:
                filters.append(ConfigurationItem.location_id.is_(None) if location_id == 'unassigned'
                               else ConfigurationItem.location_id == location_id)
            if location:
                normalized_location = location.strip()
                if normalized_location.lower() == "unassigned":
                    filters.append(
                        or_(
                            ConfigurationItem.location.is_(None),
                            func.trim(ConfigurationItem.location) == "",
                        )
                    )
                elif normalized_location:
                    filters.append(func.lower(func.trim(ConfigurationItem.location)) == normalized_location.lower())
            if network_only:
                type_filters = [
                    func.lower(ConfigurationItem.ci_type).like(f"%{term}%")
                    for term in NETWORK_TYPE_TERMS
                ]
                filters.append(
                    or_(
                        ConfigurationItem.vendor.in_(NETWORK_VENDORS),
                        *type_filters,
                    )
                )
            if server_only:
                network_terms = [func.lower(ConfigurationItem.ci_type).like(f"%{term}%") for term in NETWORK_TYPE_TERMS]
                server_terms = [func.lower(ConfigurationItem.ci_type).like(f"%{term}%") for term in SERVER_TYPE_TERMS]
                is_network = or_(ConfigurationItem.vendor.in_(NETWORK_VENDORS), *network_terms)
                filters.append(and_(not_(is_network), or_(*server_terms)))

            if search and "\x00" in search:
                # SQLite LIKE truncates at NUL; never send a truncated pattern
                # that can turn an invalid search into a fleet-wide match.
                filters.append(false())
            elif search and search.strip():
                s = f"%{search.strip()}%"
                filters.append(
                    or_(
                        ConfigurationItem.name.ilike(s),
                        ConfigurationItem.ip_address.ilike(s),
                        ConfigurationItem.serial_number.ilike(s),
                        ConfigurationItem.vendor.ilike(s),
                        ConfigurationItem.source_id.ilike(s),
                        ConfigurationItem.operating_system.ilike(s),
                    )
                )

            if filters:
                stmt = stmt.where(*filters)
                count_stmt = count_stmt.where(*filters)

            # Count total matching records
            total_res = await self.session.execute(count_stmt)
            total = total_res.scalar_one() or 0

            # Sorting
            sort_col = getattr(
                ConfigurationItem,
                sort_by if sort_by in SORTABLE_CI_COLUMNS else "name",
                ConfigurationItem.name,
            )
            if (sort_order or "asc").lower() == "desc":
                stmt = stmt.order_by(desc(sort_col))
            else:
                stmt = stmt.order_by(sort_col)

            # Pagination window
            offset = max(0, (page - 1) * page_size)
            stmt = stmt.offset(offset).limit(page_size)

            result = await self.session.execute(stmt)
            items = list(result.scalars().all())

            return items, total

        except SQLAlchemyError as exc:
            logger.exception("Inventory datastore query failed")
            raise InventoryUnavailableError("Inventory datastore unavailable") from exc

    async def get_location_names(self, location_ids: set[str]) -> Dict[str, str]:
        """Resolve the current page's canonical names in one bounded query."""
        if self.session is None or not location_ids:
            return {}
        try:
            rows = await self.session.execute(select(Location.id, Location.name).where(Location.id.in_(location_ids)))
            return dict(rows.all())
        except SQLAlchemyError as exc:
            logger.exception("Reporting location lookup failed")
            raise InventoryUnavailableError("Inventory datastore unavailable") from exc

    async def get_network_devices(
        self,
        page: int = 1,
        page_size: int = 25,
        search: Optional[str] = None,
        ci_type: Optional[str] = None,
        vendor: Optional[str] = None,
        health_tier: Optional[str] = None,
        status: Optional[str] = None,
        location: Optional[str] = None,
        sort_by: Optional[str] = "name",
        sort_order: Optional[str] = "asc",
    ) -> Tuple[List[Any], int]:
        """Return the existing SolarWinds node inventory classified as network gear.

        This intentionally does not claim interface, volume, or alert telemetry.
        Classification is traceable to the persisted SolarWinds vendor and
        ``MachineType``/CI type fields.
        """
        return await self.get_cis_paginated(
            page=page,
            page_size=page_size,
            search=search,
            source_system="SOLARWINDS",
            ci_type=ci_type,
            vendor=vendor,
            health_tier=health_tier,
            status=status,
            location=location,
            network_only=True,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    async def get_server_devices(self, **kwargs) -> Tuple[List[Any], int]:
        """Return only classified SolarWinds servers, excluding network/unknown roles."""
        return await self.get_cis_paginated(source_system="SOLARWINDS", server_only=True, **kwargs)

    async def get_cmdb_summary(self) -> Dict[str, Any]:
        """Aggregate fleet metrics, vendor distributions, and health tier breakdown."""
        if self.session is None:
            return {
                "data_available": False,
                "total_cis": 0,
                "high_health_count": 0,
                "medium_health_count": 0,
                "low_health_count": 0,
                "total_servers": 0,
                "total_network_devices": 0,
                "total_unclassified": 0,
                "total_other_categories": 0,
                "total_endpoints": 0,
                "health_breakdown": {},
                "status_breakdown": {},
                "ci_type_distribution": {},
                "vendor_distribution": {},
                "compliance_rate_pct": None,
            }

        try:
            # Total counts
            total = await self.count()
            if total == 0:
                from app.repositories.freshness_repository import FreshnessRepository
                freshness = await FreshnessRepository(self.session).get_freshness()
                available = all(freshness["sources"][source].get("last_synchronized_at")
                                for source in ("INTUNE", "SOLARWINDS"))
                return {
                    "data_available": available,
                    "source_breakdown": {"INTUNE": 0, "SOLARWINDS": 0} if available else {},
                    "total_cis": 0,
                    "high_health_count": 0,
                    "medium_health_count": 0,
                    "low_health_count": 0,
                    "total_servers": 0,
                    "total_network_devices": 0,
                    "total_unclassified": 0,
                    "total_other_categories": 0,
                    "total_endpoints": 0,
                    "health_breakdown": {},
                    "status_breakdown": {},
                    "ci_type_distribution": {},
                    "vendor_distribution": {},
                    "compliance_rate_pct": None,
                }

            # Health tier breakdown
            health_stmt = select(
                ConfigurationItem.health_tier, func.count(ConfigurationItem.id)
            ).group_by(ConfigurationItem.health_tier)
            health_res = await self.session.execute(health_stmt)
            health_breakdown = {row[0]: row[1] for row in health_res.all()}

            # Status breakdown
            status_stmt = select(
                ConfigurationItem.status, func.count(ConfigurationItem.id)
            ).group_by(ConfigurationItem.status)
            status_res = await self.session.execute(status_stmt)
            status_breakdown = {row[0]: row[1] for row in status_res.all()}

            # CI Type breakdown
            type_stmt = select(
                ConfigurationItem.ci_type, func.count(ConfigurationItem.id)
            ).group_by(ConfigurationItem.ci_type)
            type_res = await self.session.execute(type_stmt)
            ci_type_distribution = {row[0]: row[1] for row in type_res.all()}

            # Vendor distribution
            vendor_stmt = select(
                ConfigurationItem.vendor, func.count(ConfigurationItem.id)
            ).group_by(ConfigurationItem.vendor)
            vendor_res = await self.session.execute(vendor_stmt)
            vendor_distribution = {row[0]: row[1] for row in vendor_res.all()}

            # Role categorization using canonical network and server rules
            source_stmt = select(
                ConfigurationItem.source_system, func.count(ConfigurationItem.id)
            ).group_by(ConfigurationItem.source_system)
            source_res = await self.session.execute(source_stmt)
            source_counts = {row[0]: row[1] for row in source_res.all()}
            endpoints = source_counts.get("INTUNE", 0)

            sw_stmt = select(
                ConfigurationItem.vendor,
                ConfigurationItem.ci_type,
                func.count(ConfigurationItem.id),
            ).where(ConfigurationItem.source_system == "SOLARWINDS").group_by(
                ConfigurationItem.vendor, ConfigurationItem.ci_type
            )
            sw_res = await self.session.execute(sw_stmt)

            SERVER_TERMS = ("server", "linux", "ubuntu", "redhat", "centos", "esx", "hyper-v", "nutanix", "freebsd")
            network_devices = 0
            servers = 0
            unclassified = 0
            for v, t, count in sw_res.all():
                v_low = (v or "").strip().lower()
                t_low = (t or "").strip().lower()
                c = int(count)
                is_net = any(nv.lower() in v_low for nv in NETWORK_VENDORS) or any(nt in t_low for nt in NETWORK_TYPE_TERMS)
                if is_net:
                    network_devices += c
                elif any(st in t_low for st in SERVER_TERMS):
                    servers += c
                else:
                    unclassified += c

            category_rows = (await self.session.execute(select(
                ConfigurationItem.status,
                ConfigurationItem.attributes,
            ).where(ConfigurationItem.source_system == "SOLARWINDS"))).all()
            native_categories = category_counts(category_rows)
            has_native_categories = native_categories["total_devices"] > native_categories["unclassified_count"]
            other_categories = 0
            if has_native_categories:
                servers = native_categories["server_count"]
                network_devices = native_categories["network_count"]
                unclassified = native_categories["unclassified_count"]
                other_categories = native_categories["other_count"]

            high_health = health_breakdown.get("High", 0)
            med_health = health_breakdown.get("Medium", 0)
            low_health = health_breakdown.get("Low", 0)

            # Compliance belongs to Intune; every Intune device is in the denominator.
            compliant_stmt = select(func.count(ConfigurationItem.id)).where(
                ConfigurationItem.source_system == "INTUNE",
                func.lower(func.trim(ConfigurationItem.status)) == "compliant",
            )
            comp_count = (await self.session.execute(compliant_stmt)).scalar_one()
            comp_rate = round((comp_count / endpoints) * 100.0, 2) if endpoints > 0 else 0.0

            return {
                "data_available": True,
                "source_breakdown": dict((await self.session.execute(select(
                    ConfigurationItem.source_system, func.count(ConfigurationItem.id)
                ).group_by(ConfigurationItem.source_system))).all()),
                "total_cis": total,
                "high_health_count": high_health,
                "medium_health_count": med_health,
                "low_health_count": low_health,
                "total_servers": servers,
                "total_network_devices": network_devices,
                "total_endpoints": endpoints,
                "total_unclassified": unclassified,
                "total_other_categories": other_categories,
                "unclassified_count": unclassified,
                "classification_model": "source_categories_v1" if has_native_categories else "canonical_rules_v2",
                "health_breakdown": health_breakdown,
                "status_breakdown": status_breakdown,
                "ci_type_distribution": ci_type_distribution,
                "vendor_distribution": vendor_distribution,
                "compliance_rate_pct": comp_rate,
            }

        except Exception as exc:
            logger.debug("Database query fallback triggered in get_cmdb_summary: %s", exc)
            return {
                "data_available": False,
                "total_cis": 0,
                "high_health_count": 0,
                "medium_health_count": 0,
                "low_health_count": 0,
                "total_servers": 0,
                "total_network_devices": 0,
                "total_unclassified": 0,
                "total_other_categories": 0,
                "total_endpoints": 0,
                "health_breakdown": {},
                "status_breakdown": {},
                "ci_type_distribution": {},
                "vendor_distribution": {},
                "compliance_rate_pct": None,
            }

    async def get_history_by_ci_id(
        self, ci_id: uuid.UUID | str, limit: int = 50
    ) -> List[CIStatusHistory]:
        """Fetch temporal status and health transition records for a specific CI."""
        if self.session is None:
            return []
        try:
            target_id = uuid.UUID(str(ci_id)) if isinstance(ci_id, str) else ci_id
            stmt = (
                select(CIStatusHistory)
                .where(CIStatusHistory.ci_id == target_id)
                .order_by(desc(CIStatusHistory.recorded_at))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception:
            return []

    async def get_relationships_by_ci_id(
        self, ci_id: uuid.UUID | str
    ) -> List[CIRelationship]:
        """Fetch incoming and outgoing graph relationship edges for a CI."""
        if self.session is None:
            return []
        try:
            target_id = uuid.UUID(str(ci_id)) if isinstance(ci_id, str) else ci_id
            stmt = select(CIRelationship).where(
                or_(
                    CIRelationship.source_ci_id == target_id,
                    CIRelationship.target_ci_id == target_id,
                )
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception:
            return []

    async def get_solarwinds_sites(self) -> List[Dict[str, Any]]:
        """Return the source-backed, canonical SolarWinds location catalog.

        A location's display name is the most frequently occurring spelling in
        the persisted SolarWinds custom-property data. Grouping uses a trimmed,
        case-insensitive key so values such as ``BANGALORE`` and ``Bangalore``
        never create separate device groups. The raw source value itself is not
        overwritten.
        """
        # If session is active, aggregate from persisted CIs
        if self.session is not None:
            try:
                # Treat null, empty, and whitespace-only values as a single
                # explicitly labelled bucket. The resulting catalog remains
                # derived entirely from persisted SolarWinds data.
                unassigned_marker = "__UNASSIGNED_LOCATION__"
                source_location = func.coalesce(
                    func.nullif(func.trim(ConfigurationItem.location), ""),
                    unassigned_marker,
                ).label("source_location")
                normalized_location = func.lower(source_location).label("location_key")

                # First determine the canonical SolarWinds spelling per
                # normalized key. Choosing the most common source spelling is
                # deterministic and avoids an application-maintained alias map.
                spelling_stmt = (
                    select(
                        normalized_location,
                        source_location,
                        func.count(ConfigurationItem.id).label("source_count"),
                    )
                    .where(ConfigurationItem.source_system == "SOLARWINDS")
                    .group_by(normalized_location, source_location)
                )
                spelling_rows = (await self.session.execute(spelling_stmt)).all()
                canonical_by_key: Dict[str, str] = {}
                for key, raw_value, count in spelling_rows:
                    normalized_key = str(key or unassigned_marker.lower())
                    candidate = str(raw_value or unassigned_marker)
                    current = canonical_by_key.get(normalized_key)
                    if current is None:
                        canonical_by_key[normalized_key] = candidate
                        continue
                    current_count = next(
                        row[2] for row in spelling_rows
                        if str(row[0] or unassigned_marker.lower()) == normalized_key and str(row[1] or unassigned_marker) == current
                    )
                    if int(count or 0) > int(current_count or 0) or (
                        int(count or 0) == int(current_count or 0) and candidate.casefold() < current.casefold()
                    ):
                        canonical_by_key[normalized_key] = candidate

                status_stmt = (
                    select(
                        normalized_location,
                        ConfigurationItem.status,
                        func.count(ConfigurationItem.id).label("status_count"),
                    )
                    .where(ConfigurationItem.source_system == "SOLARWINDS")
                    .group_by(normalized_location, ConfigurationItem.status)
                )
                rows = (await self.session.execute(status_stmt)).all()

                if rows:
                    totals: Dict[str, Dict[str, int]] = {}
                    for key, status, count in rows:
                        bucket = totals.setdefault(str(key or unassigned_marker.lower()), {
                            "total_nodes": 0, "up_nodes": 0, "down_nodes": 0,
                            "warning_nodes": 0, "critical_nodes": 0,
                        })
                        bucket["total_nodes"] += int(count or 0)
                        status_key = str(status or "").casefold()
                        if status_key == "up":
                            bucket["up_nodes"] += int(count or 0)
                        elif status_key == "down":
                            bucket["down_nodes"] += int(count or 0)
                        elif status_key == "warning":
                            bucket["warning_nodes"] += int(count or 0)
                        elif status_key == "critical":
                            bucket["critical_nodes"] += int(count or 0)

                    sites = []
                    for key, metrics in totals.items():
                        raw_location = canonical_by_key.get(key, unassigned_marker)
                        is_unassigned = raw_location == unassigned_marker
                        loc = "Unassigned" if is_unassigned else raw_location
                        tot = metrics["total_nodes"]
                        up = metrics["up_nodes"]
                        down = metrics["down_nodes"]
                        warn = metrics["warning_nodes"]
                        crit = metrics["critical_nodes"]
                        avail = round((up / tot) * 100.0, 1) if tot > 0 else 0.0
                        ht = "healthy" if avail >= 90.0 else "warning" if avail >= 75.0 else "critical"
                        region = "UNASSIGNED" if is_unassigned else None
                        site_slug = "unassigned" if is_unassigned else loc.lower().replace(" ", "_").replace("-", "_").replace(".", "")[:32]

                        sites.append({
                            "id": site_slug,
                            "name": loc,
                            "region": region,
                            "total_nodes": tot,
                            "up_nodes": up,
                            "down_nodes": down,
                            "warning_nodes": warn,
                            "critical_nodes": crit,
                            "availability_pct": avail,
                            "avg_cpu": None,
                            "avg_ram": None,
                            "health_status": ht,
                            "trend_24h": [],
                        })
                    return sorted(sites, key=lambda site: (-site["total_nodes"], site["name"].casefold()))
            except Exception as exc:
                raise RuntimeError("Location database query failed") from exc

        if self.session is None:
            raise RuntimeError("Database unavailable")
        return []

    async def get_solarwinds_site_trend(self, site_id: str, hours: int = 24) -> Dict[str, Any]:
        """Periodic performance samples are not collected; never synthesize trends."""
        return {"site_id": site_id, "hours": hours, "data_available": False,
                "reason": "Historical performance samples are not collected",
                "data_points": []}
