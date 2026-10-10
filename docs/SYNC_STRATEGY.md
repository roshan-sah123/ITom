# Telemetry synchronization

The backend scheduler runs `SyncService.execute_sync_with_lock` every `SYNC_INTERVAL_SECONDS` (default 600). Opening the portal reads the stored snapshot. It does not fetch Graph or SolarWinds directly.

## Current pipeline

1. Acquire a PostgreSQL transaction advisory lock, or the process-local SQLite guard.
2. Fetch each selected source through its read-only adapter in a worker thread.
3. Validate source identifiers and normalize records.
4. Persist inventory and status/health history under a savepoint.
5. Retire missing assets only after a validated complete source snapshot.
6. Record a separate success or failure for each source and commit.
7. Invalidate affected summary caches after successful ingestion.

The SQLite guard does not establish exclusion between separate processes. Operate a single ingestion process for a local SQLite installation.

## Controls

- `SCHEDULER_ENABLED=false` disables scheduled collection for development.
- `SYNC_INTERVAL_SECONDS` changes the collection interval.
- Graph and SolarWinds credentials, TLS and proxy settings are defined in `.env.example` and `app/core/config.py`.
- `python scripts/run_live_sync.py --source intune`, `--source solarwinds`, or `--source all` runs the current ingestion path and prints reconciliation results.
- `POST /api/v1/sync/trigger` starts background ingestion. Protect access before exposing it to shared networks.

`/api/v1/system/freshness` derives freshness from successful database audit records. `/api/v1/sync/status` reports the latest attempts, including failures. `/healthz` is process liveness; `/ready` checks database connectivity and migration state.

## Snapshot utilities

The `fetch_intune_data.py`, `fetch_solarwinds_data.py`, `generate_dashboard_payload.py` and `fetch_cmdb_data.py` scripts support explicit local snapshot/export workflows. Their files are not the production ingestion source. `FixtureSource` is reserved for tests and offline demonstrations. The former Firestore/file-summary sync runner has been retired.

See [data flow](DATA_FLOW.md), [deployment](DEPLOYMENT.md) and [troubleshooting](TROUBLESHOOTING.md).
