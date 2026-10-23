# SolarWinds category dashboard research

Reviewed 23 October 2026, 16:23 IST. This is a recommendation for the current
version; no portal behavior or source configuration was changed.

## Recommendation

Keep the seven SolarWinds business categories visible, with a separate
Unclassified bucket. Use the same active-node population for dashboard totals,
status counts, inventory filters, and exports. Improve category consistency and
measurement coverage before adding more charts.

## Verified inventory

The local live portal mirror contained **1,607 active, distinct SolarWinds node
IDs**. Its last completed sync was successful at 16:17:59 IST. Health and readiness
checks passed; source freshness was FRESH. All eight category counts matched the
inventory API and group fleet overview.

| Source category | User's approximate count | Checked count | CPU value in range 0–100 |
| --- | ---: | ---: | ---: |
| Client IP | 3 | 3 | 0 / 3 |
| Cloud | 18 | 18 | 12 / 18 |
| Collaboration | 35 | 35 | 0 / 35 |
| Network | 704 | 714 | 524 / 714 |
| Server | 573 | 573 | 273 / 573 |
| Telecom | 251 | 254 | 44 / 254 |
| URL | 6 | 6 | 0 / 6 |
| Unclassified | — | 4 | 2 / 4 |
| **Total** | **1,590** | **1,607** | **855 / 1,607** |

Counts describe SolarWinds node records, not distinct physical assets across
Intune and SolarWinds. These are dated observations, never fixed product targets.
A numeric value alone does not prove a poller is supported, enabled, or current.

## What the current version already does well

- Ingestion preserves custom `NodeCategory` and `NodeType` from
  `Orion.NodesCustomProperties`.
- Visible Server and Network cards already show the correct source-category
  totals: 573 and 714. Group details already expose dynamic category filters.
- Native operational status and calculated Site Score are separate. The node
  status card already labels its numerator and denominator. Freshness and
  unsupported capacity/alert features are explicitly shown.

## Changes in priority order

### 1. Make all category summaries agree

The older `/api/v1/solarwinds/summary` classification still uses vendor and
MachineType keywords: **286 servers, 537 network, 784 unclassified**. The legacy
`/network-devices` API also returns 537. This differs from the source categories,
even though newer visible cards are correct. Add a shared source-category
aggregation for summaries and inventory, then migrate consumers while documenting
legacy aliases. `total_server_nodes` is currently an alias for all 1,607 nodes;
new consumers should use `total_nodes`.

Keep category and technical type as separate dimensions. Cloud includes 17 nodes
whose source type is Server and one PaloAlto Firewall. Telecom includes 103
Internet, 34 MPLS, 28 Router, and 22 ISP PE IP nodes. These are business groupings;
vendor/model inference must not overwrite them. Custom properties are explicitly
user-defined in [SolarWinds documentation](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-creating-custom-properties-sw1391.htm).

### 2. Make every category visible and actionable

Replace the broad "Other / unclassified" presentation with a category summary
table: **Category, Total, Up, Warning, Critical, Down, Unmanaged, Unknown,
telemetry coverage**. Seven compact category shortcuts and Unclassified should
open matching inventory. Retain a readable table on smaller screens.

Add Category and Source type filters to the full node inventory. Combine them
with existing status, location, and search filters. Counts, pagination, charts,
and CSV exports must use the selected scope; clearly label fleet-wide cards if
they remain global. Preserve unexpected future source categories automatically.

### 3. Separate node status, resource pressure, and service health

The checked snapshot had 1,444 Up, 28 Warning, 70 Critical, 22 Down, and 43
Unmanaged nodes. That means **120 nodes needing attention**, not 120 active
alerts. The current Up share was **1,444 / 1,564 = 92.33%**, excluding Unmanaged.
Keep Unknown and Unmanaged distinct. Preserve native status rollup semantics;
groups can use best, worst, or mixed status policies.
[SolarWinds rollup documentation](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-status-rollup-mode-sw2114.htm).

