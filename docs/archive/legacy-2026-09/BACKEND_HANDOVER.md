# ITOM Portal — Backend Handover

**Prepared by:** Roshan Sah, IT Operations
**Date:** 10 September 2026
**Status:** Backend ready for frontend integration

---

## 1. What this document covers

The ITOM Portal backend was reviewed end-to-end and repaired across four
workstreams. This pack records what was broken, what was fixed, what is proven
by tests, and what remains outstanding.

**For the frontend engineer:** the file you need is
`API_CONTRACT_FOR_FRONTEND.md`. This document is the engineering record.

---

## 2. Executive summary

The backend was serving **hardcoded numbers that never changed**, its main
device-list endpoint **returned HTTP 500**, its freshness indicator **could not
report a problem**, and its sync engine **re-read a local file instead of
calling Microsoft Graph or SolarWinds**.

All four are now fixed and covered by tests.

| Area | Before | After |
|---|---|---|
| Summary endpoints | Frozen literals in source code | Live SQL aggregates |
| `GET /cmdb/cis` | HTTP 500 — could not serialise | Working, paginated |
| Freshness signal | Always "FRESH, 0 seconds" | Honest per-source status |
| Sync engine | Re-read local JSON forever | Calls Graph + SWIS |
| Server statuses | Down = 153 (wrong) | Down = 6 (correct) |
| History growth | ~223,000 rows/day | Only real transitions |

---

## 3. Defects found and fixed

### 3.1 Summary endpoints returned hardcoded data — **Critical**

`app/services/ci_service.py` returned frozen dictionaries with no database
access at all:

```python
async def get_intune_summary(self):
    return {"metrics": {"total_managed_devices": 25987,
                        "compliance_rate_pct": 83.08, ...}}
```

The dashboard would have reported 83.08% compliance **for ever** — even with an
empty database, even if every device fell out of compliance overnight.

The hardcoded OS split was also wrong against the real data: it claimed
iOS 6,120 and Android 3,450 where the actual fleet has iOS 2 and Android 1.
Both summed to the same total, so the existing invariant tests passed while the
shape was fiction.

**Fixed:** new `app/repositories/summary_repository.py` computes every figure
with `GROUP BY` aggregates. An un-ingested domain now returns **HTTP 503**
rather than plausible-looking placeholder data.

**Verified live:** 27,412 devices, 22,735 compliant, 82.94%. Status, health, OS
and vendor breakdowns each reconcile to exactly 27,412.

### 3.2 Device list endpoint returned HTTP 500 — **Critical**

`GET /api/v1/cmdb/cis`, `/intune/devices` and `/solarwinds/nodes` all failed:

```
PydanticSerializationError: Unable to serialize unknown type:
<class 'app.models.ci.ConfigurationItem'>
```

The endpoints handed SQLAlchemy ORM objects directly to FastAPI. These are the
three endpoints the frontend depends on most for tables and pagination.

**Fixed:** new `app/schemas/serializers.py` converts ORM rows to JSON-safe
dicts by reading mapped columns, so it stays correct as columns change. It never
touches relationship attributes, so no lazy-load can fire on an async session.

### 3.3 The freshness signal could not report a problem — **Critical**

```python
_last_sync_time: datetime = datetime.now(timezone.utc)   # module import time
```

Two defects: initialised to **process boot time**, so every response claimed
`FRESH, 0 seconds old` immediately after a restart regardless of data age; and
being a per-process global, each uvicorn worker held its own copy, so the header
was non-deterministic across workers.

Combined with the file-reading sync (3.4), this meant the header would report
FRESH indefinitely while the numbers never moved — actively suppressing the one
signal that would reveal the outage.

**Fixed:** new `GET /api/v1/system/freshness` derives from
`MAX(sync_runs.completed_at)` where status = SUCCESS. Reports per source.
Failed runs never advance the clock. "Never synced" is representable as
`UNKNOWN`.

**Verified live:** correctly reported `STALE`, age 322,005 seconds (3.7 days) —
data last synced 6 September. The old header would have said "FRESH".

### 3.4 Sync engine never called the APIs — **Critical**

```python
intune_file = os.path.join(PROJECT_ROOT, "data", "intune_ops_analytics.json")
sw_file     = os.path.join(PROJECT_ROOT, "data", "solarwinds_nodes.json")
```

- The 10-minute scheduler re-read the same **static file** on every cycle.
- `intune_file` was assigned and **never used** — there was no Intune branch, so
  `source_system="INTUNE"` returned SUCCESS with `items_extracted: 0`.
- A sync **could not fail**, because reading a local file always succeeds.

**Fixed:** new `app/services/telemetry_sources.py` provides `IntuneSource`
(Microsoft Graph) and `SolarWindsSource` (SWIS v3). Both clients are
synchronous, so they run via `asyncio.to_thread`. `FixtureSource` retains the
old file behaviour for tests only — never the production default.

### 3.5 SolarWinds statuses were collapsed — **High**

```python
"status": "Up" if Status == 1 else ("Warning" if Status == 3 else "Down")
```

