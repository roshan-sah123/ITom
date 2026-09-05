# Original User Request

## Initial Request — 2026-09-01T17:12:49Z

You are the Project Orchestrator (orchestrator_3) for the ITOM platform enterprise transformation project.

## Your Identity & Workspace
- Identity: orchestrator_3
- Working directory: c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\orchestrator_3
- Project root: c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur
- Authoritative user request: c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md

## Mission & Scope
Transform the IT Operations Management (ITOM) platform from flat-file JSON storage to a production-grade, persistent enterprise backend running on private/local server infrastructure.

### Detailed Requirements
1. **R1. Persistent Relational Database Layer (PostgreSQL 16 & SQLAlchemy 2.0 Async)**:
   - Establish PostgreSQL database schema supporting current configuration items (`configuration_items`, `ci_relationships`), time-series status history (`ci_status_history`), sync execution runs (`sync_runs`), and error logs (`sync_error_logs`).
   - Configure Alembic database migration pipeline.

2. **R2. FastAPI Asynchronous REST Backend**:
   - Implement modular FastAPI application with clean architecture (`app/api/v1`, `app/services`, `app/repositories`, `app/integrations`, `app/models`, `app/schemas`).
   - Implement paginated REST endpoints for CMDB (`/api/v1/cmdb/*`), Intune telemetry (`/api/v1/intune/*`), and SolarWinds (`/api/v1/solarwinds/*`).
   - Return standard data freshness and age headers on all responses (`last_synchronized_at`, `data_age_seconds`, `sync_status`).

3. **R3. Resilient Read-Only SolarWinds & Intune Background Ingestion Engine**:
   - Implement decoupled background worker (APScheduler) executing periodic sync every 10 minutes.
   - Strictly enforce read-only SWQL validation (`ALLOWED_METHODS = ["GET"]`).
   - Implement identity resolution, delta change detection, and execution audit logging.

4. **R4. Local Server Docker Compose Infrastructure**:
   - Create production Dockerfile, Docker Compose multi-container stack (`nginx`, `api`, `postgres`), and healthcheck endpoints.

### Acceptance Criteria
- [ ] Database tables successfully migrate via Alembic.
- [ ] All 1,543 SolarWinds CIs and 25,987 Intune devices persist in PostgreSQL with zero data loss.
- [ ] Historical changes generate records in `ci_status_history`.
- [ ] All REST endpoints return sub-20ms responses for paginated queries.
- [ ] Write attempts (`POST`, `PUT`, `DELETE`) against SolarWinds integrations strictly return HTTP 405 Method Not Allowed.
- [ ] Stale data (> 15m) correctly sets `sync_status = "STALE"`.
- [ ] 100% test pass rate across existing 115 test suite plus new database integration tests.

### Project Rules & Constraints (GEMINI.md)
- Zero-Hallucination Policy: Never create, display, or commit mock/simulated numbers for executive metrics.
- Intune: 25,987 total endpoints across Windows, macOS, Linux, iOS, Android. Compliance and storage invariants must reconcile with raw Graph datasets.
- SolarWinds Orion: 1,548 total server nodes (1,543 active CIs). Health tiers: High (Up & CPU<75% & RAM<80%), Medium (Warning or CPU/RAM 75-90%), Low/Critical (Down/Critical or CPU/RAM>90%).
- Security: Never commit credentials to git. All credentials stored exclusively in `.env`.
- XSS prevention: All rendered strings sanitized with `escapeHtml()`.

Execute this project systematically using your subagent swarms (explorers, workers/implementers, reviewers/challengers, synthesis/testing). Keep your progress.md updated regularly. When completely done and verified, report completion back to the Sentinel.

## Follow-up — 2026-09-02T11:28:29+05:30

Upgrade the ITOM Portal into an enterprise-grade platform with an industry-level high-contrast Obsidian frontend UI and a scalable, persistent FastAPI + PostgreSQL backend.

Working directory: c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur
Integrity mode: development

## Requirements

### R1. Industry-Grade Frontend UI/UX (`frontend-engineering`)
- Apply Obsidian dark-mode design tokens (`#0B0B0B` canvas, `#141414` cards, `#16161A` elevated headers, `#222222` borders).
- Polish the unified 3-Zone Telemetry Table with real-time 200ms debounced search, page size selectors (`10`, `25`, `50`, `100`), smart window pagination, and container scroll resets.
- Implement Chart.js slice-to-filter interactions with tooltip hints and memory leak prevention (`destroy()`).
- Enforce strict XSS escaping (`escapeHtml()`) across all dynamic tabular cells.
- Add accessibility attributes (`role="region"`, `aria-label`, `aria-current="page"`).

### R2. Scalable Backend & Relational Persistence (`backend-engineering`)
- Deploy modular FastAPI async architecture (`app/api/v1`, `app/services`, `app/repositories`, `app/integrations`, `app/models`, `app/schemas`).
- Establish PostgreSQL relational persistence for current state (`configuration_items`, `ci_relationships`), time-series history (`ci_status_history`), and execution logs (`sync_runs`, `sync_error_logs`).
- Expose REST API routes returning standard data freshness headers (`last_synchronized_at`, `data_age_seconds`, `sync_status`).

