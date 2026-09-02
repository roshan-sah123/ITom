# DISPATCH: Worker - Milestone 2: Relational Database Persistence & Schema

## Objective
Implement the persistent database layer with SQLAlchemy 2.0 Async, PostgreSQL 16 schema models, Alembic migration pipeline, and automated seeding scripts to persist all 25,987 Intune CIs and 1,543 SolarWinds CIs.

## Scope & Instructions
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\PROJECT.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\GEMINI.md`
- Read skill: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\skills\backend-engineering\SKILL.md`
- Read survey handoff: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\explorer_survey_backend\handoff.md` and `analysis.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
- `app/models/*` (`base.py`, `ci.py`, `history.py`, `sync.py`)
- `app/core/*` (`config.py`, `database.py`)
- `app/schemas/*` (`common.py`, `ci.py`, `sync.py`)
- `alembic.ini`, `alembic/*` (`env.py`, `script.py.mako`, `versions/0001_initial_schema.py`)
- `scripts/seed_database.py`
- `requirements.txt` (add required dependencies: `fastapi`, `uvicorn`, `sqlalchemy>=2.0.0`, `asyncpg`, `alembic`, `pydantic-settings`, `apscheduler`, `aiosqlite`)

## Tasks
1. Update `requirements.txt` with necessary backend packages.
2. Implement `app/core/config.py` using `pydantic-settings` to load `.env` securely without committing secrets.
3. Implement `app/core/database.py` providing async SQLAlchemy engine, async sessionmaker, and `get_db_session()` dependency. Support both PostgreSQL (`asyncpg`) and SQLite (`aiosqlite`) for test flexibility.
4. Implement SQLAlchemy 2.0 declarative models in `app/models/`:
   - `ConfigurationItem` and `CIRelationship` in `app/models/ci.py`
   - `CIStatusHistory` in `app/models/history.py`
   - `SyncRun` and `SyncErrorLog` in `app/models/sync.py`
   - Include all composite B-tree, covering, and GIN trigram indexes per `PROJECT.md`.
5. Configure Alembic migration environment (`alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial_schema.py`) mapping all tables and indexes.
6. Implement `scripts/seed_database.py` (and service functions) to seed database from `data/intune_ops_analytics.json` (25,987 devices) and `data/solarwinds_nodes.json` / `data/cmdb_summary.json` (1,543 CIs), maintaining zero data loss and recording initial `sync_runs` entry.
7. Run verification tests to validate models, schema creation, seeding, and invariant counts.
8. Document all changes, test commands, and passing output in `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m2_backend_db\handoff.md`.
