# Deployment

The supported runtime is `app.main:app`. It serves `frontend/` and the database-backed API on one listener. The former file-based HTTP daemon and its remote deployment script have been retired.

## UI revamp deployment handoff

The `feature/itom-ui-revamp` source contains the approved Vendor, Assets and
Knowledge changes. The running 8080 portal was not deployed or restarted.
Preview databases, credentials, workbooks and generated preview bundles are not
part of the source handoff.

The local `feature/itom-main-preview` integration merges main's Home, location
analytics and inventory telemetry updates while preserving the three custom
module workspaces. Its 5173 preview uses a separately migrated module backend;
it does not deploy the integration to 8080. Browser verification must set
`ITOM_BROWSER_FRONTEND_DIR` to the matching build for both telemetry and module
journeys, not test old static bundles while serving different source in Vite.

Before cutover, identify the **running service's actual database and environment**,
not merely this checkout's default `.env`. During local preflight, the running
8080 API and the shell-configured SQLite database had different telemetry counts
and schema state. Do not migrate or restart against that unverified default.
Back up the actual production database and frontend, install the updated
requirements, and apply the existing primary migration chain only against the
verified `DATABASE_URL`. Initialize the separate module database as described
below; the primary migration command does not initialize it.
For a populated database without an Alembic version table, reconcile its schema
first; do not blindly stamp head or run the full initial migration chain.

Transfer the private source workbooks separately: the approved chargeback workbook
to `data/asset_inventory/server.xlsx`, plus the existing network and telecom
workbooks. They are intentionally excluded from Git. Already-seeded categories
are not overwritten just by replacing files; any source replacement needs an
explicit backed-up migration. Preview Vendor/Knowledge records are not imported
automatically.

Build the approved frontend source in a release checkout:

```powershell
Set-Location frontend-revamp
npm ci
npm run build
```

This writes the deployable frontend and its matching asset references; do not use
the earlier preview bundles. Configure `CMDB_INVENTORY_ADMIN_TOKEN` privately in
the actual service environment, never in Git. Restart during the approved window
and verify readiness, scheduler state, existing telemetry routes and all three
module workflows. For shared access, integrate the authenticated gateway with
the local-client/Host and same-origin guards; no public-origin bypass or SSO/RBAC
implementation is included here.

### Separate module database

Keep Roshan's existing PostgreSQL `DATABASE_URL` unchanged. Configure the three
workspaces separately in the actual API service environment:

```dotenv
DATABASE_URL_2=sqlite+aiosqlite:///./data/modules.db
```

Vendor, Knowledge (including uploaded file bytes) and workbook Assets always use
this shared, server-side SQLite file. If unset, `DATABASE_URL_2` defaults to the
same new filename; an explicitly blank/invalid value is rejected. There is no
single-database fallback. Relative module paths resolve from the repository root,
independently of `SQLITE_DB_PATH`; using the primary SQLite file is rejected.

Run the independent migrations before launching the updated API:

```powershell
.venv\Scripts\python.exe -m alembic -c alembic-modules.ini upgrade head
```

This creates only the five module tables and `module_alembic_version`. It does
not connect to or migrate PostgreSQL. The separate baseline reuses the frozen
definitions from revisions 0011–0013 without changing the existing primary
migration chain. Historical module tables may remain in a previously migrated
primary database; they are not read, written or dropped by these workspaces.
Non-production primary bootstrap now creates telemetry tables only. Module
schemas must be initialized through their migration command in all environments.

Check `/ready` for primary telemetry and `/ready/modules` for module connectivity,
schema and write access. A primary-ready response alone does not establish module
readiness. Module requests return a safe 503 for an unavailable or mismatched
module schema, without switching databases. The scheduler, sync, telemetry and
location routes retain their existing primary sessions and behavior.

**Existing records are not automatically copied.** Before cutover from the old
single-database setup, back up its module data and explicitly transfer the five
tables (including attachments, reviews, audits and tombstones) into the migrated
secondary database, verifying contents and counts before switching. Do not copy
the entire telemetry database, blindly stamp its schema, or reseed over existing
edits. The running preview and production databases are not migrated by this code
change.

