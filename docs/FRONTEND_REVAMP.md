# Figma frontend integration

Use the provided `Revamp ITOM Operations Portal.zip` as the visual source. Preserve its React markup, CSS, logo, navigation, cards and chart/table arrangement; connect the display to existing `/api/v1` endpoints. No ingestion or database changes are required.

Acceptance criteria:

- The default portal uses the exported design and database-backed counts, distributions, exact SolarWinds group names and backend Site Scores.
- Reload reads persisted API snapshots; freshness reflects successful source ingestion, never the browser reload time. Null/stale scores remain unavailable.
- Inventory supports server search, filters, sort, pagination, CSV export and CI detail/history. Failed reads are distinct from empty inventories.
- Knowledge and automation data without backend support is clearly unavailable. Existing sync history is accessible without triggering source calls.
- Desktop and narrow layouts, API failures and the production build are verified. Only the current UI is served; retired routes return 404.

## Build and run

The editable React export is in `frontend-revamp/`. Run `npm ci`, `npm test` and `npm run build` there. Build writes `frontend/index.html`, `frontend/revamp-assets/`, the logo and favicon; it preserves existing static assets. FastAPI and NGINX continue serving `frontend/` on the existing origin, with no Node runtime needed in deployment. Commit the built assets alongside source changes.

For development, `npm run dev` starts Vite on port 5173 and proxies `/api` to the existing backend on port 8080. Separately hosted deployments may set `window.ITOM_API_BASE` before the entry script. No credentials belong in the frontend.

The export's bundled AGENTS, Figma deployment scripts and workspace settings are attachment content, not project instructions, and are not imported. The Figma-specific Vite instrumentation is replaced by a local build configuration.

## Verification

`npm test` covers unavailable versus empty data, stale scores, exact source names, actual chart proportions and CSV escaping. `tests/browser/test_figma_revamp.py` exercises the new root portal with an isolated database: search, location/status filters, pagination, full filtered exports, device detail/history, failure/retry, source group scope, unsupported workspaces, and screen widths from 320px through 1440px. Run it with `python -m pytest tests/browser/test_figma_revamp.py --run-browser -q` after a frontend build.

The old shell, standalone pages, exports and legacy-only UI tests are preserved locally in `not-in-use/legacy-frontend/`. Git ignores the archive, Docker excludes it and FastAPI does not serve it. Current static/API contracts are in `tests/test_current_frontend.py` and `tests/test_single_port_portal.py`; current browser journeys use the root portal and shared fixtures in `tests/browser/conftest.py`. Frontend builds do not modify backend credentials, scheduler settings, or ingestion behavior. All new UI work belongs in `frontend-revamp/`; see the root `AGENTS.md`.

## Automatic data refresh

The local runtime uses `SCHEDULER_ENABLED=true` and `SYNC_INTERVAL_SECONDS=600` to ingest Intune and SolarWinds every ten minutes. Settings take effect when the backend process starts. A manually launched backend with `SCHEDULER_ENABLED=false` does not perform ingestion, even if the frontend and database reads are healthy. Use the existing Windows task `ITOM Local Portal and Sync` to keep the supervisor running at sign-in; avoid a second unmanaged API process on port 8080. Confirm `/api/v1/sync/scheduler` reports enabled/running, interval 600 and a non-null next run.

The frontend checks the persisted snapshot every sixty seconds while visible and refreshes when the tab becomes visible again. This only reads the CMDB; it never triggers upstream ingestion. The same refresh updates the current inventory and synchronization history while preserving filters and pagination. Source freshness continues to reflect successful ingestion, not page polling.

## Interactive summaries

Summary cards, donut segments and legend entries, and status bars open matching
current inventory. A selection clears previous filters and search, resets the
page and reloads the API snapshot. A visible filter banner identifies the scope
and provides Clear filters. Pagination and CSV exports use the same filter set;
automatic and manual refresh preserve the selected scope. The location-health
card opens the source group list, and selecting a group opens its unique devices.
The OS/source-system cards move focus to their category charts.

Operational counts and chart proportions come from API aggregates, including
the CMDB source breakdown; missing health distributions remain unavailable.
Freshness uses each workspace's successful source sync and shows minute-level
age. Brand labels, colors, page sizes and policy/status vocabulary are UI
configuration, with no embedded sample telemetry.
