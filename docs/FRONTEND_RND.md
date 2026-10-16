# Frontend research and relevance inventory

Baseline: `main=e95047e2a7267632d925247d554e5c53dd2fa3b9`; local branch `feat/itom-frontend-reformation`, based directly on main. The SQLite fix branch is excluded. Documentation only; preserve FastAPI, vanilla JS/shared CSS, SQLite, existing API contracts, exports, source integrations and Windows deployment. No live sync or production reads.

This is source R&D, not a screenshot audit. Browser behavior, visual density, contrast, mobile layout and actual production field coverage are unverified. The checkout is partial; missing assets/history are not deletion evidence. Contract IDs and all formulas/time semantics are defined once in [UI_DATA_DICTIONARY](UI_DATA_DICTIONARY.md). Acceptance IDs/tickets are in [UX_ACCEPTANCE](UX_ACCEPTANCE.md).

## Page and consumer map

| Surface | Actual consumer / placement | Decision |
| --- | --- | --- |
| `/`, `/index.html` | [app.main](../app/main.py) serves index/static assets. [app.js](../frontend/js/app.js) imports home, infrastructure, endpoints, CMDB, drawer, modal, freshness, sync ledger/schedule. Home replaces initial static home markup at mount; initial shell is not a second active dashboard. | KEEP routes and component architecture; improve initial loading content, not duplicate the old shell. |
| Infrastructure | Tabs: servers (actually all SolarWinds node inventory), networks, sites/canonical locations, baseline placeholder. [infraWorkspace](../frontend/js/components/infraWorkspace.js), [locations](../frontend/js/components/locations.js), [locationReviews](../frontend/js/components/locationReviews.js). | IMPROVE scope labels; preserve all tabs/capabilities. |
| Endpoints / CMDB | [endpoints](../frontend/js/components/endpoints.js), [cmdb](../frontend/js/components/cmdb.js). | KEEP source-specific inventory and shared detail drawer; reorganize progressively. |
| Knowledge / Automations | Primary navigation to planned content; Automations contains external TechAdmin link. | MOVE supporting/planned destinations below operational navigation; KEEP link external, no integration. |
| Sync runs / Sync & schedule | Footer Operations links, not primary tabs; [syncLedger](../frontend/js/components/syncLedger.js), [syncSchedule](../frontend/js/components/syncSchedule.js). | MOVE under Data Confidence while retaining existing navigation targets. |
| `/cmdb_explorer.html` | Static mount exposes it; links to itself, infrastructure analytics and index. Inline renderer consumes `constants.js`, `utils.js`, `services.js`. UMD services and ES-module utilities are different loading conventions. | IMPROVE; served compatibility surface, not dead code. Runtime interoperability unverified. |
| `/infrastructure_analytics.html` | Static mount and CMDB links expose it. Own inline/Tailwind styles, Chart.js CDN; [entry JS](../frontend/js/infrastructure_analytics.js) only loads F/B and binds no inventory/chart/filter handlers. | IMPROVE truthfulness; don't silently remove page or assume controls work. |
| Campus trend modal | Imported/initialized by main; exported open function has no call site in inspected active components. Backend T explicitly returns no samples. | REMOVE-CANDIDATE for unsupported SLA wording/unused chart rendering only, after consumer search; preserve route/unavailable contract. |

## Relevance inventory

Notation: V=VP, N=NOC, O=operator. Fields use dictionary contract IDs. All inventory/summary rows are stored snapshots, qualified by F/Y; denominators follow the dictionary. Raw counts have no percentage denominator. KEEP retains current intent; IMPROVE repairs evidence/interaction; MOVE retains capability in a secondary placement; REMOVE-CANDIDATE requires usage evidence and approval, not deletion now.

### Overview and common shell — evidence: [home](../frontend/js/components/home.js), [header](../frontend/js/components/header.js), [workspaceFreshness](../frontend/js/components/workspaceFreshness.js)

