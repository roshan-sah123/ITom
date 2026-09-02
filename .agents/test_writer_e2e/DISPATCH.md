# DISPATCH: E2E Test Suite Creation Track

## Objective
Design and implement the comprehensive, opaque-box E2E and integration test suite covering requirements R1-R4 per `PROJECT.md` and `ORIGINAL_REQUEST.md`. Create `TEST_INFRA.md` and publish `TEST_READY.md` upon completion.

## Scope & Requirements
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\PROJECT.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\GEMINI.md`
- Read skill: `C:\Users\Roshan.Sah\.gemini\config\skills\test-driven-development\SKILL.md`
- Read survey analysis: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\explorer_survey_sync_test\analysis.md`

## Required Deliverables
1. `TEST_INFRA.md` at project root documenting testing methodology, feature inventory coverage matrix, and test architecture.
2. New test modules in `tests/`:
   - `tests/test_database_persistence.py`: Testing SQLAlchemy models, Alembic migrations, CRUD, relationship integrity, time-series history tracking, and JSONB queries.
   - `tests/test_fastapi_backend.py`: Testing FastAPI REST endpoints (`/api/v1/cmdb/*`, `/api/v1/intune/*`, `/api/v1/solarwinds/*`, `/healthz`, `/ready`), pagination envelope, sorting, search, and response headers (`X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status` FRESH/STALE).
   - `tests/test_background_sync_security.py`: Testing APScheduler lifespan integration, PostgreSQL advisory lock concurrency safety, SHA-256 delta detection, read-only SWQL validation (`ALLOWED_METHODS = ["GET"]`), and HTTP 405 Method Not Allowed error envelopes for mutating methods (`POST`, `PUT`, `DELETE`, `PATCH`).
   - `tests/test_docker_infra_compliance.py`: Testing Dockerfile multi-stage structure, non-root user `itom`, healthcheck configurations, docker-compose.yml 3-tier services (`nginx`, `api`, `postgres`), and `nginx.conf` routing rules.
3. Update `tests/run_e2e_tests.py` to include all new test modules in the master test runner.
4. Verify all tests pass cleanly with 100% pass rate.
5. Create `TEST_READY.md` at project root with full coverage summary across Tiers 1-4.

Write your completion report and handoff to `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\test_writer_e2e\handoff.md` and notify parent via `send_message`.
