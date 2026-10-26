# ITOM Portal Development Guidelines

## Source-backed telemetry

- Display metrics from persisted, verified Microsoft Graph and SolarWinds telemetry.
- Never hardcode fleet totals or substitute demo values for unavailable data.
- Present non-integrated features as unavailable or coming soon.
- Preserve source provenance, freshness and per-source failure states.

## Runtime

- Use `app.main:app` for the API and `frontend/` for browser assets.
- Use the scheduler and `scripts/run_live_sync.py` for database ingestion.
- SolarWinds access remains read-only: HTTP GET and SELECT-only SWQL.
- Use [architecture](docs/ARCHITECTURE.md) and [data flow](docs/DATA_FLOW.md) for current contracts.

## UI

- Work exclusively in the current React source at `frontend-revamp/`; build its static output into `frontend/`.
- Preserve the exported design in `frontend-revamp/src/index.css` and the existing React components. Let React escape untrusted values; avoid raw HTML injection.
- The retired UI is local-only in the ignored `not-in-use/legacy-frontend/` directory. Do not import or restore it for current work.
- Compute labels and counts from API responses rather than historical baselines.

## Secrets

- Keep credentials out of Git and read them from runtime environment configuration.
- Keep TLS verification enabled and follow the configured source proxy policy.
