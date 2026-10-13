# Operations decision metrics

The overview presents current posture, operational exceptions and data confidence
as separate evidence. It does not add endpoints, infrastructure nodes and source
failures into a single risk number.

## How to use the overview

1. Check source freshness and summary availability. A successful refresh describes
   ingestion, not whether every device has recently checked in.
2. Read the metric's numerator, denominator and coverage. Open **Definition &
   evidence** for its population, exclusions, observation time and measurement window.
3. Use the operational queue to open matching low-tier nodes or noncompliant
   endpoints. The queue counts categories separately; they are not a deduplicated
   count of physical assets or a business-impact ranking.
4. Review data confidence before concluding that no reported exceptions means a
   healthy fleet. Missing fields, old device check-ins and failed summaries require
   their own investigation.

## Measurement policy

| Measure | Interpretation | Decision boundary |
|---|---|---|
| Confirmed endpoint compliance | Confirmed compliant / active managed endpoints; unknown states remain in the denominator | Latest reported posture, not a fresh evaluation of every policy |
| Recent endpoint check-ins | Valid check-in within seven days / active managed endpoints | Reporting recency, not compliance evaluation time; seven days is a local review policy |
| Current node Up ratio | Up / active nodes excluding explicit Unmanaged; Unknown remains in scope | Current snapshot, not uptime or an SLA |
| Observed resource pressure | Nodes with an observed CPU >=75% or memory >=80% reading / active nodes | Investigation trigger, not sustained saturation or a capacity forecast |
| CPU and memory coverage | Valid bounded percentage readings / active nodes | Missing measurements do not become zero usage or measured health |

An empty eligible population has no percentage. Invalid, missing, nonfinite,
boolean and out-of-range resource readings are unavailable. A single elevated
reading is evidence of pressure even if its companion reading is absent; full
resource assessment still needs both fields.

The resource-pressure thresholds are initial operating policies. Validate them
against workload baselines and incident outcomes before using them for purchasing
or automatic remediation.

## Compatibility and limits

Legacy summary aliases and persisted health tiers remain available for existing
consumers. In particular, a legacy High tier can be based on Up status with missing
resources. It must not be treated as proof that CPU and memory were measured healthy.
The overview presents measured resource evidence separately.

Legacy `availability_pct` excludes Unknown and Unmanaged statuses. New decision
metrics retain Unknown in the eligible monitored denominator, matching the
location score's population policy. Use the new explicit metric for portal
comparisons; do not compare the legacy percentage without accounting for exclusions.

Each source is read separately. Observation times and coverage are shown, but the
overview is not a transactionally frozen cross-source snapshot. Counts can change
between a headline and its inventory drilldown.

Service ownership, business criticality, incident age, remediation performance,
historical service availability and sustained resource-pressure trends require
additional authoritative mappings or regular observations. They are not inferred
from node counts or change-only history. No owner, SLA or trend is fabricated.

## Reference guidance

- [Google SRE monitoring](https://sre.google/sre-book/monitoring-distributed-systems/):
  latency, traffic, errors and saturation for service-level monitoring.
- [Google SLI/SLO definitions](https://sre.google/sre-book/service-level-objectives/):
  explicit populations, measurement windows and distributions.
- [Microsoft compliance reporting](https://learn.microsoft.com/en-us/intune/device-security/compliance/monitor-policy):
  distinguish compliance states and policy failures.
- [CIS Control 1](https://www.cisecurity.org/controls/inventory-and-control-of-enterprise-assets):
  inventory and visibility of unmanaged assets.

These references inform the design; they do not certify the local scoring weights
or thresholds as industry-mandated targets.