| ID / current item | Question / audience | Field and calculation / denominator | Usefulness and decision |
| --- | --- | --- | --- |
| O1 managed endpoints | How large is endpoint scope? V/O | I `metrics.total_managed_devices` | KEEP compact inventory context; source records, not unique assets. |
| O2 SolarWinds nodes | How large is infrastructure scope? V/N | S `metrics.total_nodes` | KEEP compact context, not an availability KPI. |
| O3 configuration items | How many source records exist? V/O | C `total_cis` | IMPROVE label to source records; don't imply deduplication. |
| O4 endpoint compliance | Which share is confirmed compliant? V/O | I `decision_metrics.confirmed_compliance`; compliant/all active endpoints | KEEP headline with count, denominator, unknowns and definition. |
| O5 nodes reporting Up | Which monitored nodes report Up? V/N | S `decision_metrics.current_node_status`; Up/(all−Unmanaged) | KEEP headline; snapshot, not SLA. |
| O6 resource pressure | Where are observed CPU/RAM breaches? N/O | S `decision_metrics.resource_pressure`; breaches/all nodes; separate CPU/memory coverage | KEEP headline; incomplete telemetry can overlap breaches. |
| O7 exceptions / category count | What should I investigate? N/O | S `metrics.low_critical_nodes` (fallback low_health_count), I `metrics.noncompliant_devices`; count of displayed categories | IMPROVE exact landing filters; never sum these populations into risk. No-reported-exceptions message requires successful evidence. |
| O8 confidence / source rows | Can the assessment be trusted? All | F states/time; Y latest attempts; I normalized unknown/check-in buckets; S status/resource coverage; C availability | KEEP concise warning summary; MOVE extended evidence into Data Confidence. |
| O9 header, workspace and inventory freshness | When did each source succeed and fail? All | F `sources`, Y source status; B engine/database status | IMPROVE consistent terminology. Header polls 10s, workspace ages loaded evidence each minute, overview refresh is GET-only. These are not source-refresh rates. |
| O10 global search / workspace links / reload | How do I reach matching records? O | D `/cmdb/cis?search=`; local navigation; F/I/S/C/B/Y GETs | IMPROVE first-use listener ordering and slash shortcut in editable controls; KEEP explicit snapshot reload, separate from ingestion. |

### Infrastructure — evidence: [infraWorkspace](../frontend/js/components/infraWorkspace.js)

| ID / current item | Question / audience | Field and calculation / denominator | Usefulness and decision |
| --- | --- | --- | --- |
| S1 Servers category | How many classified servers? N/O | S `metrics.server_nodes_count`; contextual total_server_nodes means all nodes | KEEP category; clarify the subsequent inventory includes all nodes. |
| S2 Networks category | How many network-classified nodes? N/O | D `/solarwinds/network-devices`.total | KEEP; don't assume it equals all SolarWinds records. |
| S3 Sites category | How many populated reporting groups? O | L items excluding Unassigned with endpoints+nodes>0; mode changes scope | IMPROVE; mixed levels are not physical-site count. |
| S4 Node inventory total/context | What is my eligible node scope? N | S total_nodes; server/network/unclassified counts and monitored context | KEEP; align category counts and explicit scope. |
| S5 Nodes Up percentage | What is operational state now? N | S decision current_node_status, numerator/denominator/unknown | KEEP; old DOM name swSlaVal does not make this an SLA. |
| S6 Attention count | How many Warning/Critical/Down records? N | Sum S metrics.status_counts.warning+critical+down | IMPROVE label as node states, not unique alerts/incidents. |
| S7 Vendor text KPI | What platforms comprise scope? O | Keys of S vendor_distribution | MOVE into composition; names are not OS/runtime evidence. |
| S8 Health donut | How are derived tiers distributed? N/O | S health_breakdown High/Medium/Low; share of plotted counts | IMPROVE definition and unknown/unexpected category handling; click applies health_tier. |
| S9 Status bar | What statuses need investigation? N | S metrics.status_counts up/warning/critical/down/unmanaged_unknown | IMPROVE: final bar labeled Unmanaged combines Unknown; clicking only Unmanaged changes population. Shutdown/other states need reconciliation against raw status_breakdown. |
| S10 Vendor donut | Which vendors are present? O | S vendor_distribution; shares of nodes | MOVE to composition; KEEP vendor click filter. |
| S11 Saturated server list | Which measured servers merit review? N | S top_saturated_servers, CPU/RAM warning breaches, top 10 by max reading | KEEP bounded triage; clicking searches name, not ID. Do not imply it exhausts all-node O6 breaches. |
| S12 All-node table | Which records support the result? N/O | D nodes: name/IP/status/type/vendor/health; attributes CPU/RAM/latency aliases | KEEP. Missing measurements remain unavailable; per-row latency is not fleet SLA. |
| S13 Network table | Which classified network devices? N/O | D network-devices: name/IP/type/vendor/status/health/raw location | KEEP; separate operational status and health; same drawer. |
| S14 Node filters/export | Which subset and deliverable? O | search, health_tier, status, vendor (chart), raw location, page/page_size; D nodes | IMPROVE race safety and persistent visible filters; KEEP all-filter CSV across pages. |
| S15 Network filters/export | Which network subset? O | search, ci_type, health_tier, raw location, page/page_size; D network-devices | KEEP filtering/export, IMPROVE consistency with node controls. No new facet API needed. |
| S16 Baseline tab | Is configuration compliance measured? O | No bound volume/alert compliance response; Coming soon | MOVE planned item; REMOVE-CANDIDATE for unsupported invariants/operational wording, not routes. |

