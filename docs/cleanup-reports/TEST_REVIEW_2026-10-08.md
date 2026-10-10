# Test review — 8 October 2026

## Result

The suite now exercises the current application without depending on historical fleet snapshots or an already-running portal. The final offline run passed **273 tests**, with **4 strict expected failures**, **41 passing subtests** and **12 deprecation warnings**. Both isolated browser journeys passed. A combined offline/browser run passed **275 tests** with the same four expected failures.

Starting baseline after repository cleanup: 317 passed and 19 failed. Counts are not directly comparable because simulation tests were removed, real cases added and useful checks parameterized. No code-coverage percentage is claimed.

## Removed or replaced

Removed 11 obsolete test/helper files:

- `test_database_persistence.py`: copied database/models; replaced with real SQLAlchemy constraint, JSON, scope and cascade tests.
- `test_fastapi_backend.py`: copied API behavior; replaced with requests against the actual FastAPI app.
- `test_tab_navigation.py`, `test_e2e_scenarios.py`, `test_tier5_adversarial_stress.py`: copied router/filter/CSV/chart simulations and prototype workflows; replaced relevant operator journeys with real browser checks.
- `test_background_sync_security.py`: simulated scheduler, locks and ingestion. Retained its actual SWQL guard cases in `test_swql_security.py`; added tests of actual scheduler and sync lock code.
- `test_fastapi_live_integration.py`, `test_enterprise_fortune5_audit.py`: obsolete contracts, local-server assumptions and historical snapshot assertions. Consolidated useful API, hostile-input, freshness and serialization checks into isolated integration tests.
- `run_e2e_tests.py`: custom unittest runner with obsolete imports and duplicate discovery; pytest is the canonical runner.
- `verify_executive_digest.py`, `verify_math_invariants.py`: unsupported digest and historical cross-file checks outside the current application feature set.

Replaced the copied payload generator in `test_payload_generator.py` with calls to production functions. Replaced copied Docker/Compose specifications with checks of the actual deployment files. Removed the historical Intune reconciliation class from the otherwise useful Graph/payload boundary suite. Converted the permutation test to deterministic records instead of reading developer telemetry files.

Preserved useful source security, normalization, summaries, forecast, ingestion, rollback, reconciliation, caching and UI contract tests. Updated outdated assumptions about comments in SWQL, unknown-device defaults, server classification, error wording and the current TechAdmin navigation link. These updates did not change production behavior.

## Added real coverage

- Inventory pagination boundaries, filters, sorting, source isolation, retired assets and JSON-safe identities/timestamps across the actual inventory routes.
- Source summaries reconciled to controlled persisted inventory, empty CMDB disclosure and unavailable source-domain summaries.
- Hostile search inputs without SQL mutation or unintended inventory expansion.
- CI detail, relationships and status history, including history persisted by actual background ingestion.
- Source freshness, failed-attempt handling, sync audit serialization, source filtering, valid/invalid manual-sync dispatch, disabled scheduler and CORS allowlists.
- Site catalog totals reconciled with the corresponding location-filtered inventory.
- Real natural-key uniqueness, source namespaces, JSON roundtrips, foreign-key enforcement, cascades and retired read scope.
- Configurable scheduler cadence, transaction-scoped PostgreSQL lock SQL, lock failure behavior and the real SQLite process-local overlap guard.
- Clean Alembic upgrade, schema-column parity, idempotent upgrade, index parity and downgrade roundtrip.
- Untrusted/cyclic Graph pagination URLs and malformed Graph pages.
- Production snapshot generator file roundtrip, sample limits, capacity weighting and rejection of empty input.

See [the testing guide](../../tests/README.md) for the requirement/feature mapping and commands.

## Isolation and CI

`tests/conftest.py` neutralizes test configuration before application imports, clears credentials, disables periodic ingestion, blocks unexpected requests-based source traffic and provides isolated databases/API fixtures. The SQLite pragma test now uses pytest's temporary directory. Shared model records live in `tests/factories.py` instead of importing another test module.

Browser tests are explicit opt-in under `tests/browser/`. They create a seeded temporary portal on an ephemeral port rather than reading the user's running service. Browser asset loading still needs access to the portal's CDN dependencies.

Added `requirements-test.txt` for YAML validation and `requirements-browser.txt` for the installed Playwright version. CI installs test dependencies and runs the complete offline suite. Its previously unquoted SQLite URL was invalid YAML; the YAML test exposed that and the URL is now quoted. Added Alembic's explicit `path_separator` setting to eliminate its configuration deprecation warnings.

The workflow was parsed and checked locally; no remote GitHub workflow run was triggered. Application business logic was not changed by this test review.

## Defects remain explicit

Four narrow strict expected-failure markers preserve genuine defects:

1. Database read exceptions become empty inventory.
2. NUL-containing SQLite search matches unrelated inventory.
3. Migration 0004 omits three indexes.
4. Its downgrade attempts to drop missing indexes.

Running these with `--runxfail` produced **4 failures and 5 passing hostile-input controls**, confirming that the expected failures reproduce actual defects. Strict XPASS handling requires removing each marker after its fix. This is not a fully defect-free or production-approved release.

The remaining 12 warnings concern deprecated HTTP 422 constant names in production routes; they were not suppressed. Live Graph/SolarWinds access, actual PostgreSQL lock behavior, PostgreSQL migrations, container startup and representative load were not verified by this offline SQLite suite.

## Verification artifacts

Local ignored output files:

- `scratch/test-review-offline-final.txt`: final default/CI-equivalent suite.
- `scratch/test-review-final.txt`: combined suite including browser journeys.
- `scratch/test-review-browser.txt`: independent browser run.
- `scratch/test-review-known-defects.txt`: known-defect reproduction without markers.

All local test-module imports resolve. Whitespace checks passed with CRLF-aware Git settings for the Windows checkout. Changes remain in the working tree alongside the preceding authorized repository cleanup.
