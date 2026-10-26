# ITOM Data Flow

The current runtime has two separate paths. See [Architecture](ARCHITECTURE.md) for the component diagram and deployment details.

## Scheduled collection

```text
APScheduler (default: every 600 seconds)
  -> SyncService with overlap protection
  -> Microsoft Graph / SolarWinds SWIS clients
  -> Source adapters normalize and validate the snapshot
  -> Update current configuration items
  -> Record status/health transitions
  -> Retire missing items only after a validated complete snapshot
  -> Record per-source sync outcomes and errors
```

Live source clients are called directly by the adapters. Staged JSON files are not a required link in this runtime. Explicit fixture adapters support tests and offline demonstrations.

## Browser request

```text
frontend-revamp/src/App.tsx / Inventory.tsx
  -> frontend-revamp/src/api.ts
  -> /api/v1 endpoint
  -> service
  -> repository
  -> database
  -> JSON response
  -> table or chart
```

For example, `/api/v1/cmdb/cis?page=1&page_size=25` returns `items`, `total`, `page`, `page_size`, `total_pages`, `has_next`, and `has_prev`. Allowed inventory page sizes are 10, 25, 50, and 100.

## Failure behavior

- Source failure is recorded as a failed sync; it does not advance successful freshness.
- Per-source audit records keep Intune and SolarWinds freshness independent.
- Inventory and retirement changes for a source ingestion use a savepoint so failure can roll them back together.
- The current frontend API client propagates request failures rather than substituting a static data file.
- An empty telemetry domain can return HTTP 503.
- `/api/v1/system/freshness` distinguishes fresh, stale, and unknown data.

The database stores the latest known state. Dashboard reads do not synchronously poll external source systems, and status history is not a continuous CPU/RAM sampling stream.
