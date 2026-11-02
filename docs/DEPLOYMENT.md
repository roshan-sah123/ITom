# Deployment

The supported runtime is `app.main:app`. It serves `frontend/` and the database-backed API on one listener. The former file-based HTTP daemon and its remote deployment script have been retired.

## UI revamp deployment handoff

### Vendor SOP attachment compatibility update

The approved relaxation is deployed on 8080 and the HTTPS portal: PDF, DOCX and
TXT SOPs are accepted as opaque download-only attachments up to 10 MiB. Internal
content checks do not reject links, PDF object streams, encryption or text
encodings; the portal does not scan or preview them. Downloads must be treated
as untrusted and checked with approved endpoint protection before opening.
Filename/extension, base64, file/request-size limits, screenshot checks and
admin-key guards remain enforced. Knowledge and Assets validation is unchanged.

The matching UI and Vendor backend were deployed using the existing startup
task, with a private previous-source/static-entry backup and verified module
snapshot. No runtime configuration or database migration changed. Live HTTPS
nonexistent-record edit probes passed PDF/DOCX/TXT attachment validation and
returned 404 without saving records; readiness and both source summaries
returned 200 and telemetry remained FRESH. Isolated browser journeys cover
upload/save/download for each type, screenshots and existing asset dialogs.

### Asset dialog UI deployment (8080 and 5173)

The current React preview places Vendor Management before Automations.
Server, Network and Telecom inventory dialogs have top-right fullscreen/restore
and close controls; fullscreen expands within the browser viewport and preserves
search, pagination and loaded records. Escape still closes the inventory.
The explanatory workbook/reviewer paragraph is removed from the dialog header;
source provenance and admin/reviewer requirements are unchanged.

After preview approval, only the matching CSS/JS and HTML entry point were
deployed to 8080. Existing assets and a private copy of the previous entry point
were retained for rollback. The API process was not restarted; backend source,
runtime configuration, database schemas and ingestion settings were unchanged.
The new assets are `index-zCH6sAQl.js` and `index-C77Zs5vD.css`.

The TypeScript/build check and three isolated asset browser journeys passed,
including desktop/mobile sizing, nested admin dialogs and Escape closing.
Live Edge checks passed on both localhost:8080 and the HTTPS portal for navigation
order, all three persisted inventories, top-right close, fullscreen/restore and
paragraph removal without changing records. Both readiness endpoints, source
summaries and module read smoke checks returned 200.

For future previews, build into an isolated output and run
`tests/browser/test_asset_reviews.py --run-browser`; do not write into the live
`frontend/` directory merely to test changes.

### Deploying this branch on another server

Use `feature/itom-main-preview`, which contains the latest-main integration,
separate module storage, current access policy and matching built `frontend/`.
Keep the server's existing PostgreSQL `DATABASE_URL`, source credentials,
proxy/TLS settings, scheduler configuration and `CMDB_INVENTORY_ADMIN_TOKEN`.
Configure these additional values privately:

```dotenv
DATABASE_URL_2=sqlite+aiosqlite:///./data/modules.db
MODULE_SHARED_ORIGIN=https://itom.coforge.com
MODULE_NETWORK_ACCESS=true
```

Network mode needs no `MODULE_SHARED_ACCESS_KEY`. It allows reads, downloads and
additions without login only on the configured portal origin; Edit, Delete and
Validate still require the existing admin key. The corporate gateway/firewall
must restrict portal reachability. Do not expose this mode to the public internet.

