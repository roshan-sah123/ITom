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

- Follow `frontend/css/style.css` and existing components rather than copying old root assets.
- Escape untrusted values with `escapeHtml()` before rendering HTML.
- Compute labels and counts from API responses rather than historical baselines.

## Secrets

- Keep credentials out of Git and read them from runtime environment configuration.
- Keep TLS verification enabled and follow the configured source proxy policy.
