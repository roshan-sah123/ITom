# API contracts

The current service is `app.main:app`. Its OpenAPI document at `/openapi.json` and interactive documentation at `/docs` describe the exact parameters and schemas from the running checkout. Versioned routes use `/api/v1`; the former `/api/cmdb/*` file-server routes have been retired.

## Route map

| Route | Purpose |
|---|---|
| `GET /healthz` or `/health` | Process liveness |
| `GET /ready` | Primary database connectivity and migration readiness; 503 when unavailable or mismatched |
| `GET /ready/modules` | Independent module SQLite schema/write readiness; 503 when unavailable or mismatched |
| `GET /api/v1/system/freshness` | Successful-sync freshness by source |
| `GET /api/v1/cmdb/summary` | Database-backed inventory aggregates |
| `GET /api/v1/cmdb/cis` | Filtered, paginated active inventory |
| `GET /api/v1/cmdb/cis/{ci_id}` | Configuration item detail |
| `GET /api/v1/cmdb/cis/{ci_id}/history` | Recorded status/health changes |
| `GET /api/v1/cmdb/cis/{ci_id}/relationships` | Inventory relationships |
| `GET /api/v1/assets/summary` | Availability and current record/review counts for workbook-backed local CMDB inventory |
| `GET /api/v1/assets/inventory/{category}` | Paginated current inventory values (`server`, `network` or `telecom`) |
| `GET /api/v1/assets/records/{category}` | Local inventory rows including column order, provenance, revisions and cell review metadata |
| `GET /api/v1/assets/admin/check` | Check local/production inventory editing access |
| `POST /api/v1/assets/records/{category}` | Add a manual inventory row using the source column schema |
| `PUT /api/v1/assets/records/{category}/{id}` | Edit a row, preserving workbook columns and unchanged cell reviews |
| `POST /api/v1/assets/records/{category}/{id}/validate` | Review every cell in a row |
| `POST /api/v1/assets/records/{category}/{id}/fields/{index}/validate` | Review one zero-based workbook column |
| `DELETE /api/v1/assets/records/{category}/{id}` | Hide a local inventory row without modifying its workbook |
| `GET /api/v1/intune/summary` | Managed-device compliance, OS and storage summaries |
| `GET /api/v1/intune/forecast` | Projection from successful daily observations |
| `GET /api/v1/intune/devices` | Filtered managed-device inventory |
| `GET /api/v1/solarwinds/summary` | Infrastructure operational summary |
| `GET /api/v1/solarwinds/nodes` | Filtered infrastructure inventory |
| `GET /api/v1/solarwinds/network-devices` | Network-only inventory |
| `GET /api/v1/solarwinds/groups` | Top-level regular source groups, including empty groups |
| `GET /api/v1/solarwinds/groups/{group_id}/members` | Direct child groups and device members |
| `GET /api/v1/solarwinds/groups/{group_id}/devices` | Unique devices across the group and all descendants |
| `GET /api/v1/solarwinds/sites` | Site/location aggregates |
| `GET /api/v1/solarwinds/sites/{site_id}/trend` | Recorded trend, with `hours` between 1 and 168 |
| `GET /api/v1/analytics/locations` | Location analytics |
| `GET /api/v1/analytics/stale-assets` | Stale inventory analytics |
| `GET /api/v1/sync/scheduler` | Scheduler state and cadence |
| `GET /api/v1/sync/status` | Latest source attempts and overall sync state |
| `GET /api/v1/sync/runs` | Sync run list |
| `GET /api/v1/sync/runs/latest` | Latest run; optional source filter |
| `GET /api/v1/sync/runs/{run_id}` | Run detail |
| `POST /api/v1/sync/trigger` | Queue ingestion; accepts `source_system=ALL`, `INTUNE` or `SOLARWINDS` |

## Inventory lists

SolarWinds group routes use `{status: "success", data: ...}`. Groups use numeric
SolarWinds `group_id` values, not canonical location IDs. Group names and native
status descriptions are preserved verbatim. Only non-deleted `Owner = Core`
groups are included; map containers are excluded. Groups can have multiple parents.
The devices route accepts `page`, `page_size` in `{10,25,50,100}`, literal name/IP
`search`, and exact case-insensitive `status`. Filtering and unique-node selection
happen before pagination. Unknown group IDs return 404; invalid parameters return
422; database failures return a safe 503.