### Endpoints and CMDB — evidence: [endpoints](../frontend/js/components/endpoints.js), [cmdb](../frontend/js/components/cmdb.js), [drawer](../frontend/js/components/drawer.js)

| ID / current item | Question / audience | Field and calculation / denominator | Usefulness and decision |
| --- | --- | --- | --- |
| E1 Managed devices / compliant subcount | What endpoint population is mirrored? O | I metrics.total_managed_devices, compliant_devices | KEEP source-record context. |
| E2 Compliance rate | What fraction is compliant? O | I metrics.compliance_rate_pct, compliant/all Intune | KEEP; align evidence with O4, preserve known-other/unknown distinction. |
| E3 OS diversity | How varied is inventory? O | Number of keys in I os_distribution, including Unknown if present | MOVE composition; not a modernization score. |
| E4 OS donut | What operating systems are reported? O | I os_distribution/os_breakdown; counts/shares | MOVE composition; IMPROVE click claim: general search also matches name/IP/vendor/etc., not an exact OS facet. |
| E5 Compliance bar | Which source compliance states exist? O | I compliance_breakdown; raw status counts | KEEP investigation; every category needs an equivalent selectable/status filter. |
| E6 Manufacturer donut | Which hardware vendors dominate? O | I vendor_distribution; count/share | MOVE composition; KEEP vendor parameter. |
| E7 Storage meters and coverage | What measured storage pressure exists? O | I median_device_storage_used_pct, fleet_capacity_used_pct, storage_sample_size; sample/total | KEEP secondary evidence; IMPROVE null handling (Number(null) can become 0), distinguish weighting. No capacity forecast. |
| E8 Inventory trend estimate | How has ingestion volume changed? V/O planning | P fields; latest successful count/day regression | MOVE Planning, retain observation window/method/notice and unavailable state. |
| E9 Zero Trust | Is posture measured? V/O | No bound metric; Coming soon | MOVE planned content; no proxy score from compliance. |
| E10 Endpoint table / filters / CSV | Which devices need review? O | D devices: name, owner attributes, OS/type, vendor, status, serial; search/status/vendor, page/page_size | KEEP; IMPROVE stale-response and cross-control consistency; CSV uses all pages/current filters. |
| C1 Total / Intune / SolarWinds KPIs | What records came from each source? O | C total_cis; total_endpoints; total_servers+total_network_devices+total_unclassified | KEEP; reconciliation must hold before presentation. |
| C2 Provenance stacked bar | What share is source provenance? O | C1 source counts/total; zero total produces empty state | KEEP; composition, not cross-source asset coverage or duplicate rate. |
| C3 CMDB table / filters / CSV | Which source record is this? O | D cis: name/type/source/health/status/serial; search/source_system/health_tier/raw location/page/page_size | KEEP; IMPROVE initialization, race safety and explicit active filter summary. Location choices currently come from W (raw SolarWinds locations). |
| C4 Shared drawer / status history | What evidence supports this record? N/O | H detail and history; identifiers, status/health, mirror time, type/vendor/model/OS/serial/IP/MAC, owner attrs, raw/canonical-location fallback, first recorded | KEEP accessible drawer architecture; missing optional canonical_location is not proof of canonical identity. Use actual location_id/resolution for future assignment evidence. History means recorded changes, not uptime or policy failures. |

### Canonical locations — evidence: [locations](../frontend/js/components/locations.js), [review UI](../frontend/js/components/locationReviews.js); formulas/gates in dictionary

