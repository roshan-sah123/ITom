# SolarWinds integration: verified data, history, and operations roadmap

Review date: **17 October 2026 (IST)**. This is a read-only investigation of the configured SolarWinds SWIS source, the active local CMDB, production ingestion code, portal APIs, and current browser UI. Counts are observations taken during this review, not fixed fleet baselines. Normal scheduled syncs continued during the investigation.

**Conclusion:** The existing connection works, and substantially more usable operational data is available than the portal currently ingests. Historical CPU/memory and availability records were retrieved in date windows approximately a year old. The most valuable next work is to expose observation freshness and repair location coverage, then add an actionable alert queue, historical node evidence, disk capacity, and interface diagnostics.

## 1. Connection and reconciliation

- A GET-only `SELECT TOP 1 NodeID FROM Orion.Nodes` succeeded using the existing configured client and credentials.
- `COUNT(NodeID)` returned **1,620 nodes**, matching the active SolarWinds CI population in SQLite.
- The actual `SolarWindsSource.fetch()` adapter successfully extracted and normalized **1,620 records in memory**, without database writes. Its complete-snapshot validation succeeded.
- Latest saved runtime evidence: `/api/v1/health`, `/ready`, `/api/v1/system/freshness`, `/api/v1/solarwinds/summary`, `/api/v1/solarwinds/sites`, and `/api/v1/sync/status` all returned HTTP 200.
- At **18:34:08 IST**, freshness was FRESH; the latest SolarWinds run completed successfully at **18:33:15 IST**, processing 1,620 records. An earlier inspected successful run recorded 1,620 extracted, 1,620 normalized, and zero rejected.
- The configured scheduler cadence is **600 seconds**. This is periodic collection while the application runs, not an event stream.
- `items_persisted=0` on a successful refresh means **zero newly inserted CIs** in the current implementation; it does not mean 1,620 existing records failed to refresh. Operational reporting should label inserts, updates, unchanged, rejects, and retirements explicitly.

Initial sandbox requests failed DNS resolution and could not reach localhost. The same queries succeeded outside the sandbox. That initial failure was an execution-environment restriction, not evidence of a SolarWinds outage or rejected credentials. The existing transport has certificate verification disabled; the successful request verifies connectivity and account read access, not certificate trust. No transport or credential settings were changed.

## 2. What SolarWinds actually exposes to this account

These are live **record counts**, not counts inferred from documentation or merely from schema presence. Child entities overlap their parent nodes and must not be added to CMDB node totals.

| Data | Verified population | Current portal ingestion | Operational opportunity |
|---|---:|---|---|
| Orion nodes | 1,620 | Yes | Current inventory, status, resource readings |
| Interfaces | 10,756 | No | Link health, throughput, utilization, errors/discards |
| Volumes | 1,482 | No | Free space, disk utilization and growth |
| Active alerts | 468 | No | Prioritized investigation queue, alert age and acknowledgement evidence |
| SAM applications | 237 | No | Application availability and service context |
| SAM components | 43,519 | No | Component diagnostics; includes disabled and unknown states |
| Hardware sensors/items | 6,545 | No | Temperature, fan/power and hardware fault evidence |
| Virtual machines | 445 | No | CPU ready, memory pressure, datastore/snapshot context where populated |
| Groups/containers | 325 | No | Existing SolarWinds grouping and service views |
| Dependencies | 574 | No | Parent/child impact evidence |
| Topology connections | 5,365 | No | Network adjacency and affected paths |
| Wireless access points | 508 | No | AP availability and client/load context |
| NCM nodes (`Cirrus.Nodes`) | **0 visible rows** | No | No populated configuration-management inventory verified |

The account returned recent actual records from response-time/availability history, CPU/memory history, interface traffic history, interface error history, volume usage history, events, alert history, and object-state history. A module having schema entries does not establish full licensing, universal field coverage, or every user's access. For example, NCM metadata exists but its node query returned zero rows. No NTA entities matched the discovery query; NetFlow drilldowns are therefore unverified.

### Useful data already present but unused

