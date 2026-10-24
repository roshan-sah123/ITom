# SolarWinds location browsing

Open **Infrastructure → Location health → Infrastructure · SolarWinds**.
The default view mirrors the regular SolarWinds group hierarchy. Source names,
including spacing, punctuation, capitalization and Unicode, remain unchanged.
Map-owned containers and deleted groups are excluded. Empty source groups remain
visible. There is no generated Unassigned location or name-based membership.

- Click an arrow to expand direct child groups and devices.
- Click a group name to list every unique device in that group and its descendants.
- Click a device to open the shared CI drawer.
- Filter devices by name/IP and status; choose a page size. Reset preserves group scope.
- Back restores the expanded hierarchy, location filters and triggering control's focus.
- The View selector retains Intune and available-source canonical scorecards.
  SolarWinds and Combined share the group browser and inline panel; see
  [dashboard Site Scores](DASHBOARD_SITE_SCORES.md) for current classification and
  approved-link behavior.

Group statuses come directly from SolarWinds, not from the portal score policy.
Source rollup settings can make a group's status differ from the statuses of its
individual nodes. Freshness and the latest refresh attempt are shown separately;
stale or failed refreshes never become an empty or healthy-looking result.

## Data path and integrity

The existing scheduled SolarWinds sync fetches count-reconciled ordered pages
from `Orion.Nodes`, `Orion.Container`, and `Orion.ContainerMembers`. Membership
types are `Orion.Groups` and `Orion.Nodes`; dynamic memberships are consumed as
resolved by SolarWinds, without reimplementing dynamic rules locally. Regular
groups with unsupported member types, missing references or cycles fail
validation. Identical membership edges are deduplicated. Names are not cleaned
or inferred from City/ITSM location fields.

An Alembic migration adds separate source groups and typed membership edges.
The existing sync transaction persists node updates, hierarchy replacement,
retirement and the audit together. Failure retains the last successful snapshot.
Count/order reconciliation detects incomplete paging and many concurrent source
changes; separate SWIS SELECTs are not an upstream point-in-time transaction.

The browser reads the new `/api/v1/solarwinds/groups` endpoints from the CMDB.
Recursive SQL uses distinct group traversal and node identities, so shared
descendants never duplicate devices. The source can place one group under
multiple parents; expansion state follows each visible path. Nodes without
regular-group membership stay in the existing inventory.

## Verification

Run offline backend tests with `python -m pytest tests/test_solarwinds_groups.py
tests/test_snapshot_reconciliation.py tests/test_migration_contracts.py -q`.
Run real browser journeys with `python -m pytest tests/browser/test_solarwinds_groups.py
--run-browser -q`. The browser fixtures use an isolated database and blocked
upstream requests. Captures are saved under `output/playwright/solarwinds-groups/`.

Migration tests execute SQLite upgrade/downgrade and compile PostgreSQL DDL.
Execute migrations against an isolated PostgreSQL database before deploying to
that database engine; DDL compilation alone does not confirm server execution.

Official references: [container schema](https://solarwinds.github.io/OrionSDK/2024.1/schema/Orion.Container.html),
[membership schema](https://solarwinds.github.io/OrionSDK/2024.1/schema/Orion.ContainerMembers.html),
[group semantics](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-managing-groups-sw2603.htm).
