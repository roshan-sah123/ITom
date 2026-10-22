# Dashboard nomenclature and group Site Scores

The visible workspaces are Home page, Operations Analytics, Digital Workspace,
and Assets Analytics. Their route IDs remain `home`, `infrastructure`, `endpoints`,
and `cmdb`. `frontend/js/labels.js` owns shared workspace labels. Global search
opens Assets Analytics; the Home Overview Table has its own location search.

Home's three decision tiles use compact spacing with unchanged text sizes.
Definitions and detailed coverage evidence expand on demand. Freshness and
coverage warnings remain visible. Reload snapshot reads persisted data only;
it never calls the source ingestion endpoint. Location, score mode and filters
survive reloads.

## Location and classification scope

The Overview Table is one row per active, top-level Core group, including empty
groups. Names and raw NodeCategory / NodeType strings retain source spelling,
Unicode, punctuation and spacing. Those custom properties belong to the tenant;
they are not universal fields guaranteed by the public schema. MachineType stays
in the generic CI type field as hardware information. No classification is
inferred when source tags are missing.
The pressure list uses additive `top_source_servers` evidence; the legacy
hardware-classified summary fields remain compatible for existing API clients.

Summary Server/Network counts compare their category labels ignoring surrounding
whitespace and case; category tiles and exact-category filters retain each raw
source value separately. Other and missing categories share a compact table
column but expand separately. Inventory and category tiles describe SolarWinds
group members. Combined uses the same inventory layout and adds the explicitly
linked Intune population to the score evidence. Filtering inventory never changes
the full-location Site Score. Fleet totals count NodeID once across overlapping
groups; individual location rows can overlap. Ungrouped devices remain in full
inventory, with no synthetic location.

## Read APIs

- `GET /api/v1/solarwinds/groups/overview?score_mode=infrastructure|combined`
  returns batched top-level summaries, unique fleet category/coverage totals,
  source snapshot ID, observation time, freshness and latest attempt outcome.
- `GET /api/v1/solarwinds/groups/{id}/summary?score_mode=...` returns the same
  selected group summary, component evidence, mapping state and freshness.
- Group devices and `/solarwinds/nodes` support exact `category`,
  `category_missing=true`, and exact `source_type`, alongside existing filters.
  `/cmdb/cis` supports the same additive filters. Generic fields stay compatible;
  source_category and source_type are additive SolarWinds response fields.

Summary queries load minimal projected node evidence in batches. Read assessments
are bracketed by sync, inventory and approval revisions and retried if those
change. Snapshot IDs let panels reject inventory from a different group snapshot.

Native SolarWinds health is independent of the calculated Site Score. The latter
reuses the existing score policy: SolarWinds is monitored nodes Up across all
classes; Combined is 40% Intune compliance + 35% SolarWinds Up + 25% Intune
check-ins within seven days. Existing thresholds, component floors, Down/Critical,
failed-refresh, freshness and 95% field-coverage guards remain in effect.

## Explicit local group links

No links are inferred or preapproved by this change. Combined is Unavailable
until a named reviewer provides evidence for an active top-level group and an
existing canonical/Intune location ID. Preview without writing:

```powershell
.venv/Scripts/python.exe scripts/manage_locations.py --group-link GROUP_ID --location-id LOCATION_ID --reviewer "REVIEWER" --comment "APPROVAL EVIDENCE"
```

Replace placeholders with approved values. Add `--apply` to commit. To revoke,
use `--revoke-group-link GROUP_ID --reviewer "REVIEWER" --comment "REASON" --apply`.
The administration command records reviewer, UTC date, evidence and before/after
decisions in database audit tables. There is no new mapping-review screen.
Source sync updates stable IDs in place, preserves links on rename, soft-deactivates
removed groups, and moves approved links to REVIEW when the group disappears or
becomes a child. Reappearing groups require explicit reapproval. Children never
inherit a parent's link.

## Local rollout and verification

Stop the supervisor and create a checked SQLite backup before `alembic upgrade
head`. Revision 0009 adds stable activity state and reviewed group-link tables.
Run the normal locked SolarWinds sync to fetch the new native custom properties,
then restart the portal and reconcile current source counts and memberships.
Do not hardcode observed fleet sizes into production logic or tests.