In an approved deployment window, back up both databases and the running
environment/frontend. Install `requirements.txt` in the server's own virtual
environment, then run both migration commands from the checkout:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic -c alembic-modules.ini upgrade head
```

The first uses the existing primary migration chain; the second initializes only
the separate module database. Already-current schemas need no additional upgrade.
Privately transfer a database-aware snapshot of `data/modules.db` to retain
existing module content and attachments; a fresh database starts without these
submissions. Workbooks must be supplied separately to `ASSET_INVENTORY_DIR`
for any categories not yet initialized. Neither databases nor workbooks are in Git.
Do not overwrite a live database or copy only a SQLite file while its WAL is active.

The checked-in frontend is ready to serve; no Node build is needed unless React
source is changed. Preserve the public Host through the HTTPS reverse proxy
(IIS ARR: `preserveHostHeader=true`, server-level on this installation), then
restart the API using the existing supported launcher/service. Do not run two
schedulers against the same production database. Verify `/ready`,
`/ready/modules`, both source summaries, module reads without a cookie and
admin-key rejection/acceptance before completing cutover.

### Local production cutover completed

The integrated release is now served on loopback port 8080 from this isolated
checkout using its dedicated `.venv`, production `.env` and `data/modules.db`.
The former runtime was Roshan's separate desktop checkout, whose files and
environment were left intact. Its actual production secret, PostgreSQL URL,
source credentials, TLS/proxy policy and scheduler settings were preserved.

Before applying primary revisions 0011-0013, the previous supervisor/backend
were stopped by their verified process IDs. A fresh custom-format PostgreSQL
archive was created and checked. Every one of the 15 pre-existing PostgreSQL
tables had identical row counts and content fingerprints after migration.
Only the five new historical module tables were added.

Both `/ready` and `/ready/modules` and the live telemetry/module API smoke checks
returned 200. The scheduler reports enabled/running with a 600-second interval.
The matching built UI and centered desktop asset dialog were checked on 8080.
Subsequent telemetry changes are expected from the normal live scheduler.

The `ITOM Integrated Portal and Sync` Windows task starts this release at the
current deployment user's login. The former `ITOM Local Portal and Sync` task
is retained disabled, with its XML backed up. Do not enable both. This is an
interactive-login task, not an unattended Windows service or cross-user login
guarantee; preserve this release path and its private runtime files.

Rollback materials are in the private session directory
`production-backup-20261101-223122`: `postgresql-cutover.dump`, original task XML,
actual production environment/frontend and database-aware module snapshots.
For application rollback, stop the integrated supervisor, disable its task and
restore/start the original checkout/task. Do not blindly restore PostgreSQL
over newer live ingestion. The original code expects revision 0010; reconcile
its readiness/schema through an approved rollback plan, rather than stamping
or erasing newly collected telemetry.

The 5173 preview remains separate from production SQLite. Once live, submit
shared production content through 8080; later preview edits do not automatically
replicate into production.

### Earlier preview preparation (historical)

The `feature/itom-ui-revamp` source contains the approved Vendor, Assets and
Knowledge changes. At that earlier preview stage, the running 8080 portal had
not been deployed or restarted; the completed cutover above supersedes that state.
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
module workflows. Configure the HTTPS origin and approved access mode described
above. SSO/RBAC is not implemented; operator names remain self-reported.

### Separate module database

Keep Roshan's existing PostgreSQL `DATABASE_URL` unchanged. Configure the three
workspaces separately in the actual API service environment:

```dotenv
DATABASE_URL_2=sqlite+aiosqlite:///./data/modules.db
```

#### Earlier prepared local release (historical)

The isolated integration checkout has a dedicated, ignored `.venv` with the
pinned runtime requirements and an ignored `.env` prepared from the original
checkout. Production mode, loopback host, a generated runtime secret and the
separate `data/modules.db` are configured. The primary database URL, source
credentials, existing TLS/proxy settings, shared module key and 600-second
scheduler settings were preserved; the original checkout's `.env` was not edited.
The release's workbook directory points to the original private workbook folder.
None of these runtime files are part of the Git handoff.

The prepared module database is a verified database-aware copy of the integrated
preview, including uploaded bytes, reviews, audits and deleted-record tombstones.
It is a point-in-time copy, not ongoing replication. Before actual cutover,
reconcile any submissions or edits made subsequently on 5173; do not overwrite
either database without a backup and an explicit transfer.

The Windows launcher was verified using `start_itom_service.bat --help`; its
existing `.venv` preference now selects the provisioned release interpreter.
No launcher or Roshan telemetry business logic changes were needed.
For another checkout or server, create its own `.venv`, restore `requirements.txt`
and securely provision that machine's runtime configuration rather than relying
on global Python or copying executable virtual environments.

Production-configured release verification on a temporary port used PostgreSQL
connections with `default_transaction_read_only=on` and disabled synchronization.
Intune, SolarWinds, CMDB, locations, module routes and the matching static shell
responded successfully. The temporary verifier was stopped afterward.
At this preparation stage, the original 8080 service and PostgreSQL migration
state had not yet been changed.

**Earlier preflight blocker, now resolved by the completed cutover:** the checked
PostgreSQL database was at `0010_geographic_reporting`; this release expects
`0013_knowledge_content`. Its `/ready` correctly returned 503 until the approved,
backed-up primary upgrade was applied. Revisions 0011-0013 only add historical module tables; module runtime
data still uses the separate SQLite database. Do not stamp head or weaken
readiness to hide this mismatch. During an approved deployment window, confirm
the runtime identity/configuration, back up PostgreSQL and both module snapshots,
apply the primary migrations with the release interpreter, and perform the
controlled 8080 cutover. Verify both readiness endpoints and the original
source scheduler afterward. Preparation is not a deployment or authorization
to run the release alongside production with synchronization enabled.

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
bootstrap changes into this branch. CMDB writes require the same portal Origin
and local access or a configured shared module session.
All environments require `CMDB_INVENTORY_ADMIN_TOKEN`, read only from the runtime
environment. No development bypass is allowed: an unset token keeps sensitive
operations locked (503); an incorrect/missing supplied key returns 401 when
configured. The same key protects Edit, Validate and Delete across Vendor,
Knowledge and all three CMDB categories (including cell review). CMDB Add data
requires local access or a shared session, but not the administration key.
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
Without shared access configuration, module guards remain local-only.
An isolated preview database is not the production database.

### Interim shared-domain module access (without SSO)

**Current Coforge-network policy:** `MODULE_NETWORK_ACCESS=true` is explicitly
enabled with `MODULE_SHARED_ORIGIN=https://itom.coforge.com`. Anyone who can
reach this configured portal can read, download and add Vendor, Knowledge and
workbook Asset content without entering a shared key. Edit, Delete and Validate
still require the unchanged `CMDB_INVENTORY_ADMIN_TOKEN` on every API mutation.
No access-key dialog or session-lock toolbar is displayed in network mode.
Host and same-origin write guards remain enforced. This flag does not verify
network membership: the IIS gateway/firewall must restrict reachability to the
approved corporate network. Do not enable it on an externally reachable portal.
The API remains loopback-bound; primary telemetry routes/settings are unchanged.
Set `MODULE_NETWORK_ACCESS=false` and restart to restore the shared-session
policy below. The default is false; enabling it requires an explicit HTTPS origin.

