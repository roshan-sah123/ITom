# Repository cleanup — 8 October 2026

## Outcome

Removed 53 obsolete tracked files and archived 12 historical reports/specifications. Kept the active FastAPI application, current frontend, telemetry clients, migrations, local database/snapshots and user data exports. The existing October audit remains available.

## Removed

- Root-level duplicate frontend HTML, JavaScript, styles and images, plus the obsolete root `js/` tree. The current portal remains in `frontend/`.
- Unreferenced `frontend/app.js`, `frontend/ops_analytics.js`, `frontend/style.css` and old shared/Intune/SolarWinds/CMDB modules. Retained standalone infrastructure/CMDB pages and their referenced modules.
- The old file-server and incomplete remote-deployment scripts, the file-summary/Firestore runner and integration, and already-applied sync-status patch scripts.
- The older cleanup script and legacy static security verifier tied to retired assets.
- The two demo-only site tests, obsolete storage-demo assertions, duplicate CSS assertions, old launcher/static DOM tests and Firestore-only tests. Preserved current request-safety, ingestion, inventory and normalization tests and shared test helpers still imported by other suites.
- 20 preview copies whose hashes exactly matched retained files under `docs/demo_previews/`, and two obsolete `.bak` source patches. Workspace Python/pytest cache cleanup was checked; no cache directories remained visible at the final check.

## Preserved history

Historical readiness reports, the original request, old audit/final reports and backend handover material now live under `docs/archive/legacy-2026-09/`. Original `PROJECT.md` and API specifications were archived before replacing their current references. The root avatar was an exact duplicate of the retained frontend image; the different legacy logo was preserved in the archive rather than discarded.

## Updated

- Linux systemd now launches the same `app.main:app` used by Windows, through the installation virtual environment and loopback port 8080. Existing installations must adapt the user/path and reload their service configuration; no running service was restarted.
- README, deployment, onboarding, sync strategy, troubleshooting, API contracts, architecture and development guidance now describe the current runtime without fixed fleet totals or obsolete fallback claims.
- Updated startup links and issue-template commands; removed the stale dependency comment claiming a fully passing suite.
- `.gitignore` covers local `outputs/`, `scratch/` and browser reports; `.dockerignore` excludes outputs. Existing user files in those directories were preserved.
- Frontend linkage checks now verify served HTML assets and ES-module imports. Deployment tests check current launchers, and the SQLite path test exercises the current helper.

## Validation

- Audit baseline: 327 passed, 26 failed, 41 subtests passed.
- Focused post-cleanup checks: **83 passed**, including asset/module linkage, current deployment entry points, request safety, snapshot reconciliation, ingestion, cache and UI contracts.
- Full post-cleanup run: **317 passed, 19 failed, 4 warnings, 41 subtests passed**. All remaining failing test case names also appeared in the audit baseline; no new failing cases appeared. Counts changed because obsolete tests were removed or consolidated, not because application defects were fixed.
- `git diff --check` passed. Edited tracked files retain their original line-ending convention.
- Full output: `scratch/cleanup-pytest.txt` (local, ignored). Tests used an in-memory application database with scheduled ingestion disabled and source credentials cleared. Some full-suite checks independently use fixture data or existing localhost services.

## Remaining work

This cleanup does not resolve the audit's access-control, database error handling, Compose configuration or migration defects. The 19 remaining failures include older contracts, missing integration setup, local-service assumptions and proxy/environment sensitivity; they were retained for explicit triage instead of removing failing regression tests indiscriminately. Browser tests reported existing wording/capitalization discrepancies. No live ingestion or deployment was performed.

Legacy simulator/helper tests remain where other suites import them; migrating those tests to production implementations needs a separate test refactor. Historical archive commands are labeled as historical and may point to intentionally removed files.

## Exact tracked removals

- `app.js`
- `avatar.jpg`
- `cleanup_backend.ps1`
- `cmdb_explorer.html`
- `frontend/app.js`
- `frontend/demo_previews/current_ops_analytics_tab1.png`
- `frontend/demo_previews/current_tab1_bottom.png`
- `frontend/demo_previews/current_tab1_top.png`
- `frontend/demo_previews/current_tab2_solarwinds.png`
- `frontend/demo_previews/current_tab3_cmdb.png`
- `frontend/demo_previews/edge_landing_page.png`
- `frontend/demo_previews/final_master_donut_filter_critical.png`
- `frontend/demo_previews/final_master_donut_filter_interaction.png`
- `frontend/demo_previews/final_master_drilldown_modal.png`
- `frontend/demo_previews/final_master_reference_dashboard.png`
- `frontend/demo_previews/ia_01_endpoint_analytics.png`
- `frontend/demo_previews/ia_02_server_analytics.png`
- `frontend/demo_previews/ia_03_telecom_analytics.png`
- `frontend/demo_previews/ia_04_network_analytics.png`
- `frontend/demo_previews/infra_analytics_clean_mockup.png`
- `frontend/demo_previews/infra_analytics_mockup_1788700087678.jpg`
- `frontend/demo_previews/infra_analytics_with_site_report.png`
- `frontend/demo_previews/unified_infra_pie_site_mockup.png`
- `frontend/demo_previews/user_avatar_1788697435806.jpg`
- `frontend/demo_previews/user_original_uploaded_photo.jpg`
- `frontend/js/cmdb.js`
- `frontend/js/intune.js`
- `frontend/js/shared.js`
- `frontend/js/solarwinds.js`
- `frontend/ops_analytics.js`
- `frontend/style.css`
- `index.html`
- `infrastructure_analytics.html`
- `js/cmdb.js`
- `js/constants.js`
- `js/infrastructure_analytics.js`
- `js/intune.js`
- `js/services.js`
- `js/shared.js`
- `js/solarwinds.js`
- `js/utils.js`
- `logo.png`
- `ops_analytics.html`
- `ops_analytics.js`
- `scripts/deploy_to_vm.py`
- `scripts/fix_sync_status.py`
- `scripts/patch_sync_status.py`
- `scripts/run_sync.py`
- `scripts/start_server.py`
- `src/sync/firestore_sync.py`
- `style.css`
- `tests/test_solarwinds_site_routes.py`
- `tests/verify_adversarial_security.py`
