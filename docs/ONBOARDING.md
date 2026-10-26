# Developer onboarding

The application is FastAPI with async SQLAlchemy persistence and a zero-build frontend. Start with [README](../README.md), [architecture](ARCHITECTURE.md), [data flow](DATA_FLOW.md) and [API contracts](API_CONTRACTS.md).

## Set up a local checkout

Use Python 3.11 or later; CI currently runs Python 3.12.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

For API development, set `SCHEDULER_ENABLED=false` in `.env`. Configure `DATABASE_URL` and apply migrations before checking readiness:

```powershell
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Open `http://localhost:8080/`. The same listener serves `frontend/` and `/api/v1`. No Node build is required. The Windows supervisor is described in [deployment](DEPLOYMENT.md).

## Where to work

- `frontend-revamp/src/`: the only editable current UI; run `npm run build` in `frontend-revamp/` to update served files in `frontend/`.
- `frontend-revamp/src/api.ts`: same-origin API client; `window.ITOM_API_BASE` overrides the base.
- `not-in-use/legacy-frontend/`: local, ignored archive of the retired UI; not served or used by active tests.
- `app/api/v1/endpoints/`, `app/services/`, `app/repositories/`: routes, orchestration and database queries.
- `src/sync/graph_client.py`, `src/sync/solarwinds_client.py`, `app/services/telemetry_sources.py`: live extraction and normalization.
- `app/models/`, `alembic/`: schema and migrations.

Keep metrics source-backed, escape untrusted values in HTML, and preserve the distinction between unavailable telemetry and zero results. Do not hardcode fleet sizes.

## Verification

Install `requirements-test.txt` and run `python -m pytest tests/ -q -ra`. The complete offline suite uses isolated fixtures and does not require live credentials, snapshot files or a running portal. CI runs this suite.

Optional browser journeys use `requirements-browser.txt` and `--run-browser`; they start a temporary seeded portal on an ephemeral port. See [the testing guide](../tests/README.md) for commands, requirement coverage and documented expected failures.