### R3. Resilient Read-Only Background Sync Engine
- Implement decoupled `APScheduler` async worker executing 10-minute recurring telemetry ETL.
- Strictly enforce read-only SWQL validation (`ALLOWED_METHODS = ["GET"]`) with HTTP 405 error envelopes.
- Implement delta change detection and PostgreSQL advisory locks for multi-worker safety.

### R4. Local Server Docker Compose Infrastructure
- Provide multi-container Docker Compose topology (`nginx` reverse proxy, `api`, `postgres` 16) with automated healthchecks.

## Acceptance Criteria

### Frontend Quality & Visual Polish
- [ ] Initial dashboard paint occurs in < 50ms.
- [ ] Tabular search and pagination operate seamlessly across all 25,987 Intune devices and 1,548 SolarWinds nodes.
- [ ] All charts support click-to-filter drill-downs into the data grid without memory leaks.
- [ ] 0 XSS vulnerabilities on user inputs.

### Backend Scalability & Invariant Contracts
- [ ] All REST endpoints return sub-20ms responses for paginated queries.
- [ ] Mutating HTTP requests (`POST`, `PUT`, `DELETE`) against read-only integrations strictly return HTTP 405.
- [ ] Stale data (> 15m) correctly sets `sync_status = "STALE"`.

### Verification Suite
- [ ] 100% pass rate across existing 115 tests + new backend integration tests.

## Follow-up — 2026-09-03T19:22:52+05:30

This is a single self-contained fix; keep it small and focused.

Fix the 5 verified bugs in the ITOM Portal codebase (Data Pipeline Drift, CORS Misconfiguration, Hardcoded SECRET_KEY, DEBUG Default, and Duplicate Frontend Assets) and ensure 100% test pass rate with strict security standards.

Working directory: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur`
Integrity mode: development

## Requirements

### R1. Resolve Data Pipeline Drift & Harden Test Guard
- Reconcile `data/solarwinds_nodes.json` and `data/solarwinds_summary.json` so summary metrics derive from the current raw dataset.
- Ensure `HealthClassification` is computed via `classify_node_health()` and persisted on each raw node record in `data/solarwinds_nodes.json` and generated in `src/sync/solarwinds_client.py`.
- Enhance `tests/verify_solarwinds_data.py` with an explicit guard that raises a descriptive error explaining that counts diverged and directing the operator to run `python scripts/fetch_solarwinds_data.py` or `python scripts/run_sync.py` instead of a bare `AssertionError`.
- Ensure `python tests/run_e2e_tests.py` achieves 214/214 passing tests.

### R2. Fix CORS Misconfiguration
- In `app/core/config.py` and `app/main.py`, replace wildcard `BACKEND_CORS_ORIGINS = ["*"]` with an explicit allow-list parsed from comma-separated `CORS_ORIGINS` in environment, defaulting to `["http://localhost:8080"]` for local development.
- Add Settings-load-time validation: if `allow_credentials=True` and any origin is `*`, fail fast at startup with a `ValueError`.
- Document `CORS_ORIGINS` in `.env.example`.

### R3. Eliminate Hardcoded SECRET_KEY
- In `app/core/config.py`, remove the hardcoded fallback secret string.
- Require `SECRET_KEY` from environment/`.env`. In non-development environments (`ENVIRONMENT != "development"`), raise a startup validation error if `SECRET_KEY` is unset or empty.
- Add instructions and generation command (e.g. `openssl rand -hex 32`) to `.env.example`.

### R4. Enforce Safe DEBUG Default
- In `app/core/config.py`, change default `DEBUG` to `False`.
- Only permit `DEBUG=True` when `ENVIRONMENT == "development"`.
- Enforce that `DEBUG=True` when `ENVIRONMENT == "production"` raises a startup validation error.

### R5. Harmonize Duplicate Frontend Assets & Verify Zero-Drift
- Designate `src/frontend/` as canonical source of truth for `index.html`, `app.js`, `ops_analytics.html`, `ops_analytics.js`, `style.css`, and `js/`.
- Ensure root-level assets are synchronized and byte-identical to `src/frontend/`, with `tests/test_zero_build_compliance.py` enforcing zero drift in automated test runs.
- Document any environment changes only in `.env.example` (no extraneous markdown docs).

## Acceptance Criteria

### Security & Configuration
- [ ] No wildcard CORS origin (`"*"`) allowed when `allow_credentials=True`. App fails fast at startup if configured insecurely.
- [ ] No hardcoded `SECRET_KEY` in source code; app refuses to start in production if `SECRET_KEY` is missing.
- [ ] `DEBUG` defaults to `False` in all environments; `DEBUG=True` is prohibited in `ENVIRONMENT=production`.
- [ ] All configuration options (`CORS_ORIGINS`, `SECRET_KEY`, `DEBUG`) documented in `.env.example`.

### Data Integrity & Test Automation
- [ ] `data/solarwinds_nodes.json` and `data/solarwinds_summary.json` reconciled with `HealthClassification` present on all nodes.
- [ ] `tests/verify_solarwinds_data.py` contains descriptive failure messages directing to sync scripts.
- [ ] Root-level and `src/frontend/` assets are verified byte-identical.
- [ ] `python tests/run_e2e_tests.py` reports **214/214 (100%) tests passing** with exit code 0.