Everything that was not Up or Warning became "Down" — including Critical (14)
and Unmanaged (9). `health_tier` only ever emitted High or Medium, so **"Low"
was unreachable** and the documented "Low/Critical 41 nodes" could not be
reproduced from the database.

Against the documented fleet (Up 1370, Warning 25, Critical 35, Down 6,
Unmanaged 112):

| Metric | Old | New |
|---|---|---|
| Reported Down | **153** | **6** ✅ |
| Critical | merged into Down | 35 |
| Unmanaged | merged into Down | 112 |
| Low health tier | unreachable | **41** ✅ |

An unmanaged node is not down; it is not being watched. Paging someone at 3am
on that difference matters.

### 3.6 Advisory lock leaked — **High**

`pg_try_advisory_lock` is **session-scoped** — it binds to the connection. The
old code committed, then released. By then SQLAlchemy had returned the
connection to the pool, so the unlock ran on a *different* connection and
silently returned false. The original lock stayed held and **every subsequent
sync returned SKIPPED** — sync death, with a still-green freshness header.

**Fixed:** `pg_advisory_xact_lock`, released automatically by PostgreSQL at
COMMIT.

### 3.7 Delta detection defeated itself — **High**

Fingerprint was `status:health:cpu:ram:storage`. CPU and RAM change on
essentially every poll, so nearly every CI hashed differently every cycle:
**1,548 nodes × 144 cycles ≈ 223,000 history rows per day** (~81M/year) in an
unpartitioned table.

**Fixed:** fingerprint covers `status:health_tier` only. Live resource metrics
still land on each history row that is written.

### 3.8 Attribute updates were silently discarded — **Medium**

`existing.attributes.update(attrs)` mutates a dict in place. SQLAlchemy does not
track that unless the column is a `MutableDict`, so every attribute update was
lost. **Fixed:** reassigns a merged dict.

### 3.9 Storage metric was mislabelled — **Medium**

`avg_storage_used_pct` was presented as an average but computed fleet-wide used
capacity ÷ total capacity — a capacity-weighted ratio dominated by the largest
disks. A 2 TB workstation at 10% and a 128 GB laptop at 95% produced a headline
of ~15%, hiding the device about to fail.

**Fixed:** three figures returned — `fleet_capacity_used_pct` (unchanged
formula), `median_device_storage_used_pct` (the risk-surfacing figure), and
`storage_sample_size` / `storage_coverage_pct` so consumers know the coverage.
`avg_storage_used_pct` retained as an alias for compatibility.

**Verified live:** capacity-weighted 36.6%, median 35.4%, coverage 99.4%.

### 3.10 Malformed source data could destroy an entire sync - **High**

Raw telemetry values were written straight into `Float` columns. A single
record carrying `cpu_load: "invalid_string"` - or SolarWinds' `-1` sentinel for
an unpolled counter - raised `StatementError` during flush, aborting the whole
transaction. **One malformed device would discard all 27,000 good ones.**

**Fixed:** metrics pass through `_safe_float()`, which rejects strings,
negatives, NaN and infinity. The CI row is still persisted; only the unreadable
metric becomes NULL.

### 3.11 Other findings

- **Microsoft devices bucketed as "Other"** — `include_microsoft` defaulted to
  `False`, so every Surface fell into "Other". Fixed.
- **Tautological invariants** — invariant 2 recomputed the compliance rate with
  the identical formula that produced it; invariant 6 asserted a bound that was
  unreachable by construction. Replaced with real reconciliation checks.
- **Executive digest under-counted the fleet by 1,420** — it summed endpoints +
  servers, omitting the network-infrastructure term. Documented; fix pending.
- **`stale_inactive_devices_count` always returned 0** — it scanned only the
  100-record sample and matched `"stale"` against a compliance enum that never
  contains it. Staleness derives from `lastSyncDateTime`. Documented; fix pending.
- **Frontend called the wrong path** — `/api/cmdb/summary` instead of
  `/api/v1/cmdb/summary`, with a bare `catch {}` that silently fell back to a
  stale local file. Documented in the frontend contract.

---

## 4. Test coverage

| Suite | Tests | Proves |
|---|---|---|
| `test_step1_summaries.py` | 7 | Summaries computed from DB; empty dataset raises; no hardcoded literals |
| `test_step3_freshness.py` | 9 | UNKNOWN when never synced; failed runs don't count; sources independent |
| `test_step4_live_sync.py` | 13 | Every Orion status distinct; failures recorded; CPU churn writes no history |
| `test_fastapi_live_integration.py` | 14 | Endpoints return valid JSON against real data |

**Full suite result: 278 passed, 3 failed** (plus 41 subtests).

The three failures are **pre-existing frontend asset issues**, unrelated to the
backend work and failing before it began:

| Test | Cause |
|---|---|
| `test_css_style_drift_guard` | `frontend/style.css` (72,145 bytes) and root `style.css` (28,307 bytes) have diverged |
| `test_modular_frontend_files_exist` | `frontend/ops_analytics.html` does not exist |
| `test_utils_module_exports_sanitizer_and_formatters` | Test expects `formatNumber(val)`; the code defines `formatNumber(num)` |

