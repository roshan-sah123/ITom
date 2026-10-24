# VP dashboard feedback — implementation and data dependencies

## Active implementation

The served portal is `frontend/index.html`, styled by `frontend/css/style.css`
and routed by `frontend/js/app.js`. Its active workspaces are Overview,
Infrastructure (Servers, Networks, Locations, Capacity/Alerts), Endpoints,
CMDB, Knowledge Centre, Automations, and the footer sync views. Infrastructure
loads `infraWorkspace.js` and `locations.js`; endpoint, CMDB, and overview
modules own their existing filters and summaries. Capacity/Alerts and roadmap
views remain honest unavailable states rather than invented health controls.

FastAPI routes under `app/api/v1` use services and repositories over SQLAlchemy.
The runtime supports configured SQLite or PostgreSQL storage. No backend,
database schema, source transport, credential, or scheduler changes are needed
for this increment.

`telemetry_sources.py` normalizes Graph managed-device compliance/check-ins and
SolarWinds node status/resource measurements. `src/sync/solarwinds_client.py`
enforces GET requests and validated SELECT-only SWQL. Those guards are preserved.
The Graph client and ingestion reconciliation remain unchanged.

`location_service.py` resolves Intune device-name prefixes and SolarWinds city /
ITSM location aliases through canonical database mappings. Conflicting or
unconfirmed assignments remain reviewable. Shared predicates drive both issue
counts and inventory drilldowns; freshness and field coverage gate scores.
Unassigned records remain separate. Cross-source records are not deduplicated
into physical devices, and overlapping issue counts must not be added.

## Completed improvements

- Compact location health rows at desktop widths; stacked cards on narrow screens.
- Corrected the mobile infrastructure tab grid to two columns, overriding the
  pre-existing desktop rule that crowded four tabs into narrow screens.
- Always-visible endpoint and node record counts, source scope, health, and score.
- Short Green / Amber / Red summaries, with explicit insufficient-data state.
- Subtle semantic selected surfaces for location summaries and status/health
  dropdowns in Servers, Networks, Endpoints, CMDB, and location inventory.
  CSS follows the selected option, including chart drilldowns and resets.
- Comparison guidance and scoring limitations stay accessible in disclosures.
  Primary affected-device actions, mapping review, freshness, export, paging,
  search, level filters, keyboard focus, and existing exact score rules remain.
- Network health filtering uses the existing API `health_tier` parameter and
  applies equally to pagination and CSV export. Select Health (All) to clear it.
- Versioned asset references updated so existing browsers retrieve the changes.

The design takes the summary → filters → affected resources pattern from
[AWS Health event views](https://docs.aws.amazon.com/health/latest/ug/aws-health-account-views.html).
It does not add AWS connectivity or portray reporting groups as geographical
coordinates. Scores retain the existing provisional policy, not SLA claims.

## Information required from other teams

| Owner | Required information | Current limitation |
| --- | --- | --- |
| Site operations / CMDB governance | Authoritative location IDs, hierarchy, alias ownership, approved Intune naming prefixes, mapping conflict decisions | Assignment describes a reporting group; it does not prove physical presence. |
| Network / SolarWinds team | Approved read-only volume, interface, alert and maintenance data; timestamps, severity, status and resource joins | Node status and available CPU/RAM/latency do not establish capacity, incident impact, or service availability. |
| Endpoint / Intune team | Compliance policy interpretation, expected check-in windows, ownership of naming rules and unknown states | Compliance and check-in recency are distinct from infrastructure availability. |
| ITSM / service owners | Service-to-CI relationships, incident/change records, business criticality, ownership and SLA definitions | Business impact and SLA attainment cannot be inferred from node counts. |
| Asset management | Approved cross-source device identity keys and duplicate reconciliation rules | Source records cannot be labeled unique physical devices. |
| Data owners / VP | Approval of health bands, weighting, coverage floor, source freshness expectations | Existing operating bands remain provisional and unchanged. |

These are collection dependencies, not new authorized integrations. No requests
were sent to other teams and no live source refresh was triggered for validation.

## Changed files

- `frontend/css/style.css`: selected status surfaces and responsive location layout.
- `frontend/js/components/locations.js`: concise labels and visible record counts.
- `frontend/js/components/infraWorkspace.js`: network health filter and export scope.
- `frontend/index.html`: network control and cache version references.
- `frontend/js/app.js`: updated infrastructure module reference.
- `tests/browser/test_vp_dashboard.py`: location counts, filter selection surfaces,
  and real network filtering/export contracts against isolated inventory.
- This report: architecture, scope, and outstanding data ownership.

## Validation scope

Tests use temporary databases and isolated portal servers, with live source
requests blocked. Deterministic fixture records are test evidence only and are
never substituted for operational dashboard metrics. Browser chart rendering is
stubbed by the existing test harness; real portal modules, APIs and database
operations run. Production connectivity and production database health are not
claimed by these checks. No deployment was performed.

Validation results: the standard suite passed with **345 passed, 2 expected
failures, and 41 passing subtests**. The full browser run passed **57 tests**;
the added network filter/export contract also passed in the six-test VP suite.
Desktop and 390px screenshots were inspected. A redundant concurrent browser
run hit one page-navigation timeout; the same journey passed in the full run
and passed in the final focused run: **16 passed**, including the VP contracts
and all location scorecard clarity journeys after the responsive change.
Existing FastAPI 422 deprecation
warnings are unrelated to this dashboard change.
