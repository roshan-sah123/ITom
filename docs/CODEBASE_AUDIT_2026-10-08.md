# Codebase audit — 8 October 2026

Overall production-readiness confidence: **62/100 (moderate)**.

The application has credible ingestion and data-integrity safeguards, but the supplied deployment and verification story do not justify broad production confidence. This score is an engineering assessment, not a measured probability of failure or a certification. A loopback-only installation has less exposure than the supplied network-accessible Compose deployment.

Reviewed working tree at commit `76b653c`. No application code was changed. Existing untracked output and workbook work was preserved.

## Scoring method

| Dimension | Weight | Score | Main evidence |
|---|---:|---:|---|
| Correctness and data integrity | 25% | 75 | Snapshot validation, savepoints, reactivation and per-source audits; database errors still become empty inventory |
| Security and access control | 20% | 40 | Read-only source guards and TLS checks; no application authentication or sync authorization |
| Deployment and operational resilience | 20% | 45 | Health/readiness routes exist; Compose omits source configuration and gates on liveness |
| Verification and regression protection | 15% | 60 | Focused checks pass; full suite fails and includes simulations and environment-dependent tests |
| Architecture and maintainability | 10% | 72 | Clear API/service/repository boundaries; duplicated frontend assets and outdated contracts |
| Performance and scalability | 10% | 65 | Pagination and summary cache; per-record ingestion queries and database work on static responses |

Weighted result: 61.95, rounded to 62. Scores reflect reviewed paths and executed checks, not every possible behavior.

## Findings, ordered by priority

### 1. P1 — Anonymous callers can trigger ingestion and read inventory

Evidence: `app/api/v1/endpoints/sync.py:165–171`, `app/api/deps.py`, `app/main.py`, and `nginx.conf`. The sync route queues work without authentication, authorization, or a request-rate guard. The supplied reverse proxy also provides no access-control layer. Inventory endpoints expose operational metadata to anyone who can reach them. `SECRET_KEY` validation does not implement authentication.

Reproduction: using the actual app with `run_manual_sync` replaced by an `AsyncMock`, an unauthenticated POST to `/api/v1/sync/trigger?source_system=ALL` returned **202** and awaited the mocked background job once. No source ingestion was performed for this reproduction.

Remedy: require authenticated inventory access and an operator permission for sync; enforce rate limits or admission control. Validate these controls through the deployed proxy. This is a blocker for shared-network deployment unless an independently verified access-control layer supplies the protection.

### 2. P1 — Database errors look like a valid empty inventory

Evidence: `app/repositories/ci_repository.py:176–178`. `get_cis_paginated` catches every exception and returns `([], 0)`. Its service wraps that result as a normal pagination response. `get_by_id` similarly catches exceptions and returns `None` (`:49–52`).

Reproduction: a mocked session whose `execute` raises `RuntimeError('database unavailable')` produced **`([], 0)`** from the production repository. Operators can interpret a failed read as zero matching assets; lookup errors can become false not-found results. Freshness headers do not make the inventory body an error response.

Remedy: propagate datastore failures to an explicit 503/error response, reserve empty results for successful queries, and log the failure at an actionable level.

### 3. P1 — Compose does not configure live source ingestion or enforce readiness

Evidence: `docker-compose.yml:30–46` supplies only `DATABASE_URL` and `PORT` to the API; there is no `env_file` or source-settings mapping. `.dockerignore` excludes `.env`, so credentials configured in the host file do not enter the image. Compose's interpolation of its own database variables does not automatically forward other host settings to the container.

The API therefore uses its development environment default and enabled scheduler without Graph/SolarWinds credentials. Its health check targets `/healthz`, which reports liveness without checking migration state. Development startup uses `create_all`, which does not establish Alembic revision state; a live container can consequently fail `/ready`.

Remedy: explicitly pass environment, secrets, source settings and proxy configuration; apply migrations before API readiness; gate deployment on `/ready`. Require a configured database password instead of the supplied fixed fallback. Verify a clean container installation end to end.

### 4. P2 — Index migration does not create its indexes

Evidence: `alembic/versions/0004_sqlite_query_indexes.py:10–22`. Upgrade is `pass`, while downgrade drops `ix_sync_runs_started_at`, `ix_ci_last_sync_time`, and `ix_ci_location`. Those indexes exist in ORM metadata but are absent from earlier migration creation steps.

