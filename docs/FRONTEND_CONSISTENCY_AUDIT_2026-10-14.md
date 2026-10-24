# Frontend consistency audit — 14 October 2026

Reviewed the running portal at localhost:8080 using the existing in-app browser,
current screenshots, DOM observations and frontend source. Application files were
not changed during this review. Counts below are observations of saved snapshots,
not fixed baseline values. The source snapshots changed during the review.

## Captured steps

1. SolarWinds location table and status summaries — `01-locations.jpg`.
2. Ahmedabad Red badge → location inventory — `02-inventory.jpg`.
3. SolarWinds inventory + Noncompliant filter → zero results — `03-source-filter.jpg`.
4. Endpoints, including stale-source disclosure — `04-endpoints.jpg`.
5. CMDB totals and source provenance — `05-cmdb.jpg`.
6. Server workspace, classifications and location filters — `06-servers.jpg`.
7. Network workspace with Low health selected — `07-networks.jpg`.
8. Full location view and 390px mobile layout — `08-location-full.jpg`, `09-mobile.jpg`.

All screenshots were captured and visually inspected during this run. They are
stored in `output/frontend-audit/`. The temporary viewport override was removed.
The portal was returned to the SolarWinds location view and the temporary network
health selection was cleared.

## Confirmed findings

| Priority | Finding and evidence | Recommended correction |
| --- | --- | --- |
| High | Infrastructure category controls are clickable DIVs with no role or tabindex. DOM inspection confirms the four controls are absent from keyboard tab order. `frontend/index.html:272`; `infraWorkspace.js:173`. | Use native buttons and expose the selected subview. Preserve the existing routing handlers. |
| Medium | SolarWinds inventory offers Noncompliant and Intune check-in issue filters. Selecting Noncompliant for Ahmedabad produced zero records even though the location has 12 nodes. The table also repeats Not applicable under Last Intune check-in. Screenshot 03; `locations.js:253`, `locations.js:258`. | Offer source-specific issue options and hide the Intune-only column for a SolarWinds-only selection. Reset an incompatible issue when source changes. |
| Medium | Location scope is unclear: category total is 84 populated groups across sources, while SolarWinds summary is 63. These are different populations, not proven incorrect counts. Screenshot 08; `locations.js:135`, `locations.js:189`. | Label the category as all-source groups, or update the total and label to the selected source scope. |
| Medium | Network device type is always displayed with a green healthy pill, even on Critical / Low rows. Operational Status itself is plain text. Screenshot 07; `infraWorkspace.js:760`. | Use neutral styling for device type and semantic styling for operational state. |
| Medium | Network device names are plain strong text, whereas Servers, CMDB and location inventory offer device-detail buttons. Screenshot 07 and DOM; `infraWorkspace.js:758`. | Reuse the existing CI drawer interaction and keyboard-accessible device link. |
| Medium | Health naming varies: location Green/Amber/Red, network filter Green · High/Amber · Medium/Red · Low, and server/CMDB filters High Health/Medium Health/Low. Location score and per-device resource tier also measure different things. Screenshots 05–08. | Use consistent colour labels while keeping the metric meaning explicit: location status versus node health tier. Do not equate the scoring rules. |
| Medium | Score denominator is not exposed beside the row. Mexico / Hermosillo shows 27 total, 20 Up, 2 Down/Critical and 90.9%. This follows the existing monitored-node denominator (22), rather than total nodes (27); the global footnote is easy to miss. Current DOM and `locations.js:230`; `location_service.py` excludes unmanaged nodes. | Show eligible-node counts in the score explanation, such as 20 / 22 monitored, without changing scoring. |
| Medium | Snapshot age and freshness remain frozen while staying in a workspace. Initial panel still said 4m old for a 10:22 snapshot when the drilldown response was timestamped 11:30. Navigating refreshed it to a newer source snapshot. Screenshot 02 and DOM; `workspaceFreshness.js:49` has no periodic age refresh. | Clarify that evidence belongs to the loaded snapshot and advance its age; reevaluate freshness without silently mixing new data with old counts. |
| Low | Footer API documentation links use localhost:8000, whereas this portal runs on 8080. Screenshot 08 and DOM; `frontend/index.html:1062`. The target server was not independently probed, so this is a confirmed wrong-origin inconsistency rather than a verified connection failure. | Use same-origin /docs and /redoc links. |
| Low | Several server, endpoint and CMDB selects have no accessible label; option text provides context only after interacting. Network health and location controls have better names. Current DOM; `index.html:424`, `index.html:741`, `index.html:905`. | Add explicit associated labels or meaningful aria-labels. |

## Additional code risks — not reproduced with missing live fields

- **Missing health can be shown as Green/High.** Networks default missing
  `health_tier` to High both on screen and in CSV (`infraWorkspace.js:754`,
  `infraWorkspace.js:860`). CMDB uses a green class for missing health while
  printing Unknown (`cmdb.js:165`, `cmdb.js:179`). Unknown evidence should have
  neutral styling and should not be promoted to a measured health tier.
- **Unknown device status becomes Amber.** `locations.js:13` maps every
  unrecognized node status to warning. Preserve a separate neutral unknown state.
- **Reset changes the dashboard source mode.** `locations.js:164` resets to auto,
  switching the SolarWinds table back to mixed-source cards. This is existing
  implemented behavior, but retaining the selected source while clearing search,
  level and status would be less surprising.
- **Network handlers accumulate on workspace re-entry.** Unlike server filters,
  `initNetworkFilters()` has no initialized guard and uses addEventListener for
  search, type, location, pagination and export. Each render can attach another
  handler. Multiple requests/downloads were not measured in this audit; add a
  guard or lifecycle-safe binding and verify re-entry explicitly.

## Working behavior and limits

The Ahmedabad Red badge opened its SolarWinds-scoped inventory with 12 records:
8 Up and 4 Critical. The 66.7% score and Red classification match the existing
policy. Amber above 90% is also possible under the existing Down/Critical guard;
it is not by itself a scoring regression. A neutral insufficient-data score is
appropriate for mapping review or ineligible evidence.

CMDB displayed matching source totals: 30,034 Intune + 1,624 SolarWinds = 31,658
records, with a clear cross-source duplicate warning. Endpoints explicitly
disclosed a stale snapshot and failed latest sync. These source outcomes are
operational evidence, not frontend defects.

Mobile location content stayed within its table scroll region. However, Status
and Health score require horizontal scrolling; a sticky location column or
small-screen status summary would improve discoverability. No claim of full
accessibility compliance is made: contrast, screen-reader behavior and all
keyboard journeys were not comprehensively tested.

This was a read-only review. No upstream sync, credentials, schemas, integrations,
TechAdmin code or production infrastructure were changed, and nothing was deployed.