`Orion.Nodes` exposes `IsServer`, `ObjectSubType`, `PercentLoss`, `LastBoot`, `TotalMemory`, `DetailsUrl`, `EngineID`, `MinutesSinceLastSync`, `IsPollingError`, and maintenance fields. The current node fetch does not select most of these.

Custom properties include criticality, department, project, asset/procurement information, node category/type, WAN/Telecom flags and `ITSM_LocationID`. Live coverage checks found:

- **815** nodes with nonempty Criticality.
- **634** with nonempty Department.
- **276** with non-null Project; nonempty values were not separately verified.
- **1,598** with non-null ITSM location ID; validity and mapping to the portal catalogue still need checking.
- Azure cost/inventory custom-property fields exist, but only **one** row has nonempty `Az_LastSync`. These are custom stored properties, not proof of a complete or current Azure billing integration. Validate their producer, period, currency and freshness before using them in a dashboard.

Read only allowlisted properties. Some SolarWinds schemas contain credential-related properties; blanket `SELECT *` ingestion would collect unnecessary sensitive data.

## 3. Historical data: source history versus portal history

### Actual source history is present

Bounded queries against one node that currently reports CPU returned both `Orion.CPULoad` and `Orion.ResponseTime` records in these windows:

| Approximate lookback | Date window with returned records | Meaning |
|---|---|---|
| 7 days | 9 October 2026 | Historical performance/availability is queryable |
| 30 days | 16 September 2026 | Older samples remain available |
| 90 days | 18 July 2026 | Historical rollups are available |
| 365 days | **17 October 2025** | Approximately one-year-old records exist for the sampled node |

This proves availability in the tested windows for that node. It does **not** prove continuous year-long coverage for all 1,620 nodes or identify the oldest record in the entire installation. A global earliest-date sort was slow and was stopped; targeted node/date queries completed quickly. Bulk history was not downloaded.

Recent historical samples also returned:

| Entity | Verified fields in returned sample |
|---|---|
| `Orion.ResponseTime` | timestamp, availability, response time, packet loss |
| `Orion.CPULoad` | timestamp, average CPU load, average memory percentage |
| `Orion.NPM.InterfaceTraffic` | timestamp, inbound/outbound average bps |
| `Orion.NPM.InterfaceErrors` | timestamp, inbound/outbound errors |
| `Orion.VolumeUsageHistory` | timestamp, disk-used percentage |
| `Orion.Events` | event timestamp/type |
| `Orion.AlertHistory` | alert event timestamp/type |
| `Orion.NetObjectDowntime` | state interval start/end, state and duration |

An object-state history row can describe an Up interval as well as a Down interval. Filter by verified state semantics before calculating outages.

### Configured retention, read from this installation

| History category | Configured retention |
|---|---:|
| General detailed performance | **30 days** |
| General hourly performance | **100 days** |
| General daily performance | **365 days** |
| Alert history | **90 days** |
| Events | **30 days** |
| Auditing trails | **365 days** |
| Object downtime history | **7 days** |

Modules have independent settings: for example VIM and hardware hourly retention are 30 days, and wireless hourly/daily retention are 14/180 days. These settings describe configured retention, not a guarantee that every entity has that much populated history.

SolarWinds documents the progression from detailed statistics to hourly and daily summaries. Its published defaults must not replace the values verified above. [SolarWinds retention documentation](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-database-settings-sw1817.htm).

### The portal's existing history is different

At the local database observation:

- SolarWinds had **18,874 CI history rows** across **1,737 current and retired CIs**.
- **1,572** are tagged `INITIAL_SEED_INGESTION`. The earliest local timestamp, 1 October 2025, belongs to that seeded population. It is not evidence that this portal collected live periodic samples since 2025.
- **165** rows are tagged `INITIAL_INGESTION`; **117** are retirement events; **17,020** have no event tag. Tag absence alone does not prove provenance.
- The current sync code writes history on initial ingestion, status/health transitions and retirement. CPU/RAM values are attached to those sparse transition rows; stable status/health does not generate periodic metric history.
- There were **68,473 location score snapshots** across both sources, including **30,476** tied to SolarWinds runs. These are derived location-score observations from 9 October onward, not historical SolarWinds performance samples.
- The SolarWinds site-performance-trend repository explicitly returns `data_available=False` because periodic performance samples are not collected.

