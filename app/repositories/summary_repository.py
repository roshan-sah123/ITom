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
                 status_counts          -> normalized chart-ready availability
                                           counts (lowercase keys)

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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ci import ConfigurationItem
from app.models.sync import SyncRun
from app.repositories.decision_metrics import intune_evidence, solarwinds_evidence, resources

logger = logging.getLogger("itom.summary")

# Age buckets for stale-asset reporting, in days. An asset that stopped
# reporting yesterday is an incident; one that stopped six months ago is a
# records-cleanup task. The dashboard should be able to tell them apart.
STALE_AGE_BUCKETS = [
    ("0-1 days", 0, 2),
    ("2-7 days", 2, 8),
    ("8-30 days", 8, 31),
    ("31-90 days", 31, 90),
    ("90+ days", 90, None),
]

# Compliance state tokens, normalised to lowercase before comparison.
COMPLIANT_STATES: Set[str] = {"compliant"}
NONCOMPLIANT_STATES: Set[str] = {"noncompliant", "non-compliant", "non_compliant"}

# SolarWinds operational statuses considered "reachable and monitored".
AVAILABLE_STATUSES: Set[str] = {"up"}

# Statuses meaning "this node is not actively monitored by Orion".
UNMONITORED_STATUSES: Set[str] = {"unmanaged", "unknown"}

SOLARWINDS_NETWORK_VENDOR_TERMS = (
    "cisco", "juniper", "arista", "fortinet", "palo alto", "check point",
    "extreme", "hpe aruba", "ubiquiti", "f5", "mikrotik",
)
SOLARWINDS_NETWORK_TYPE_TERMS = (
    "switch", "router", "firewall", "wireless", "wlc", "access point",
    "network", "catalyst", "asa", "nexus", "fortigate", "palo alto",
)
SOLARWINDS_SERVER_TYPE_TERMS = (
    "server", "linux", "ubuntu", "redhat", "centos", "esx", "hyper-v",
    "nutanix", "freebsd",
)


