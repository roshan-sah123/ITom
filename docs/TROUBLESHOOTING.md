# Troubleshooting

## Portal or API unavailable

Run `start_itom_service.bat --status` for the Windows supervisor. Inspect its logs and check `/healthz` separately from `/ready`. A successful liveness response does not establish database readiness or source freshness.

For direct development, launch `python -m uvicorn app.main:app --host 127.0.0.1 --port 8080`. Ensure another process is not already using the port.

## Database readiness fails

Confirm `DATABASE_URL` selects the intended database and run `alembic upgrade head` using the same environment. A development `create_all` bootstrap is not an Alembic migration. Check permissions, database reachability and the configured driver. The current index migration limitation is recorded in the [audit](CODEBASE_AUDIT_2026-10-08.md).

## Telemetry missing or stale

Inspect `/api/v1/sync/status`, `/api/v1/sync/runs` and `/api/v1/system/freshness`. Failed extraction must not advance successful-sync timestamps. A 503 summary can mean no domain records have been ingested; do not substitute demo counts.

Check source credentials, source service permissions, proxy policy and certificate trust. Keep TLS verification enabled. Use `python scripts/check_live_connectivity.py` only when explicitly checking live source access. `scripts/run_live_sync.py --source intune` or `--source solarwinds` performs real ingestion and writes to the configured database.

## Browser request failures

The usual installation serves portal and API together, using `/api/v1`. If hosting the frontend separately, set `window.ITOM_API_BASE` before its module loads and configure CORS for that origin. Inspect browser request failures and console output. CDN-hosted fonts and Chart.js also require network access.

## Tests fail

Install `requirements-test.txt` and run `python -m pytest tests/ -q -ra`. Fixtures provide isolated databases, disable the scheduler and block live source requests. Four strict expected failures document genuine defects; use `--runxfail` to reproduce them as failures. Browser tests are explicit opt-in and start an isolated portal. See [the testing guide](../tests/README.md).

Historical prototype instructions are retained under [archive](archive/legacy-2026-09/README.md). Current entry points are listed in [onboarding](ONBOARDING.md).
