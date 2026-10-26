# Deployment

The supported runtime is `app.main:app`. It serves `frontend/` and the database-backed API on one listener. The former file-based HTTP daemon and its remote deployment script have been retired.

## Windows local service

Create `.venv`, install `requirements.txt`, and configure `.env` from `.env.example`. Apply schema migrations:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
```

Use the local supervisor:

```cmd
start_itom_service.bat --background
start_itom_service.bat --status
start_itom_service.bat --restart
start_itom_service.bat --stop
```

It binds the portal to `127.0.0.1:8080`. `--open-browser` opens the portal after launch. The older `start_server.bat` is a forwarding alias to this launcher.

For ten-minute ingestion, set `SCHEDULER_ENABLED=true` and `SYNC_INTERVAL_SECONDS=600` in the runtime environment or `.env`, then restart the backend. Environment variables inherited by an already running process remain authoritative until it is restarted. Verify `/api/v1/sync/scheduler` reports `enabled=true`, `running=true`, `interval_seconds=600` and a future `next_run`; a healthy `/ready` response alone does not confirm ingestion is enabled.

For login startup, use `scripts/register_local_itom_task.ps1`; its `-Status` and `-Remove` switches inspect or remove that task. The older root `register_startup_service.ps1` manages a differently named task and remains available for existing installations. Do not register both tasks for one checkout.

## Linux service

The template `systemd/itom.service` starts `.venv/bin/python -m uvicorn app.main:app` on loopback port 8080. Adapt its user, group, working directory and executable path to the installation. Create the virtual environment, install dependencies, configure `.env`, and run `alembic upgrade head` before enabling the service. The template does not perform migrations.

Use a separately configured authenticated TLS reverse proxy for shared-network access. The app currently does not provide its own authentication; restrict inventory and manual sync access at the deployment boundary.

## Containers

`Dockerfile` runs FastAPI on port 8000 as a non-root user. Compose adds PostgreSQL and NGINX, bound to `127.0.0.1:8080` by default. Set `POSTGRES_PASSWORD` in the Compose environment or local `.env` before starting; there is no fallback password. If it contains URL-reserved characters, encode it for the API connection URL or configure `DATABASE_URL` separately.

```bash
docker compose up --build -d
docker compose ps
docker compose logs api
```

Compose forwards only database configuration and `PORT` to the API. Configure explicit runtime environment/secrets for source credentials, proxy settings, `ENVIRONMENT=production` and a strong `SECRET_KEY`; `.env` is excluded from the image. Raw `data/` files are not mounted into the web root, and NGINX rejects `/data` requests.

Keep the loopback binding unless an authenticated gateway protects inventory, exports, and manual sync. The application has no sign-in or sync rate limit. Sync API responses hide stored messages, stack traces, and diagnostic context; administrators can investigate the run ID using restricted backend records/logs.

Apply Alembic migrations against the intended database before starting the production API. Production startup does not create tables. The supplied container health check uses `/healthz`; independently verify `/ready` before allowing traffic. The [audit](CODEBASE_AUDIT_2026-10-08.md) records remaining deployment and migration limitations.

### SolarWinds source groups

Revision `0008_solarwinds_groups` adds the source group/membership tables and
nullable audit counts. Stop the local supervisor, back up the configured database,
apply `alembic upgrade head`, and restart the supervisor. The next normal
SolarWinds sync populates the hierarchy; before that, the UI reports that no group
snapshot is available. Confirm `/ready`, the latest successful SolarWinds run's
group counts, and `/api/v1/solarwinds/groups`. Reconcile IDs and descendant device
sets with SWIS rather than historical fleet counts. A failed hierarchy extraction
keeps the last complete node/group snapshot and its original freshness timestamp.
Opening or refreshing the group browser only reads the CMDB.

Revision `0009_group_site_scores` preserves stable source group IDs and adds
explicit reviewed links to canonical/Intune locations. For this rollout, stop
the local supervisor, create a checked SQLite backup, upgrade to head, ingest
NodeCategory and NodeType through the normal locked SolarWinds sync, then restart.
Verify unique fleet/category counts, group coverage, selected summaries and
snapshot evidence. Combined starts unavailable without explicit approved links;
use the local administration command documented in
[dashboard Site Scores](DASHBOARD_SITE_SCORES.md). PostgreSQL DDL compilation
does not replace a migration test against an isolated PostgreSQL server.

## Operational checks

- `/healthz`: process liveness.
- `/ready`: database connectivity and migration head.
- `/api/v1/system/freshness`: last successful source refreshes.
- `/api/v1/sync/status`: last source attempts and failures.
- `python scripts/run_live_sync.py --source all`: explicitly fetch and persist live telemetry; requires credentials and source connectivity.

Keep databases, snapshot files, backups and exports out of the image and Git. Back up the configured datastore before schema changes. See [troubleshooting](TROUBLESHOOTING.md).