def _solarwinds_role(vendor: Optional[str], ci_type: Optional[str]) -> str:
    """Classify a SolarWinds CI using the same precedence as fleet summaries."""
    vendor_value = (vendor or "").strip().lower()
    type_value = (ci_type or "").strip().lower()
    is_network = (
        any(term in vendor_value for term in SOLARWINDS_NETWORK_VENDOR_TERMS)
        or any(term in type_value for term in SOLARWINDS_NETWORK_TYPE_TERMS)
    )
    if is_network:
        return "network"
    if any(term in type_value for term in SOLARWINDS_SERVER_TYPE_TERMS):
        return "server"
    return "unclassified"


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


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return a timezone-aware UTC datetime, tolerating naive database values."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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

    async def get_intune_device_count_forecast(
        self, window_days: int = 14, horizon_days: int = 7, min_observations: int = 7
    ) -> Dict[str, Any]:
        """Project the Intune inventory count from the latest successful daily syncs."""
        now = datetime.now(timezone.utc)
        window_start = now.date() - timedelta(days=window_days - 1)
        response: Dict[str, Any] = {
            "forecast_available": False,
            "source_system": "INTUNE",
            "metric": "managed_device_count",
            "horizon_days": horizon_days,
            "window_days": window_days,
            "minimum_observations": min_observations,
            "observed_days": 0,
            "method": "linear trend of latest successful sync count per UTC day",
            "notice": "This is a simple trend estimate, not a machine-learning prediction. Onboarding, retirement, or sync gaps can change the result.",
        }
        if self.session is None:
            response["reason"] = "Database is unavailable."
            return response

        statement = select(SyncRun.completed_at, SyncRun.records_processed).where(
            SyncRun.source_system == "INTUNE",
            SyncRun.status == "SUCCESS",
            SyncRun.completed_at.is_not(None),
            SyncRun.completed_at >= datetime.combine(
                window_start, datetime.min.time(), tzinfo=timezone.utc
            ),
        )
        result = await self.session.execute(statement)
        daily_latest: Dict[Any, tuple[datetime, int]] = {}
        for completed_at, count in result.all():
            completed_utc = _as_utc(completed_at)
            if completed_utc is None or completed_utc.date() > now.date():
                continue
            day = completed_utc.date()
            if day not in daily_latest or completed_utc > daily_latest[day][0]:
                daily_latest[day] = (completed_utc, max(0, int(count or 0)))

        observations = sorted(daily_latest.items())
        response["observed_days"] = len(observations)
        if len(observations) < min_observations:
            response["reason"] = (
                f"Need {min_observations} successful daily observations; "
                f"found {len(observations)} in the last {window_days} days."
            )
            return response

        first_day = observations[0][0]
        x_values = [(day - first_day).days for day, _ in observations]
        y_values = [value for _, (_, value) in observations]
        x_mean = sum(x_values) / len(x_values)
        y_mean = sum(y_values) / len(y_values)
        variance = sum((x - x_mean) ** 2 for x in x_values)
        slope = (
            sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / variance
            if variance else 0.0
        )
        latest_day, (latest_at, latest_count) = observations[-1]
        target_x = (latest_day + timedelta(days=horizon_days) - first_day).days
        forecast_count = max(0, round(y_mean + slope * (target_x - x_mean)))
        response.update({
            "forecast_available": True,
            "current_count": latest_count,
            "forecast_count": forecast_count,
            "change_count": forecast_count - latest_count,
            "trend_per_day": round(slope, 2),
            "observed_from": observations[0][0].isoformat(),
            "observed_through": latest_day.isoformat(),
            "as_of": latest_at.isoformat(),
        })
        return response

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
            "avg_storage_used_pct": None,
            "fleet_capacity_used_pct": None,
            "median_device_storage_used_pct": None,
            "storage_sample_size": 0,
            "storage_coverage_pct": 0.0,
            "missing_storage_record_count": 0,
            "invalid_storage_record_count": 0,
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
        missing_count = 0
        invalid_count = 0

        for attrs in rows:
            if not isinstance(attrs, dict):
                continue
            raw_total = attrs.get("total_storage_bytes")
            raw_free = attrs.get("free_storage_bytes")

            if raw_total is None or raw_free is None:
                missing_count += 1
                continue
            if (not isinstance(raw_total, (int, float)) or isinstance(raw_total, bool)
                    or not isinstance(raw_free, (int, float))
                    or isinstance(raw_free, bool) or raw_free < 0 or raw_free > raw_total):
                invalid_count += 1
                continue
            if raw_total <= 0:
                invalid_count += 1
                continue

            tot = float(raw_total)
            free = float(raw_free)

            total_bytes += tot
            free_bytes += free
            per_device_pct.append(((tot - free) / tot) * 100.0)

        sample = len(per_device_pct)
        if sample == 0 or total_bytes <= 0:
            return {**empty, "missing_storage_record_count": missing_count,
                    "invalid_storage_record_count": invalid_count, "storage_coverage_pct": 0.0}

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
            "missing_storage_record_count": missing_count,
            "invalid_storage_record_count": invalid_count,
        }

    async def _last_successful_sync_start(self, source_system: str) -> Optional[datetime]:
        """When the most recent successful sync for a source BEGAN.

        The start time is the correct reference, not the completion time. Every
        CI the source returned had its ``last_sync_time`` stamped at some point
        between start and completion, so a CI whose ``last_sync_time`` predates
        the start was NOT in that extraction.
        """
        stmt = (
            select(func.max(SyncRun.started_at))
            .where(SyncRun.status == "SUCCESS")
            .where(SyncRun.source_system.in_([source_system.upper(), "ALL"]))
        )
        result = await self.session.execute(stmt)
        return _as_utc(result.scalar_one_or_none())

    async def get_stale_assets(
        self,
        source_system: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Assets held in the CMDB that the source system no longer reports.

        WHY THIS MATTERS
        ----------------
        These are not bad records to be purged. Each one is an asset the
        organisation still has on its books but which has stopped appearing in
        Intune or SolarWinds. That gap is the finding:

            * a laptop that stopped checking in - lost, stolen, or failed
            * a server decommissioned without a CMDB update
            * a licence still being paid for on a machine nobody uses
            * a node dropped from monitoring, so nobody is watching it

        HOW STALENESS IS DETERMINED
        ---------------------------
        Every sync stamps ``last_sync_time`` on every CI the source returned -
        including unchanged ones. So a CI whose ``last_sync_time`` predates the
        start of the last successful sync was absent from that extraction.

        No schema change and no extra bookkeeping: the evidence is already in
        the data.

        Args:
            source_system: ``INTUNE``, ``SOLARWINDS``, or None for all sources.
            limit: How many individual asset records to return (0 for none).

        Returns:
            Counts, breakdowns for charting, and a sample of the assets.
        """
        if self.session is None:
            raise EmptyDatasetError(source_system or "ALL")

        now = datetime.now(timezone.utc)
        wanted = [source_system.upper()] if source_system else ["INTUNE", "SOLARWINDS"]

        reference: Dict[str, Optional[str]] = {}
        stale_rows: List[Any] = []
        active_by_source: Dict[str, int] = {}
        stale_by_source: Dict[str, int] = {}

        for src in wanted:
            cutoff = await self._last_successful_sync_start(src)
            reference[src] = cutoff.isoformat() if cutoff else None

            total = int((await self.session.execute(
                select(func.count(ConfigurationItem.id))
                .where(ConfigurationItem.source_system == src)
            )).scalar_one())

            if cutoff is None:
                # Never synced successfully - staleness is not measurable, and
                # guessing would be worse than saying so.
                active_by_source[src] = total
                stale_by_source[src] = 0
                continue

            rows = (await self.session.execute(
                select(ConfigurationItem)
                .where(ConfigurationItem.source_system == src)
                .where(ConfigurationItem.last_sync_time < cutoff)
                .order_by(ConfigurationItem.last_sync_time.asc())
            )).scalars().all()

            stale_rows.extend(rows)
            stale_by_source[src] = len(rows)
            active_by_source[src] = total - len(rows)

        total_cis = sum(active_by_source.values()) + sum(stale_by_source.values())
        stale_count = len(stale_rows)

        # Breakdowns for the dashboard.
        by_age: Dict[str, int] = {label: 0 for label, _, _ in STALE_AGE_BUCKETS}
        by_location: Dict[str, int] = {}
        by_vendor: Dict[str, int] = {}
        by_last_status: Dict[str, int] = {}
        by_ci_type: Dict[str, int] = {}

        assets: List[Dict[str, Any]] = []

        for row in stale_rows:
            last_seen = _as_utc(row.last_sync_time)
            days = (now - last_seen).total_seconds() / 86400 if last_seen else 0.0

            for label, lower, upper in STALE_AGE_BUCKETS:
                if days >= lower and (upper is None or days < upper):
                    by_age[label] += 1
                    break

            site = (row.location or "").strip() or "Unknown"
            by_location[site] = by_location.get(site, 0) + 1
            by_vendor[row.vendor or "Other"] = by_vendor.get(row.vendor or "Other", 0) + 1
            by_last_status[row.status or "Unknown"] = by_last_status.get(row.status or "Unknown", 0) + 1
            by_ci_type[row.ci_type or "Unknown"] = by_ci_type.get(row.ci_type or "Unknown", 0) + 1

            if len(assets) < limit:
                assets.append({
                    "id": str(row.id),
                    "source_id": row.source_id,
                    "source_system": row.source_system,
                    "name": (row.name or "").strip(),
                    "ci_type": row.ci_type,
                    "last_known_status": row.status,
                    "last_known_health_tier": row.health_tier,
                    "vendor": row.vendor,
                    "model": row.model,
                    "serial_number": row.serial_number,
                    "ip_address": row.ip_address,
                    "location": row.location,
                    "last_seen_at": last_seen.isoformat() if last_seen else None,
                    "days_since_last_seen": round(days, 1),
                })

        return {
            "source_system": source_system.upper() if source_system else "ALL",
            "data_source": "DATABASE",
            "generated_at": now.isoformat(),
            "definition": (
                "Assets present in the CMDB that were absent from the most "
                "recent successful synchronization of their source system."
            ),
            "reference_sync_started_at": reference,
            "total_cis": total_cis,
            "active_cis": sum(active_by_source.values()),
            "stale_cis": stale_count,
            "stale_pct": _pct(stale_count, total_cis),
            "active_by_source": active_by_source,
            "stale_by_source": stale_by_source,
            "stale_by_age": by_age,
            "stale_by_location": dict(sorted(by_location.items(), key=lambda kv: -kv[1])),
            "stale_by_vendor": dict(sorted(by_vendor.items(), key=lambda kv: -kv[1])),
            "stale_by_last_known_status": by_last_status,
            "stale_by_ci_type": dict(sorted(by_ci_type.items(), key=lambda kv: -kv[1])),
            "returned_assets": len(assets),
            "assets": assets,
        }

    async def get_location_analytics(
        self,
        source_system: Optional[str] = None,
        sort_by: str = "total",
    ) -> Dict[str, Any]:
        """Per-location operational analytics, computed live from the database.

        SolarWinds populates ``location`` from the Orion custom property
        ``City`` (see the SWQL in ``solarwinds_client.fetch_nodes``). Intune
        managed devices carry no location field, so an Intune-scoped call will
        report everything under ``unlocated_cis``.

        Args:
            source_system: ``SOLARWINDS``, ``INTUNE``, or None for all sources.
            sort_by: ``total`` (largest sites first), ``risk`` (most unhealthy
                first), or ``name`` (alphabetical).

        Returns:
            A per-site report including availability, health mix and a
            reader-facing coverage figure so consumers can tell how much of the
            estate actually carries a location.
        """
        if self.session is None:
            raise EmptyDatasetError(source_system or "ALL")

        src = source_system.upper() if source_system else None

        def _scoped(stmt):
            return stmt.where(ConfigurationItem.source_system == src) if src else stmt

        # Normalize location with canonical spelling selection
        unassigned_marker = "__UNASSIGNED_LOCATION__"
        source_loc_col = func.coalesce(
            func.nullif(func.trim(ConfigurationItem.location), ""),
            unassigned_marker,
        )
        norm_loc_col = func.lower(source_loc_col)

        # 1. Determine canonical display spelling per normalized location key
        spelling_stmt = (
            select(
                norm_loc_col.label("norm_key"),
                source_loc_col.label("raw_val"),
                func.count(ConfigurationItem.id).label("cnt"),
            )
            .group_by(norm_loc_col, source_loc_col)
        )
        spelling_rows = (await self.session.execute(_scoped(spelling_stmt))).all()

        canonical_spellings: Dict[str, str] = {}
        counts_by_spelling: Dict[str, int] = {}
        for norm_k, raw_v, count in spelling_rows:
            nk = str(norm_k or unassigned_marker.lower())
            rv = str(raw_v or unassigned_marker)
            c = int(count or 0)
            if nk not in canonical_spellings or c > counts_by_spelling.get(nk, -1):
                canonical_spellings[nk] = rv
                counts_by_spelling[nk] = c

        # 2. Group status and health by normalized location key
        status_stmt = (
            select(
                norm_loc_col.label("norm_key"),
                ConfigurationItem.status,
                func.count(ConfigurationItem.id),
            )
            .group_by(norm_loc_col, ConfigurationItem.status)
        )
        status_rows = (await self.session.execute(_scoped(status_stmt))).all()

        health_stmt = (
            select(
                norm_loc_col.label("norm_key"),
                ConfigurationItem.health_tier,
                func.count(ConfigurationItem.id),
            )
            .group_by(norm_loc_col, ConfigurationItem.health_tier)
        )
        health_rows = (await self.session.execute(_scoped(health_stmt))).all()

        if not status_rows:
            raise EmptyDatasetError(src or "ALL")

        sites: Dict[str, Dict[str, Any]] = {}
        unlocated = 0

        for norm_key, status, count in status_rows:
            count = int(count)
            nk = str(norm_key or "").strip()
            if not nk or nk == unassigned_marker.lower():
                unlocated += count
                continue
            canonical_name = canonical_spellings.get(nk, nk)
            site = sites.setdefault(nk, {
                "location": canonical_name,
                "location_key": nk,
                "total_cis": 0,
                "status_breakdown": {},
                "health_breakdown": {"High": 0, "Medium": 0, "Low": 0},
            })
            site["total_cis"] += count
            site["status_breakdown"][status or "Unknown"] = count

        for norm_key, health, count in health_rows:
            nk = str(norm_key or "").strip()
            if not nk or nk not in sites:
                continue
            sites[nk]["health_breakdown"][health or "Medium"] = int(count)

        located = sum(site["total_cis"] for site in sites.values())
        total = located + unlocated

        for site in sites.values():
            site_total = site["total_cis"]
            available = _sum_matching(site["status_breakdown"], AVAILABLE_STATUSES)
            health = site["health_breakdown"]

            site["available_cis"] = available
            site["unavailable_cis"] = site_total - available
            site["availability_pct"] = _pct(available, site_total)
            site["high_health_count"] = health.get("High", 0)
            site["medium_health_count"] = health.get("Medium", 0)
            site["low_health_count"] = health.get("Low", 0)
            site["health_score_pct"] = _pct(health.get("High", 0), site_total)
            # Nodes needing attention: anything not in the High tier.
            site["at_risk_cis"] = health.get("Medium", 0) + health.get("Low", 0)

        ordered = list(sites.values())
        if sort_by == "risk":
            ordered.sort(key=lambda s: (-s["low_health_count"], -s["at_risk_cis"], s["location"]))
        elif sort_by == "name":
            ordered.sort(key=lambda s: s["location"].lower())
        else:
            ordered.sort(key=lambda s: (-s["total_cis"], s["location"]))

        return {
            "source_system": src or "ALL",
            "data_source": "DATABASE",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sorted_by": sort_by,
            "location_scope": "SOLARWINDS_INFRASTRUCTURE" if src == "SOLARWINDS" else "ALL",
            "scope_description": (
                "Geographic location telemetry is collected from SolarWinds Orion City/ITSM_Location properties. "
                "Microsoft Intune endpoints do not report geographic locations via Graph API."
            ),
            "total_cis": total,
            "located_cis": located,
            "unlocated_cis": unlocated,
            "location_coverage_pct": _pct(located, total),
            "total_locations": len(ordered),
            "locations": ordered,
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
        location_distribution = await self._group_count(ConfigurationItem.location, src)
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
            # Sites with no recorded location appear under the "Unknown" key,
            # so the map still sums to total_cis and remains chart-safe.
            "location_distribution": location_distribution,
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
        owner_counts: Dict[str, int] = {}
        owners = await self.session.execute(select(ConfigurationItem.status, ConfigurationItem.attributes, ConfigurationItem.last_sync_time).where(ConfigurationItem.source_system == "INTUNE", ConfigurationItem.is_active.is_(True)))
        records = owners.all()
        payload['decision_metrics'] = intune_evidence(records)
        for row in records:
            attrs = row.attributes
            owner = attrs.get("managed_device_owner_type") if isinstance(attrs, dict) else None
            owner = str(owner or "Unknown").strip() or "Unknown"
            owner_counts[owner] = owner_counts.get(owner, 0) + 1
        payload["ownership_distribution"] = owner_counts
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

        # Canonical category classification across SolarWinds nodes
        sw_cats_stmt = (
            select(
                ConfigurationItem.vendor,
                ConfigurationItem.ci_type,
                func.count(ConfigurationItem.id),
            )
            .where(ConfigurationItem.source_system == "SOLARWINDS")
            .group_by(ConfigurationItem.vendor, ConfigurationItem.ci_type)
        )
        sw_cats_res = await self.session.execute(sw_cats_stmt)

        sw_net = 0
        sw_srv = 0
        sw_uncl = 0
        for v, t, count in sw_cats_res.all():
            c = int(count)
            role = _solarwinds_role(v, t)
            if role == "network":
                sw_net += c
            elif role == "server":
                sw_srv += c
            else:
                sw_uncl += c

        # Query top saturated servers (CPU >= 75% or RAM >= 80%)
        sat_stmt = (
            select(
                ConfigurationItem.name,
                ConfigurationItem.ip_address,
                ConfigurationItem.location,
                ConfigurationItem.ci_type,
                ConfigurationItem.vendor,
                ConfigurationItem.attributes,
                ConfigurationItem.status,
                ConfigurationItem.last_sync_time,
            )
            .where(
                ConfigurationItem.source_system == "SOLARWINDS",
                ConfigurationItem.is_active == True,
            )
        )
        sat_res = await self.session.execute(sat_stmt)
        saturated_candidates: List[Dict[str, Any]] = []

        records = sat_res.all()
        payload['decision_metrics'] = solarwinds_evidence(records)
        for row in records:
            if _solarwinds_role(row.vendor, row.ci_type) != "server":
                continue

            cpu_val, ram_val = resources(row.attributes)

            if (cpu_val is not None and cpu_val >= 75.0) or (ram_val is not None and ram_val >= 80.0):
                eff_cpu = cpu_val if cpu_val is not None else 0.0
                eff_ram = ram_val if ram_val is not None else 0.0
                saturated_candidates.append({
                    "name": (row.name or "").strip(),
                    "Caption": (row.name or "").strip(),
                    "ip_address": row.ip_address or "Unavailable",
                    "location": row.location or "Unassigned",
                    "ci_type": row.ci_type,
                    "vendor": row.vendor,
                    "cpu_load": round(cpu_val, 1) if cpu_val is not None else None,
                    "CPULoad": round(cpu_val, 1) if cpu_val is not None else None,
                    "memory_used": round(ram_val, 1) if ram_val is not None else None,
                    "PercentMemoryUsed": round(ram_val, 1) if ram_val is not None else None,
                    "_score": max(eff_cpu, eff_ram),
                })

        saturated_candidates.sort(key=lambda s: -s["_score"])
        for item in saturated_candidates:
            item.pop("_score", None)

        metrics.update(
            {
                "total_nodes": total,
                # Legacy alias retained for existing consumers; use total_nodes
                # for inventory and server_nodes_count for classified servers.
                "total_server_nodes": total,
                "total_monitored_nodes": monitored,
                "server_nodes_count": sw_srv,
                "network_devices_count": sw_net,
                "unclassified_nodes_count": sw_uncl,
                "category_breakdown": {
                    "servers": sw_srv,
                    "network_devices": sw_net,
                    "unclassified": sw_uncl,
                },
                "available_nodes": available,
                "unavailable_nodes": total - available,
                "unmonitored_nodes": _sum_matching(status_breakdown, UNMONITORED_STATUSES),
                "availability_pct": _pct(available, monitored),
                "monitored_availability_pct": _pct(available, monitored),
                "total_fleet_availability_pct": _pct(available, total),
                "active_monitored_nodes": monitored,
                # Legacy aliases - same computed values, older key names.
                # High + Medium + Low always equals total_server_nodes.
                "high_health_nodes": metrics["high_health_count"],
                "medium_health_nodes": metrics["medium_health_count"],
                "low_critical_nodes": metrics["low_health_count"],
                # Contract for portal availability charts.  The raw source
                # labels remain available in payload["status_breakdown"] for
                # detail and backwards compatibility; this map deliberately
                # gives consumers one stable, normalized set of keys.
                "status_counts": {
                    "up": _sum_matching(status_breakdown, {"up"}),
                    "warning": _sum_matching(status_breakdown, {"warning"}),
                    "critical": _sum_matching(status_breakdown, {"critical"}),
                    "down": _sum_matching(status_breakdown, {"down"}),
                    "unmanaged_unknown": _sum_matching(
                        status_breakdown, UNMONITORED_STATUSES
                    ),
                },
            }
        )
        type_distribution = payload.pop("_type_distribution")
        payload["ci_type_distribution"] = type_distribution
        # Legacy alias - same live dictionary under its older key name.
        payload["node_type_breakdown"] = type_distribution
        payload["top_saturated_servers"] = saturated_candidates[:10]
        payload["total_saturated_nodes"] = len(saturated_candidates)
        payload["api_aliases"] = {"total_server_nodes": "legacy alias of total_nodes; not a server-only count"}
        return payload
