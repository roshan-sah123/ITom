# Project reference

The current ITOM Portal combines Microsoft Intune and SolarWinds telemetry in a relational CMDB and presents it through FastAPI and the React frontend in `frontend-revamp/`. Built assets are served from `frontend/`. The retired UI is preserved locally in the ignored `not-in-use/legacy-frontend/` directory and must not be used for current work.

Use these maintained references:

- [README](README.md): setup and repository map.
- [Architecture](docs/ARCHITECTURE.md) and [data flow](docs/DATA_FLOW.md): current implementation.
- [API contracts](docs/API_CONTRACTS.md): endpoints and response behavior.
- [Deployment](docs/DEPLOYMENT.md) and [onboarding](docs/ONBOARDING.md): supported entry points.
- [Project context](docs/PROJECT_CONTEXT.md): product and operating context.
- [Codebase audit](docs/CODEBASE_AUDIT_2026-10-08.md): evidence and unresolved issues as of the audit date.

Historical specifications and implementation reports are in `docs/archive/legacy-2026-09/`. Historical fleet sizes and pass-rate claims do not describe the current system.
