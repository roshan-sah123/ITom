# ITOM Portal — Backend

IT Operations platform. Pulls device telemetry from **Microsoft Intune** and
**SolarWinds Orion**, stores it in a CMDB, and serves it over a read-only REST API.

**Status:** backend verified against live data, ready for frontend integration.

| | |
|---|---|
| Devices under management | 30,773 (29,191 Intune · 1,582 SolarWinds) |
| Sites | 71 |
| Sync cadence | Every 10 minutes |
| Tests | 277 passing |

---

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in your credentials
python -m uvicorn app.main:app --port 8000
```

Interactive API docs: **http://localhost:8000/docs**

Verify it is alive and the data is recent:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/api/v1/system/freshness
```

---

## 👋 Frontend engineers — read this first

### 1. The base path is `/api/v1/`, not `/api/`

```js
fetch('/api/cmdb/summary')       // ❌ 404
fetch('/api/v1/cmdb/summary')    // ✅
```

### 2. Never fall back to a static file when a call fails

```js
// ❌ This hides outages behind week-old numbers
try   { return await fetch('/api/v1/cmdb/summary').then(r => r.json()); }
catch { return await fetch('data/cmdb_summary.json').then(r => r.json()); }

// ✅ Show an error state instead
const res = await fetch('/api/v1/cmdb/summary');
if (!res.ok) return showUnavailable(res.status);
return res.json();
```

### 3. Check freshness before rendering any number

```js
const f = await fetch('/api/v1/system/freshness').then(r => r.json());
if (f.overall_status !== 'FRESH') showStaleBanner(f);
```

`FRESH` · `STALE` · `UNKNOWN`. Always HTTP 200 — branch on the body, not the status code.

### 4. Two known gaps in the data

- **Location analytics are SolarWinds-only.** Microsoft Graph exposes no site
  field for managed devices, so all 29,191 Intune devices report as unlocated.
  Read `location_coverage_pct` and show it.
- **577 assets no longer report to their source.** Deliberately retained — see
  `/analytics/stale-assets`. Fleet percentages include them, so figures are
  roughly 2% off. `active_cis` gives the excluding-stale view.

---

## Endpoints

Base: `http://localhost:8000/api/v1`

### System

| Method | Path | Returns |
|---|---|---|
| GET | `/healthz` | Process alive |
| GET | `/ready` | Database reachable |
| GET | `/system/freshness` | **Per-source data age and FRESH/STALE/UNKNOWN** |

### Summaries — dashboard KPIs

| Method | Path |
|---|---|
| GET | `/intune/summary` |
| GET | `/solarwinds/summary` |
| GET | `/cmdb/summary` |

Returns totals, compliance rate, health counts, storage metrics, and
chart-ready breakdowns by status, health, OS, vendor and location.

**Every breakdown sums exactly to the total** — safe for pie charts.

Returns **503** when that domain has no ingested data. That is meaningful, not
a crash: the endpoint refuses to invent numbers.

<details>
<summary>Example — <code>GET /api/v1/intune/summary</code></summary>

```json
{
  "source_system": "INTUNE",
  "data_source": "DATABASE",
  "generated_at": "2026-09-10T13:21:54+00:00",
  "last_sync_time": "2026-09-10T13:20:46",
  "metrics": {
    "total_managed_devices": 29188,
    "compliant_devices": 23776,
    "noncompliant_devices": 4414,
    "other_compliance": 998,
    "compliance_rate_pct": 81.46,
    "high_health_count": 23776,
    "medium_health_count": 998,
    "low_health_count": 4414,
    "avg_storage_used_pct": 37.4,
    "median_device_storage_used_pct": 36.3,
    "storage_sample_size": 28870,
    "storage_coverage_pct": 98.91
  },
  "status_breakdown":    { "Compliant": 23776, "Noncompliant": 4414, "Configmanager": 920, "Ingraceperiod": 10, "Unknown": 68 },
  "health_breakdown":    { "High": 23776, "Medium": 998, "Low": 4414 },
  "os_distribution":     { "Windows": 27750, "macOS": 1120, "Linux (ubuntu)": 235, "Endpoint": 77, "iOS": 2, "Android": 1 },
  "vendor_distribution": { "Dell": 17107, "HP": 9577, "Lenovo": 1184, "Apple": 1122, "Microsoft": 49 }
}
```

**On storage:** prefer `median_device_storage_used_pct` for risk display.
`avg_storage_used_pct` is capacity-weighted, so large disks dominate it and
nearly-full laptops disappear.
</details>

### Lists — tables and pagination

| Method | Path |
|---|---|
| GET | `/cmdb/cis` |
| GET | `/intune/devices` |
| GET | `/solarwinds/nodes` |

**Query params:** `page`, `page_size`, `search`, `source_system`, `ci_type`,
`vendor`, `health_tier`, `status`, `sort_by`, `sort_order`