| ID / current item | Question / audience | Field and calculation / denominator | Usefulness and decision |
| --- | --- | --- | --- |
| L1 Source assignment coverage | How much inventory can be grouped? O | L coverage per source: assigned/unassigned/total; source freshness | KEEP; mapping coverage is not operational health. |
| L2 Endpoints / infrastructure / combined score | Which groups require investigation? N/O | L items.scores with component C/R/H, exact formulas/gates from dictionary | IMPROVE component-first display; preserve score and reasons as expandable derived policy. |
| L3 Group counts / status summary / unassigned | What groups lack evidence or have exceptions? O | L items populations; frontend filters group totals/status; Unassigned source count | KEEP counts with source scope/level; IMPROVE compatible comparison rather than mixed-mode ranking. |
| L4 Per-group issue links / components | Why is this group flagged? N/O | L items.issues, components, status_breakdown; endpoints/nodes and mapping/freshness | KEEP exact issue drill-downs; overlapping counts must not be summed. |
| L5 Catalogue controls | Which comparable groups? O | Local name search, auto/endpoints/infrastructure/combined mode, status and level, show-more (24), refresh | IMPROVE explicit comparison constraints; preserve browsing and saved filters. |
| L6 Device investigation / export | Which records meet the issue? O | LD source/issue/name search, page=1/reset, fixed page_size=25, prev/next; source-specific columns and CI drawer; CSV same scope | KEEP; distinguish raw CI fields from canonical group. Backend export is buffered/capped at 1,000,000; don't promise unlimited/streamed export. |
| L7 Score history | What was previously observed? O | LD history recorded_at/policy/mapping/data.scores; UI selects same policy/mapping | MOVE secondary detail; KEEP empty history and unavailable; never continuous SLA trend. |
| L8 Mapping review queue / editor / history | Why is assignment uncertain? O | LR enabled-rule status totals, filtered total, linked devices, reviewer/date, notes, legacy_approval, locations, write_enabled | KEEP capability; MOVE entry under assignment confidence with location backlink. Counts cover all enabled rules, not filtered queue. Preserve local-write restriction and optimistic revision conflict handling; no new writes in R&D/tests. |

### Sync and standalone surfaces

| ID / current item | Question / audience | Source/calculation/freshness | Decision / risk |
| --- | --- | --- | --- |
| D1 Schedule facts | Is collection configured/running? O | K enabled/running/interval_seconds/next_run/timezone; Y state/reason/latest completed/age | KEEP under confidence; configured next run is not guaranteed success. Panel polls 30s. Y last_sync must not be called last successful source sync. |
| D2 Source cards / run ledger | What did ingestion report? O | Y per-source status/completion/records; R first 20 run IDs/source/status/count/duration ms→s/completion | KEEP; IMPROVE missing status/count defaults and source-specific last-success context. No ledger pagination control currently. |
| D3 Run sync now | Explicitly request ingestion? Authorized O | Existing POST `/sync/trigger?source_system=ALL`; UI acceptance response only | KEEP capability; no triggering here. Authorization contract is unresolved security work outside frontend scope; don't simulate sign-in or claim backend enforcement. |
| X1 Legacy CMDB KPI set | What is CMDB scope/provenance/health? O | Inline total; Intune/SolarWinds shares; High count; remainder warning/critical; static widths/copy and fallback constants | IMPROVE P0. Actual C provides category counts/health_breakdown, not source_distribution/health_distribution assumed inline. No aggregate cross-source compliance claim justified. |
| X2 Legacy CMDB inventory / controls / export | Which CIs match? O | D cis; source/health/search/page-size/prev-next; services wrapper maps camelCase; export requests first 100 unfiltered rows | KEEP served page; IMPROVE export semantics and error escaping. Show whether CSV is filtered/full, never silently truncated. Row defaults include High/Active/Live Sync without evidence. |
| X3 Standalone infrastructure KPI shells | What is infrastructure/endpoint/location posture? V/N/O | Only F/B bound. Unbound shells: total/monitored nodes, High count/share, Medium/Low counts, average CPU, average RAM, latency/SLA; managed/compliant/rate/noncompliant endpoints, average storage, grace count, security gate; total facilities, top density hub, global availability, at-risk facilities | IMPROVE P0 unsupported constants (SLA/key coverage/facility counts) and label unbound content unavailable. Some snapshot equivalents exist in I/S/L, but averages/security/SLA claims lack current response support. Do not implement integrations to fill the shells. |
| X4 Standalone chart shells | What is trend/composition? N/O | Unbound canvases: fleet CPU/RAM trend; availability trend; incident-frequency trend; health donut; vendor bar; endpoint risk levels; OS drift; OS donut; manufacturer bar; location top-density bar; regional donut; selected-site trend | IMPROVE unavailable state. Snapshot distributions can reuse existing contracts only in separately approved tickets; no historical SLA/incident/risk/region data source established. |
| X5 Standalone controls/tables | Can I investigate/export a scoped list? O | Unbound source tabs; date/location/environment filters; node health/search/page-size/export; endpoint status/search/export; facility region/search/trend selector/table; static region/facility counts | IMPROVE: no handlers beyond F/B in entry module. Preserve URL and navigation; distinguish visible shells from working journeys. Runtime confirmation required. |
| X6 Campus trend modal | What happened over 24 hours? N | T unavailable/empty; modal contains SLA/CPU line-series schema but no source samples or inspected active opener call | REMOVE-CANDIDATE for misleading SLA rendering/text after usage confirmation; KEEP explicit unavailable route/state. |
| X7 Knowledge/Automations/Baseline/Zero Trust | Is this capability available? All | Planned/static content; no supporting telemetry API | MOVE supporting destinations; REMOVE-CANDIDATE for obsolete duplicate promotional copy only after usage evidence. TechAdmin stays an external link. |

