# Frontend consistency fixes — 14 October 2026

Three subagents handled location controls, network/CMDB behavior, and snapshot
freshness. The main agent updated the shell, styling, asset references, and
validated the combined application.

## Changes

- Infrastructure subview controls are native buttons, with keyboard support,
  visible focus and selected state. Existing routes and layouts are retained.
- SolarWinds inventory has SolarWinds issues only and no Intune check-in column.
  Source changes clear incompatible issues. Mixed-source views keep both sets
  of options; reset preserves the dashboard source selection.
- Endpoint score cards no longer offer SolarWinds-only issue links. Their
  compliance actions open the correct Intune records.
- Location header and summary totals now share the selected source population.
  Score tooltips show Up / monitored node counts. Scoring remains unchanged.
- Unknown health is neutral in Servers, Networks, CMDB and location inventory,
  including Networks/CMDB exports. Missing values are never displayed as High.
- Network device type is neutral; operational state carries status colour.
  Network device names open the existing details drawer with keyboard access
  and focus return. Re-entering Networks/CMDB does not duplicate filter handlers.
- Health-tier filter labels consistently use Green/High, Amber/Medium, and
  Red/Low. Location health remains explicitly distinct from a node health tier.
- Snapshot ages advance every minute. Freshness is explicitly labelled as
  evaluated at load, with a checked timestamp; the page does not silently replace
  loaded inventory evidence with newer global-header metadata.
- Filter controls have accessible names. API documentation links use the same
  origin (/docs and /redoc). Asset versions ensure refreshed browsers load fixes.

## Changed files

`frontend/index.html`, `frontend/css/style.css`, `frontend/js/app.js`, and the
`locations.js`, `infraWorkspace.js`, `cmdb.js`, `workspaceFreshness.js` components.
The older progressive-disclosure browser expectation was updated to exclude
Intune-only locations from SolarWinds scope (`test_operator_queue.py`).

New regression tests: `test_shell_consistency.py`, `test_location_consistency.py`,
`test_network_consistency.py`, and `test_freshness_consistency.py` under
`tests/browser/`.

No backend scoring, source transports, credentials, schemas, TechAdmin code, or
production infrastructure changes. No deployment. Automated tests use isolated
databases with live upstream requests blocked. The local portal was manually
reviewed after refreshing its static assets.

## Validation

Standard suite: **345 passed, 2 expected failures, 41 passing subtests**.
New focused browser checks all passed. The full browser sweep had **74 passed**
and two failures: an older test expected an Intune-only location in SolarWinds
scope, and one initial navigation check did not activate the workspace. The
scope expectation was corrected and both checks passed in targeted reruns.
The final location review checks passed **14 tests**; shell plus corrected
progressive disclosure passed **3**; the navigation/export recheck passed **1**.
Additional subagent runs passed **10 freshness** and **19 network/CMDB** checks.
These runs overlap and should not be added as a count of unique tests.

The live Ahmedabad drill-down showed 12 SolarWinds
records, four inventory columns, source-appropriate issue choices and matching
63-group location header/summary totals. A current screenshot is saved at
`output/frontend-fixes/solarwinds-inventory.jpg`.
