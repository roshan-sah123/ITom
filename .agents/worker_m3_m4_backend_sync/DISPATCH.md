# DISPATCH: Worker - Milestones 3 & 4: FastAPI REST Backend & Resilient Background Sync Engine

## Objective
Implement the complete FastAPI asynchronous REST backend (endpoints, repositories, services, middleware, freshness headers) and the resilient read-only background sync engine (APScheduler, PostgreSQL advisory locks, SHA-256 delta detection, SWQL validation, and HTTP 405 error envelopes).

## Scope & Instructions
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\PROJECT.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\GEMINI.md`
- Read skills:
  - `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\skills\backend-engineering\SKILL.md`
  - `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\skills\itom-telemetry-sync\SKILL.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
- `app/api/*` (`deps.py`, `v1/router.py`, `v1/endpoints/cmdb.py`, `v1/endpoints/intune.py`, `v1/endpoints/solarwinds.py`, `v1/endpoints/sync.py`, `v1/endpoints/health.py`)
- `app/core/middleware.py`, `app/core/security.py`
- `app/repositories/*` (`base.py`, `ci_repository.py`, `sync_repository.py`)
- `app/services/*` (`ci_service.py`, `sync_service.py`)
- `app/workers/*` (`scheduler.py`)
- `app/main.py`

## Tasks
1. Implement `app/core/security.py` with read-only SWQL validator and keyword checks.
2. Implement `app/core/middleware.py` Starlette middleware for freshness headers (`X-Last-Synchronized-At`, `X-Data-Age-Seconds`, `X-Sync-Status` FRESH<=900s/STALE>900s) and strict HTTP 405 Method Not Allowed error envelopes for mutating verbs on read-only endpoints.
3. Implement `app/repositories/ci_repository.py` and `app/repositories/sync_repository.py` executing sub-20ms queries with pagination, search, and JSONB filtering.
4. Implement `app/services/ci_service.py` and `app/services/sync_service.py` with SHA-256 delta detection and time-series history logging.
5. Implement `app/workers/scheduler.py` with APScheduler async worker (10-minute cadence) and PostgreSQL session advisory lock `1048576`.
6. Implement all API v1 endpoints (`/cmdb/*`, `/intune/*`, `/solarwinds/*`, `/sync/*`, `/healthz`, `/ready`) in `app/api/v1/endpoints/` and master `app/main.py` with lifespan event handling.
7. Run verification test suites:
   ```powershell
   python tests/test_fastapi_backend.py
   python tests/test_background_sync_security.py
   python tests/run_e2e_tests.py
   ```
8. Document all changes, test commands, and passing output in `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m3_m4_backend_sync\handoff.md`.