A database created solely through Alembic reaches the revision without those indexes. Downgrade can attempt to drop indexes that do not exist. Production skips the development `create_all` path, so that path cannot repair this inconsistency.

Remedy: make index creation explicit and compatible with already-provisioned databases; verify clean upgrade, existing-database upgrade and downgrade on SQLite and PostgreSQL.

### 5. P2 — Passing selected tests does not establish a reliable release gate

Evidence: `.github/workflows/ci.yml` runs eight selected files. Other suites use duplicated in-memory implementations (`tests/test_database_persistence.py`, `tests/test_background_sync_security.py`) or a simulated router (`tests/test_e2e_scenarios.py`). Some integration checks require local services on ports 8000/8080 or historical data files.

Full-suite result in this audit: **327 passed, 26 failed, 4 warnings, 41 subtests passed** in 41.87 seconds. Failures include removed demo/fallback expectations, a root endpoint still expected to return JSON, exact wording/capitalization checks, uninitialized database assumptions, asset drift and a localhost concurrency check. These failures need triage; they are not all production defects. One proxy-routing test passed in the focused run but failed in the full run, indicating environment/order sensitivity that remains unresolved.

Remedy: separate deterministic application tests, fixture-data checks and live/browser tests; initialize and migrate isolated databases; test production implementations; update obsolete assertions against agreed contracts. Add migration and deployment smoke checks to CI. Declare browser-test dependencies explicitly; the full suite uses Playwright, which is absent from `requirements.txt`.

### 6. P2 — Static files and liveness depend on a database round trip

Evidence: `app/core/middleware.py:34–42`. Freshness lookup runs after every response, including portal HTML, JavaScript, CSS and `/healthz`. A slow database can delay delivery of otherwise independent assets and process probes, and each such request adds database load.

Remedy: restrict freshness queries to relevant API responses, keep liveness independent of datastore latency, and cache or bound freshness lookups. Static analysis establishes the extra query; no production latency benchmark was performed.

### 7. P2 — Ingestion performs a lookup per asset

Evidence: `app/services/sync_service.py:170–178` queries `get_by_source_key` inside the item loop; new records also flush individually at `:227`. A 27,000-record batch entails at least 27,000 lookup executions before its additional writes.

Remedy: load existing natural keys in bounded batches and batch persistence while preserving history and transaction guarantees. Benchmark representative PostgreSQL ingestion before setting capacity claims. No measured throughput claim is made here.

## Evidence that raises confidence

- Complete-snapshot validation guards retirement; invalid identities and failed extraction do not authorize asset retirement.
- Inventory ingestion and retirement share a savepoint, and source success/failure is audited separately.
- PostgreSQL uses a transaction-scoped advisory lock; SQLite uses a process-local guard. Cross-process SQLite sync exclusion is not established.
- Source requests have read-only SWQL protection, defensive response validation and TLS verification checks.
- Inventory pagination, a sort-column allowlist, database-derived summaries, summary caching and HTML escaping are implemented.
- **57 focused tests passed**, covering Graph limits, forecast behavior, proxy routing, caching, UI contracts, local service environment, SQLite pragmas, snapshot reconciliation, source request safety and live-sync behavior with test sources.

## Verification boundaries

Tests ran with `SCHEDULER_ENABLED=false`, development settings and an in-memory application database. Source credentials were cleared for the full-suite run. Some tests independently use fixture files and already-running localhost services, so the full suite is not a wholly isolated run. The browser tests executed against the existing local portal and reported two wording/capitalization failures. No manual visual/accessibility audit was performed.

Initial asynchronous executions stalled inside the restricted sandbox and were stopped. The focused and full runs completed outside it. The two defect reproductions also ran outside it using mocks.

No live source refresh, Docker deployment, real PostgreSQL migration/locking test, dependency vulnerability scan, disaster-recovery drill or comprehensive load test was performed. Installed dependency vulnerability status is unverified. The full test output is saved at `scratch/codebase-audit-pytest.txt`.

Prioritize access control, truthful database failure responses and reproducible deployment first; then repair migrations and establish a trustworthy release gate before revisiting the score.