Each group response carries `data_available`, `snapshot_id`, `as_of`, `freshness`,
and `last_attempt_status`. An empty catalogue before the first successful group
sync has `data_available=false`; a validated empty source snapshot has
`data_available=true`. Sync runs include nullable `groups_extracted` and
`memberships_extracted`: cleaned regular-group/edge counts. Legacy, fixture-only,
and failed runs leave these null. Nodes, hierarchy, retirement, and the success
audit commit together. Existing canonical location and `/solarwinds/sites`
contracts are preserved.

Inventory pages accept `page >= 1` and `page_size` in `{10, 25, 50, 100}`. Responses include `items`, `total`, `page`, `page_size` and `total_pages`. Filter availability depends on the route; consult OpenAPI instead of assuming a uniform set of parameters. Retired items are excluded from ordinary inventory reads.

CMDB, Intune, SolarWinds node and network-device lists return HTTP 503 with
`{"error": "Inventory datastore unavailable", "data_available": false}` when a
database query fails. A datastore outage must not be displayed as an empty fleet.
Search terms containing a NUL character return zero matches to prevent SQLite
from truncating the search pattern and matching unrelated assets.

Dashboard drill-downs use the same inventory endpoints and pagination. Intune
`/devices?ci_type=...` matches an exact source OS family from `os_distribution`.
SolarWinds `/nodes?resource_pressure=true` selects active nodes with validated
CPU >= 75% or memory >= 80%, using the summary's reading validation and legacy
attribute aliases. Filtering happens before totals and pagination. The CMDB
summary includes `source_breakdown`, an active-record count by source system;
the UI derives source totals, options and distributions from this map.

## Data and error states

Summaries are computed from persisted telemetry. A domain with no ingested data may return 503. Freshness reports use `FRESH`, `STALE` and `UNKNOWN`; a successful HTTP response does not establish that upstream ingestion is current. Optional freshness timestamps are absent when there is no known successful refresh.

The inventory source routes reject mutating methods. The separate sync trigger returns 202 before ingestion finishes; inspect status and run history for its outcome. Shared-network deployments must supply access controls, because authentication is not currently implemented by the application. Known error-handling and deployment limitations are documented in the [audit](CODEBASE_AUDIT_2026-10-08.md).

## Local asset workbooks

Vendor, Knowledge and all workbook asset routes always use `DATABASE_URL_2`
(default `sqlite+aiosqlite:///./data/modules.db`), not the telemetry `DATABASE_URL`.
Initialize it with `alembic -c alembic-modules.ini upgrade head`. Connectivity,
missing tables and migration mismatches produce a logged safe module 503; there
is no fallback to telemetry storage. Existing API payloads, review/revision rules,
file downloads and shared-key guards are unchanged. `/ready` still checks only
the primary database; `/ready/modules` checks the separate module schema.
New module data and uploaded bytes are shared across browsers through this one
server-side database, with changes visible after refresh.

The asset inventory routes read `server.xlsx`, `network.xlsx` and `telecom.xlsx`
from `ASSET_INVENTORY_DIR` (default `./data/asset_inventory`). Workbooks stay
outside the public frontend, Git and the container build context. On the first
read of each category, the selected workbook sheet seeds independent
`asset_inventory_batches` and `asset_inventory_records` tables. Subsequent reads
use that local CMDB inventory, including manual additions, edits and deletions;
the source workbooks and Graph/SolarWinds telemetry are never written.
An uninitialized category with a missing/unreadable workbook is unavailable,
not an empty inventory. A seeded category remains available independently of
the source file, and deleting its last row does not reseed it.
The inventory view and API do not accept workbook uploads or replace-imports.
Server, Network and Telecom row-count selectors offer 10, 25, 50, 100, 150
and 200 rows per page. Asset record pagination is capped at 200; the inventory
compatibility route accepts those six sizes. Defaults, search, export and
revision behaviour are unchanged. This pagination change requires no schema
migration or stored-data transformation.