Consequently, the drawer's status list is useful for recorded changes, but it cannot establish exact downtime, MTTR, historical SLA, continuous resource trends, or capacity forecasts. Short outages between ten-minute syncs may be missed.

## 4. Important operational findings

### P0: A fresh ingestion does not establish fresh device observations

The source reported **147 managed nodes** with `MinutesSinceLastSync > 30`; **140** of those still reported Up. The stale-age set comprised 69 ICMP, 55 SNMP, and 23 Agent nodes. Separately, **49** nodes reported `IsPollingError=True`.

The node fetch already retrieves `LastSync`, but normalization drops it. The stored `last_sync_time` is the portal's ingestion timestamp. The portal therefore cannot show the age of the source's node observation beside the ingestion badge. The API does acknowledge this limitation in its observation-basis text, but the underlying timestamp is unavailable to the UI.

Add distinct fields for ingestion time, source sync time, latest metric sample time and polling method. Show stale-observation and polling-error queues alongside node status. Interpret `LastSync` according to object/polling semantics; these counts are investigation flags, not proof that all 147 devices or agents have failed.

One returned engine had 0% polling completion and a keepalive age of 15,577 minutes. The other 21 returned engine rows showed 100% and current keepalive. This warrants checking engine lifecycle/registration. The stale-node engine IDs differ from that engine, so this review does not establish it as their cause.

### P0: Location decisions exclude most SolarWinds nodes

Only **275 / 1,620 (17.0%)** SolarWinds nodes were assigned in Location Health; **1,345** were unassigned. This is a canonical mapping gap, not an absence of raw location fields. Existing scorecards correctly exclude unassigned records, but large offices can consequently appear to have no infrastructure.

Prioritize unresolved source aliases by node count, reconcile City versus ITSM location, and consider validated ITSM location IDs as stable mapping keys. Use the existing review workflow and retain provenance. Do not silently combine countries, cities, offices and cloud groups or auto-approve ambiguous mappings.

### P1: Existing alert and disk data can support immediate triage

- **468 active alerts** were visible. Acknowledgement values were **2 true, 466 null, zero explicitly false**. Preserve that distinction; do not assert that all null values are definitely unacknowledged.
- **59 volumes** reported usage >=90%, but they include RAM, virtual memory, compact disks and other types. Only **30 are Fixed Disk**. A storage queue must filter supported disk types, validate size and sample age, and use a sustained-duration rule before presenting incidents.
- Hardware statuses included 2 Critical and 3 Warning items. These are sensor/item counts, not necessarily five different affected nodes.
- Application states included 11 Down, 8 Critical, 5 Warning, 50 Unknown and 1 Unmanaged among 237 applications. Component counts include disabled entries and additional status codes; preserve their full vocabulary.

### P1: Classification and telemetry coverage need better source context

- Portal classification: **290 servers, 532 network devices, 798 unclassified**.
- Native SolarWinds `IsServer`: **293 true, 1,327 false**. This is a reconciliation opportunity, not proof that either classification should simply overwrite the other.
- **697** mirrored nodes had MachineType `Unknown`. The source had **699 ICMP-only** nodes. This strongly motivates showing polling method; it does not prove those two sets are identical.
- Stored CPU coverage was **854/1,620 (52.7%)**, memory **1,520/1,620 (93.8%)**, and latency **1,582/1,620 (97.7%)**. Non-null/valid-range checks alone cannot establish fresh measurements; zero memory on an ICMP-only node should not automatically imply measured zero utilization.
- Only **517** mirrored records had nonempty Contact. Contact is operational source context, not a verified accountable service owner.
- Vendor normalization collapses **1,122** nodes into Other. Preserve raw vendor and machine type, then normalize for display without destroying diagnostic detail.

## 5. Current UI workflow audit

Goal: let an operator move from an exception to trustworthy evidence, affected scope, and a clear next action. The five screenshots below were captured and inspected during this run. Counts in the initial UI reflect its 18:23 snapshot; the saved API evidence reflects the next scheduled refresh at 18:33. The different status counts are expected snapshot changes.

