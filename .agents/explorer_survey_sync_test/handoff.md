# Handoff Report: Sync Engine, Read-Only Security, Docker Infrastructure & Test Suite Architecture

**From**: Sync Engine & Testing Explorer (`explorer_survey_sync_test`)  
**To**: Project Orchestrator (`orchestrator_3` / `sentinel`)  
**Date**: 2026-09-02  
**Handoff Type**: Hard Handoff (Survey Phase Complete)  
**Detailed Report**: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\explorer_survey_sync_test\analysis.md`

---

## 1. Observation

1. **Existing Sync Mechanism**:
   - `scripts/start_server.py:350-363`: Uses `threading.Thread(target=run_sync_daemon)` which executes `time.sleep(600)` and calls `subprocess.run([sys.executable, SYNC_SCRIPT, "--skip-firestore"], timeout=300)`.
   - `scripts/cron_daemon.py:1-21`: Marked deprecated; delegates to `scripts/run_sync.py`.
   - Current sync writes directly to flat files `data/intune_summary.json`, `data/solarwinds_summary.json`, `data/cmdb_summary.json`, and `exports/cmdb_network_cis_complete.csv`.

2. **Read-Only SWQL Validation & HTTP Verb Guards**:
   - `src/sync/solarwinds_client.py:137-177`: Defines `ALLOWED_METHODS = ["GET"]`, `FORBIDDEN_SWQL_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "MERGE"}`, and `validate_swql_read_only(query_str)`.
   - `scripts/start_server.py:233-248`: `do_POST()`, `do_PUT()`, `do_DELETE()`, `do_PATCH()` return HTTP 405 with `{"error": "Forbidden: SolarWinds CMDB API is strictly READ-ONLY.", "allowed_methods": ["GET"]}`.
   - Target backend package `app/` is not yet created in the workspace; will be built during M1-M4.

3. **Docker Infrastructure**:
   - `Dockerfile:1-5`: Minimal single-stage `FROM nginx:alpine` copying static files to `/usr/share/nginx/html`.
   - `docker-compose.yml:1-9`: Minimal single-service configuration exposing port 8080.
   - Requirements specify 3-tier architecture: `nginx` (reverse proxy), `api` (FastAPI backend with multi-stage non-root Python build), `postgres` (PostgreSQL 16 with healthchecks and volumes).

4. **Test Suite Baseline & Execution**:
   - Master E2E runner: `python tests/run_e2e_tests.py` ran 119 tests across 9 modules and passed in 4.238 seconds (100% pass rate).
   - Pytest suite: `pytest tests/` ran 120 tests and passed in 9.95 seconds.
   - Verified data invariants: Intune (25,987 endpoints, 21,589 compliant, 37.4% storage), SolarWinds (1,548 total server nodes, 1,543 active CIs, 1,357 High Health, 150 Medium, 41 Low).

---

## 2. Logic Chain

1. **Ingestion Scheduling & Multi-Worker Safety**:
   - *Premise (Observation 1)*: Background sync currently runs as a basic thread calling a CLI script, writing to flat JSON files with zero database locking or historical change tracking.
   - *Deduction*: Deploying FastAPI with multi-worker ASGI (`uvicorn --workers > 1`) would cause duplicate concurrent sync jobs.
   - *Solution*: Embed `APScheduler` (`AsyncIOScheduler`) into FastAPI's lifespan and guard execution with PostgreSQL session-level advisory locks (`SELECT pg_try_advisory_lock(1048576)`).
   - *Deduction for Time-Series*: To prevent table bloat, delta change detection (SHA-256 state fingerprinting of volatile attributes) will ensure `ci_status_history` only receives new records when a CI's operational status changes.

2. **Read-Only Security Invariant**:
   - *Premise (Observation 2)*: Upstream monitoring APIs (SolarWinds SWIS v3, Microsoft Graph) are authoritative read-only sources.
   - *Deduction*: Any mutating verb (`POST`, `PUT`, `DELETE`, `PATCH`) must be blocked at both the HTTP router/middleware layer (returning HTTP 405 with standard envelope) and the client query execution layer (validating SWQL starts with `SELECT` and contains no forbidden SQL DML/DDL tokens).

3. **Docker Multi-Container Orchestration**:
   - *Premise (Observation 3)*: The existing Docker configuration is purely static and cannot support PostgreSQL 16 or FastAPI.
   - *Deduction*: Multi-container `docker-compose.yml` must define `postgres` (16-alpine with healthcheck `pg_isready`), `api` (FastAPI backend built via multi-stage Dockerfile with non-root user `itom` and healthcheck `/healthz`), and `nginx` (reverse proxy routing `/` to static frontend and `/api/` to `api:8000/api/`).

4. **Test Coverage Expansion Strategy**:
   - *Premise (Observation 4)*: The existing 119 E2E tests thoroughly test frontend DOM, CSV export, and invariant math, but currently have zero tests for PostgreSQL database models, Alembic migrations, FastAPI REST endpoints, APScheduler advisory locks, or Docker infrastructure probes.
   - *Deduction*: 65 new test cases must be added across 4 new test modules (`test_database_persistence.py`, `test_fastapi_backend.py`, `test_background_sync_security.py`, `test_docker_infra_compliance.py`) and integrated into `tests/run_e2e_tests.py` to maintain 100% test pass rate throughout milestones M1-M5.

---

## 3. Caveats

1. **Live External Network Access**:
   - External APIs (Microsoft Graph, SolarWinds Orion at `gnoc.coforge.com:17774`) may require specific network routing or environment credentials in `.env`.
   - Tests and local ingestion fallback to local authoritative datasets (`data/intune_ops_analytics.json`, `data/solarwinds_nodes.json`) when live credentials are not present, ensuring zero disruption to offline development.
2. **PostgreSQL Service Availability**:
   - Tests for PostgreSQL persistence require a local or containerized PostgreSQL instance or an async SQLite mock engine (`aiosqlite`) during unit testing to allow zero-dependency test execution in environments without a running Postgres daemon.

---

## 4. Conclusion

The technical blueprints for the background ingestion engine, read-only security guards, Docker Compose topology, and test suite expansion are fully defined and validated against the project requirements (R1-R4) and acceptance criteria:
- **APScheduler Ingestion**: 10-minute cadence, PostgreSQL advisory locks (`1048576`), SHA-256 delta detection, and audit tables (`sync_runs`, `sync_error_logs`).
- **Read-Only SWQL Guard**: `ALLOWED_METHODS = ["GET"]`, HTTP 405 on mutating verbs, discrete token blocklists.
- **Docker Compose Topology**: 3-tier stack (`nginx:alpine`, `api` Python 3.11 multi-stage non-root, `postgres:16-alpine`), `/healthz` and `/ready` probes.
- **Testing Strategy**: 119 existing E2E tests + 65 new backend/integration tests spanning Tiers 1-5 with 100% pass rate target.

---

## 5. Verification Method

To independently verify the observations, existing test suite baseline, and analysis report:

1. **Verify Master E2E Test Suite (119 Tests)**:
   ```bash
   python tests/run_e2e_tests.py
   ```
   *Expected*: 119/119 tests pass across 9 suites in < 5 seconds.

2. **Verify Full Pytest Suite (120 Tests)**:
   ```bash
   pytest tests/
   ```
   *Expected*: 120 passed in ~10 seconds.

3. **Verify Technical Analysis Document**:
   Inspect `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\explorer_survey_sync_test\analysis.md`.
