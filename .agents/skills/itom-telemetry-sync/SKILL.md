---
name: itom-telemetry-sync
description: Verify and operate ITOM Microsoft Graph and SolarWinds SWIS ingestion into its configured SQLite or PostgreSQL CMDB.
---

# ITOM Telemetry Sync

## Current architecture

- Microsoft Intune data is read from Microsoft Graph; SolarWinds data is read from Orion SWIS.
- `app.services.sync_service.SyncService` normalizes and persists records into the database selected by `DATABASE_URL`.
- The active portal and versioned APIs read the database-backed repositories and summaries.
- When `SCHEDULER_ENABLED=True`, the FastAPI process runs APScheduler at `SYNC_INTERVAL_SECONDS` (default 600 seconds). Sync runs only while the app process is running.
- SQLite is the local VM default. PostgreSQL is used only when `DATABASE_URL` explicitly configures it.
- GitHub Actions runs code checks only. Live telemetry sync belongs to the configured ITOM runtime, not an ephemeral GitHub-hosted runner.

## Safe operational checks

1. Check `/api/v1/health`, `/ready`, `/api/v1/system/freshness`, and recent sync-run records before interpreting dashboard values.
2. Reconcile source counts against the latest successful run and active CI rows for that source. Never compare against historical counts embedded in old docs or tests.
3. For read-only extraction checks, use `scripts/run_live_sync.py --source intune --dry-run` or `--source solarwinds --dry-run`. These contact the configured source but do not persist CI records.
4. To intentionally persist a live sync, use `scripts/run_live_sync.py --source intune`, `--source solarwinds`, or `--source all`. Confirm the target database and credentials first; this updates the configured CMDB.
5. Compare extracted, normalized, rejected, persisted, and active-row counts. A failed or partial run must not advance freshness or retire source records.
6. Never print `.env` values in logs or reports. Keep secret-bearing environment files out of Git.

## Legacy artifacts

`scripts/run_sync.py`, `data/*.json` payload checks, Firestore references, Firebase deployment steps, and fixed historical fleet baselines are legacy workflows. They are not authoritative for the current FastAPI + repository + SQLite/PostgreSQL application. Do not reintroduce them into the active sync schedule without an explicit architecture decision.
