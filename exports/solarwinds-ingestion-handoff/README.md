# SolarWinds Fetch-to-Database Handoff

Prepared: 2026-10-26. This is a source-code handoff of the current working tree,
not a database export or a complete portal deployment. Original source paths are
preserved under `source/`. See `MANIFEST.csv` for source-file SHA-256 checksums.

## Start Here

| Stage | Source file | Owning functions |
| --- | --- | --- |
| SWIS HTTP, pagination, queries | `src/sync/solarwinds_client.py` | `query`, `_fetch_complete_pages`, `fetch_nodes`, `fetch_groups`, `fetch_group_members` |
| Source normalization | `app/services/telemetry_sources.py` | `SolarWindsSource.fetch`, `validated_snapshot`, `normalize_solarwinds_node`, `classify_solarwinds_health`, `normalize_vendor` |
| Group validation | `app/services/solarwinds_group_service.py` | `validate_group_snapshot` |
| Database ingestion | `app/services/sync_service.py` | `execute_sync_with_lock`, `sync_single_source`, `ingest_telemetry_batch`, `retire_missing` |
| Group persistence | `app/repositories/solarwinds_group_repository.py` | `replace` |
| Canonical location assignment | `app/services/location_service.py` | `LocationResolver.resolve`, `LocationService.assign` |
| Manual entry point | `scripts/run_live_sync.py` | `dry_run`, `live_sync` |

Flow: SWIS SELECTs -> complete raw snapshots -> normalized node dictionaries and
validated groups -> transaction/lock -> CI upserts, group replacement, retirement,
history, location observations, and per-source sync audit -> commit.

`SWQL_QUERIES.md` lists all query templates used by this live extraction path.

## Connection and Extraction

- SWIS endpoint: `https://<host>:<port>/SolarWinds/InformationService/v3/Json/Query`.
- HTTP Basic authentication, GET only, SELECT-only query validation. This code
  does not write to SolarWinds; database writes target the configured local CMDB.
- Default client timeout is 30 seconds. The requests adapter configures three
  retries with backoff for HTTP 500, 502, 503, and 504. TLS and proxy behavior
  are controlled by runtime configuration; retain TLS verification.
- Node, group, and membership reads each count before and after extraction,
  use ordered pages of up to 500 rows, verify exact page lengths and strictly
  increasing keys, and reject changed totals. These checks detect several
  incomplete-read cases but do not establish a transactionally frozen SWIS
  snapshot across all requests or entities.
- A nonempty node list, valid identifiers, and no duplicate normalized node
  identifiers are required. Group extraction/validation is also required for a
  live SolarWinds run to succeed.

## Node Field Mapping

| SWIS input | Normalized / persisted result |
| --- | --- |
| `NodeID` | `external_id = SW-NODE-<NodeID>` -> CI `source_id`; `source_system = SOLARWINDS` |
| `Caption` | CI `name`; fallback `Node-<NodeID>` |
| `MachineType` | CI `ci_type` (fallback `Server`), `model`, and `operating_system` |
| `IPAddress` | CI `ip_address` |
| `Status` | CI `status`, derived `health_tier`, and JSON `attributes.orion_status_code` |
| `Vendor` | Canonical CI `vendor` via shared `normalize_vendor` |
| `CPULoad` | `cpu_load`; JSON `attributes.cpu_load`; history `cpu_utilization` on history writes |
| `PercentMemoryUsed` | `ram_used`; JSON `attributes.memory_used`; history `memory_utilization` on history writes |
| `AvgResponseTime` | `latency_ms`; JSON `attributes.latency_ms`; history `latency_ms` on history writes |
| `City`, `ITSM_Location` | Trimmed; CI raw `location` prefers City then ITSM_Location; both retained in JSON attributes |
| `StatusDescription` | JSON `attributes.status_description` |
| `SystemUpTime` | JSON `attributes.system_uptime` |
| `NodeDescription`, `Contact` | JSON `attributes.node_description`, `attributes.contact` |
| `NodeCategory`, `NodeType` | JSON `attributes.node_category`, `attributes.node_type`, only if strings |
| `ResponseTime`, `LastSync` | Fetched but not mapped by the live CI normalizer; no ResponseTime fallback here |
| No source serial/storage mapping | `serial_number` and `storage_used` remain null |

CI IDs are generated UUIDs. CI `last_sync_time` is the ingestion timestamp,
not Orion `LastSync`. Current CPU, memory, and latency evidence lives in CI JSON
attributes; dedicated numeric measurements are written to history only when a
history row is created.

### Status, Health, Vendor, and Metric Rules

- Status mapping: `0=Unknown`, `1=Up`, `2=Down`, `3=Warning`, `4=Shutdown`,
  `9=Unmanaged`, `14=Critical`; `17`, `19`, `22`, unmapped integers, and noninteger
  values become Unknown. Boolean values are not valid integer statuses.
- Base health: Up -> High; Down/Critical -> Low; other current mapped statuses
  -> Medium. Low remains Low. CPU >90 or RAM >90 -> Low; otherwise CPU >=75 or
  RAM >=80 -> Medium; otherwise keep base health. Exactly 90 is not critical.
- Vendor checks, in order: Dell, HP/Hewlett/HPE, Lenovo, Apple, Microsoft,
  Cisco, VMware; anything else -> Other. See the function for exact substring
  and prefix matches. The live normalizer does not retain the original vendor.
