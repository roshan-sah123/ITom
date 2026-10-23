# API contracts

The current service is `app.main:app`. Its OpenAPI document at `/openapi.json` and interactive documentation at `/docs` describe the exact parameters and schemas from the running checkout. Versioned routes use `/api/v1`; the former `/api/cmdb/*` file-server routes have been retired.

## Route map

| Route | Purpose |
|---|---|
| `GET /healthz` or `/health` | Process liveness |
| `GET /ready` | Database connectivity and migration readiness; 503 when unavailable or mismatched |
| `GET /api/v1/system/freshness` | Successful-sync freshness by source |
| `GET /api/v1/cmdb/summary` | Database-backed inventory aggregates |
| `GET /api/v1/cmdb/cis` | Filtered, paginated active inventory |
| `GET /api/v1/cmdb/cis/{ci_id}` | Configuration item detail |
| `GET /api/v1/cmdb/cis/{ci_id}/history` | Recorded status/health changes |
| `GET /api/v1/cmdb/cis/{ci_id}/relationships` | Inventory relationships |
| `GET /api/v1/intune/summary` | Managed-device compliance, OS and storage summaries |
| `GET /api/v1/intune/forecast` | Projection from successful daily observations |
| `GET /api/v1/intune/devices` | Filtered managed-device inventory |
| `GET /api/v1/solarwinds/summary` | Infrastructure operational summary |
| `GET /api/v1/solarwinds/nodes` | Filtered infrastructure inventory |
| `GET /api/v1/solarwinds/network-devices` | Network-only inventory |
| `GET /api/v1/solarwinds/groups` | Top-level regular source groups, including empty groups |
| `GET /api/v1/solarwinds/groups/{group_id}/members` | Direct child groups and device members |
| `GET /api/v1/solarwinds/groups/{group_id}/devices` | Unique devices across the group and all descendants |
| `GET /api/v1/solarwinds/sites` | Site/location aggregates |
| `GET /api/v1/solarwinds/sites/{site_id}/trend` | Recorded trend, with `hours` between 1 and 168 |
| `GET /api/v1/analytics/locations` | Location analytics |
| `GET /api/v1/analytics/stale-assets` | Stale inventory analytics |
| `GET /api/v1/sync/scheduler` | Scheduler state and cadence |
| `GET /api/v1/sync/status` | Latest source attempts and overall sync state |
| `GET /api/v1/sync/runs` | Sync run list |
| `GET /api/v1/sync/runs/latest` | Latest run; optional source filter |
| `GET /api/v1/sync/runs/{run_id}` | Run detail |
| `POST /api/v1/sync/trigger` | Queue ingestion; accepts `source_system=ALL`, `INTUNE` or `SOLARWINDS` |

## Inventory lists

SolarWinds group routes use `{status: "success", data: ...}`. Groups use numeric
SolarWinds `group_id` values, not canonical location IDs. Group names and native
status descriptions are preserved verbatim. Only non-deleted `Owner = Core`
groups are included; map containers are excluded. Groups can have multiple parents.
The devices route accepts `page`, `page_size` in `{10,25,50,100}`, literal name/IP
`search`, and exact case-insensitive `status`. Filtering and unique-node selection
happen before pagination. Unknown group IDs return 404; invalid parameters return
422; database failures return a safe 503.

Each group response carries `data_available`, `snapshot_id`, `as_of`, `freshness`,
and `last_attempt_status`. An empty catalogue before the first successful group
sync has `data_available=false`; a validated empty source snapshot has
`data_available=true`. Sync runs include nullable `groups_extracted` and
`memberships_extracted`: cleaned regular-group/edge counts. Legacy, fixture-only,
and failed runs leave these null. Nodes, hierarchy, retirement, and the success
audit commit together. Existing canonical location and `/solarwinds/sites`
contracts are preserved.

Inventory pages accept `page >= 1` and `page_size` in `{10, 25, 50, 100}`. Responses include `items`, `total`, `page`, `page_size` and `total_pages`. Filter availability depends on the route; consult OpenAPI instead of assuming a uniform set of parameters. Retired items are excluded from ordinary inventory reads.