Every browser using this API sees the same persisted module data after refresh;
SQLite is on the server, not each user's device. Keep the database on local
persistent storage writable by the service account, not a network share. Use one
API instance for this SQLite deployment; horizontal multi-host deployment needs a
deliberately supported shared datastore rather than independent SQLite files.
Back up both datastores independently using database-aware backups (including
SQLite's committed WAL data), and preserve the module file across deployments.

## Windows local service

Create `.venv`, install `requirements.txt`, and configure `.env` from `.env.example`. Apply schema migrations:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic -c alembic-modules.ini upgrade head
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

### Local asset inventory workbooks

Place the three read-only source workbooks at `data/asset_inventory/server.xlsx`,
`data/asset_inventory/network.xlsx` and `data/asset_inventory/telecom.xlsx`, or
set `ASSET_INVENTORY_DIR` to another private directory. These files are excluded
from Git and the container build context and are never served from the frontend.
The approved server source is `CHARGEBACK_MASTER_v3.xlsx`, copied byte-for-byte
to the private `server.xlsx` deployment slot. Its `CHARGEBACK MASTER` sheet has
24 columns; use the actual workbook's non-empty records, not a hard-coded count.
Network and telecom retain their existing source workbooks.
The inventory page has no upload control. The module migration baseline adds
independent inventory records, source batches and review audits in `DATABASE_URL_2`. The first
read of each category seeds its selected workbook sheet once; subsequent reads
use the persisted local CMDB, including manual rows and reviewed edits.
The source files and live Graph/SolarWinds CMDB remain untouched. Replacing a
workbook does not overwrite an already initialized category or resurrect deleted
rows. There is deliberately no replace-import endpoint.

Back up the intended database and run migrations only in an approved deployment
window. Do not copy the reference branch's conflicting migration chain or database
bootstrap changes into this branch. CMDB writes are same-origin and loopback-only.
All environments require `CMDB_INVENTORY_ADMIN_TOKEN`, read only from the runtime
environment. No development bypass is allowed: an unset token keeps sensitive
operations locked (503); an incorrect/missing supplied key returns 401 when
configured. The same key protects Edit, Validate and Delete across Vendor,
Knowledge and all three CMDB categories (including cell review). CMDB Add data
also retains its existing administration guard.
The UI holds a supplied token only for the open
inventory dialog, never in browser storage. Configure shared operator sign-in
at the deployment boundary before exposing local administration remotely.

### Shared Knowledge Centre

The module migration baseline stores metadata and uploaded documents/media
in `knowledge_content` in the SQLite database selected by `DATABASE_URL_2`.
Back up that database and apply migrations in the approved deployment window.
The grid/list,
search, validation filters, categories (including Other), add/edit/delete,
reviewer validation, file download and media preview workflows are available.
Uploads are capped at 5 MiB (7 MiB JSON request). Reviewer names are self-reported.
Validation is available only from the library action, not the content editor.
Edit, Validate and Delete always require the same `CMDB_INVENTORY_ADMIN_TOKEN` as CMDB, including in
development. Missing configuration returns 503; an incorrect key returns 401.
The key is held only while the relevant editor/action dialog is open and is never persisted.
Edits reset validation to Pending. Revisions reject stale edits/reviews/deletions.
Files and metadata commit atomically. Deletion clears stored file bytes and keeps
a retry-protection tombstone.

New content and uploaded files save directly to the database on submission;
no browser-copy action is needed or displayed. The portal does not read, publish
or delete reference-branch localStorage/IndexedDB libraries. If older browser-only
content needs migration, arrange an explicit export/migration before clearing
that browser's storage; it is not automatically included in the shared library.
Videos use browser-native playback; unsupported codecs/Office formats need a
compatible downloaded application.

All three module datastores (Vendor, Knowledge, workbook CMDB) are now server-side.
Operators using the same deployed API/database see the same changes after refresh.
Merely assigning `itom.coforge.com` does not deploy this code or share a browser
library: deploy frontend/API, migrate and back up a persistent shared database,
configure the key, and provide an authenticated gateway and approved access policy.
Current module guards require loopback client/Host and same-origin writes;
remote gateway/origin integration must be explicitly configured and verified,
not bypassed. An isolated preview database is not the production database.

### Portal Vendor Management

Vendor Management is an in-portal workspace: submissions, the add/edit form and
the details dialog remain on the portal's current origin. It uses the SQLite
database selected by `DATABASE_URL_2`, with `vendor_submissions` initialized by
the module migration baseline. Install the updated requirements (including
Pillow), back up the intended datastore, and apply
`alembic -c alembic-modules.ini upgrade head` during
an approved deployment window before restarting the API. Do not migrate or
restart a running production portal just to preview this UI.

Vendor reads and writes are loopback-only until sign-in is implemented; writes
also require the same portal Origin. Reviewer names are explicitly self-reported,
not authenticated identities. Submissions start Pending; editing resets review.
Edit, Validate and Delete additionally require the shared CMDB admin key on the
actual API mutation, not just a UI unlock. New submissions remain available
without that key, subject to existing local/origin guards.
Deletion removes the submission from the directory and clears its attachments,
while a tombstone prevents a retry from recreating a deleted submission.
Displayed serials are consecutive active-record ranks in creation order;
database IDs remain unchanged. Search/pagination preserve the global sequence.
SOPs are optional for every method, with PDF/DOCX/TXT limited to 10 MiB.
Each step supports a validated PNG/JPEG/WebP image up to 1.5 MiB and 16 megapixels.
The complete JSON request is limited to 14 MiB.

The old loopback companion and `data/vendor_management.db` remain independent.
No old records are imported, rewritten or deleted by the new workspace.

### Future SSO / RBAC

The shared key is an interim authorization gate, not user authentication or RBAC.
When SSO is implemented, verify identity and designated-admin permissions
server-side for every sensitive endpoint across these three modules. Hiding
buttons is not sufficient. No SSO/RBAC integration is claimed by this change.
Replacing a seeded workbook inventory is an explicit, backed-up deployment
operation; it must not silently discard existing reviews or edit history.

Vendor, Knowledge and workbook inventory popups are centered in the viewport,
including nested action dialogs and file previews. Tall content scrolls inside
the popup. Vendor/Knowledge detail views show content rather than repeating the
serial, validation status, reviewer or validation date already in their libraries.

For isolated Vite verification, start `app.main:app` on another loopback port
with isolated `DATABASE_URL` and `DATABASE_URL_2`, `SCHEDULER_ENABLED=false` and no
source credentials. Migrate the preview module database before starting it.
Set `ITOM_MODULE_API_PROXY` to that backend URL when starting Vite on 5173.
Only vendor, knowledge and asset routes use this optional proxy; the existing operations
routes continue to read from 8080. Browser navigation never leaves 5173.
Build previews into a separate directory with `npm run build -- --outDir <path>`
so verification does not replace production-served frontend assets.
For the isolated browser journeys, install `requirements-browser.txt` and an
available Edge/Chromium browser, set `ITOM_BROWSER_FRONTEND_DIR` to that build,
then run:

```powershell
.venv\Scripts\python.exe -m pytest tests\browser\test_vendor_management.py tests\browser\test_knowledge_centre.py tests\browser\test_asset_reviews.py --run-browser -q
```

## Linux service

The template `systemd/itom.service` starts `.venv/bin/python -m uvicorn app.main:app` on loopback port 8080. Adapt its user, group, working directory and executable path to the installation. Create the virtual environment, install dependencies, configure `.env`, and run both `alembic upgrade head` and `alembic -c alembic-modules.ini upgrade head` before enabling the service. The template does not perform migrations.

Use a separately configured authenticated TLS reverse proxy for shared-network access. The app currently does not provide its own authentication; restrict inventory and manual sync access at the deployment boundary.

## Containers

`Dockerfile` runs FastAPI on port 8000 as a non-root user. Compose adds PostgreSQL and NGINX, bound to `127.0.0.1:8080` by default. Set `POSTGRES_PASSWORD` in the Compose environment or local `.env` before starting; there is no fallback password. If it contains URL-reserved characters, encode it for the API connection URL or configure `DATABASE_URL` separately.

```bash
docker compose build api
docker compose up -d postgres
docker compose run --rm api python -m alembic upgrade head
docker compose run --rm api python -m alembic -c alembic-modules.ini upgrade head
docker compose up --build -d
docker compose ps
docker compose logs api
```

Compose forwards database configuration, the read-only asset workbook mount and `PORT` to the API. Configure explicit runtime environment/secrets for source credentials, proxy settings, `ENVIRONMENT=production` and a strong `SECRET_KEY`; `.env` is excluded from the image. Raw `data/` files are not mounted into the web root, and NGINX rejects `/data` requests.
Compose fixes `DATABASE_URL_2` to `/app/data/modules/modules.db` inside the
`modules_data` persistent volume, writable by the API's non-root user. Do not
delete that volume during upgrades. Back it up independently of `postgres_data`.
The existing Compose health check remains primary liveness; also verify
`/ready/modules` before routing users to the module UI.

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
