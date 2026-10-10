# ITOM Portal — Backend API Contract

**For:** Frontend engineer
**Base URL:** `http://localhost:8000`
**All routes are prefixed** `/api/v1` (except the probes)
**Interactive docs:** `http://localhost:8000/docs`

---

## ⚠️ Read this first — three rules

### 1. The base path is `/api/v1`, not `/api`

```js
// WRONG — returns 404
fetch('/api/cmdb/summary')

// RIGHT
fetch('/api/v1/cmdb/summary')
```

### 2. Never silently fall back to a static file

If a call fails, show an error state. Do not quietly load `data/*.json` instead —
that is how the dashboard ends up showing numbers that are weeks old while
looking perfectly healthy.

```js
// WRONG — hides the failure
try { return await fetch('/api/v1/cmdb/summary').then(r => r.json()); }
catch { return await fetch('data/cmdb_summary.json').then(r => r.json()); }

// RIGHT
const res = await fetch('/api/v1/cmdb/summary');
if (!res.ok) return showUnavailable(res.status);
return res.json();
```

### 3. Always check freshness before rendering numbers

Call `/api/v1/system/freshness` once on page load. If `overall_status` is not
`FRESH`, show a banner above the dashboard.

---

## Endpoint list

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Is the server alive? |
| GET | `/ready` | Can it reach the database? |
| GET | `/api/v1/system/freshness` | **Is the data recent?** |
| GET | `/api/v1/cmdb/summary` | CMDB totals + breakdowns |
| GET | `/api/v1/cmdb/cis` | Paginated CI list (main table) |
| GET | `/api/v1/cmdb/cis/{id}` | One CI |
| GET | `/api/v1/cmdb/cis/{id}/history` | Status history for a CI |
| GET | `/api/v1/cmdb/cis/{id}/relationships` | Topology links |
| GET | `/api/v1/intune/summary` | Intune compliance + OS split |
| GET | `/api/v1/intune/devices` | Paginated Intune devices |
| GET | `/api/v1/solarwinds/summary` | Node health + availability |
| GET | `/api/v1/solarwinds/nodes` | Paginated SolarWinds nodes |
| GET | `/api/v1/sync/runs` | Sync history |
| GET | `/api/v1/sync/runs/latest` | Most recent sync |

**Only `GET` works** on telemetry routes. `POST`/`PUT`/`PATCH`/`DELETE` return
`405` with `Allow: GET, HEAD, OPTIONS`.

---

## 1. Freshness — call this first

### `GET /api/v1/system/freshness`

Always returns `200`. Branch on the body, not the status code.

```json
{
  "checked_at": "2026-09-10T12:00:00+00:00",
  "freshness_window_seconds": 1500,
  "overall_status": "FRESH",
  "oldest_age_seconds": 412,
  "sources": {
    "INTUNE":     { "last_synchronized_at": "2026-09-10T11:53:08+00:00", "age_seconds": 412, "status": "FRESH" },
    "SOLARWINDS": { "last_synchronized_at": "2026-09-10T11:53:48+00:00", "age_seconds": 372, "status": "FRESH" }
  }
}
```

| `status` | Meaning | Suggested UI |
|---|---|---|
| `FRESH` | Synced recently | Normal |
| `STALE` | Synced, but too long ago | Amber banner + "Last updated X ago" |
| `UNKNOWN` | **Never synced** | Red banner, treat numbers as unverified |

`overall_status` is the **worst** of all sources. `oldest_age_seconds` is `null`
when nothing has ever synced.

```js
const f = await fetch('/api/v1/system/freshness').then(r => r.json());
if (f.overall_status !== 'FRESH') showStaleBanner(f);
```

---

## 2. Summary endpoints

`GET /api/v1/intune/summary` · `GET /api/v1/solarwinds/summary` · `GET /api/v1/cmdb/summary`

**Returns `200` with data, or `503` when that domain has never been ingested.**
A `503` here is meaningful — it means "no data", not "server broken".

### Intune response