1. **Overview — useful and candid, limited action context.** Shows current Up ratio, resource coverage and operator exceptions. It explicitly avoids claiming historical uptime and flags incomplete resource readings. Add source-observation age, alert age and affected service/owner context to the queue. The low-tier queue and Warning/Critical/Down count use different definitions; name those populations consistently.

![Step 1: Overview](../output/solarwinds-rd-2026-10-17/01-overview.png)

2. **Infrastructure — good inventory evidence, incomplete investigation workflow.** Filters, resource summary and node access work. Capacity & Alert Analytics remains Coming soon even though the source already exposes populated volume and alert entities. The missing work is portal ingestion/API/UI integration. Make the servers card either filter the inventory to servers or clearly name the current all-node view. Show measured resource health separately from operational status and incomplete coverage.

![Step 2: Infrastructure](../output/solarwinds-rd-2026-10-17/02-infrastructure.png)

3. **Node drawer — accessible entry to provenance, sparse diagnostic detail.** The opened drawer displayed source ID, ingestion time, identity and location; its DOM also exposed ten recorded status entries. It does not provide CPU/RAM/latency charts, interface/volume context, active alerts, maintenance window or a source deep link. Add a compact evidence panel and a selected time range before adding more decorative charts.

![Step 3: Node drawer](../output/solarwinds-rd-2026-10-17/03-node-drawer.png)

4. **Network — working node inventory, limited network diagnostics.** The 532-device inventory supports search, filters and device inspection. It lacks interface utilization, admin versus operational state, circuit information, errors, flapping, packet loss and topology. A working device can have a failing WAN link; node Up alone cannot resolve that investigation. The 532 node count and 10,756 interface count describe different entities.

![Step 4: Network](../output/solarwinds-rd-2026-10-17/04-network.png)

5. **Location Health — clear exclusions, severe coverage limitation.** The UI reports assignment coverage and offers mapping review. Its 41 reporting groups mix levels and sources, with those limits explained. Repair the 1,345 unassigned SolarWinds records before relying on site-wide infrastructure comparisons. A Bengaluru inventory drilldown was also opened and exposed source/issue filters; no edits were made.

![Step 5: Location Health](../output/solarwinds-rd-2026-10-17/05-locations.png)

Accessibility observations: visible text accompanies colored status cues, filters have several explicit names, and the drawer has dialog semantics/focus handling in code. The node/network search inputs rely on placeholder text without an explicit label, and interactive chart canvases need a keyboard-operable equivalent and textual summaries. Add visible or programmatic labels and list/table alternatives. Contrast measurement, screen-reader operation, mobile reflow, zoom and a full keyboard-only journey were not tested; this is not a WCAG compliance claim.

## 6. Recommended implementation order

| Order | Deliverable | Operator benefit | Acceptance evidence |
|---|---|---|---|
| 1 | Source-observation age, polling method/errors; reconcile location mappings | Prevent confidently acting on old observations or incomplete site populations | Reproduce stale-but-Up cases; show source and ingestion times separately; reconcile assigned + unassigned to 1,620 |
| 2 | Read-only active-alert queue and enhanced node drawer | Find oldest/severe alerts, see affected node/service and related evidence | Reconcile source alert IDs/counts; preserve null acknowledgement; filter by age, severity, location and entity; source deep link |
| 3 | Node CPU/RAM/latency/loss/availability history | Determine when deterioration started and whether it persists | Verify source samples for selected windows; label gaps and resolution; distinguish status transitions from periodic samples |
| 4 | Fixed-disk capacity and interface triage | Investigate disk pressure, busy links and packet errors | Validate disk type/size/age, thresholds and duration; distinguish interface AdminStatus from OperStatus; preserve bps units |
| 5 | Dependencies/topology, SAM/VM/hardware/wireless context | Explain affected services and related failure signals | Validate parent/child mapping, stale edges, disabled monitors and object-specific status codes; never infer causality solely from adjacency |

