# Dashboard data confidence — 8 October 2026

**Overall assessment: 78/100.** Main inventory counts and reconciled snapshot percentages have strong evidence. Classification, device recency and interpretation of health/alert/forecast figures require caution. This is an engineering confidence assessment, not a measured 78% accuracy rate, and is separate from production-readiness scoring.

## Evidence captured

Read-only API/database check at **12:28 IST on 8 October 2026**. Rendered overview, infrastructure and endpoint pages were subsequently inspected in a temporary browser tab. No sync was triggered and no inventory was changed.

| Check | Result |
|---|---|
| Database readiness | Ready; migration marker current |
| Source ingestion | Both FRESH; latest successful runs approximately four minutes old |
| Latest run reconciliation | Intune 29,998 extracted/normalized/processed; SolarWinds 1,626; zero rejected in those runs |
| Active Intune inventory | 29,998, matching API and rendered overview |
| Active SolarWinds inventory | 1,626, matching API and rendered overview |
| Active CMDB records | 31,624 = 29,998 + 1,626 |
| Intune compliance | 25,173 compliant; 4,045 noncompliant; 780 other; compliant/total = 83.92% |
| SolarWinds monitored availability | 1,476 Up / 1,590 monitored = 92.83%; excludes 36 Unmanaged nodes |
| SolarWinds fleet availability | 1,476 / 1,626 = 90.77%; a different denominator |
| Location catalog | 68 normalized source-location groups, summing to 1,626 nodes |
| Intune storage | 35.8% capacity weighted; 34.1% median per-device usage; independently recalculated |
| Storage coverage | 29,645 usable records / 29,998 = 98.82%; 353 invalid records excluded |
| Database structural checks | SQLite quick_check OK; zero foreign-key errors and duplicate source identities |

Eleven API-to-database reconciliation checks passed, including totals, status distributions, compliance, availability, site totals and storage calculations.

## Limits on trust

### Fresh source collection does not mean every device recently checked in

The freshness badge measures ingestion success. Intune's stored source `lastSyncDateTime` shows **5,698 devices (18.99%)** last checked in over seven days earlier, including **3,403 (11.34%)** over 30 days earlier. All active Intune rows had a readable device check-in timestamp; no timestamps more than five minutes in the future were found.

Compliance is therefore the latest reported state held by Intune, not proof that every endpoint is currently compliant. The dashboard's active inventory means present in the last complete source snapshot, not necessarily online or recently reporting.

### High health is a derived classification with partial measurements

SolarWinds metric coverage: usable CPU for **855/1,626 nodes (52.58%)**, RAM for **1,525 (93.79%)**, and latency for **1,591 (97.85%)**. Of 1,463 nodes classified High, **704 lack usable CPU or RAM measurements**.

The normalizer can retain High health based on Up status when resource telemetry is absent. Consequently the displayed high-health percentage does not establish that both CPU and memory were measured below thresholds on every High node. It is also not an uptime/SLA achievement over a historical period.

### Device roles and locations are source-derived categories

SolarWinds contains **293 classified servers, 531 classified network devices and 802 unclassified nodes (49.32%)**. Server/network counts are classification results, not a complete independently verified asset taxonomy.

The 68 locations are normalized source labels. Values include cloud/location labels and entries such as `NA`, `others`, `1` and `Unassigned`; they should not be described as 68 verified physical offices. Intune locations remain unsupported in the active source extraction.

### Some figures require explicit metric definitions

- The displayed **114 Active anomaly alerts** is 31 Warning + 80 Critical + 3 Down nodes. It is a node-status count, not a count of SolarWinds alert records; the UI subtitle does disclose that it is derived from node status.
- CMDB totals count source-specific inventory records. Unique `(source_system, source_id)` keys do not deduplicate the same physical asset appearing in both systems.
- Storage percentages exclude the 353 invalid storage records and are not a measurement of every managed endpoint. The rendered storage panel does disclose coverage.
- The device forecast is a linear estimate from 12 daily observations, not an observed future fact or a backtested prediction.

### Error and cache behavior still matter

The existing repository error-handling defect can turn datastore errors into an empty inventory result. A successful HTTP response alone is therefore insufficient proof of valid data during an outage. Summary caches can also delay refreshed totals for other worker processes; the current calculations describe the checked snapshot, not continuous real-time monitoring.

## Scoring rationale

| Dimension | Weight | Assessment |
|---|---:|---:|
| Database/API reconciliation and calculation correctness | 30% | 95 |
| Collection freshness and device recency | 25% | 75 |
| Field/classification completeness | 20% | 65 |
| Display semantics and interpretation | 15% | 60 |
| Source lineage and audit evidence | 10% | 85 |

Weighted result: 77.75, rounded to 78. Scores are judgment-based and scoped to the reviewed snapshot and paths. High reconciliation confidence is not independent certification of every source field.

## Verification boundary

The check independently read local database aggregates and compared them with the running API and selected rendered cards. It used existing successful-sync audit records; it did **not** re-fetch Microsoft Graph or SolarWinds, independently certify source permissions/fleet scope, verify every displayed row, or deduplicate physical devices across sources.

The current test suite provides supporting evidence (273 offline checks and two isolated browser journeys passed; four known defects remain expected failures). Test success is not a substitute for live data reconciliation.

Local evidence is saved in `scratch/dashboard_data_evidence.json`; the read-only collection script is `scratch/dashboard_data_audit.py`. Those local files are ignored by Git. The scheduled runtime continues normally, so later dashboard totals can legitimately change.

## Highest-value improvements

Show device-check-in age separately from ingestion freshness; distinguish missing resource telemetry from measured High health; label anomaly counts as affected nodes; expose unclassified/invalid-field coverage; and make database failures explicit instead of showing empty inventory.