All asset reads, exports and writes require local access or the shared module session below.
Writes require same-origin requests; in every environment, administration
also requires `Authorization: Bearer <CMDB_INVENTORY_ADMIN_TOKEN>`. An unset token
keeps editing locked in every environment (503); an invalid/missing supplied key
returns 401 when configured. There is no development bypass.
Actor/reviewer names are self-reported, not authenticated identities.
Every write sends `actor`; edit/validate/delete also send `expected_revision`.
Create sends `name`, `source_sheet`, and ordered `data: [{index, header, value}]`;
edit sends `name` and `data`. Values are plain finite numbers, strings, booleans
or null. Column labels/order cannot change. JSON bodies are capped at 256 KiB.
Stale revisions return 409, missing records 404, invalid data 422, and database
failures a logged safe 503. Changes and their restricted audit records commit
atomically. Row validation reviews every field; an edit invalidates only changed
cells, preserving unchanged review evidence.

## Shared Knowledge Centre

`/api/v1/knowledge/content` uses the configured server database, independent of
source telemetry. Reads require local access or the shared module session; writes require the same
portal Origin. `GET` accepts `page >= 1` and `page_size` from 1 to 100 and returns
`items`, `total`, `page`, `page_size`, `total_pages`. Items include permanent `id`,
consecutive display `serial`, `revision`, `name`, `description`, `category`,
`file: {name,type,size,url}`, `validatedOn` and `validatedBy`.

`POST` sends a unique 32-lowercase-hex `request_id`, metadata and
`file: {name,type,data}` (strict base64). Replaying unchanged creation requests is
idempotent; changed or deleted replays return 409.
`PUT /{id}` sends metadata, `expected_revision` and optionally a replacement file;
`file: null` preserves bytes. Validation fields are forbidden in create/edit
bodies, and editing resets validation to Pending.
Both editing and deletion require the same CMDB Bearer key as validation.
`POST /{id}/validate` sends `reviewer`, `expected_revision` and a Bearer key matching
`CMDB_INVENTORY_ADMIN_TOKEN`. The same CMDB key is enforced on actual validation
in every environment (unset 503, incorrect 401). Reviewer names are self-reported.
`DELETE /{id}?expected_revision=...` clears bytes and keeps a retry tombstone.
Stale mutations return 409; missing rows 404; invalid files/fields 422; oversized
JSON 413; database failures a logged safe 503. `GET /{id}/file` returns bytes with
attachment disposition, no-store, nosniff and sandbox CSP. Add `?preview=true`
for a supported native preview or local Office-to-PDF conversion, as described
under Attachment previews below. Unsupported formats return an explicit error,
not the original attachment as a download fallback.
Metadata/file writes commit atomically.

Content submissions save metadata and file bytes directly to the database.
There is no browser-copy button or active browser persistence. Legacy browser
libraries are neither read, published nor deleted. Operators sharing the API/database see changes after
refresh, subject to approved gateway authentication and existing module guards.
New uploads and replacement files accept only DOCX, PDF, PPTX, TXT and
MP4/WebM/MOV videos, up to 5 MiB. Excel (including XLS/XLSX/CSV), images,
extensionless files and other formats are rejected by both the React form and
API. Extension checks are case-insensitive; a declared MIME type does not bypass
them. Existing stored files are preserved, and metadata-only edits do not
revalidate or remove their bytes.
File bytes are stored opaquely; internal contents and declared MIME are not
inspected or malware-scanned on upload. Original-byte APIs use `application/octet-stream` and
attachment disposition. The View action opens a dedicated
same-origin viewer tab; its preview responses keep no-store, nosniff and sandbox
CSP headers. There is no attachment Download action in this UI.
The existing filename/path-character, strict base64, 5 MiB file and 7 MiB request
limits, and admin-key guards remain enforced. Treat every download as untrusted
and scan it with approved endpoint protection before opening. Validation
timestamps come from the server, never an editable form field.
No Figma sample records or figures are shipped.

## Vendor submissions

`/api/v1/vendors/submissions` is separate from source telemetry.
All routes require local access or the shared module session; writes require the same
portal Origin. No frontend navigation redirects to the old companion port.
Edit, Validate and Delete require the same runtime CMDB administration key on
each API request in every environment (unconfigured 503, incorrect/missing 401).
Creating submissions and ordinary reads require local access or a valid shared session.
The interim shared key is not SSO/RBAC; designated-admin role enforcement must
be implemented server-side when authenticated identities become available.

### Interim shared module access