## Contract and presentation risks to carry into tickets

1. P0: X1/X3 have static operational numbers/unsupported claims even before fetch. X1 uses response keys C does not return. Truthfulness checks must inspect initial HTML, successful zero/missing responses and errors, not only a few historical literals.
2. P1: S9 unmanaged_unknown is neither an Unmanaged-only count nor the complete raw status partition. Use raw S.status_breakdown for a future faithful chart; test clicks against D.status. Preserve decision-metric denominator differences.
3. P1: S8 only plots three tier keys. Unexpected categories may be omitted; do not synthesize a missing category count or relabel unknown as Medium. E5 dropdown has fewer options than chart states.
4. P1: O10 first-use search event can arrive before CMDB registers its listener; C3/E10/S14/S15 grids lack consistent request-generation protection. L/drawer/home already demonstrate guards worth preserving, not rewriting.
5. P1: E4 OS click uses general search (CI name/IP/serial/vendor/source_id/operating_system), not a ci_type-only endpoint facet. S11 name search can match more than one device. Global search promises sites but navigates to that same CI search, which does not search location names. Label these as searches unless exact scope is supported; no backend additions in this plan.
6. P1: F/Y/header/summary-cache timestamps are independently refreshed. Never attach newer freshness to older rendered values without qualification; default SUCCESS/0 in ledger and Number(null) storage coercion need tests.
7. P1: L Auto + All levels mixes denominators/calculations. Existing guidance, coverage gates and fail-closed scores are strengths; enforce comparability for comparison actions without deleting mixed browsing.
8. P2: Shared CSS main shell versus inline legacy/Tailwind shell and duplicate API/CSV/format helpers are maintenance risks. Code removal requires demonstrated consumers and equivalent route behavior; no rewrite or new framework.
9. P2: main exports page through mutable snapshots; equal totals do not prove row identity stayed stable across pages. Show export failure/incompleteness honestly; don't claim transaction-consistent snapshots without an API contract.
10. No source supports a new business-impact, deduplicated-asset, incident-rate or SLA KPI. Optional owner details can contain personal data; preserve current access boundaries and avoid exposing more fields merely because serialized columns exist.

## Official reference patterns

| Official reference | Adopt within existing data | Do not infer |
| --- | --- | --- |
| [AWS Health account views](https://docs.aws.amazon.com/health/latest/ug/aws-health-account-views.html) | Summary → filtered affected-resource list → detail; matching export scope | ITOM exception categories are not incident events, affected services or recovery timelines. |
| [Datadog Host List](https://docs.datadoghq.com/infrastructure/list/) | Visible scope/filtering, inventory-first investigation, property grouping where supported | No arbitrary tags, exact OS facet, agent stream or live host state is available here. |
| [ServiceNow traversal rules](https://www.servicenow.com/docs/r/it-operations-management/service-mapping/traversal-rules-service-mapping.html) | Explicit CI identity/provenance; relationships only when demonstrated | Existing relationship endpoint alone does not establish service topology, criticality or business impact. |
| [Grafana dashboard practices](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/) | Consistent overview/detail hierarchy; small purpose-led KPI set | Don't copy RED/SLA charts without time-series/service-request data. |
| [Intune device details](https://learn.microsoft.com/en-us/intune/device-management/inventory-and-status/device-details) | Device identity, compliance and check-in evidence with inventory drill-down | No policy-level failure reason or remote-action parity without source fields. |

These are reference-pattern research from the accepted baseline, not a visual comparison. No before/after screenshot claim is made.