```json
{
  "source_system": "INTUNE",
  "data_source": "DATABASE",
  "generated_at": "2026-09-10T12:00:00+00:00",
  "last_sync_time": "2026-09-06T18:49:33",
  "metrics": {
    "total_managed_devices": 27412,
    "compliant_devices": 22735,
    "noncompliant_devices": 3774,
    "non_compliant_devices": 3774,
    "other_compliance": 903,
    "compliance_rate_pct": 82.94,
    "high_health_count": 22735,
    "medium_health_count": 903,
    "low_health_count": 3774,
    "high_health_pct": 82.94,
    "medium_health_pct": 3.29,
    "low_health_pct": 13.77,
    "avg_storage_used_pct": 41.2,
    "fleet_capacity_used_pct": 41.2,
    "median_device_storage_used_pct": 48.6,
    "storage_sample_size": 24180,
    "storage_coverage_pct": 88.2
  },
  "status_breakdown":     { "Compliant": 22735, "Noncompliant": 3774, "Configmanager": 850, "Ingraceperiod": 9, "Unknown": 44 },
  "compliance_breakdown": { "Compliant": 22735, "Noncompliant": 3774, "Configmanager": 850, "Ingraceperiod": 9, "Unknown": 44 },
  "health_breakdown":     { "High": 22735, "Medium": 903, "Low": 3774 },
  "os_distribution":      { "Windows": 26357, "macOS": 891, "Linux (ubuntu)": 123, "Endpoint": 36, "iOS": 2, "Android": 1, "Linux ()": 2 },
  "os_breakdown":         { "Windows": 26357, "macOS": 891, "Linux (ubuntu)": 123, "Endpoint": 36, "iOS": 2, "Android": 1, "Linux ()": 2 },
  "vendor_distribution":  { "Dell": 16383, "HP": 8938, "Lenovo": 1061, "Apple": 893, "Other": 89, "Microsoft": 48 }
}
```

**Notes**

- `data_source` is `"DATABASE"` on success, `"NONE"` on a 503. Check it.
- `compliance_breakdown` / `os_breakdown` are aliases of `status_breakdown` /
  `os_distribution` — same object, older names. Use either.
- Every breakdown sums exactly to `total_managed_devices`. Safe for pie charts.
- **Storage:** prefer `median_device_storage_used_pct` for risk display.
  `avg_storage_used_pct` is capacity-weighted, so large disks dominate it and
  nearly-full laptops disappear. `storage_coverage_pct` tells you what share of
  devices reported storage at all.

### SolarWinds response

Same envelope. Different metrics:

```json
{
  "metrics": {
    "total_server_nodes": 1548,
    "available_nodes": 1370,
    "unavailable_nodes": 178,
    "availability_pct": 88.5,
    "active_monitored_nodes": 1436,
    "high_health_nodes": 1357,
    "medium_health_nodes": 150,
    "low_critical_nodes": 41,
    "status_counts": {
      "up": 1370,
      "warning": 25,
      "critical": 35,
      "down": 6,
      "unmanaged_unknown": 112
    }
  },
  "status_breakdown": { "Up": 1370, "Warning": 25, "Critical": 35, "Down": 6, "Unmanaged": 112 },
  "ci_type_distribution": { "Server": 1548 }
}
```

Use `metrics.status_counts` for availability charts. Its lowercase keys are the
stable frontend contract. `status_breakdown` remains the source-labelled
SolarWinds detail for tables and backward compatibility.

`Critical`, `Down` and `Unmanaged` are **distinct** — do not merge them.
An unmanaged node is not down; it is simply not being watched. `Unknown` and
`Unmanaged` are combined only in `unmanaged_unknown`.

### 503 response

```json
{
  "error": "Telemetry dataset unavailable",
  "detail": "No Configuration Items persisted for source system 'INTUNE'. Run a telemetry synchronization first.",
  "source_system": "INTUNE",
  "data_source": "NONE"
}
```

---

## 3. List endpoints (tables + pagination)

`GET /api/v1/cmdb/cis` · `/api/v1/intune/devices` · `/api/v1/solarwinds/nodes`

### Query parameters

| Param | Type | Default | Notes |
|---|---|---|---|
| `page` | int | `1` | 1-based |
| `page_size` | int | `25` | **Only 10, 25, 50, 100** — anything else returns `422` |
| `search` | string | — | Matches name, IP, serial, vendor |
| `source_system` | string | — | `INTUNE` or `SOLARWINDS` (cmdb only) |
| `ci_type` | string | — | e.g. `Server`, `Windows` |
| `vendor` | string | — | e.g. `Dell` |
| `health_tier` | string | — | `High`, `Medium`, `Low` |
| `status` | string | — | e.g. `Up`, `Compliant` |
| `sort_by` | string | `name` | Column name |
| `sort_order` | string | `asc` | `asc` or `desc` |

### Response envelope

```json
{
  "items": [
    {
      "id": "3f2b8c10-...",
      "source_id": "SW-NODE-1042",
      "source_system": "SOLARWINDS",
      "name": "MUM-APP-014",
      "ci_type": "Server",
      "status": "Up",
      "health_tier": "High",
      "ip_address": "10.14.22.8",
      "mac_address": null,
      "vendor": "Dell",
      "model": "PowerEdge R740",
      "serial_number": "J7K2L9",
      "operating_system": "Windows Server 2019",
      "location": "Mumbai",
      "last_sync_time": "2026-09-10T11:53:08+00:00",
      "state_hash": "9f2c...",
      "attributes": { "cpu_load": 34.2, "memory_used": 61.0 },
      "created_at": "2026-09-01T10:00:00+00:00",
      "updated_at": "2026-09-10T11:53:08+00:00"
    }
  ],
  "total": 28984,
  "page": 1,
  "page_size": 25,
  "total_pages": 1160,
  "has_next": true,
  "has_prev": false
}
```