- Source `_num` accepts nonnegative numeric values, not booleans or numeric
  strings; unusable values become null. Persistence `_safe_float` additionally
  accepts numeric strings and rejects negatives, NaN, and infinity for numeric
  history columns. Do not assume those two helpers have identical contracts.

## Groups and Locations

- Query all containers, then keep only `Owner == Core` and `IsDeleted == false`.
  Preserve source group names verbatim, status code, and status description
  (fallback Unknown).
- Membership types are `Orion.Groups` and `Orion.Nodes`. Validate parent/child
  references against fetched groups/nodes, reject unsupported regular-group
  membership and cycles, allow multiple parents, and deduplicate identical
  edges. Persist into native group and membership tables.
- Raw source location is separate from canonical location assignment. The
  resolver uses enabled database mapping rules, approval states, and City /
  ITSM_Location evidence; incompatible known locations produce conflict instead
  of silently choosing a site. Never infer canonical sites from group names.
- Organization-specific `app/data/location_seed.json` is NOT exported. The
  package substitutes `examples/location_seed.empty.json` at that source path.
  For a clean-room run, retain the empty catalogue or provide your team's
  approved rules with the same schema. Empty rules leave
  canonical locations unassigned; they do not reproduce this deployment's
  site assignments. Existing database mapping decisions are not in this ZIP.

## Database Behavior and Safeguards

- SQLAlchemy selects SQLite or PostgreSQL using `DATABASE_URL`. Models and
  schema migrations are included for review; source migrations are authoritative
  for an existing database. Use a new isolated database for evaluation.
- Source identity is `(source_system, source_id)`. New nodes create a CI and an
  INITIAL_INGESTION history record. Existing records refresh inventory fields,
  attributes, canonical assignment, and last-sync timestamps.
- State fingerprint is SHA-256 of `status:health_tier`, not resource metrics.
  A stable active state does not create history just because CPU/RAM change.
  State changes and reactivation create history; retirement records an event.
  On the stable-state branch attributes are replaced; on the changed-state
  branch nonempty attributes are merged into the previous dictionary.
- Missing nodes are soft-retired (`is_active=false`, `retired_at` set), only
  after a validated complete live snapshot. They are not deleted. Injected test
  records and fixture reads do not authorize complete-snapshot retirement.
- Inventory, group replacement, retirement, successful audit, and location
  score observations share a nested transaction. Failure rolls that work back
  and records a FAILED source run without advancing successful freshness.
- PostgreSQL uses a transaction-scoped advisory lock. The SQLite fallback is
  an in-process lock, not a multi-process deployment lock.
- Sync audit includes extracted, normalized, rejected, new, updated, unchanged,
  retired, group and membership counts, status, timestamps, and duration.

## Important Legacy Distinction

The client also contains `process_telemetry`, `classify_node_health`,
`normalize_solarwinds_vendor`, `fetch_and_save`, and file reconciliation helpers.
Those serve a separate JSON-export path and are NOT called by the live
SolarWinds-to-database pipeline above. Their vendor buckets, status handling,
and latency fallback differ. `FixtureSource` is test/demo-only. Shared modules
contain Intune support, but this handoff targets `--source solarwinds` only.

## Evaluation Commands

Run from `source/` using Python 3.11+ and a virtual environment. Install
`requirements.txt`. Configure your own values using `examples/solarwinds.env.example`
as a reference; never send real credentials in the ZIP. Set an absolute isolated
SQLite path or an approved PostgreSQL connection URL, and keep scheduling off.
The package includes an empty, synthetic location-seed file for evaluation.

```text
python scripts/run_live_sync.py --source solarwinds --dry-run
python scripts/run_live_sync.py --source solarwinds
```

The first command contacts SWIS but does not write inventory. Its console output
includes a sample device, so treat that output as operationally sensitive. The
second command WRITES the selected database and may retire missing records;
run it only after confirming credentials, source permissions, and target DB.
No live source calls or writes to the configured CMDB were used to prepare
this handoff. Regression tests write only to isolated test databases.

Offline regression checks (the shared normalization tests also cover Intune
without contacting it):

```text
python -m pytest tests/test_step4_live_sync.py tests/test_snapshot_reconciliation.py tests/test_swql_security.py -q
```

The copied test fixtures block live requests and use isolated databases. Tests
requiring the complete portal's HTTP API or real telemetry are not included.
Packaging verification on 2026-10-26: all 32 tests in the command above passed
from the staged `source/` directory. This does not verify the receiving team's
SWIS connectivity, custom-property schema, credentials, or production database.
`app/workers/scheduler.py` is included as a scheduling reference; the runner
above is a one-shot sync and does not start the web app or scheduler.

The original `alembic.ini` is replaced by a credential-free evaluation config.
Migration scripts themselves remain exact source copies. For an existing DB,
review migrations and run `python -m alembic upgrade head` against the explicitly
configured target; never assume `create_all` upgrades an existing schema.

## Package Boundaries

Included: allowlisted ingestion source, supporting models/repositories/services,
schema migrations, dependency declarations, offline unit tests, and handoff notes.
Shared support modules are retained rather than rewritten into a new pipeline.
This is not a complete web application; frontend and HTTP deployment are omitted.

Excluded: `.env` files, real passwords/tokens, source telemetry exports, local
databases, logs, backups, organization-specific location rules, frontend assets,
Git history, caches, and installed dependencies. The synthetic examples are
handoff-only additions, not changes to the production ingestion implementation.
The manifest labels synthetic substitutions separately from original copies.