Verified the current mode on the actual HTTPS domain without cookies: all three
module reads return 200, Add controls are available, and the existing admin key
is requested by Vendor, Knowledge and Assets edit dialogs in Microsoft Edge.
Unkeyed Vendor/Knowledge Edit, Delete and Validate requests return 401; the
unchanged key passes authorization on nonexistent-record probes (404), without
modifying content. Assets admin checking rejects no key (401) and accepts the
existing key (200). Network-mode isolated tests also prove additions and files
are shared across browsers without login. Validation passed 145 backend/API
tests, 25 frontend tests, nine module browser journeys and the React build.
Primary/module readiness and both source summaries remain available.

Set `MODULE_SHARED_ORIGIN=https://itom.coforge.com` and a high-entropy
`MODULE_SHARED_ACCESS_KEY` in the deployed, ignored runtime environment. Keep
the existing `CMDB_INVENTORY_ADMIN_TOKEN` unchanged and distinct. Build the
current React frontend and restart only the deployed API; no additional database
migration is needed for access sessions.

Each remote browser enters the shared access key once to read, download and add
content in the three modules. The server sets a Secure, HttpOnly, SameSite=Strict
cookie that expires after eight hours. Use **Lock shared modules** to clear this
browser's access, or **Recheck module access** after expiry. Rotate the shared
access key and restart the API to invalidate all sessions. Edit, Delete and
Validate still require the separate existing admin key on each mutation.

