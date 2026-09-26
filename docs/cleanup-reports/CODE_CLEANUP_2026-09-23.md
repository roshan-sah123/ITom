# Code cleanup - 2026-09-23

## Scope and evidence

Added the current architecture diagram to README.md and rewrote ARCHITECTURE.md and DATA_FLOW.md around the implemented live-source ingestion and current frontend entry point. Removed outdated staged-file, static-fallback, and fixed fleet-count descriptions from those two guides.

Removed 10 tracked HTML prototypes: the nine files under frontend/archive/previews/ and frontend/preview_infra_with_pie_and_sites.html. Reference searches found only links between the archived prototypes, with no callers in the active frontend, tests, scripts, or documentation searched. Their prior contents remain recoverable from Git history (pre-cleanup HEAD: ba6be9b).

## Removed files

- frontend/archive/previews/final_master_reference_asset.html
- frontend/archive/previews/ops_analytics.html
- frontend/archive/previews/preview_ia01_endpoints.html
- frontend/archive/previews/preview_ia02_servers.html
- frontend/archive/previews/preview_ia03_telecom.html
- frontend/archive/previews/preview_ia04_network.html
- frontend/archive/previews/preview_infra_analytics.html
- frontend/archive/previews/preview_infra_with_pie_and_sites.html
- frontend/archive/previews/preview_infra_with_sites.html
- frontend/preview_infra_with_pie_and_sites.html

## Retained compatibility paths

Root-level frontend files, older standalone pages/domain scripts, and scripts/start_server.py still have compatibility launcher or test references. They require a coordinated migration before removal. Data, credentials, database files, and the user's pre-existing .gitignore edit were not changed.

## Validation

- Baseline: 7 tests passed across frontend home, location/network contracts, and local service environment suites.
- After cleanup: 27 tests passed across those suites plus snapshot reconciliation and live-sync unit tests.
- Traversed local HTML asset links and JavaScript imports from frontend/index.html: 13 reachable HTML/JS files, zero missing targets.
- No production sync or deployment was initiated. This was a documentation and unused-prototype cleanup, not a live integration validation.

New UI work should use frontend/index.html and frontend/js/app.js. Keep experiments outside the served frontend tree to avoid confusing prototypes with deployed screens.