Show resource pressure alongside measured/eligible coverage. Only 47.6% of
Server-category nodes had a numeric CPU value. All Collaboration, URL, and
Client IP memory values were zero; 297 Server memory values were also zero.
Investigate polling capability and timestamps before treating these as complete
healthy measurements. Preserve genuine zero readings; use N/A for confirmed
unsupported metrics and Unknown for expected measurements that are absent.

Do not label a snapshot Up share as uptime or SLA. SolarWinds availability uses
historical polling; a Critical node can remain reachable.
[SolarWinds availability calculation](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-calculating-node-availability-sw1184.htm).

### 4. Choose metrics that fit the actual category

| Category | Useful with current mirror | Additional source evidence to discover and ingest |
| --- | --- | --- |
| Server | Native status; CPU/RAM with coverage; resource-pressure list | Volumes, services/apps, polling capability, metric timestamps |
| Network | Status, node response time, source types, supported CPU/RAM | Interface state, utilization, errors/discards, packet loss |
| Telecom | Circuit/connectivity status, node response time, Internet/MPLS/ISP breakdown | Circuit/interface identity, provider, bandwidth, loss, path tests |
| Collaboration | VC endpoint status and response time | Platform/device capabilities and call/session quality where available |
| Cloud | Category status and supported node resources | Verified provider/account/region/resource IDs; cloud-service health |
| URL | Status and node response time, explicitly labeled as node evidence | HTTP(S) monitor results, web response time, content checks, certificate expiry |
| Client IP | Reachability status and node response time | Confirm target purpose and polling method; loss where available |

The current adapter collects nodes and groups; it does not ingest interfaces,
volumes, application monitors, alert instances, call-quality statistics, or cloud
service APIs. A URL-category node marked Up does not demonstrate that its web
application passed an HTTP check. SolarWinds provides separate
[HTTPS monitors](https://documentation.solarwinds.com/en/success_center/sam/content/sam-https-monitor-sw3245.htm).
Call-quality metrics such as jitter and MOS require suitable monitoring evidence,
for example [VNQM](https://documentation.solarwinds.com/en/success_center/vnqm/content/vnqm-quality-of-service-metrics-sw206.htm);
do not assume Telecom means voice or that the required modules are installed.

### 5. Keep location and freshness coverage explicit

There are **662 nodes in regular groups and 945 outside them**. Group/location
rows overlap and cannot be summed into fleet totals. Retain the full-inventory
link and add category-by-location analysis without hiding ungrouped nodes.

Raw source location text exists for 1,605 nodes, whereas only 271 have a canonical
reporting location ID. Raw location, canonical location, and regular group
membership are different measures. Canonical mapping needs reconciliation;
ungrouped does not mean location missing.

Keep last successful mirror sync separate from source measurement freshness.
The adapter fetches `n.LastSync` but does not preserve it in normalized attributes.
Verify its source meaning, preserve provenance, and discover actual poll/metric
timestamps before introducing per-metric freshness guarantees. Add historical
availability or trends only with a defined measurement window and persisted or
retrieved samples; repeated snapshots alone do not establish an SLA.

## Implementation and acceptance

First align additive category summary contracts and resource coverage in
`app/repositories/summary_repository.py` and `decision_metrics.py`. Reuse existing
source filtering and `group_score_service.py` category counts. Then update
`frontend/js/components/infraWorkspace.js` and the home/group category summary.
Keep additional telemetry ingestion as a subsequent capability-driven change.

Acceptance checks: category and status sums equal active node IDs; retired nodes
stay excluded; source-category counts agree across cards, APIs, filtered inventory,
and exports; empty categories and new labels render correctly; unsupported,
missing, stale, unmanaged, and unknown evidence remain distinct; group overlap
cannot inflate fleet counts. Cover these behavior changes with backend and
browser tests when implemented.

Five read-only reconciliation checks passed for this research. Exact SQL,
aggregate results, the rerunnable `profile.py`, and a companion notebook are kept
privately under `outputs/solarwinds-category-rd-2026-10-23/`. No product tests were
run because this research changed no application code.