The approved HTTPS gateway must preserve the public Host, Origin and cookies,
forward `/api/v1/modules/access` and all module routes to this deployed API, and
restrict unprotected telemetry/manual-sync routes using its existing access
policy. Do not rewrite Host to localhost or trust arbitrary forwarded headers.
Verify both remote session creation and subsequent cookie-bearing requests on
the actual domain. Localhost checks alone do not prove domain deployment.
This interim shared credential is not per-user identity, SSO or RBAC;
operator/reviewer names remain self-reported. Neither key belongs in Git or chat.
Roshan's `DATABASE_URL`, ingestion settings and source API authorization are
unchanged; module records remain in `DATABASE_URL_2`.

The deployed Windows IIS ARR reverse proxy rewrites requests to
`http://127.0.0.1:8080`. ARR Host preservation is server-level on this installation;
the site-only setting was rejected without committing changes. With operator
approval, `system.webServer/proxy` now has `preserveHostHeader=true`. This setting
also applies to future IIS proxy sites. The other current site is stopped.
The previous proxy configuration and release environment/static assets are
backed up privately alongside the release. For gateway rollback, restore the
prior `preserveHostHeader=false` value with IIS configuration tools; this will
again block shared module requests until the public Host is preserved.

Verified on the actual HTTPS domain: session login and logout, Secure/HttpOnly
cookie, Vendor/Knowledge/workbook reads, both readiness endpoints, Intune and
SolarWinds summaries, rejection of the shared access key for administration,
and acceptance of the unchanged administration key. Verification created no
production module records and required no database migration.
Live Microsoft Edge also passed the public key dialog, login, all three module
views, the three Assets tiles, and session locking with TLS verification enabled.
Regression checks passed 145 backend/API tests, 25 frontend data tests and the
React TypeScript/build check. Isolated browser checks passed 28 journeys; one
existing telemetry refresh assertion expects 14 fixture records but receives
15. The same assertion fails against the unchanged pre-update static build;
no Roshan telemetry logic was changed to accommodate it.

### Portal Vendor Management

Vendor Management is an in-portal workspace: submissions, the add/edit form and
the details dialog remain on the portal's current origin. It uses the SQLite
database selected by `DATABASE_URL_2`, with `vendor_submissions` initialized by
the module migration baseline. Install the updated requirements (including
Pillow), back up the intended datastore, and apply
`alembic -c alembic-modules.ini upgrade head` during
an approved deployment window before restarting the API. Do not migrate or
restart a running production portal just to preview this UI.

Vendor reads and writes require local access or the shared module session; writes
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
Vendor SOP content restrictions are relaxed by explicit request: these files
are stored as opaque bytes, not parsed, extracted or scanned. Filenames,
extensions, strict base64, the 10 MiB file limit and 14 MiB request cap remain
enforced. Compressed/encrypted PDFs, linked DOCX documents and non-UTF-8 TXT
attachments are accepted. This does not certify their safety or readability.
SOP downloads use `application/octet-stream`, attachment disposition, `nosniff`,
no-store and sandbox CSP; the portal no longer offers SOP previews. Screenshot
previews and Knowledge Centre validation are unchanged. Scan downloaded files
with approved endpoint protection and open only trusted documents.
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