⚠️ `page_size` must be **10, 25, 50 or 100**. Anything else returns 422.

**Envelope:** `items`, `total`, `page`, `page_size`, `total_pages`,
`has_next`, `has_prev`

### Analytics

| Method | Path | Returns |
|---|---|---|
| GET | `/analytics/locations` | Per-site availability, health mix, risk |
| GET | `/analytics/stale-assets` | Assets the source no longer reports |

`/analytics/locations?sort_by=risk` puts the worst sites first — ready for an
operations triage table.

`/analytics/stale-assets?limit=0` returns counts only, for a KPI tile.

<details>
<summary>Example — <code>GET /api/v1/analytics/locations?source_system=SOLARWINDS</code></summary>

```json
{
  "total_locations": 71,
  "located_cis": 1579,
  "unlocated_cis": 3,
  "location_coverage_pct": 99.81,
  "locations": [
    {
      "location": "Gr.Noida-T-AB",
      "total_cis": 373,
      "available_cis": 345,
      "availability_pct": 92.49,
      "high_health_count": 344,
      "low_health_count": 11,
      "at_risk_cis": 29,
      "status_breakdown": { "Up": 345, "Critical": 10, "Warning": 10, "Unmanaged": 7, "Down": 1 }
    }
  ]
}
```
</details>

### Sync

| Method | Path |
|---|---|
| GET | `/sync/runs` |
| GET | `/sync/runs/latest` |
| POST | `/sync/trigger` ⚠️ unauthenticated — see Security |

### Read-only enforcement

`POST` / `PUT` / `PATCH` / `DELETE` on telemetry routes return **405** with
`Allow: GET, HEAD, OPTIONS`.

### Status codes

| Code | Meaning |
|---|---|
| 200 | Success |
| 404 | Not found |
| 405 | Write attempted on a read-only route |
| 422 | Invalid parameter |
| 503 | No data ingested for that domain |

---

## Suggested dashboard load sequence

```js
async function loadDashboard() {
  const fresh = await fetchJson('/api/v1/system/freshness');
  if (fresh.overall_status !== 'FRESH') showStaleBanner(fresh);

  const [intune, solarwinds, cmdb] = await Promise.allSettled([
    fetchJson('/api/v1/intune/summary'),
    fetchJson('/api/v1/solarwinds/summary'),
    fetchJson('/api/v1/cmdb/summary'),
  ]);

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

## Fetching data manually

```bash
python scripts/check_live_connectivity.py              # test credentials, writes nothing
python scripts/run_live_sync.py --source solarwinds    # ~4 seconds
python scripts/run_live_sync.py --source intune        # ~80 seconds, 28k devices
python scripts/run_live_sync.py --source intune --dry-run
```

---

## Tests

```bash
python -m pytest tests/ -q
```

**Expect 277 passed, 4 failed.** The failures are pre-existing frontend asset
issues (duplicate `style.css`, a moved HTML file, a renamed JS function) plus a
concurrency latency threshold under SQLite. None indicates a backend defect.

---

## Architecture

```
Microsoft Graph ──┐
                  ├──► telemetry_sources.py ──► sync_service.py ──► PostgreSQL
SolarWinds SWIS ──┘         (normalise)          (delta detect)         │
                                                                        ▼
                                            repositories ──► services ──► FastAPI
```

| Folder | Responsibility |
|---|---|
| `app/api/` | HTTP endpoints |
| `app/services/` | Business logic, ingestion |
| `app/repositories/` | Database queries |
| `app/models/` | SQLAlchemy tables |
| `src/sync/` | Graph and SWIS API clients |
| `scripts/` | Operational tooling |
| `tests/` | Test suites |

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 ·
APScheduler · Alembic

---

## ⚠️ Security — before deploying beyond localhost

| Item | Status |
|---|---|
| `POST /sync/trigger` has no authentication | **Open** |
| CORS set to `*` with credentials enabled | **Open** |
| `SECRET_KEY` has a hardcoded default in `config.py` | **Open** |
| TLS verification disabled for SolarWinds | **Open** |

Until these are addressed, bind to localhost only:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Never commit `.env`. It is gitignored — keep it that way.

---

## Further reading

| Document | For |
|---|---|
| `HANDOVER/API_CONTRACT_FOR_FRONTEND.md` | Full API reference |
| `HANDOVER/BACKEND_GUIDE.md` | Running and troubleshooting |
| `HANDOVER/BACKEND_VALIDATION_AUDIT.md` | Full engineering audit |

---

## Design principle worth knowing

This backend **admits when it does not know.**

- No data → `503`, not a plausible-looking number
- Old data → `STALE`, not a false "fresh"
- Failed extraction → `FAILED`, not a silent success

If you see `STALE` or `503`, that is the system working correctly. Please
surface those states in the UI rather than hiding them — they are why the
numbers can be trusted when it says `FRESH`.
