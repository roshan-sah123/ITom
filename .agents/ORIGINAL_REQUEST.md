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