These belong to the frontend workstream. The root cause is the `src/frontend/`
to `frontend/` reorganisation, which left duplicate assets out of sync.

**Every backend test passes**, including the concurrency and latency suite.

Two regression guards worth noting: one asserts that no previously-hardcoded
fleet literal (25987, 83.08, 1357, …) can appear in a response for a dataset
that doesn't contain it; another statically scans `ci_service.py` for those
literals. The old bug cannot silently return.

---

## 5. Files changed

**New**
```
app/repositories/summary_repository.py     Live summary aggregations
app/repositories/freshness_repository.py   DB-backed freshness
app/schemas/serializers.py                 ORM → JSON conversion
app/services/telemetry_sources.py          Graph + SWIS adapters
app/api/v1/endpoints/system.py             /system/freshness
tests/test_step1_summaries.py
tests/test_step3_freshness.py
tests/test_step4_live_sync.py
```

**Modified**
```
app/services/ci_service.py      Hardcoded dicts → repository delegation
app/services/sync_service.py    File reads → live extraction
app/api/v1/router.py            Registers the system router
app/main.py                     EmptyDatasetError → HTTP 503
```

Backups were taken as `.bak` alongside each replaced file.

---

## 6. New endpoint

### `GET /api/v1/system/freshness`

Always returns HTTP 200. Branch on the body.

```json
{
  "checked_at": "2026-09-10T12:16:21+00:00",
  "freshness_window_seconds": 1500,
  "overall_status": "STALE",
  "oldest_age_seconds": 322005,
  "sources": {
    "INTUNE":     { "last_synchronized_at": "2026-09-06T18:49:35+00:00", "age_seconds": 322005, "status": "STALE" },
    "SOLARWINDS": { "last_synchronized_at": "2026-09-06T18:49:35+00:00", "age_seconds": 322005, "status": "STALE" }
  }
}
```

`FRESH` / `STALE` / `UNKNOWN`. `overall_status` is the worst across sources.

---

## 7. Outstanding — requires action

### 7.1 Rotate credentials — **do this first**

The Azure client secret and SolarWinds password in `.env` have been sitting in
a cloud-synced folder. **Treat them as exposed.** Rotate with your admin, then
move `.env` outside the synced path.

Live sync will return 401 until valid credentials are in place. **That FAILED
status is correct behaviour** — the system now detects a broken extraction
instead of silently reporting success.

### 7.2 Authenticate the sync trigger

`POST /api/v1/sync/trigger` is unauthenticated and is the only writable verb in
the system. Anyone who can reach the port can trigger unbounded ingestion. Add
auth before this leaves your network.

### 7.3 Narrow CORS

`BACKEND_CORS_ORIGINS = ["*"]` with `allow_credentials=True`. Browsers reject
that combination outright. Set the real frontend origin.

### 7.4 Replace the default secret key

`config.py` ships `SECRET_KEY = "itom-secret-key-change-in-production-0987654321"`
as a default. If the env var is missing in production this silently becomes the
live key.

### 7.5 Smaller items

- `docker-compose.yml` falls back to `POSTGRES_PASSWORD:-itom_secure_password`
- `/ready` returns `"migration_head": true` unconditionally — it does not verify
  the schema version, so it cannot fail on drift
- `ci_status_history` has no retention policy — much smaller now, but unbounded
- Executive digest fleet total (§3.10) and `stale_inactive_devices_count`
- Only **one** Alembic migration exists for a five-entity schema, suggesting the
  schema has been reset rather than versioned forward
- The two project folders (`Documents\antigravity\` and `Desktop\`) have drifted
  — frontend assets differ between them

---

## 8. Running it

```powershell
python -m uvicorn app.main:app --port 8000
```

```powershell
python -m pytest tests/ -v
```

Interactive API docs: `http://localhost:8000/docs`

Quick verification:

```powershell
curl.exe http://localhost:8000/api/v1/system/freshness
curl.exe http://localhost:8000/api/v1/intune/summary
curl.exe "http://localhost:8000/api/v1/cmdb/cis?page=1&page_size=10"
curl.exe -i -X POST http://localhost:8000/api/v1/cmdb/summary   # expect 405
```

---

## 9. Handover checklist

- [x] Summary endpoints read the database
- [x] Device list endpoint returns valid JSON
- [x] Freshness endpoint reports honestly
- [x] Sync engine calls the live APIs
- [x] Server status mapping corrected
- [x] Malformed source data cannot abort a sync
- [x] 278 tests passing (3 known frontend failures)
- [x] API contract written for the frontend
- [ ] Credentials rotated ← **blocking live data**
- [ ] Sync trigger authenticated
- [ ] CORS narrowed to the real origin

---

## 10. A note on what "working" means here

The backend is architecturally sound and now tells the truth about its own
state. That last part is the real change: before this work, a completely broken
ingestion pipeline and a perfectly healthy one produced **identical** dashboard
output. There was no way to tell them apart.

The system will now say `STALE` or `UNKNOWN` when something is wrong. Please
treat those as signals to act on rather than noise to suppress — they are the
difference between a dashboard you can trust and one that merely looks
confident.