Suggested alert flow: **exception → scope and severity → source timestamp/maintenance evidence → node/service details → aligned historical charts → related alerts/dependencies → runbook or source console → later recovery evidence**.

An initial alert UI can remain fully read-only. Acknowledge, reset, unmanage, configuration change and remediation are separate write capabilities, outside the present integration contract. Ticket creation or assignment requires its own destination and authorization; no such actions were taken here.

### Data/API approach

- Keep current CI inventory separate from metric samples, alerts, interfaces, volumes and relationships. Avoid expanding one large attributes JSON into a time-series database.
- For a pilot, retrieve bounded history on demand through the backend with short caching. If scheduled ingestion is needed, add per-entity checkpoints, identity-based deduplication, rate/row limits, and separate freshness from inventory runs. Validate query plans and source load before scaling.
- Key samples by source/object, metric family, source timestamp and resolution. Preserve `Archive`, `ObservationFrequency` and `Weight` when exposed. Do not merge detailed/hourly/daily rows as equivalent observations or double count overlapping rollups.
- Support explicit windows such as 24h/7d/30d/90d/365d with suitable resolution. Show `source_observed_at`, `ingested_at`, unit, coverage and resolution in API responses. Show gaps rather than interpolating healthy values.
- Historical availability needs an agreed time window, eligible population, maintenance policy and time weighting. Polling gaps must not become healthy time. Daily averages cannot reconstruct exact short outages or true raw-sample percentiles.
- Capacity forecasting needs enough comparable, fresh samples and validated disk size. A single 90% reading is pressure evidence, not a depletion date.
- Keep generic CI relationships empty until verified edges have been mapped. The local relationship table currently contains **zero rows**, despite populated upstream dependency/topology entities.
- Backfill in small object/date batches. The slow global earliest-date lookup during this review is direct evidence to avoid unrestricted history scans.

## 7. Inspectable evidence and source references

Generated local artifacts are under `output/solarwinds-rd-2026-10-17/`: current screenshots, `live-source-evidence.json`, `local-database-evidence.json`, and `portal-api-evidence.json`. The live evidence contains metadata and aggregate/sample metric results, not passwords or raw node inventory. The probe is in `scratch/solarwinds_rd_probe.py` and was used only for this review.

Code paths checked:

- `src/sync/solarwinds_client.py:295` — active SWQL node field selection.
- `app/services/telemetry_sources.py:239` — normalization and fields retained/dropped.
- `app/services/telemetry_sources.py:359` — source adapter validation.
- `app/services/sync_service.py:255` — stable state updates without periodic history.
- `app/repositories/ci_repository.py:534` — site performance history deliberately unavailable.
- `app/repositories/summary_repository.py:88` — heuristic role classification.
- `frontend/js/components/drawer.js:50` — current inspection content and ten-entry status history.
- `app/services/location_service.py:76` — source alias and canonical location resolution.

Official documentation was used to validate entity purpose and interpretation; the live installation's metadata and results determine actual availability:

- [Orion SDK](https://solarwinds.github.io/OrionSDK/) — SWIS/SWQL interface.
- [CPU and memory history schema](https://solarwinds.github.io/OrionSDK/2024.2/schema/Orion.CPULoad.html) — time-series resource fields.
- [Availability, latency and loss history schema](https://solarwinds.github.io/OrionSDK/2024.2/schema/Orion.ResponseTime.html) — supported historical measures.
- [Interface schema](https://solarwinds.github.io/OrionSDK/2024.2/schema/Orion.NPM.Interfaces.html) — traffic units and admin/operational state distinction.
- [Active-alert schema](https://solarwinds.github.io/OrionSDK/2024.2/schema/Orion.AlertActive.html) — triggered alerts, acknowledgement fields and separate mutation verbs.
- [Database retention and summarization](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-database-settings-sw1817.htm) — settings and granularity.

No application behavior, source configuration, credentials, location approvals, tickets or source records were changed. No full performance backfill or fleet-wide historical completeness audit was performed. Verification consisted of live read-only source requests, in-memory production-adapter extraction, database SELECTs, runtime API reads, code tracing, and current browser captures; application tests were not needed for this research-only change.
