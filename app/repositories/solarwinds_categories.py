"""Shared SolarWinds source-category counts and resource evidence."""
from collections import Counter, defaultdict

from app.repositories.decision_metrics import resources, above_resource_thresholds


def _category(row):
    value = getattr(row, "category", None)
    if value is None:
        attributes = getattr(row, "attributes", None)
        value = attributes.get("node_category") if isinstance(attributes, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def category_evidence(rows):
    """Aggregate native category, status, and resource evidence."""
    buckets = defaultdict(list)
    for row in rows:
        buckets[_category(row)].append(row)

    evidence = []
    for value, members in sorted(
        buckets.items(), key=lambda item: (item[0] is None, (item[0] or "").casefold())
    ):
        statuses = Counter((getattr(row, "status", None) or "Unknown") for row in members)
        health = Counter((getattr(row, "health_tier", None) or "Unknown") for row in members)
        cpu_count = memory_count = both_count = pressure_count = 0
        for row in members:
            cpu, memory = resources(getattr(row, "attributes", None))
            cpu_count += cpu is not None
            memory_count += memory is not None
            both_count += cpu is not None and memory is not None
            pressure_count += above_resource_thresholds(cpu, memory)
        evidence.append({
            "value": value,
            "name": value if value is not None else "Unclassified",
            "count": len(members),
            "status_counts": dict(sorted(statuses.items())),
            "health_counts": dict(sorted(health.items())),
            "cpu_count": cpu_count,
            "memory_count": memory_count,
            "both_resources_count": both_count,
            "resource_pressure_count": pressure_count,
        })
    return evidence


def category_counts(rows):
    """Return the compact category contract used by group scorecards."""
    categories = category_evidence(rows)
    server = sum(row["count"] for row in categories if (row["value"] or "").casefold() == "server")
    network = sum(row["count"] for row in categories if (row["value"] or "").casefold() == "network")
    unclassified = sum(row["count"] for row in categories if row["value"] is None)
    total = sum(row["count"] for row in categories)
    return {
        "total_devices": total,
        "server_count": server,
        "network_count": network,
        "other_count": total - server - network - unclassified,
        "unclassified_count": unclassified,
        "categories": [
            {"value": row["value"], "name": row["name"], "count": row["count"]}
            for row in categories
        ],
    }