An explicit `MODULE_NETWORK_ACCESS=true` changes only ordinary module access
on `MODULE_SHARED_ORIGIN`: reads, downloads and additions no longer require a
session cookie or shared key. `GET /api/v1/modules/access` then returns
`{authorized: true, local: false, network: true}` for the approved remote host.
Edit, Delete and Validate still require `CMDB_INVENTORY_ADMIN_TOKEN`; all host
and same-origin guards remain. Network membership must be restricted at the
gateway/firewall, not inferred from a Host header. This mode defaults to false.

Configure `MODULE_SHARED_ORIGIN` as the exact HTTPS portal origin and set a
separate runtime `MODULE_SHARED_ACCESS_KEY`, distinct from
`CMDB_INVENTORY_ADMIN_TOKEN`. Without this configuration the existing local-only
policy remains. These routes and sessions cover only Vendor, Knowledge and
workbook Assets; telemetry authentication and API contracts are unchanged.

- `GET /api/v1/modules/access`: `{authorized, local}`. A loopback client/Host
  returns authorized local access; the configured remote host reports its session.
- `POST /api/v1/modules/access`: `{key}` authenticates remote module access;
  incorrect keys return 401. Success sets an eight-hour, Secure, HttpOnly,
  SameSite=Strict signed cookie scoped to `/api/v1`.
- `DELETE /api/v1/modules/access`: clears this browser's cookie (204).

Unopened or expired remote module sessions return 401. Other hosts and
cross-origin requests return 403; writes must send the configured Origin.
The TLS proxy must preserve the public Host and forward cookies and Origin.
Arbitrary forwarded-host headers do not confer access. Rotating the access key
invalidates all existing sessions. Keys are never persisted by the frontend.
Reads, downloads and additions share the same module database; Edit, Delete and
Validate still additionally require the existing administration Bearer key.

- `GET /`: searchable vendor list with `items`, `total`, `page`, `page_size`
  and tentative `next_serial` (active count + 1). `serial` is the consecutive
  active-record rank in creation order, independent of permanent database `id`.
  Search/pagination preserve this global sequence; deletion closes display gaps
  without rewriting or reusing IDs.
- `POST /`: create with `request_id` (32 lowercase hexadecimal characters),
  `vendor`, free-text `method`, 1-30 `steps`, and nullable `sop`.
  Each step has `what_to_do`, `how_to_do` and nullable `image`.
  Attachments are `{name, data}` with base64 content.
- `GET /{id}`: details, review metadata and same-origin attachment URLs.
  `include_files=true` additionally supplies `draft` and `sop_file` for editing.
- `PUT /{id}`: edit using the creation shape plus `expected_revision`.
  Edits reset validation to Pending. The form preserves existing files unless
  the user removes or replaces them.
- `POST /{id}/validate`: `{reviewer, expected_revision}`; records server UTC
  time and a self-reported reviewer name, not an authenticated identity.
- `DELETE /{id}?expected_revision=...`: removes a submission and its files.
- `GET /{id}/sop` and `GET /{id}/images/{zero_based_step_index}`:
  attachment bytes; screenshots remain content-validated. SOP downloads use
  `application/octet-stream` and attachment disposition. Add `?preview=true`
  on the SOP route for the dedicated viewer. `nosniff`, no-store
  and sandbox CSP remain set; unsupported previews return an explicit error.

Create retries reuse `request_id`; conflicting payloads, deleted-request replays
and stale edit/review/delete revisions return 409. Invalid inputs return 422,
oversized JSON returns 413, unsupported request types return 415, unknown records
return 404, and datastore failures return a safe 503. Portal SOPs are optional,
unlike the legacy companion contract. New data never modifies the legacy
`data/vendor_management.db`.

Vendor SOPs accept `.pdf`, `.docx` and `.txt` files from 1 byte through 10 MiB,
with filename, extension, strict base64 and overall request-size validation.
Their internal content is not inspected, parsed, extracted or malware-scanned:
hyperlinks, PDF object streams, encryption and alternative text encodings do
not cause rejection. Acceptance does not establish a safe or readable document.
Users must scan downloads and open only trusted files in an appropriate local
application. Knowledge Centre uses opaque storage with its own extension
allowlist and existing 5 MiB limit; other media validation and screenshot checks
are unchanged. The stricter shared helper remains the default for other callers.

## Attachment previews

