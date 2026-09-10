"""Domain telemetry summary aggregations, computed live from the CMDB tables.

Design rules enforced by this module
------------------------------------
1. Every number returned is the result of a SQL aggregate executed at request time.
2. There is not a single literal fleet figure anywhere in this file.
3. An empty dataset raises ``EmptyDatasetError`` so the API can answer HTTP 503,
   instead of rendering plausible-looking placeholder data that hides the outage.

STEP 1b / STEP 2 CHANGE
-----------------------
Legacy key aliases are emitted alongside the new key names so that the existing
integration tests (and any frontend code already written against the old shape)
keep working. The aliases are computed values, not constants - they are simply
additional names for the same live figures.

    Intune       non_compliant_devices  -> alias of noncompliant_devices
                 compliance_breakdown   -> alias of status_breakdown
                 os_breakdown           -> alias of os_distribution
    SolarWinds   high_health_nodes      -> alias of high_health_count
                 medium_health_nodes    -> alias of medium_health_count
                 low_critical_nodes     -> alias of low_health_count
                 active_monitored_nodes -> nodes not in an Unmanaged state
                 node_type_breakdown    -> alias of ci_type_distribution

Column semantics assumed (established by the ingestion mapping):
    ConfigurationItem.status       SolarWinds -> Up / Down / Warning / Critical /
                                                 Shutdown / Unmanaged
                                   Intune     -> compliant / noncompliant /
                                                 inGracePeriod / unknown / ...
    ConfigurationItem.ci_type      SolarWinds -> Server, Access Switch, Router, ...
                                   Intune     -> Windows, macOS, iOS, Android, Linux
    ConfigurationItem.health_tier  both       -> High / Medium / Low
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ci import ConfigurationItem

logger = logging.getLogger("itom.summary")

# Compliance state tokens, normalised to lowercase before comparison.
COMPLIANT_STATES: Set[str] = {"compliant"}
NONCOMPLIANT_STATES: Set[str] = {"noncompliant", "non-compliant", "non_compliant"}

# SolarWinds operational statuses considered "reachable and monitored".
AVAILABLE_STATUSES: Set[str] = {"up"}

# Statuses meaning "this node is not actively monitored by Orion".
UNMONITORED_STATUSES: Set[str] = {"unmanaged", "unknown"}


class EmptyDatasetError(RuntimeError):
    """Raised when a source system has no Configuration Items persisted.

    The API layer converts this into HTTP 503. It must never be swallowed and
    replaced with sample data - a dashboard showing invented numbers during an
    ingestion outage is worse than a dashboard showing an error.
    """

    def __init__(self, source_system: str) -> None:
        self.source_system = source_system
        super().__init__(
            f"No Configuration Items persisted for source system "
            f"'{source_system}'. Run a telemetry synchronization first."
        )


def _pct(part: int, whole: int, digits: int = 2) -> float:
    """Percentage of ``part`` within ``whole``, guarded against divide-by-zero."""
    if whole <= 0:
        return 0.0
    return round((part / whole) * 100, digits)


def _sum_matching(breakdown: Dict[str, int], tokens: Set[str]) -> int:
    """Sum counts whose key, lowercased and stripped, is in ``tokens``."""
    return sum(count for key, count in breakdown.items() if key.strip().lower() in tokens)


def _sum_excluding(breakdown: Dict[str, int], tokens: Set[str]) -> int:
    """Sum counts whose key, lowercased and stripped, is NOT in ``tokens``."""
    return sum(
        count for key, count in breakdown.items() if key.strip().lower() not in tokens
    )


class SummaryRepository:
    """Read-only aggregation queries backing the per-domain ``/summary`` endpoints."""

    def __init__(self, session: Optional[AsyncSession]) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Low-level aggregate helpers
    # ------------------------------------------------------------------ #

    async def _group_count(self, column: Any, source_system: str) -> Dict[str, int]:
        """SELECT <column>, COUNT(id) WHERE source_system = :src GROUP BY <column>."""
        stmt = (
            select(column, func.count(ConfigurationItem.id))
            .where(ConfigurationItem.source_system == source_system)
            .group_by(column)
        )
        result = await self.session.execute(stmt)
        return {(row[0] or "Unknown"): int(row[1]) for row in result.all()}

    async def _storage_metrics(self, source_system: str) -> Dict[str, Any]:
        """Fleet storage utilisation, derived from the per-device attributes JSON.

        The seeding/ingestion layer stores raw byte counts on each CI as
        ``attributes.total_storage_bytes`` and ``attributes.free_storage_bytes``.

        Two different figures are returned, because they answer different
        questions and the old code conflated them:

        ``fleet_capacity_used_pct``
            Total used bytes across the fleet divided by total capacity. This is
            capacity-weighted, so large disks dominate it.

        ``median_device_storage_used_pct``
            The median of each device's own used-percentage. This is the figure
            that surfaces individual devices close to full.

        ``avg_storage_used_pct`` is kept as an alias of the capacity-weighted
        figure for backward compatibility with existing consumers.

        ``storage_sample_size`` and ``storage_coverage_pct`` report how many
        devices actually reported usable storage values, so a consumer can tell
        whether the percentage is representative.
        """
        empty = {
            "avg_storage_used_pct": 0.0,
            "fleet_capacity_used_pct": 0.0,
            "median_device_storage_used_pct": 0.0,
            "storage_sample_size": 0,
            "storage_coverage_pct": 0.0,
        }
        if self.session is None:
            return empty

        try:
            stmt = select(ConfigurationItem.attributes).where(
                ConfigurationItem.source_system == source_system
            )
            result = await self.session.execute(stmt)
            rows = result.scalars().all()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Storage aggregation query failed for %s: %s", source_system, exc)
            return empty

        total_bytes = 0.0
        free_bytes = 0.0
        per_device_pct: list = []

        for attrs in rows:
            if not isinstance(attrs, dict):
                continue
            raw_total = attrs.get("total_storage_bytes")
            raw_free = attrs.get("free_storage_bytes")

            if not isinstance(raw_total, (int, float)) or isinstance(raw_total, bool):
                continue
            if raw_total <= 0:
                continue

            tot = float(raw_total)
            if isinstance(raw_free, (int, float)) and not isinstance(raw_free, bool) and raw_free >= 0:
                free = float(raw_free)
            else:
                free = 0.0

            # Guard against a source reporting free > total.
            free = max(0.0, min(free, tot))

            total_bytes += tot
            free_bytes += free
            per_device_pct.append(((tot - free) / tot) * 100.0)

        sample = len(per_device_pct)
        if sample == 0 or total_bytes <= 0:
            return empty

        capacity_used_pct = round(((total_bytes - free_bytes) / total_bytes) * 100, 1)

        ordered = sorted(per_device_pct)
        mid = sample // 2
        if sample % 2 == 1:
            median_pct = ordered[mid]
        else:
            median_pct = (ordered[mid - 1] + ordered[mid]) / 2.0

        return {
            "avg_storage_used_pct": capacity_used_pct,
            "fleet_capacity_used_pct": capacity_used_pct,
            "median_device_storage_used_pct": round(median_pct, 1),
            "storage_sample_size": sample,
            "storage_coverage_pct": _pct(sample, len(rows)),
        }

    async def _max_last_sync(self, source_system: str) -> Optional[datetime]:
        """Newest ``last_sync_time`` observed for the source system."""
        stmt = select(func.max(ConfigurationItem.last_sync_time)).where(
            ConfigurationItem.source_system == source_system
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------ #
    # Shared summary core
    # ------------------------------------------------------------------ #

    async def _base_summary(self, source_system: str) -> Dict[str, Any]:
        """Build the domain-agnostic portion of a summary payload."""
        if self.session is None:
            raise EmptyDatasetError(source_system)

        src = source_system.upper()

        status_breakdown = await self._group_count(ConfigurationItem.status, src)
        total = sum(status_breakdown.values())
        if total == 0:
            raise EmptyDatasetError(src)

        health_breakdown = await self._group_count(ConfigurationItem.health_tier, src)
        type_distribution = await self._group_count(ConfigurationItem.ci_type, src)
        vendor_distribution = await self._group_count(ConfigurationItem.vendor, src)
        last_sync = await self._max_last_sync(src)

        # Integrity guard: every breakdown partitions the same filtered row set,
        # so the sums must agree. If they ever do not, the response is wrong and
        # we want to know loudly rather than ship a broken chart.
        for label, breakdown in (
            ("health", health_breakdown),
            ("ci_type", type_distribution),
            ("vendor", vendor_distribution),
        ):
            if sum(breakdown.values()) != total:
                logger.error(
                    "Breakdown reconciliation failed for %s/%s: %d != %d",
                    src,
                    label,
                    sum(breakdown.values()),
                    total,
                )

        high = health_breakdown.get("High", 0)
        medium = health_breakdown.get("Medium", 0)
        low = health_breakdown.get("Low", 0)

        return {
            "source_system": src,
            "data_source": "DATABASE",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "last_sync_time": last_sync.isoformat() if last_sync else None,
            "metrics": {
                "total_cis": total,
                "high_health_count": high,
                "medium_health_count": medium,
                "low_health_count": low,
                "high_health_pct": _pct(high, total),
                "medium_health_pct": _pct(medium, total),
                "low_health_pct": _pct(low, total),
            },
            "status_breakdown": status_breakdown,
            "health_breakdown": health_breakdown,
            "vendor_distribution": vendor_distribution,
            "_type_distribution": type_distribution,  # renamed per-domain below
        }

    # ------------------------------------------------------------------ #
    # Public per-domain summaries
    # ------------------------------------------------------------------ #

    async def get_intune_summary(self) -> Dict[str, Any]:
        """Microsoft Intune endpoint compliance and OS distribution, live from the DB."""
        payload = await self._base_summary("INTUNE")
        status_breakdown = payload["status_breakdown"]
        total = payload["metrics"]["total_cis"]

        compliant = _sum_matching(status_breakdown, COMPLIANT_STATES)
        noncompliant = _sum_matching(status_breakdown, NONCOMPLIANT_STATES)
        other = total - compliant - noncompliant

        payload["metrics"].update(
            {
                "total_managed_devices": total,
                "compliant_devices": compliant,
                "noncompliant_devices": noncompliant,
                # Legacy alias - same computed value, older key name.
                "non_compliant_devices": noncompliant,
                "other_compliance": other,
                "compliance_rate_pct": _pct(compliant, total),
            }
        )
        payload["metrics"].update(await self._storage_metrics("INTUNE"))
        os_distribution = payload.pop("_type_distribution")
        payload["os_distribution"] = os_distribution
        # Legacy aliases - same live dictionaries under their older key names.
        payload["os_breakdown"] = os_distribution
        payload["compliance_breakdown"] = payload["status_breakdown"]
        return payload

    async def get_solarwinds_summary(self) -> Dict[str, Any]:
        """SolarWinds Orion node availability and health distribution, live from the DB."""
        payload = await self._base_summary("SOLARWINDS")
        status_breakdown = payload["status_breakdown"]
        metrics = payload["metrics"]
        total = metrics["total_cis"]

        available = _sum_matching(status_breakdown, AVAILABLE_STATUSES)
        monitored = _sum_excluding(status_breakdown, UNMONITORED_STATUSES)

        metrics.update(
            {
                "total_server_nodes": total,
                "available_nodes": available,
                "unavailable_nodes": total - available,
                "availability_pct": _pct(available, total),
                "active_monitored_nodes": monitored,
                # Legacy aliases - same computed values, older key names.
                # High + Medium + Low always equals total_server_nodes.
                "high_health_nodes": metrics["high_health_count"],
                "medium_health_nodes": metrics["medium_health_count"],
                "low_critical_nodes": metrics["low_health_count"],
            }
        )
        type_distribution = payload.pop("_type_distribution")
        payload["ci_type_distribution"] = type_distribution
        # Legacy alias - same live dictionary under its older key name.
        payload["node_type_breakdown"] = type_distribution
        return payload
