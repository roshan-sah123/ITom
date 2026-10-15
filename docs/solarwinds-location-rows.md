# SolarWinds location health rows

Select **Infrastructure → Location health → Score: Infrastructure · SolarWinds**.
The view presents Location name, Total nodes, Up, Warning, Down/Critical,
Health score, and Status. Search, reporting level, status summaries, refresh,
and Show more continue to work. Other score selections keep their card view.

Each populated SolarWinds location appears once, ordered by existing health
priority and name. Intune-only locations are excluded. Unassigned SolarWinds
nodes are counted separately and remain available for inventory review;
Intune freshness is hidden in this view. A location name opens inventory scoped
to that location and SOLARWINDS. Resetting inventory filters preserves that
source scope. CSV export uses the same source and filters as inventory.

The row's Green, Amber, Red, and Insufficient data badges are now buttons.
Clicking one, or pressing Enter/Space while it has focus, opens that location's
SolarWinds inventory. The inventory heading retains the location score and
explanation; individual node states remain visible and can be filtered with
the Issue control. Location health is an aggregate score, so the badge opens
all nodes for that location rather than treating its colour as a node status.
Returning to locations restores focus to the badge.

## Data interpretation

All values come from the existing `/api/v1/locations` catalogue. No new source
queries, synthetic metrics, backend scoring changes, or schema changes:

- Total nodes: `nodes`, including unmanaged and other states.
- Up and Warning: existing `issues.up` and `issues.warning` predicates.
- Down/Critical: `issues.down + issues.critical`; these are mutually exclusive
  node status values, so a node is counted once in this column.
- Health score and Status: `scores.infrastructure.value/status`, displayed
  as a percentage and Green, Amber, Red, or Insufficient data.
- Score uses Up / monitored nodes; unmanaged nodes are excluded from its
  denominator. Existing freshness, coverage, mapping review, exact thresholds,
  and latest-refresh rules remain authoritative. Unscored values show an em dash.

The status columns may not sum to Total nodes because other node states exist.
The table notes this once, rather than repeating explanations per row. Score
and status tooltips expose the existing score explanation. Policy and comparison
disclosures remain available. Mobile uses an accessible, keyboard-focusable
horizontal scroll region to preserve all seven columns and readable values.

The interaction follows [AWS Health's table/filter/affected-resource pattern](https://docs.aws.amazon.com/health/latest/ug/aws-health-account-views.html)
within the existing portal design. It does not add an AWS integration.

## Files and validation

- `frontend/js/components/locations.js`: conditional SolarWinds table, source
  coverage, source-scoped unassigned count and inventory reset.
- `frontend/css/style.css`: compact table, numeric alignment, neutral missing
  data status, and contained horizontal scrolling.
- `frontend/index.html`, `frontend/js/app.js`, and
  `frontend/js/components/infraWorkspace.js`: asset version updates.
- `tests/browser/test_solarwinds_location_rows.py`: API-to-row comparisons,
  all four status filters, level/search/empty results, source-scoped keyboard
  drilldown, inventory reset, export, stale evidence, and mobile screenshots.

Validation uses isolated databases and source-backed test fixtures. Live
upstream access is blocked during tests. SolarWinds GET/SELECT-only transport,
credentials, database schema, TechAdmin, and production infrastructure were
not modified. No deployment or new integration was performed.

Results: **345 automated tests passed**, **2 expected failures**, **41 passing
subtests**; **18 related browser tests passed**, followed by **2 final SolarWinds
row tests passed** after expanding the search, export, and stale-evidence checks.
Desktop and 390px screenshots were visually inspected. Test fixtures cover
Green, Amber, Red, unmanaged-only insufficient data, and stale evidence.
Screenshots are saved under `output/playwright/solarwinds-location-rows/`.