Regression tests cover real SQLite migrations, explicit approvals, score boundaries,
freshness, failed refreshes, coverage, shared descendants, batch query counts,
browser filter/reload semantics and responsive layouts. PostgreSQL DDL compilation
is a separate check and must not be reported as execution against a server.

References: [SolarWinds custom properties](https://solarwinds.github.io/OrionSDK/2024.1/schema/Orion.NodesCustomProperties.html),
[resolved group members](https://solarwinds.github.io/OrionSDK/2024.1/schema/Orion.ContainerMembers.html).

## Local verification on 19 October 2026

The checked backup is `backups/before-dashboard-site-scores-20261019T101734Z.db`.
Migration 0009 and the normal validated SolarWinds sync completed; `/ready`
confirmed database connectivity and migration head after supervisor restart.
The completed snapshot had 1,619 unique nodes, 45 top-level groups, 568 Server,
717 Network, and 334 other/unclassified nodes. Regular groups covered 657 unique
nodes, leaving 962 accessible through full inventory. These are observations,
not limits. BOCBA had eight descendants, including four Network devices.

Live browser/API reconciliation checked every inventory page against the batch
classification counts, the four screenshot devices, group expansion, zero-server
tiles, classification filters, reload retention, Combined unavailability without
approval, and narrow-screen overflow. It recorded no page errors or non-GET
requests. Desktop summary tiles measured 238.7px versus 437.9px before the change
(45.5% reduction). Captures are in `output/playwright/dashboard-site-scores-live/`.
The isolated backend suite passed 380 tests and 41 subtests, with two pre-existing
migration expected failures. Targeted changed browser journeys passed 18 tests.
SQLite migrations executed; PostgreSQL migration DDL compiled, but no isolated
PostgreSQL server was available for execution.

## Recheck on 22 October 2026

The portal again passed readiness at migration head, with both sources fresh.
The current SolarWinds snapshot reconciled 1,615 devices: 576 Server, 717 Network,
and 322 other/unclassified. Regular groups covered 664 unique devices; 951 stayed
accessible through full inventory. BOCBA still returned eight devices, including
the four screenshot network devices. The live desktop/mobile check passed with
no page errors or write requests; tile height remained 238.7px. Site Score pills
now include written Green/Yellow/Red labels in addition to colour.
The final complete isolated browser suite passed all 80 tests. The focused
approved/unmapped location tests also passed after the written status labels
were added. The repository whitespace check passed.

## Intune location layout

Selecting Digital Workspace / Intune in the Site Score view now uses the same
location list, inline summary tiles and paginated inventory layout as SolarWinds.
Intune retains its existing reporting-location assignments; it does not inherit
SolarWinds group names or memberships. Unassigned devices remain accessible from
the coverage link, and existing mapping review remains available.

Compliance tiles show total, compliant, noncompliant and other/unknown devices.
Separate check-in tiles show within seven days, over seven days and unknown.
These populations overlap across the two tile groups. Tile clicks filter only
the selected location's Intune inventory. Search, pagination, CSV export and
device details use existing APIs. Reload snapshot uses GET requests and retains
the selected location and filters without triggering ingestion.

The existing Intune score policy is unchanged:
`(40 × compliance percentage + 25 × recent-check-in percentage) / 65`, with
the existing component, coverage, freshness and location-review safeguards.
The score always describes the complete selected location's Intune population,
including when its inventory is filtered. Native SolarWinds health is not shown
as Intune health. Failed catalogue, summary and inventory reads offer retry
without treating missing evidence as zero devices.

This change requires no database migration. SQLite-backed verification passed
152 focused backend tests and 19 browser regressions. The two focused Intune
browser journeys also passed after adding summary-error retry coverage.

Live read-only verification on 22 October 2026 found 33 populated reporting
locations: 26,731 of 30,055 Intune devices assigned, with 3,324 unassigned.
Greater Noida / Tower D reconciled to 5,037 devices and 549 noncompliant devices;
its 85.5% Yellow score stayed unchanged after filtering and snapshot reload.
Desktop and mobile checks recorded no page errors or non-GET requests. The
running portal confirmed SQLite connectivity and migration head. Captures and
the verification receipt are in `output/playwright/intune-location-layout-live/`.
These counts are observations rather than application limits.
