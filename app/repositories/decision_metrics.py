"""Explicit populations and nullable evidence for current inventory decisions."""
import math
from collections import Counter
from datetime import datetime, timedelta, timezone


def resource_value(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 100 else None


def resources(attributes):
    attrs = attributes if isinstance(attributes, dict) else {}
    def first(keys):
        return next((attrs[key] for key in keys if attrs.get(key) is not None), None)
    return resource_value(first(('cpu_load', 'CPULoad'))), resource_value(first(('memory_used', 'percent_memory_used', 'PercentMemoryUsed', 'ram_used')))


def above_resource_thresholds(cpu, memory):
    """The shared observed-pressure policy used by summaries and drill-downs."""
    return (cpu is not None and cpu >= 75) or (memory is not None and memory >= 80)


def evidence_builder(rows, source, now):
    timestamps = [row.last_sync_time.replace(tzinfo=timezone.utc) if row.last_sync_time.tzinfo is None else row.last_sync_time for row in rows if row.last_sync_time]
    observed = max(timestamps).isoformat() if timestamps else None
    def metric(numerator, denominator, known, definition, exclusions=()):
        return dict(numerator=numerator, denominator=denominator,
                    value=round(100*numerator/denominator, 2) if denominator else None,
                    known_count=known, unknown_count=denominator-known,
                    coverage_pct=round(100*known/denominator, 2) if denominator else None,
                    unit='percent', source_system=source,
                    population='Active mirrored records' if not exclusions else 'Active mirrored records excluding explicit Unmanaged',
                    definition=definition, exclusions=list(exclusions),
                    observed_at=observed, calculated_at=now.isoformat(),
                    observation_basis='Latest mirrored record sync timestamp; records may have differing source observation ages',
                    measurement_window='Current persisted snapshot; not historical uptime')
    return metric


def intune_evidence(rows, now=None):
    now = now or datetime.now(timezone.utc)
    metric = evidence_builder(rows, 'INTUNE', now)
    total = len(rows)
    state_map = {'compliant':'compliant', 'noncompliant':'noncompliant',
                 'non-compliant':'noncompliant', 'non_compliant':'noncompliant',
                 'ingraceperiod':'in_grace_period', 'error':'error', 'conflict':'conflict',
                 'configmanager':'other_known'}
    states = Counter({key:0 for key in ('compliant','noncompliant','in_grace_period','error','conflict','other_known','unknown')})
    buckets = Counter({key:0 for key in ('within_7_days','8_to_30_days','over_30_days','missing_or_invalid')})
    for row in rows:
        states[state_map.get((row.status or '').strip().casefold(), 'unknown')] += 1
        attrs = row.attributes if isinstance(row.attributes, dict) else {}
        raw = attrs.get('last_sync_date_time')
        try:
            checkin = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
            if checkin.tzinfo is None:
                checkin = checkin.replace(tzinfo=timezone.utc)
            age = now-checkin
            bucket = 'missing_or_invalid' if age < -timedelta(minutes=5) else 'within_7_days' if age <= timedelta(days=7) else '8_to_30_days' if age <= timedelta(days=30) else 'over_30_days'
        except (ValueError, TypeError, OverflowError):
            bucket = 'missing_or_invalid'
        buckets[bucket] += 1
    return dict(confirmed_compliance=metric(states['compliant'], total, total-states['unknown'], 'Confirmed compliant endpoints / all active managed endpoints; known grace and error states are reported separately'),
                recent_checkins=metric(buckets['within_7_days'], total, total-buckets['missing_or_invalid'], 'Valid Intune check-in within seven days / all active managed endpoints; this is reporting recency, not compliance evaluation time'),
                compliance_state_counts=dict(states), checkin_age_buckets=dict(buckets))


def solarwinds_evidence(rows, now=None):
    now = now or datetime.now(timezone.utc)
    metric = evidence_builder(rows, 'SOLARWINDS', now)
    total = len(rows)
    statuses = Counter((row.status or '').strip().casefold() for row in rows)
    known_states = {'up','down','warning','critical','shutdown','unmanaged'}
    unknown = sum(count for status,count in statuses.items() if status not in known_states)
    unmanaged, up = statuses['unmanaged'], statuses['up']
    cpu_known = memory_known = both = pressure = 0
    health = Counter({key:0 for key in ('normal','elevated','critical','insufficient_data')})
    for row in rows:
        cpu, memory = resources(row.attributes)
        pressure += above_resource_thresholds(cpu, memory)
        cpu_known += cpu is not None
        memory_known += memory is not None
        both += cpu is not None and memory is not None
        if (cpu is not None and cpu > 90) or (memory is not None and memory > 90):
            health['critical'] += 1
        elif (cpu is not None and cpu >= 75) or (memory is not None and memory >= 80):
            health['elevated'] += 1
        elif cpu is not None and memory is not None:
            health['normal'] += 1
        else:
            health['insufficient_data'] += 1
    measured = metric(pressure, total, both, 'Observed CPU >=75% or memory >=80% / all active nodes; coverage requires both readings and incomplete telemetry can overlap an observed breach')
    if not cpu_known and not memory_known:
        measured['value'] = None
    measured['incomplete_telemetry_count'] = total-both
    return dict(current_node_status=metric(up, total-unmanaged, total-unmanaged-unknown, 'Up / active nodes excluding explicit Unmanaged; Unknown remains in denominator', ('Explicitly Unmanaged nodes',)),
                all_fleet_up=metric(up, total, total-unknown, 'Up / all active SolarWinds nodes, including Unmanaged and Unknown'),
                status_evidence=dict(unknown_count=unknown, unmanaged_count=unmanaged, known_monitored_count=total-unmanaged-unknown),
                cpu_coverage=metric(cpu_known, total, cpu_known, 'Nodes with valid CPU percentage / all active nodes'),
                memory_coverage=metric(memory_known, total, memory_known, 'Nodes with valid memory percentage / all active nodes'),
                resource_pressure=measured, resource_health_counts=dict(health))
