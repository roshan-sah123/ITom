# Testing the current ITOM Portal

The default suite tests production Python implementations and current portal contracts. It does not need the developer's `.env`, saved telemetry snapshots, a running portal or live source credentials.

## Run the offline suite

```powershell
python -m pip install -r requirements-test.txt
python -m pytest tests/ -q -ra
```

`conftest.py` selects a test database before application imports, disables scheduled ingestion, clears source credentials and fixes source transport defaults. Unexpected `requests` traffic is blocked. Database fixtures use temporary SQLite files; API fixtures wire the real routes, services, repositories and freshness middleware to that isolated database. Model-schema API fixtures are separate from tests executing actual Alembic migrations.

## Optional browser journeys

```powershell
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python -m pytest tests/browser/ --run-browser -q
```

Browser journeys launch headless Edge or Chromium and start a seeded portal on an ephemeral loopback port. They do not use port 8080 or the live inventory. The default run excludes `tests/browser/`; CI runs the whole offline suite. Shared browser fixtures stub external chart rendering and fonts for deterministic checks; their portal modules and database APIs remain real.

## Requirement and feature coverage

| Requirement / feature | Evidence |
|---|---|
| Intune inventory reporting locations, review badges, combined filters, pagination, CSV, retry and mobile layout | `test_intune_inventory_locations.py`, `browser/test_endpoint_inventory_locations.py` |
| PRD §6/§10: source filtering, search, sorting, bounded inventory pages | `test_api_contracts.py`, `test_location_and_network_contracts.py` |
| PRD §7/§14: source-backed sites reconcile with location-filtered inventory | `test_api_contracts.py`, `test_location_and_network_contracts.py`, `test_remediation_contracts.py` |
| PRD §6/§9: Intune compliance, OS/vendor and storage summaries | `test_step1_summaries.py`, `test_intune_forecast.py`, `test_endpoint_storage_panel.py` |
| PRD §6: detail/history, JSON serialization and audit visibility | `test_api_contracts.py`, `test_persistence_contracts.py`, `test_ingestion_scenarios.py` |
| PRD §8/§11: failed extraction does not advance freshness; source outcomes remain distinct | `test_step3_freshness.py`, `test_step4_live_sync.py`, `test_api_contracts.py` |
| Complete snapshot retirement, reappearance and rollback | `test_snapshot_reconciliation.py`, `test_persistence_contracts.py` |
| PRD §8: Graph pagination and SolarWinds read-only/TLS safety | `test_graph_client_contract.py`, `test_swql_security.py`, `test_source_request_safety.py` |
| PRD §11: configurable scheduler and overlap guards | `test_scheduler_and_locking.py` |
| PRD §12: relational integrity and clean migration install | `test_persistence_contracts.py`, `test_migration_contracts.py`, `test_sqlite_runtime_pragmas.py` |
| Summary cache consistency, invalidation and concurrency | `test_summary_cache.py` |
| Current portal navigation, unavailable states and asset/module linkage | `test_portal_navigation_contract.py`, `test_ui_truthfulness.py`, `test_zero_build_compliance.py` |
| Overview operator-queue drilldown and clearing filters | `browser/test_operator_queue.py` |
| Local service and deployment entry points | `test_local_service_environment.py`, `test_server_resilience.py`, `test_docker_infra_compliance.py` |
| Optional snapshot/export utilities | `test_payload_generator.py`, `test_challenger_adversarial_deep.py`, `test_tier5_adversarial.py` |

The tests use small synthetic inputs to check the production implementations. They do not define alternative database, API, router or chart implementations. AST/text checks are retained only for relevant zero-build wiring, unsupported UI states and configuration contracts.

## Two documented defects

Two cases use **strict expected-failure markers**. Their reasons are printed by `-ra`. A previously failing case that starts passing fails the run as XPASS until its marker is removed.

1. Alembic revision 0004 does not create three model indexes.
2. Its downgrade drops indexes absent from a clean migration install.

Inventory datastore failures and NUL-containing searches now have passing
regression coverage. API tests verify HTTP 503 for count and row-fetch failures
on all four list routes, without exposing database diagnostics. Invalid NUL
searches return no matches while ordinary inventory remains available.

To reproduce these as failures instead of expected failures:

```powershell
python -m pytest tests/test_migration_contracts.py --runxfail -k "all_model_indexes or downgrade_and_upgrade" -q
```

These markers document known defects; they are not a production release approval. Authentication, deployed proxy access controls, real PostgreSQL locking/migrations, container startup and representative load still need their own verification.

## Snapshot verification scripts

The remaining `verify_*.py` scripts inspect explicitly supplied or configured snapshot files for operator use. They are outside default pytest discovery and are not CI prerequisites. Their results apply to the snapshot being checked, not to the live application. The old custom E2E runner and unsupported executive-digest verification were removed.