The React viewer at `/?attachment=<encoded attachment API path>&name=<filename>`
accepts only local Knowledge file and Vendor SOP endpoint paths. It fetches
`?preview=true`; it does not navigate the browser directly to uploaded bytes.
PDFs render through bundled PDF.js and a local worker without a download/print
toolbar. Text (TXT/CSV/LOG/JSON/XML), PNG/JPEG/WebP/GIF and browser-supported
MP4/WebM/MOV render without external viewer services. UTF-16 BOMs are respected.
The same preview path works for existing stored files; no re-upload is required.

Office formats DOC/DOCX/ODT/RTF, XLS/XLSX/ODS and PPT/PPTX/ODP require
`DOCUMENT_PREVIEW_CONVERTER` pointing to an installed local LibreOffice
console executable (`soffice.com` on Windows). Each conversion uses a temporary
copy and unique profile with macros disabled. The original stored bytes and
revision are unchanged. Only one conversion per process runs at a time (429
when busy), with a 45-second timeout and 30 MiB output cap.

Missing converter returns 503; unsupported formats 415; unreadable/encrypted
conversion output 422; timeout 504. The viewer reports errors and offers retry,
never a download fallback. A PDF preview is limited to 150 pages and a maximum
6 million pixels per page. Damaged native files or unsupported video codecs
also show an explicit unavailable state.

These are viewing controls, not DRM: original download API routes remain
compatible and browser users can still save or capture displayed data. Upload
acceptance, storage limits and admin controls have not changed. Temporary
profiles are not an OS sandbox; isolate the converter and block its outbound
network access before enabling it for untrusted documents.

## Source integrations

Intune and SolarWinds summaries include additive `decision_metrics`. Percentage
metrics expose `numerator`, `denominator`, nullable `value`, `known_count`,
`unknown_count`, nullable `coverage_pct`, `definition`, `population`, `exclusions`,
`observed_at`, `calculated_at` and `measurement_window`. `observed_at` is the latest
mirrored record sync timestamp, not a guarantee that every device was measured at
that instant. Legacy summary keys remain available.

Intune provides `confirmed_compliance`, `recent_checkins`, `compliance_state_counts`
and `checkin_age_buckets`. SolarWinds provides `current_node_status`, `all_fleet_up`,
`status_evidence`, `cpu_coverage`, `memory_coverage`, `resource_pressure` and
`resource_health_counts`. No eligible population has a null percentage; resource
pressure is also null when there are no usable CPU or memory readings. Resource
pressure can be observed with one reading while complete-pair coverage remains
incomplete. See [decision metric policy](DECISION_METRICS.md) for interpretation.

Graph uses OAuth client credentials and read-only managed-device extraction, including pagination. SolarWinds uses GET requests with validated SELECT-only SWQL. Implementations live in `src/sync/graph_client.py`, `src/sync/solarwinds_client.py` and `app/services/telemetry_sources.py`. Source credentials and transport policy are configured through `app/core/config.py`; source API access is separate from the portal inventory contract.
# Group overview and Site Score additions

See [dashboard Site Scores](DASHBOARD_SITE_SCORES.md) for the additive group overview,
selected-group summary, native classification filters and reviewed Combined link
contract. Existing canonical location and legacy network endpoints are retained.

## Intune location inventory filters

Existing `GET /api/v1/locations/{location_id}/devices` and location CSV export
accept the additive `issue=compliant` and `issue=recent_checkins` values.
Both predicates match Intune records only. `recent_checkins` uses the existing
seven-day check-in policy, including its missing/invalid timestamp handling.
Filtering occurs before pagination and totals. These filters also provide the
corresponding counts in location score evidence; selecting a filter never
recalculates the full-location Site Score. Existing issue values and response
envelopes remain compatible.

## Intune inventory reporting locations

`GET /api/v1/intune/devices` accepts additive `location_id` (maximum 64
characters): a canonical location ID, or `unassigned` for missing canonical
membership. This filter combines with search, status and vendor, and is applied
before totals and pagination. Unknown IDs return an empty result. The existing
`location` parameter continues filtering the raw source location.

Each Intune list item includes additive `canonical_location` (name or null).
Existing `location_id` and `location_resolution` convey reporting membership and
review state. Location names are resolved in one query per page. The UI uses
the existing `/locations` catalogue, restricted to Intune-populated locations,
and retains Unassigned. CSV export uses the same inventory filters and includes
the reporting name plus a readable location-assignment state.

See [inventory location guide](INVENTORY_LOCATIONS.md).