All IDs and timestamps are strings. `attributes` is a free-form object whose
keys differ by source — read defensively.

### Bad page size → `422`

```json
{ "detail": "page_size must be one of [10, 25, 50, 100]" }
```

---

## 4. Sub-resources

`GET /api/v1/cmdb/cis/{id}/history?limit=50` — status changes over time
(`limit` 1–500, default 50). Each row has `status`, `health_tier`,
`previous_status`, `previous_health_tier`, `cpu_utilization`,
`memory_utilization`, `storage_used_pct`, `latency_ms`, `recorded_at`.

`GET /api/v1/cmdb/cis/{id}/relationships` — topology edges with
`source_ci_id`, `target_ci_id`, `relationship_type`.

Unknown ID on `/cis/{id}` returns `404`:

```json
{ "error": "Configuration Item not found", "id": "..." }
```

---

## 5. Sync history

`GET /api/v1/sync/runs?page=1&page_size=25` — array of runs, newest first.
`GET /api/v1/sync/runs/latest?source_system=INTUNE` — one run, or `404`.

```json
{
  "id": "8c21...",
  "source_system": "INTUNE",
  "status": "SUCCESS",
  "items_extracted": 27412,
  "items_persisted": 0,
  "records_updated": 118,
  "records_unchanged": 27294,
  "duration_ms": 8421,
  "started_at": "2026-09-10T11:53:00+00:00",
  "completed_at": "2026-09-10T11:53:08+00:00"
}
```

`status` is `SUCCESS`, `FAILED`, `RUNNING`, `PARTIAL` or `SKIPPED`.

---

## 6. Response headers on every call

| Header | Example | Meaning |
|---|---|---|
| `X-Last-Synchronized-At` | `2026-09-10T11:53:08+00:00` | Last sync time |
| `X-Data-Age-Seconds` | `412` | Age in seconds |
| `X-Sync-Status` | `FRESH` | `FRESH` / `STALE` / `UNKNOWN` |

> ⚠️ For now, trust the **`/api/v1/system/freshness` endpoint** over these
> headers. The header path still reads a per-process value and can disagree
> between server workers. The endpoint reads the database and is authoritative.

---

## 7. Status codes

| Code | Meaning | UI response |
|---|---|---|
| `200` | Success | Render |
| `404` | Not found | "Not found" |
| `405` | Write attempted on read-only API | Fix the call — use GET |
| `422` | Bad parameter | Fix the query |
| `503` | No data ingested for that domain | "Data unavailable" banner |

---

## 8. Suggested load sequence

```js
async function loadDashboard() {
  // 1. Freshness first
  const fresh = await fetch('/api/v1/system/freshness').then(r => r.json());
  if (fresh.overall_status !== 'FRESH') showStaleBanner(fresh);

  // 2. Summaries in parallel — handle each independently
  const [intune, solarwinds, cmdb] = await Promise.allSettled([
    fetchJson('/api/v1/intune/summary'),
    fetchJson('/api/v1/solarwinds/summary'),
    fetchJson('/api/v1/cmdb/summary'),
  ]);

  // 3. Table data on demand
  const page = await fetchJson('/api/v1/cmdb/cis?page=1&page_size=25');
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (res.status === 503) throw new DataUnavailable(await res.json());
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
```

---

## 9. Current limitations — please read

1. **`POST /api/v1/sync/trigger` is unauthenticated.** Do not expose it in the UI.
2. **CORS is `*`** with credentials enabled — browsers reject that combination.
   Tell the backend team your dev origin so it can be narrowed.
3. **`/ready` reports `"migration_head": true` unconditionally.** It does not
   verify the schema version; do not rely on it for deployment gating.
4. **Live ingestion is not wired yet.** The scheduler currently re-reads local
   files rather than calling Microsoft Graph and SolarWinds. Data is real, but
   it moves only when a seed or manual sync runs. This is why
   `/system/freshness` matters — it will honestly report `STALE`.

---

## Quick verification

```powershell
curl.exe http://localhost:8000/api/v1/system/freshness
curl.exe http://localhost:8000/api/v1/intune/summary
curl.exe "http://localhost:8000/api/v1/cmdb/cis?page=1&page_size=10"
curl.exe -i -X POST http://localhost:8000/api/v1/cmdb/summary   # expect 405
```