CMDB, Intune, SolarWinds node and network-device lists return HTTP 503 with
`{"error": "Inventory datastore unavailable", "data_available": false}` when a
database query fails. A datastore outage must not be displayed as an empty fleet.
Search terms containing a NUL character return zero matches to prevent SQLite
from truncating the search pattern and matching unrelated assets.

## Data and error states

Summaries are computed from persisted telemetry. A domain with no ingested data may return 503. Freshness reports use `FRESH`, `STALE` and `UNKNOWN`; a successful HTTP response does not establish that upstream ingestion is current. Optional freshness timestamps are absent when there is no known successful refresh.

The inventory source routes reject mutating methods. The separate sync trigger returns 202 before ingestion finishes; inspect status and run history for its outcome. Shared-network deployments must supply access controls, because authentication is not currently implemented by the application. Known error-handling and deployment limitations are documented in the [audit](CODEBASE_AUDIT_2026-10-08.md).

## Source integrations

Intune and SolarWinds summaries include additive `decision_metrics`. Percentage
metrics expose `numerator`, `denominator`, nullable `value`, `known_count`,
`unknown_count`, nullable `coverage_pct`, `definition`, `population`, `exclusions`,
`observed_at`, `calculated_at` and `measurement_window`. `observed_at` is the latest
mirrored record sync timestamp, not a guarantee that every device was measured at
that instant. Legacy summary keys remain available.

Intune provides `confirmed_compliance`, `recent_checkins`, `compliance_state_counts`
and `checkin_age_buckets`. SolarWinds provides `current_node_status`, `all_fleet_up`,
`status_evidence`, `cpu_coverage`, `memory_coverage`, `resource_pressure` and
`resource_health_counts`. No eligible population has a null percentage; resource
pressure is also null when there are no usable CPU or memory readings. Resource
pressure can be observed with one reading while complete-pair coverage remains
incomplete. See [decision metric policy](DECISION_METRICS.md) for interpretation.

Graph uses OAuth client credentials and read-only managed-device extraction, including pagination. SolarWinds uses GET requests with validated SELECT-only SWQL. Implementations live in `src/sync/graph_client.py`, `src/sync/solarwinds_client.py` and `app/services/telemetry_sources.py`. Source credentials and transport policy are configured through `app/core/config.py`; source API access is separate from the portal inventory contract.
# Group overview and Site Score additions

See [dashboard Site Scores](dashboard-site-scores.md) for the additive group overview,
selected-group summary, native classification filters and reviewed Combined link
contract. Existing canonical location and legacy network endpoints are retained.

## Intune location inventory filters

Existing `GET /api/v1/locations/{location_id}/devices` and location CSV export
accept the additive `issue=compliant` and `issue=recent_checkins` values.
Both predicates match Intune records only. `recent_checkins` uses the existing
seven-day check-in policy, including its missing/invalid timestamp handling.
Filtering occurs before pagination and totals. These filters also provide the
corresponding counts in location score evidence; selecting a filter never
recalculates the full-location Site Score. Existing issue values and response
envelopes remain compatible.

## Intune inventory reporting locations

`GET /api/v1/intune/devices` accepts additive `location_id` (maximum 64
characters): a canonical location ID, or `unassigned` for missing canonical
membership. This filter combines with search, status and vendor, and is applied
before totals and pagination. Unknown IDs return an empty result. The existing
`location` parameter continues filtering the raw source location.

Each Intune list item includes additive `canonical_location` (name or null).
Existing `location_id` and `location_resolution` convey reporting membership and
review state. Location names are resolved in one query per page. The UI uses
the existing `/locations` catalogue, restricted to Intune-populated locations,
and retains Unassigned. CSV export uses the same inventory filters and includes
the reporting name plus a readable location-assignment state.

See [inventory location guide](INVENTORY_LOCATIONS.md).
