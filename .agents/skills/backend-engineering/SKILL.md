---
name: backend-engineering
description: Change the ITOM FastAPI backend, repositories, source adapters, and scheduler while preserving source integrity and local deployment boundaries.
---

# ITOM backend engineering

## Current architecture

- Follow `app/api/v1` -> services -> repositories -> SQLAlchemy models. Inspect existing route contracts; avoid introducing a different response envelope for unrelated endpoints.
- `DATABASE_URL` selects SQLite or PostgreSQL. SQLite is the local default. Use Alembic for schema changes and preserve both supported database paths.
- Graph and SolarWinds integrations remain read-only. Preserve request guards, pagination validation, TLS verification, and timeouts.
- Use the configured scheduler interval (default 600 seconds). Preserve transaction-scoped PostgreSQL advisory locks and the SQLite process lock; the latter does not coordinate multiple processes.

## Source evidence

- Compute metrics from active persisted records. Missing evidence stays unavailable; identify forecasts and derived health as calculations.
- Only a validated complete snapshot can retire absent records. Failed or partial runs must not advance successful freshness.
- Preserve source identities, audit counts, and meaningful status history. Current measurements do not establish historical performance or service SLA.

## Deployment boundaries

- Keep raw telemetry, databases, backups, credentials, and generated outputs outside public static directories and container build context.
- Bind local deployments to loopback. Shared access requires an authenticated gateway with inventory/export access control and operator authorization for sync. CORS and a configured secret key do not provide sign-in.
- Require explicit deployment credentials; never add fallback database passwords or print `.env` values.
- Return safe error summaries and run IDs. Keep raw exception messages, stack traces, and diagnostic context in restricted backend storage/logs, including for previously stored failures.

## Verification

Reproduce behavior fixes with a focused failing test, then run relevant checks using isolated databases and blocked upstream requests. Do not trigger live ingestion just to test code. Maintain deployment steps in `docs/DEPLOYMENT.md` and source verification procedures in the `itom-telemetry-sync` skill. Avoid duplicated historical counts or generic architecture examples.
