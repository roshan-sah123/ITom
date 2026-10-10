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

For login startup, use `scripts/register_local_itom_task.ps1`; its `-Status` and `-Remove` switches inspect or remove that task. The older root `register_startup_service.ps1` manages a differently named task and remains available for existing installations. Do not register both tasks for one checkout.

## Linux service

The template `systemd/itom.service` starts `.venv/bin/python -m uvicorn app.main:app` on loopback port 8080. Adapt its user, group, working directory and executable path to the installation. Create the virtual environment, install dependencies, configure `.env`, and run `alembic upgrade head` before enabling the service. The template does not perform migrations.

Use a separately configured authenticated TLS reverse proxy for shared-network access. The app currently does not provide its own authentication; restrict inventory and manual sync access at the deployment boundary.

## Containers

`Dockerfile` runs FastAPI on port 8000 as a non-root user. `docker-compose.yml` adds PostgreSQL and an NGINX portal on the configured host port (default 8080).

```bash
docker compose up --build -d
docker compose ps
docker compose logs api
```

The supplied Compose file currently forwards only database configuration and `PORT` to the API. Host `.env` files are not automatically forwarded into the container, and `.dockerignore` excludes them from the image. Configure explicit runtime environment/secrets for source credentials, proxy settings, `ENVIRONMENT=production` and a strong `SECRET_KEY`. Replace the fallback database password.

Apply Alembic migrations against the intended database before starting the production API. Production startup does not create tables. The supplied container health check uses `/healthz`; independently verify `/ready` before allowing traffic. The [audit](CODEBASE_AUDIT_2026-10-08.md) records remaining deployment and migration limitations.

## Operational checks

- `/healthz`: process liveness.
- `/ready`: database connectivity and migration head.
- `/api/v1/system/freshness`: last successful source refreshes.
- `/api/v1/sync/status`: last source attempts and failures.
- `python scripts/run_live_sync.py --source all`: explicitly fetch and persist live telemetry; requires credentials and source connectivity.

Keep databases, snapshot files, backups and exports out of the image and Git. Back up the configured datastore before schema changes. See [troubleshooting](TROUBLESHOOTING.md).
