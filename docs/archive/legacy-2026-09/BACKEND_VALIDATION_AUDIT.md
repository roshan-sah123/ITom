# ITOM Portal — Backend Functional, Data, Mathematical & Test Validation Audit

**Subject:** `optimistic-pasteur` — ITOM Portal backend
**Audit date:** 10 September 2026
**Repository audited:** `C:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur`, branch `fix/step1-live-summaries`
**Classification scheme:** 🟢 PASS · 🟡 PASS WITH CONCERN · 🔴 FAIL · ⚪ NOT VERIFIED

---

## ⚠️ AUDITOR INDEPENDENCE DISCLOSURE — READ FIRST

**This audit is not independent.** Earlier the same day, the auditor authored
substantial modifications to this codebase: `summary_repository.py`,
`freshness_repository.py`, `serializers.py`, `telemetry_sources.py`,
`system.py`, and rewrites of `ci_service.py` and `sync_service.py`.

An engineer auditing their own work has an inherent conflict of interest.
Accordingly:

- Every finding covering auditor-authored code is marked **[SELF-AUTHORED]**.
- Those findings should be treated as **⚪ NOT INDEPENDENTLY VERIFIED** regardless
  of the classification shown, and re-reviewed by a second engineer before the
  system is relied upon in production.
- Findings on code the auditor did **not** write carry no such caveat.

**Additional evidence limitation:** the auditor has **no execution access** to
the host. All runtime evidence in this report was produced by the operator
(Roshan Sah) in his own terminal and pasted back. The auditor could not
independently run the test suite, query the database, call the live APIs, or
inspect `.env`. Static analysis was performed against the OneDrive-synced copy
of the repository; the operator's working copy is a **different directory** and
is known to have diverged in frontend assets (§20).

---

## 1. Executive Summary

The backend is a **Python 3.12 / FastAPI / SQLAlchemy 2.0 async application**
that ingests IT asset telemetry, persists it to a relational CMDB, and exposes
read-only REST endpoints.

As of this audit the system's **core read path is functionally and
mathematically correct** and **verified against live data**. Every aggregate
returned by `/api/v1/intune/summary` reconciles exactly to the row count
(27,412) across four independent breakdowns.

However, the audit surfaced **material unresolved risks**:

| Severity | Finding |
|---|---|
| 🔴 CRITICAL | Production credentials remain un-rotated after cloud-sync exposure |
| 🔴 CRITICAL | `POST /api/v1/sync/trigger` is unauthenticated |
| 🔴 FAIL | Live external ingestion has **never been executed successfully** — no evidence exists that Graph or SWIS extraction works |
| 🟡 CONCERN | Documented fleet figures disagree with database contents by 1,425 records |
| 🟡 CONCERN | `sort_by` is an unvalidated `getattr` against the ORM class |
| 🟡 CONCERN | Test-suite honesty is compromised by 87 silently-skipped subtests |

**The most important qualification in this report:** the ingestion pipeline was
rewritten today to call Microsoft Graph and SolarWinds, and **that code path has
not once run against a real API**. Its correctness is asserted by unit tests
using fake sources only. Until a live extraction succeeds, live ingestion must
be classified ⚪ NOT VERIFIED, not PASS.

---

## 2. Discovered Architecture

Derived from code inspection only.

### 2.1 Runtime topology

```
                    ┌─────────────────────────────────┐
                    │  Microsoft Graph (Intune)       │  ← OAuth2 client credentials
                    │  graph.microsoft.com/v1.0       │
                    └──────────────┬──────────────────┘
                                   │  requests (sync)
                    ┌──────────────▼──────────────────┐
                    │  SolarWinds Orion SWIS v3       │  ← HTTP Basic
                    │  gnoc.coforge.com:17774         │
                    └──────────────┬──────────────────┘
                                   │
        ┌──────────────────────────▼───────────────────────────┐
        │  app/services/telemetry_sources.py                   │
        │  IntuneSource · SolarWindsSource · FixtureSource     │
        │  (normalisation → CI dicts)                          │
        └──────────────────────────┬───────────────────────────┘
                                   │  asyncio.to_thread
        ┌──────────────────────────▼───────────────────────────┐
        │  app/services/sync_service.py                        │
        │  advisory lock → per-source SyncRun → SHA-256 delta  │
        └──────────────────────────┬───────────────────────────┘
                                   │
        ┌──────────────────────────▼───────────────────────────┐
        │  PostgreSQL 16  (SQLite fallback)                    │
        │  configuration_items · ci_relationships              │
        │  ci_status_history · sync_runs · sync_error_logs     │
        └──────────────────────────┬───────────────────────────┘
                                   │
        ┌──────────────────────────▼───────────────────────────┐
        │  Repositories → Services → FastAPI /api/v1           │
        │  + FreshnessHeadersMiddleware (405 guard)            │
        └──────────────────────────┬───────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │  nginx :8080  →  static frontend│
                    │  Chart.js / vanilla JS          │
                    └─────────────────────────────────┘

        ┌──────────────────────────────────────────────────────┐
        │  APScheduler (in-process, AsyncIOScheduler, UTC)      │
        │  interval = SYNC_INTERVAL_SECONDS (600s)              │
        └──────────────────────────────────────────────────────┘
```

**Evidence:** `app/main.py` (lifespan, middleware, router mounting);
`app/api/v1/router.py` (six sub-routers); `app/core/database.py`
(`create_async_engine`); `app/workers/scheduler.py` (`AsyncIOScheduler`,
`IntervalTrigger`); `docker-compose.yml` (nginx/api/postgres services).

### 2.2 Layering

The application follows a **repository → service → endpoint** clean
architecture, consistently applied:

| Layer | Path | Responsibility |
|---|---|---|
| Models | `app/models/` | SQLAlchemy 2.0 declarative (`ci`, `history`, `sync`, `base`) |
| Repositories | `app/repositories/` | Data access — `ci`, `sync`, `summary`, `freshness`, `base` |
| Services | `app/services/` | Business logic — `ci_service`, `sync_service`, `seed_service`, `telemetry_sources` |
| Schemas | `app/schemas/` | Pydantic contracts + `serializers.py` |
| API | `app/api/v1/endpoints/` | `cmdb`, `intune`, `solarwinds`, `sync`, `health`, `system` |
| Workers | `app/workers/` | `scheduler.py` |

**A second, parallel implementation exists** at `src/sync/` (`graph_client.py`,
`solarwinds_client.py`, `payload_generator.py`, `cmdb_generator.py`,
`firestore_sync.py`) driven by CLI scripts in `scripts/`. This is the
**legacy file-based pipeline** that writes `data/*.json`. It is not dead code —
`telemetry_sources.py` imports its two API clients — but the aggregation half
(`payload_generator.py`) is now **duplicated** by `summary_repository.py`.

🟡 **CONCERN — Two parallel analytics implementations.** `payload_generator.calculate_metrics()`
and `SummaryRepository.get_intune_summary()` compute the same KPIs by different
means against different stores. They can and do disagree (§7.6). Neither is
marked authoritative in code or documentation.

### 2.3 Cross-dialect design

`app/models/base.py` defines `JSONType = JSON().with_variant(JSONB, "postgresql")`
and `UUIDType = Uuid(as_uuid=True).with_variant(PG_UUID, "postgresql")`.

🟢 **PASS.** Correct SQLAlchemy 2.0 idiom. Enables the SQLite test path without
forking the models.

---

## 3. Actual System Flows

### Flow A — Scheduled ingestion (primary)

```
APScheduler tick (600s)
  ↓  app/workers/scheduler.py :: run_periodic_telemetry_sync()
AsyncSessionLocal() session
  ↓  SyncService.execute_sync_with_lock(source_system="ALL")
pg_advisory_xact_lock(1048576)                    ← transaction-scoped
  ↓  build_sources("ALL", offline=False)
[IntuneSource, SolarWindsSource]
  ↓  asyncio.to_thread(source.fetch())            ← sync client off the loop
GraphClient.fetch_managed_devices()  /  SolarWindsClient.fetch_nodes()
  ↓  normalize_intune_device() / normalize_solarwinds_node()
List[CI dict]
  ↓  SyncService.sync_single_source()  → one SyncRun row per source
ingest_telemetry_batch()
  ↓  compute_state_fingerprint(status:health_tier)
  ↓  get_by_source_key() → INSERT | UPDATE | touch last_sync_time
configuration_items + ci_status_history
  ↓  session.commit()                             ← lock auto-released
```

**Status: ⚪ NOT VERIFIED.** Steps up to `build_sources` are proven by unit tests.
`GraphClient.fetch_managed_devices()` and `SolarWindsClient.fetch_nodes()` have
**never been observed to execute** in this audit. See §8.

### Flow B — Read path (verified)

```
GET /api/v1/intune/summary
  ↓  FreshnessHeadersMiddleware.dispatch()        ← method guard + headers
  ↓  Depends(get_db) → AsyncSession
  ↓  Depends(get_ci_service) → CIService
CIService.get_intune_summary()
  ↓  SummaryRepository.get_intune_summary()
  ↓  4 × SELECT col, COUNT(id) ... GROUP BY col
  ↓  _pct(), _sum_matching(), _storage_metrics()
JSON payload
```

**Status: 🟢 PASS.** Verified end-to-end against live data (§11).

### Flow C — Legacy file pipeline (parallel, unmanaged)

```
scripts/fetch_intune_data.py → src/sync/graph_client.fetch_and_save()
  → data/intune_ops_analytics.json
scripts/generate_dashboard_payload.py → payload_generator.generate()
  → data/intune_summary.json
src/automation/executive_digest.py → data/executive_digest.json
  → nginx serves data/*.json directly to the browser
```

🟡 **CONCERN.** This flow bypasses the database and the API entirely. The
frontend's `services.js` reads `data/intune_summary.json` for Intune and
SolarWinds, calling the API only for CMDB. Two sources of truth reach the same
dashboard.

---

## 4. External Integrations

### 4.1 Microsoft Graph — `src/sync/graph_client.py`

| Aspect | Implementation | Verdict |
|---|---|---|
| Auth | OAuth2 client credentials, `/oauth2/v2.0/token`, scope `.default` | 🟢 |
| Token cache | In-memory, 60s expiry buffer (line 138) | 🟢 |
| Mid-flight 401 | Refreshes token, retries once (lines 214–219) | 🟢 |
| Retry | `Retry(total=3, backoff_factor=0.5, status_forcelist=[429,500,502,503,504])` | 🟢 |
| Pagination | Follows `@odata.nextLink` until exhausted (line 235) | 🟢 |
| Timeout | 30s default, applied to every call | 🟢 |
| Credential absence | Raises `GraphAuthError` with an explicit message | 🟢 |
| Live execution | **Never observed** | ⚪ |

**Assessment: 🟢 PASS (static) / ⚪ NOT VERIFIED (runtime).** This is
well-written client code — the 401-mid-pagination retry in particular is a
detail many implementations miss. But no successful call has been demonstrated.

### 4.2 SolarWinds Orion SWIS v3 — `src/sync/solarwinds_client.py`

| Aspect | Implementation | Verdict |
|---|---|---|
| Auth | HTTP Basic via `session.auth` | 🟡 |
| Read-only guard | `validate_swql_read_only()` — must start `SELECT`, 12 forbidden keywords, comment-obfuscation and stacked-query checks | 🟢 |
| Retry | `Retry(total=3, status_forcelist=[500,502,503,504])` | 🟡 |
| TLS | **Certificate verification disabled** | 🔴 |

🔴 **FAIL — TLS verification is disabled.**
**Evidence:** pytest run, warnings summary:
`InsecureRequestWarning: Unverified HTTPS request is being made to host 'gnoc.coforge.com'`
**Impact:** SWIS credentials and all returned telemetry are exposed to
man-in-the-middle interception on the corporate network. The credentials are
transmitted as HTTP Basic — i.e. base64, not encrypted — so an intercepted
session yields the SolarWinds password directly.
**Note:** this was pre-existing and is **not** auditor-authored.

🟡 **CONCERN — 429 is absent from the SolarWinds retry list**, unlike the Graph
client. If Orion rate-limits, the request fails without retry.

### 4.3 Google Cloud Firestore — `src/sync/firestore_sync.py`

Present in the tree and exported from `src/sync/__init__.py`. No evidence of
invocation from any active code path.

⚪ **NOT VERIFIED.** 🟡 **CONCERN:** the README asserts *"Zero Cloud Footprint
Required: Operates 100% air-gapped on-premise. No company telemetry is leaked
to third-party services."* A Firestore sync client contradicts that claim if it
is ever enabled. Its presence should be justified or the module removed.

---

## 5. Data Flow Validation

### 5.1 Intune device → API

| Stage | Location | Transformation |
|---|---|---|
| Origin | Graph `/deviceManagement/managedDevices` | OData `$select`, `$top=100` |
| Normalise | `normalize_intune_device()` | `complianceState` → `status` + `health_tier` |
| Persist | `ingest_telemetry_batch()` | Upsert keyed `(source_system, source_id)` |
| Aggregate | `SummaryRepository._base_summary()` | `GROUP BY status / health_tier / ci_type / vendor` |
| Serialise | `serializers.orm_to_dict()` | UUID→str, datetime→ISO |

**Mapping fidelity:** `normalize_intune_device()` mirrors `seed_service.py`
lines 206–264 field-for-field. Verified by direct comparison.
🟢 **PASS [SELF-AUTHORED].**

### 5.2 Null and type handling

🟢 **PASS [SELF-AUTHORED].** `_safe_float()` in `sync_service.py` rejects
strings, booleans, negatives, NaN and infinity before any `Float` column write.

**Runtime evidence:** `test_scenario_7_partial_broken_source_data` previously
raised `StatementError: could not convert string to float: 'invalid_string'`
during flush, aborting the transaction. Post-fix it passes. This matters
disproportionately: a flush abort discards the **entire batch**, so one
malformed device would have destroyed an ingestion of 27,412 good ones.

### 5.3 Silent data loss

🟡 **CONCERN — 164 Intune devices report no usable storage.**
**Evidence:** live `/intune/summary` → `storage_sample_size: 27248`,
`total_managed_devices: 27412`. Delta = 164 (0.6%).
These devices are excluded from the storage denominator. This is now *disclosed*
via `storage_coverage_pct: 99.4` — previously it was silent — but the
underlying cause (devices genuinely not reporting, versus a mapping defect) is
**⚪ NOT VERIFIED**.

### 5.4 Timezone handling

🟢 **PASS.** All models use `DateTime(timezone=True)`. `_as_utc()` in
`freshness_repository.py` normalises naive values defensively.

🟡 **CONCERN — one observed naive timestamp.** Live `/intune/summary` returned
`"last_sync_time": "2026-09-06T18:49:33.438502"` — **no offset**, whereas
`/system/freshness` returned `"2026-09-06T18:49:35.647603+00:00"` for the same
event. The `last_sync_time` value originates from SQLite, which does not
preserve tzinfo. On PostgreSQL this should not occur, but **a consumer parsing
`last_sync_time` will assume local time and be wrong by the UTC offset** —
5½ hours in IST. ⚪ NOT VERIFIED on PostgreSQL.

---

## 6. Data Transformation Validation

### 6.1 SolarWinds status mapping — 🟢 PASS [SELF-AUTHORED]

Prior implementation (`sync_service.py`, pre-audit):

```python
"status": "Up" if Status == 1 else ("Warning" if Status == 3 else "Down")
"health_tier": "High" if Status == 1 else "Medium"
```

Independent evaluation against the documented fleet distribution:

| Orion code | Documented count | Old label | New label | New health |
|---|---|---|---|---|
| 1 Up | 1,370 | Up | Up | High |
| 3 Warning | 25 | Warning | Warning | Medium |
| 14 Critical | 35 | **Down** ❌ | Critical | Low |
| 2 Down | 6 | Down | Down | Low |
| 9 Unmanaged | 112 | **Down** ❌ | Unmanaged | Medium |

**Old reported Down = 153. Correct value = 6.** A 2,450% overstatement of
down nodes.

Further, the old `health_tier` expression could emit only `High` or `Medium`,
making the tier `Low` **unreachable** — so the documented "Low/Critical 2.65%
(41 nodes)" was impossible to reproduce from the database. Under the new
mapping, Low = Critical(35) + Down(6) = **41**, matching documentation exactly.

**Independent arithmetic check:** 1,370 + 25 + 35 + 6 + 112 = 1,548 ✅

### 6.2 Vendor normalisation — 🟡 PASS WITH CONCERN

`normalize_vendor()` uses ordered substring matching. Correct for the observed
distribution, but `"hp" in text` (pre-audit form) would match any string
containing those letters. The current implementation uses
`text.startswith("hp")`, which is safer but still not token-aware — a vendor
string beginning "HP" as part of a longer word would mis-bucket.

**Live evidence:** vendor distribution sums to 27,412 with a plausible shape
(Dell 16,383 · HP 8,938 · Lenovo 1,061 · Apple 893 · Other 89 · Microsoft 48).
The presence of a non-zero Microsoft bucket confirms the `include_microsoft`
defect is resolved.

### 6.3 OS classification — 🟡 CONCERN

Live `os_distribution` contains both `"Linux ()"` (2) and `"Linux (ubuntu)"`
(123) as **distinct categories**. `ci_type` is taken verbatim from
`operatingSystem`, so upstream formatting variance fragments the taxonomy.
`"Linux ()"` is a malformed value being presented to users as a category.

**Impact:** low — 125 of 27,412 records (0.46%) — but any Linux total computed
from this map requires the consumer to know both keys exist.

---

## 7. Mathematical & Analytics Validation

Every calculation discovered in the codebase, independently evaluated.

### 7.1 Compliance rate — 🟢 PASS

**Formula:** `round((compliant / total) * 100, 2)` — `summary_repository._pct()`
**Zero-guard:** `if whole <= 0: return 0.0` ✅

| | Value |
|---|---|
| Input | compliant 22,735 · total 27,412 |
| Independent calculation | 22735 ÷ 27412 × 100 = 82.9381...→ **82.94** |
| Code output (live) | **82.94** |
| Result | **PASS** |

**Partition invariant:** 22,735 + 3,774 + 903 = **27,412** ✅ exact.

### 7.2 Health tier percentages — 🟢 PASS

High 82.94 + Medium 3.29 + Low 13.77 = **100.00** ✅
Counts 22,735 + 903 + 3,774 = **27,412** ✅

Note the rounded percentages summing to exactly 100 is fortuitous, not
guaranteed — three independent `round(x, 2)` calls can total 99.99 or 100.01.
🟡 Minor: consumers rendering a pie chart should not assume the parts sum to 100.

### 7.3 Storage utilisation — 🟢 PASS WITH DOCUMENTED SEMANTICS [SELF-AUTHORED]

Two distinct figures are now returned, resolving a mislabelling defect:

```python
fleet_capacity_used_pct        = (Σ total − Σ free) / Σ total × 100
median_device_storage_used_pct = median( (tot−free)/tot × 100 per device )
```

**Independent verification** (synthetic, auditor-run):

| Device | Total | Free | Used % |
|---|---|---|---|
| A | 512 GB | 256 GB | 50.0 |
| B | 256 GB | 64 GB | 75.0 |
| C | 1024 GB | 900 GB | 12.1 |

Capacity-weighted = **31.9%** · Median = **50.0%** — an 18-point divergence.

The prior code returned only the capacity-weighted figure, labelled
`avg_storage_used_pct` — *"Fleet Avg Storage Used"* in the README. It is not an
average. Large disks dominate it, concealing nearly-full small devices.

**Live values:** capacity 36.6% · median 35.4% · coverage 99.4%. The narrow gap
indicates a homogeneous fleet — which is itself a useful finding, and one the
old single figure could not establish.

**Edge cases verified in code:** `tot <= 0` skipped; `free` clamped to
`[0, tot]` guarding sources that report free > total; empty sample returns a
zeroed dict rather than dividing by zero.

### 7.4 SolarWinds health classification — 🟢 PASS

`classify_solarwinds_health()` — status-derived base tier, then resource
override: CPU > 90 or RAM > 90 → Low; CPU ≥ 75 or RAM ≥ 80 → Medium.

Boundary behaviour is coherent (75 and 90 both resolve deterministically).
A pre-existing parallel implementation, `src/sync/solarwinds_client.classify_node_health()`,
applies **the same thresholds with different status handling** — it treats
status 0 as Low, the new one treats Unknown as Medium.

🟡 **CONCERN — duplicated, divergent health logic in two modules.**

### 7.5 Delta fingerprint — 🟢 PASS [SELF-AUTHORED]

**Old:** `sha256(f"{status}:{health}:{cpu}:{ram}:{storage}")`
**New:** `sha256(f"{status}:{health_tier}")`

The old fingerprint included CPU and RAM, which vary on essentially every poll.
Independent estimate of the consequence:

```
1,548 nodes × (1440 min/day ÷ 10 min) = 1,548 × 144 = 222,912 history rows/day
                                                     ≈ 81.4M rows/year
```

in a table with **no partitioning and no retention policy**. The mechanism
intended to *suppress* writes was guaranteeing them. Now history records only
genuine state transitions.

🟡 **Residual concern:** CPU/RAM/latency are no longer captured on unchanged
polls at all. If time-series resource trending is a product requirement, it now
has **no data source**. This is a deliberate trade-off that should be confirmed
against product intent — a separate metrics table was recommended but not built.

### 7.6 Executive digest fleet total — 🔴 FAIL (pre-existing, unfixed)

`src/automation/executive_digest.py` line 51:

```python
"total_managed_fleet_size": i_metrics.get("total_managed_devices", 0)
                          + s_metrics.get("total_server_nodes", 0)
```

= 25,987 + 1,548 = **27,535**

README documents: *Endpoints (25,987), Servers (1,548), Network Infrastructure
(1,420)* = **28,955**.

**Discrepancy: 1,420 — exactly the omitted network-infrastructure term.**
The code and the documentation disagree about the size of the estate.
**Status: confirmed defect, NOT FIXED.**

### 7.7 Stale device count — 🔴 FAIL (pre-existing, unfixed)

`executive_digest.py` line 62:

```python
"stale_inactive_devices_count": len([d for d in intune_data.get("sample_devices", [])
                                     if "stale" in (d.get("complianceState") or "").lower()])
```

Two independent defects:

1. Scans `sample_devices` — capped at **100 records**, not 27,412.
2. `"stale"` is not a member of the Intune `complianceState` enum
   (`compliant`, `noncompliant`, `conflict`, `error`, `inGracePeriod`,
   `unknown`, `notApplicable`). Staleness is a function of `lastSyncDateTime`.

**This KPI returns 0 unconditionally and always has.** Confirmed by inspection;
mathematically unable to return non-zero.

### 7.8 Payload generator invariants — 🟡 PASS WITH CONCERN (pre-existing)

`payload_generator.validate_payload()` asserts six invariants. Two are vacuous:

**Invariant 2** — recomputes the compliance rate with the *identical expression*
that produced it:
```python
expected_rate = round((compliant / total) * 100, 2)
assert abs(rate - expected_rate) < 0.01
```
This tests that Python is deterministic. It cannot fail.

**Invariant 6** — `assert len(samples) <= max(500, total)` where `samples` is
already bounded by `limit ≤ 500` at construction. Unreachable.

**Missing:** no invariant covers `compliance_breakdown`, which is the one map
that may be sourced from upstream `raw_summary` rather than recomputed:
```python
if raw_summary and "compliance_breakdown" in raw_summary:
    compliance_breakdown = dict(raw_summary["compliance_breakdown"])
```
It can therefore silently disagree with `compliant_devices` / `noncompliant_devices`.

### 7.9 Pagination arithmetic — 🟢 PASS

`total_pages = max(1, (total + page_size - 1) // page_size)` — standard ceiling
division. `max(1, …)` correctly yields page 1 for an empty set.
**Live check:** total 28,984 ÷ 25 = 1,159.36 → **1,160** ✅

---

## 8. Database Validation

| Aspect | Evidence | Verdict |
|---|---|---|
| Uniqueness | `UniqueConstraint("source_system", "source_id")` — `models/ci.py` L69 | 🟢 |
| Indexing | 10 indexes incl. composite `(source_system, ci_type, status)` | 🟢 |
| Referential integrity | `ondelete="CASCADE"` + `cascade="all, delete-orphan"` | 🟢 |
| Timestamps | `DateTime(timezone=True)` throughout | 🟢 |
| Duplicate prevention | Upsert keyed on the unique pair — `ingest_telemetry_batch()` | 🟢 |
| Advisory lock | `pg_advisory_xact_lock` — auto-released at COMMIT | 🟢 [SELF-AUTHORED] |
| Migrations | **One** migration for a five-entity schema | 🔴 |
| Retention | None on `ci_status_history` | 🟡 |
| Tombstoning | None — vanished CIs persist indefinitely | 🟡 |

🔴 **FAIL — Migration history is not credible.** `alembic/versions/` contains a
single revision (`0001_initial_schema.py`) for a schema comprising five
entities, ten indexes and documented trigram work. Combined with
`create_db_and_tables()` being invoked in `main.py`'s lifespan — which calls
`Base.metadata.create_all` and bypasses Alembic entirely — the schema is being
**created from model metadata, not migrated**. The first production schema
change has no tested upgrade path.

🟡 **CONCERN — Advisory lock fix is unverified on PostgreSQL.** The
`pg_advisory_xact_lock` path cannot execute under SQLite; the test suite
exercises only the in-memory fallback. The original defect (session-scoped lock
released after commit on a pooled connection, silently leaking and causing all
subsequent syncs to return SKIPPED) is a **PostgreSQL-only failure mode**, and
so is its fix. ⚪ NOT VERIFIED.

🟡 **CONCERN — No tombstoning.** A CI removed from Intune or decommissioned in
Orion is never marked inactive; it simply stops being touched. `last_sync_time`
goes stale but the row still counts toward every total. Fleet size can only grow.

---

## 9. Scheduler / Automation Validation

**Mechanism:** APScheduler `AsyncIOScheduler`, timezone UTC, started in the
FastAPI lifespan — `app/workers/scheduler.py`.

| Property | Value | Verdict |
|---|---|---|
| Frequency | `IntervalTrigger(seconds=600)` | 🟢 |
| Overlap prevention | `max_instances=1` + `coalesce=True` | 🟢 |
| Misfire grace | 60s | 🟡 |
| Startup behaviour | First run at T+600s — **no run at boot** | 🟡 |
| Failure behaviour | Caught and logged; loop continues | 🟢 |
| Retry | **None** — waits a full interval | 🟡 |
| Multi-worker safety | Advisory lock | ⚪ (§8) |
| Persistence | In-memory jobstore — schedule lost on restart | 🟡 |

🟡 **CONCERN — no startup sync.** After a restart the system serves data at
least 10 minutes old before the first ingestion. Combined with the freshness
window of 1,500s, a restart during a stale period prolongs staleness.

🟡 **CONCERN — the scheduler is in-process.** Every uvicorn worker starts its own
`AsyncIOScheduler`. With N workers, N scheduler instances contend for the
advisory lock every 600s. Correct if and only if the lock works (⚪).

🔴 **FAIL — the scheduler has never been observed to complete a live cycle.**
There is no log excerpt, no `sync_runs` row with `status=SUCCESS` and a
non-zero `items_extracted` from a live source, and no operator report of one.
The most recent successful sync in the database predates the rewrite:
`2026-09-06T18:49:35Z` — produced by the **seed script**, not live ingestion.

---

## 10. API / Output Validation

### 10.1 Endpoint inventory

| Method | Path | Verified |
|---|---|---|
| GET | `/healthz` | 🟢 200 |
| GET | `/ready` | 🟡 (§10.3) |
| GET | `/api/v1/system/freshness` | 🟢 live |
| GET | `/api/v1/cmdb/summary` | 🟢 test |
| GET | `/api/v1/cmdb/cis` | 🟢 live |
| GET | `/api/v1/cmdb/cis/{id}` | 🟢 test |
| GET | `/api/v1/cmdb/cis/{id}/history` | ⚪ |
| GET | `/api/v1/cmdb/cis/{id}/relationships` | ⚪ |
| GET | `/api/v1/intune/summary` | 🟢 live |
| GET | `/api/v1/intune/devices` | ⚪ |
| GET | `/api/v1/solarwinds/summary` | 🟢 test |
| GET | `/api/v1/solarwinds/nodes` | ⚪ |
| GET | `/api/v1/sync/runs`, `/runs/latest`, `/runs/{id}` | ⚪ |
| POST | `/api/v1/sync/trigger` | 🔴 (§17) |

### 10.2 Read-only enforcement — 🟢 PASS

`FreshnessHeadersMiddleware` intercepts POST/PUT/DELETE/PATCH on `/api/v1/*`
(excluding `/sync`) and returns 405 with `Allow: GET, HEAD, OPTIONS`.
**Runtime evidence:** `test_read_only_{post,put,patch,delete}_returns_405` — all pass.

🟡 **CONCERN:** the guard fires **before routing**, so `POST /api/v1/does-not-exist`
returns 405 rather than 404. Cosmetic, but misleading during integration work.

### 10.3 `/ready` is not a readiness probe — 🔴 FAIL (pre-existing)

```python
return {"status": "ready", "database": "connected", "migration_head": True, ...}
```

`migration_head` is a **hardcoded literal**. The probe executes `SELECT 1` and
then asserts schema currency it never checked. An orchestrator will route
traffic to a pod running against an outdated schema. A probe that cannot fail on
its stated condition is worse than no probe.

### 10.4 Serialisation — 🟢 PASS [SELF-AUTHORED]

Prior state: `GET /api/v1/cmdb/cis` returned **HTTP 500**:
`PydanticSerializationError: Unable to serialize unknown type: <class 'app.models.ci.ConfigurationItem'>`

This affected the three list endpoints the frontend depends on most. Fixed via
`schemas/serializers.py`, which reads mapped columns through
`sqlalchemy.inspect` — so it remains correct if columns are added — and never
touches relationship attributes, avoiding lazy-load on an async session.

**Runtime evidence:** `test_cmdb_cis_pagination_envelope` now passes; live curl
returns a valid envelope.

### 10.5 Input validation — 🟡 PASS WITH CONCERN

`page_size` is whitelisted to {10, 25, 50, 100} → 422 otherwise.
**Runtime evidence:** `curl "…?page_size=5"` → `{"detail":"page_size must be one of [10, 25, 50, 100]"}` ✅

🟡 **CONCERN — `sort_by` is an unvalidated attribute lookup:**

```python
sort_col = getattr(ConfigurationItem, sort_by or "name", ConfigurationItem.name)
```
— `ci_repository.py` line 217.

This is **not** SQL injection; SQLAlchemy parameterises. But `sort_by` is
user-controlled and `getattr` will resolve **any** class attribute, including
`metadata`, `registry`, `__table__`, or a relationship such as `status_history`.
Passing `?sort_by=metadata` yields `order_by(MetaData)`, which raises inside the
query builder → HTTP 500. `sort_by` should be whitelisted exactly as
`page_size` is.

⚪ **NOT VERIFIED** — no test exercises a malicious `sort_by`; the auditor could
not issue the request.

🟡 **Minor:** `search` is interpolated into an `ilike` pattern
(`f"%{search.strip()}%"`). Parameterised and therefore safe, but `%` and `_` in
user input act as wildcards, so a search for `a_b` matches `axb`.

---

## 11. Source → Processing → Storage → Output Reconciliation

### 11.1 Internal consistency — 🟢 PASS

Live `/api/v1/intune/summary`, all four breakdowns independently summed:

| Breakdown | Sum | Expected | Result |
|---|---|---|---|
| `status_breakdown` (5 keys) | 27,412 | 27,412 | ✅ |
| `health_breakdown` (3 keys) | 27,412 | 27,412 | ✅ |
| `os_distribution` (7 keys) | 27,412 | 27,412 | ✅ |
| `vendor_distribution` (6 keys) | 27,412 | 27,412 | ✅ |

Four independent `GROUP BY` queries over the same filtered set, each
reconciling exactly. **This is strong evidence of aggregation correctness.**

### 11.2 Documentation vs database — 🟡 CONCERN

| Quantity | README | Live database | Delta |
|---|---|---|---|
| Intune devices | 25,987 | **27,412** | **+1,425** |
| Total CIs | 28,955 | **28,984** | +29 |
| Implied non-Intune rows | 1,548 | **1,572** | **+24** |

*(Total CIs 28,984 observed in the pagination envelope; non-Intune derived as
28,984 − 27,412.)*

The README's "100% Verified Invariants" table is **stale by 1,425 endpoint
records**. Documentation asserting verified exactness while diverging from the
live store by 5.5% is actively misleading. The 24-record gap on the SolarWinds
side is unexplained and **⚪ NOT VERIFIED**.

### 11.3 Source → output — ⚪ NOT VERIFIED

Reconciliation from the *external source* (Graph / Orion) through to the API
**could not be performed**: no live extraction has executed. The chain is
verified only from the database onward. What the source actually returns, and
whether normalisation preserves it, remains unproven.

---

## 12. Existing Test Suite Results

**Framework:** pytest 9.1.1 · `asyncio_mode=auto` · plugins: anyio, hypothesis,
asyncio, mock, recording.

```
Total collected:  ~281 tests + 41 subtests
Passed:           278
Failed:           3
Skipped:          0 explicit  (87 'u' markers — see below)
Errors:           0
Duration:         24.14s
```

### Failure analysis

| Test | Root cause | Classification |
|---|---|---|
| `test_css_style_drift_guard` | `frontend/style.css` 72,145 B vs root `style.css` 28,307 B | **TEST FAILURE** — asset drift, frontend scope |
| `test_modular_frontend_files_exist` | `frontend/ops_analytics.html` absent | **TEST FAILURE** — file relocated to `frontend/archive/previews/` |
| `test_utils_module_exports_sanitizer_and_formatters` | Test expects `formatNumber(val)`; code defines `formatNumber(num)` | **TEST FAILURE** — brittle assertion on a parameter name |

All three are **frontend asset issues**, pre-existing, traceable to the
`src/frontend/` → `frontend/` reorganisation. None indicates a backend defect.

🟡 **CONCERN — 87 subtests are silently marked `u`.** The progress line contains
a contiguous run of 87 `u` characters. These are neither counted as passes nor
reported as skips in the summary. A suite reporting "278 passed" while 87
assertions quietly did not execute **overstates coverage**. The `u` marker
should be identified and the outcomes surfaced.

🟡 **CONCERN — the suite makes live external calls.** `test_cmdb_live_solarwinds.py`
triggers `InsecureRequestWarning` against `gnoc.coforge.com`, so the test suite
reaches a production monitoring system over unverified TLS. Tests should not
depend on production availability, and CI runs would leak credentials.

---

## 13. Test Coverage Assessment

| Dimension | Assessment | Evidence |
|---|---|---|
| Functional | 🟢 Good | Endpoints, 405 guards, pagination, probes covered |
| Data transformation | 🟢 Good [SELF-AUTHORED] | Every Orion status asserted distinctly |
| Mathematical | 🟡 Mixed | Live figures reconcile; two payload-generator invariants are tautological (§7.8) |
| Integration | 🔴 Weak | **No test exercises `GraphClient` or `SolarWindsClient`**; all sources faked |
| Database | 🟡 Partial | SQLite only — Postgres-specific paths (advisory lock, JSONB, trigram) untested |
| API | 🟢 Good | Envelope, status codes, validation |
| Error handling | 🟢 Good [SELF-AUTHORED] | Unreachable source, empty extraction, malformed metrics |
| Boundary | 🟡 Partial | Storage clamps tested; `sort_by` and huge pages untested |
| Regression | 🟢 Strong [SELF-AUTHORED] | `test_no_hardcoded_fleet_literals_in_response` and a static source scan make the hardcoding defect unable to silently return |

**Central weakness:** the highest-risk code in the system — live external
extraction — has the weakest coverage. Every source in every test is a fake.

---

## 14. Missing Test Cases

| ID | Area | Scenario | Input | Expected Result | Priority |
|---|---|---|---|---|---|
| T-01 | API | Malicious `sort_by` | `?sort_by=metadata` | 422, not 500 | **Critical** |
| T-02 | API | Relationship `sort_by` | `?sort_by=status_history` | 422 | **Critical** |
| T-03 | DB | Advisory lock on real Postgres | Two concurrent syncs | One runs, one SKIPPED | **Critical** |
| T-04 | DB | Lock released after commit | Sync, then sync again | Second acquires | **Critical** |
| T-05 | Integration | Graph 401 | Expired token | `SourceUnavailableError`, run FAILED | **Critical** |
| T-06 | Integration | Graph pagination | 3-page `@odata.nextLink` | All records, no duplicates | High |
| T-07 | Integration | SWIS mutating SWQL | `DELETE FROM Orion.Nodes` | `SolarWindsSecurityError` | High |
| T-08 | Integration | SWIS timeout | Unreachable host | FAILED, freshness unchanged | High |
| T-09 | Freshness | Clock does not advance on failure | Failed run after success | Age keeps growing | High |
| T-10 | Data | Duplicate `source_id` in one batch | Two identical IDs | One row, no constraint error | High |
| T-11 | Data | CI disappears from source | Present, then absent | Defined behaviour (tombstone?) | High |
| T-12 | Math | Percentages sum under rounding | 3 tiers, thirds | Documented tolerance | Medium |
| T-13 | Math | Storage with zero coverage | All devices report 0 bytes | 0.0 and `sample_size` 0 | Medium |
| T-14 | Math | Storage free > total | free = 2 × total | Clamped, no negative | Medium |
| T-15 | API | Page beyond last | `?page=99999` | Empty items, `has_next` false | Medium |
| T-16 | API | `last_sync_time` carries tz | Any summary | Offset present | Medium |
| T-17 | Scheduler | Overlapping ticks | Sync > 600s | `max_instances=1` honoured | Medium |
| T-18 | Security | Unauthenticated trigger | POST with no creds | 401 once auth exists | **Critical** |
| T-19 | Data | Unicode / control chars in name | Emoji, NUL | Stored and serialised safely | Low |
| T-20 | Perf | Large page on Postgres | `page_size=100`, 28k rows | p50 under agreed budget | Medium |

---

## 15. Failure & Recovery Assessment

| Failure | Caught | Logged | Data protected | Recovers | Next op continues | Verdict |
|---|---|---|---|---|---|---|
| Graph unreachable | ✅ `SourceUnavailableError` | ✅ | ✅ rollback | ✅ next tick | ✅ | 🟢 [SELF-AUTHORED] |
| SWIS unreachable | ✅ | ✅ | ✅ | ✅ | ✅ | 🟢 [SELF-AUTHORED] |
| Zero records returned | ✅ treated as failure | ✅ | ✅ | ✅ | ✅ | 🟢 [SELF-AUTHORED] |
| Malformed metric | ✅ `_safe_float` → NULL | ⚠️ silent | ✅ | ✅ | ✅ | 🟡 |
| DB unavailable at request | ✅ 503 from `/ready` | ✅ | n/a | ✅ | ✅ | 🟢 |
| DB unavailable at sync | ✅ generic handler | ✅ | ✅ | ✅ | ✅ | 🟢 |
| Empty dataset | ✅ `EmptyDatasetError` → 503 | ✅ | n/a | n/a | ✅ | 🟢 [SELF-AUTHORED] |
| Lock held by peer | ✅ SKIPPED | ✅ | ✅ | ✅ | ✅ | ⚪ Postgres |
| Engine creation fails | ⚠️ returns `None` | ⚠️ warning only | ❌ | ❌ | ❌ | 🔴 |

🔴 **FAIL — silent degradation to a null engine.** `database.create_engine_for_url()`
catches `Exception` at three levels and ultimately `return None`. `get_db()`
then yields `None`, and repositories fall back to `_init_offline_cis()` — **200
rows of fabricated data** with invented vendors and a hardcoded
`compliance_rate_pct: 83.08`. A database outage therefore produces a
plausible-looking dashboard rather than an error. `SummaryRepository` correctly
raises `EmptyDatasetError` for a `None` session, but `CIRepository`'s CMDB path
does not.

🟡 **CONCERN — malformed metrics are dropped without a counter.** `_safe_float`
returns `None` silently. If a source begins emitting garbage for every device,
the metric quietly becomes empty fleet-wide with no alert. A rejection count
should be recorded on the `SyncRun`.

---

## 16. Performance Assessment

| Area | Evidence | Verdict |
|---|---|---|
| Concurrency test | Previously p50 1,185 ms (fail); passed on the final run | 🟡 |
| Aggregation queries | 4 × `GROUP BY` per summary, all indexed | 🟢 |
| Pagination | `LIMIT`/`OFFSET`; deep offsets degrade | 🟡 |
| N+1 | None found — no lazy relationship access in serialisation | 🟢 |
| Blocking I/O | Sync clients run via `asyncio.to_thread` | 🟢 [SELF-AUTHORED] |
| History growth | Reduced from ~223k rows/day to transitions only | 🟢 [SELF-AUTHORED] |
| Storage aggregation | **Loads every `attributes` JSON into Python** | 🟡 |
| Unbounded retrieval | `fetch_managed_devices(max_devices=None)` — full fleet in memory | 🟡 |

🟡 **CONCERN — `_storage_metrics()` does not aggregate in the database.**
`SELECT attributes FROM configuration_items WHERE source_system = 'INTUNE'`
pulls **27,412 JSON blobs** into Python on **every** `/intune/summary` request,
then computes a median by sorting 27,248 floats. This is O(n log n) per request
with no caching. It is the single most expensive operation in the read path and
should be a JSONB expression aggregate on PostgreSQL. **[SELF-AUTHORED]** —
disclosed rather than defended.

🟡 **CONCERN — deep pagination.** `OFFSET` on page 1,160 of 1,160 requires the
database to scan and discard 28,975 rows. Keyset pagination is the standard
remedy.

⚪ **NOT VERIFIED** — all timing evidence comes from SQLite on a developer
laptop. No PostgreSQL measurement exists. The one recorded latency failure
(1,185 ms) cannot be attributed with confidence.

---

## 17. Security Assessment

### 🔴 CRITICAL — Credentials exposed and un-rotated

**Evidence:** `.env` (584 bytes) resides in
`Desktop/optimistic-pasteur/`, a **OneDrive-synchronised directory**, and has
been replicated to `ntlgnoida-my.sharepoint.com`. It contains
`AZURE_CLIENT_SECRET`, `SOLARWINDS_PASSWORD` and related values per
`.env.example`. The operator has deferred rotation pending admin availability.

**Impact:** the Azure client secret grants
`DeviceManagementManagedDevices.Read.All` across the tenant — read access to
27,412 corporate endpoint records including user principal names, serial
numbers and device inventory.

**Note:** `.gitignore` correctly excludes `.env` from git; the exposure is via
cloud sync, not version control.

### 🔴 CRITICAL — Unauthenticated write endpoint

`POST /api/v1/sync/trigger` has no authentication. It is explicitly exempted
from the read-only middleware guard (`not path.startswith("/api/v1/sync")`) and
is the sole writable verb in the system. Anyone with network reach can trigger
unbounded ingestion cycles against Graph and Orion — a denial-of-service vector
against **third-party production systems**, not merely this application.

### 🔴 HIGH — TLS verification disabled for SolarWinds

Per §4.2. HTTP Basic credentials over unverified TLS.

### 🔴 HIGH — Hardcoded production secret default

`app/core/config.py` line 29:
```python
SECRET_KEY: str = "itom-secret-key-change-in-production-0987654321"
```
A missing environment variable silently promotes this literal to the live key.
Pydantic Settings would fail loudly if the field were declared without a default.

### 🟡 CONCERN — Weak Docker credential defaults

`docker-compose.yml`: `POSTGRES_PASSWORD:-itom_secure_password`. Activates
whenever the variable is unset — the most likely condition on a hurried deploy.

### 🟡 CONCERN — CORS misconfiguration

`BACKEND_CORS_ORIGINS = ["*"]` with `allow_credentials=True`. Browsers reject
this combination outright, so it is simultaneously **broken and permissive** —
evidence the policy was never exercised against a real origin.

### 🟢 PASS — SWQL injection defence

`app/core/security.py::validate_swql_read_only()` requires a leading `SELECT`,
rejects 12 mutating keywords via word-boundary regex, blocks comment
obfuscation (`--`, `/*`) and inspects stacked statements after `;`.
**Runtime evidence:** `test_swql_validator_security` passes.

### 🟢 PASS — ORM parameterisation

All queries use SQLAlchemy expression constructs. The only raw SQL is
`text(f"SELECT pg_advisory_xact_lock({self.ADVISORY_LOCK_ID})")`, interpolating
an **integer from settings**, not user input.

### 🟡 CONCERN — Stack traces persisted

`SyncErrorLog.stack_trace` stores `traceback.format_exc()`, exposed through
`GET /api/v1/sync/runs/{id}` with `selectinload(error_logs)`. Tracebacks can
contain connection strings and header fragments. This endpoint is unauthenticated.

### ⚪ NOT VERIFIED — Log hygiene

Whether tokens or credentials reach `itom_server.log` (68 KB, committed to the
repository) was not examined.

---

## 18. Confirmed Bugs

| # | Bug | Location | Status |
|---|---|---|---|
| B-01 | Executive digest omits network CIs — under-counts fleet by 1,420 | `src/automation/executive_digest.py:51` | **OPEN** |
| B-02 | `stale_inactive_devices_count` structurally always 0 | `executive_digest.py:62` | **OPEN** |
| B-03 | `/ready` returns hardcoded `migration_head: true` | `endpoints/health.py:35` | **OPEN** |
| B-04 | Two tautological invariants that cannot fail | `payload_generator.py:374,392` | **OPEN** |
| B-05 | `compliance_breakdown` has no reconciliation invariant | `payload_generator.py:179` | **OPEN** |
| B-06 | Null-engine fallback serves 200 fabricated CIs as real | `database.py:55`, `ci_repository.py:21` | **OPEN** |
| B-07 | TLS verification disabled against SolarWinds | `solarwinds_client.py` | **OPEN** |
| B-08 | `sort_by` unvalidated `getattr` → potential 500 | `ci_repository.py:217` | **OPEN** |
| B-09 | Frontend calls `/api/cmdb/*` instead of `/api/v1/cmdb/*` | `js/services.js` | **OPEN** |
| B-10 | Bare `catch {}` silently substitutes stale JSON | `js/services.js` | **OPEN** |
| B-11 | Hardcoded summary literals | `ci_service.py` | **FIXED** [SELF-AUTHORED] |
| B-12 | ORM serialisation 500 on list endpoints | `ci_service.py` | **FIXED** [SELF-AUTHORED] |
| B-13 | Freshness initialised to process boot time | `middleware.py` | **PARTIAL** — new endpoint added; the legacy header path is unchanged |
| B-14 | Sync read local files; no Intune branch | `sync_service.py` | **FIXED, UNVERIFIED** [SELF-AUTHORED] |
| B-15 | Orion statuses collapsed into "Down" | `sync_service.py` | **FIXED** [SELF-AUTHORED] |
| B-16 | Session-scoped advisory lock leaked | `sync_service.py` | **FIXED, UNVERIFIED** [SELF-AUTHORED] |
| B-17 | Fingerprint churn → ~223k history rows/day | `sync_service.py` | **FIXED** [SELF-AUTHORED] |
| B-18 | In-place `attributes` mutation discarded | `sync_service.py` | **FIXED** [SELF-AUTHORED] |
| B-19 | Malformed metric aborted the whole batch | `sync_service.py` | **FIXED** [SELF-AUTHORED] |

**B-13 warrants emphasis.** The `X-Sync-Status` header emitted on every response
still derives from the module-level `_last_sync_time` global in
`middleware.py`, which is initialised to import time and is per-worker. The new
`/system/freshness` endpoint is correct, but **two freshness mechanisms now
coexist and can disagree**. Any consumer trusting the header rather than the
endpoint still receives the original defect.

---

## 19. Risks / Concerns

| # | Risk | Severity |
|---|---|---|
| R-01 | Live ingestion has never executed; correctness is asserted, not demonstrated | **Critical** |
| R-02 | Credentials exposed via cloud sync, rotation deferred | **Critical** |
| R-03 | Unauthenticated trigger can DoS third-party production systems | **Critical** |
| R-04 | PostgreSQL-specific paths untested — advisory lock, JSONB, trigram | High |
| R-05 | Schema created via `create_all`, not migrated; one revision exists | High |
| R-06 | Two parallel analytics implementations can diverge silently | High |
| R-07 | Documentation overstates verification while diverging 5.5% from the data | High |
| R-08 | 87 subtests marked `u` inflate apparent coverage | Medium |
| R-09 | Tests call production SolarWinds over unverified TLS | Medium |
| R-10 | No tombstoning — fleet counts can only grow | Medium |
| R-11 | `_storage_metrics` loads 27k JSON blobs per request | Medium |
| R-12 | No history retention policy | Medium |
| R-13 | Two project directories have diverged | Medium |
| R-14 | 410-file commit mixes audited changes with unrelated work | Medium |

**R-14 detail:** the commit `07fd480` recorded *410 files changed, 30,322
insertions(+), 29,612 deletions(-)* — sweeping in `.agents/` deletions, a
`src/frontend/` → `frontend/` move, a `scratch/` directory, ~60 screenshots and
`app/services/ci_service.py.bak`. The backend changes under audit are
effectively unreviewable within that diff.

---

## 20. NOT VERIFIED Items

Explicitly **not** converted to PASS:

1. **Live Graph extraction** — never executed. No token acquired, no device retrieved.
2. **Live SWIS extraction** — never executed against the rewritten path.
3. **`pg_advisory_xact_lock` behaviour** — SQLite only; Postgres path unexercised.
4. **JSONB / trigram index behaviour** — SQLite has neither.
5. **Multi-worker freshness consistency** — single-process testing only.
6. **PostgreSQL performance** — all timings from SQLite on a laptop.
7. **Alembic upgrade path** — never run; schema comes from `create_all`.
8. **`/cmdb/cis/{id}/history` and `/relationships`** — no runtime call observed.
9. **`/intune/devices`, `/solarwinds/nodes`** — not called directly.
10. **`sort_by` injection behaviour** — theorised from code, not executed.
11. **`.env` contents** — deliberately not read.
12. **Log credential hygiene** — `itom_server.log` not examined.
13. **The operator's working tree** — audited copy is the OneDrive replica; the two are known to differ.
14. **The 24-record SolarWinds gap** (1,572 actual vs 1,548 documented) — unexplained.
15. **The 87 `u`-marked subtests** — marker meaning not established.

---

## 21. Overall Scorecard

| Category | Result | Confidence | Evidence |
|---|---|---|---|
| Architecture | 🟢 PASS | High | Clean layering consistently applied; §2 |
| Functional behavior | 🟡 PASS WITH CONCERN | Medium | Read path verified live; write path unverified; §3 |
| Data correctness | 🟢 PASS | High | Four breakdowns reconcile to 27,412 exactly; §11.1 |
| Mathematics | 🟢 PASS | High | Compliance, health, storage, pagination independently recomputed; §7 |
| Analytics | 🟡 PASS WITH CONCERN | Medium | Core correct; digest KPIs B-01/B-02 defective; §7.6–7.7 |
| Database | 🟡 PASS WITH CONCERN | Medium | Schema sound; migrations not credible; §8 |
| Automation | ⚪ NOT VERIFIED | Low | Scheduler configured; no live cycle observed; §9 |
| APIs/Outputs | 🟢 PASS | High | Live responses valid; 405/422 enforced; §10 |
| Error handling | 🟡 PASS WITH CONCERN | Medium | Strong on sync; null-engine fallback fabricates data; §15 |
| Security | 🔴 FAIL | High | Exposed credentials, open trigger, disabled TLS; §17 |
| Performance | ⚪ NOT VERIFIED | Low | SQLite only; §16 |
| Testing | 🟡 PASS WITH CONCERN | Medium | 278 pass; integration coverage absent; 87 hidden subtests; §12–13 |

---

## 22. FINAL VERDICT

# 🟠 NEEDS FIXES

**Not** a failing system — the analytical core is demonstrably correct, and the
evidence for that is strong: four independent aggregations reconciling to the
exact row count is not a coincidence. The architecture is sound, the read path
is verified against live data, and the mathematics withstand independent
recomputation.

But three conditions each independently block a production verdict:

**1. Security is failing, not merely weak.** Live tenant credentials sit in a
cloud-synchronised folder and have not been rotated. An unauthenticated endpoint
can drive traffic at third-party production systems. TLS verification is
disabled against a host receiving Basic credentials. These are not hardening
items; they are open exposures.

**2. The primary purpose of the system is unproven.** This application exists to
ingest live telemetry from Microsoft Intune and SolarWinds. That code path was
rewritten today and **has never once run against a real API**. Its correctness
rests entirely on unit tests using fabricated sources. The most recent
successful sync in the database — 6 September, four days before this audit —
was produced by a seed script. Until a live extraction succeeds, the system's
central claim is untested.

**3. The audit is not independent.** Nine of the nineteen catalogued bugs were
fixed by the auditor hours before the audit. Those findings require review by a
second engineer. This does not invalidate the analysis, but it does bound how
much assurance it can carry.

**What is genuinely established:** the system no longer lies about its own
state. Before today, a fully broken ingestion pipeline and a healthy one
produced identical dashboard output — a hardcoded 83.08% compliance rate that
would have persisted through a total outage. The freshness endpoint now
correctly reported data 3.7 days stale during live testing. That is the single
most valuable property recovered, because it is the property that makes every
other guarantee auditable.

**Recommended posture:** suitable for frontend integration work against a
non-production deployment. **Not** suitable for production until the Critical
items in §23 are closed and a live extraction has been demonstrated end to end.

---

## 23. Prioritised Fix Plan

*Advisory only — no changes were made during this audit.*

### CRITICAL

**C-1 — Rotate exposed credentials**
- **Problem:** Azure client secret and SolarWinds password replicated to SharePoint via OneDrive sync.
- **Evidence:** `.env` (584 B) in the synced `Desktop/optimistic-pasteur/` tree; §17.
- **Impact:** Tenant-wide read access to 27,412 endpoint records.
- **Solution:** Rotate both in Azure AD and Orion. Relocate `.env` outside any synced path. Audit Azure sign-in logs for use of the old secret.
- **Affected:** `.env`, Azure app registration, Orion service account.
- **Risk of fixing:** Low — brief sync outage.
- **Priority:** Immediate.

**C-2 — Authenticate `POST /api/v1/sync/trigger`**
- **Problem:** The only writable endpoint has no auth and is exempt from the read-only guard.
- **Evidence:** `middleware.py` — `not path.startswith("/api/v1/sync")`; `endpoints/sync.py:56`.
- **Impact:** Unauthenticated parties can drive load against Graph and Orion.
- **Solution:** API key or bearer auth; rate-limit to one concurrent run.
- **Affected:** `endpoints/sync.py`, `core/security.py`, `main.py`.
- **Risk:** Low.

**C-3 — Demonstrate a live extraction end to end**
- **Problem:** The rewritten ingestion path has never executed against a real API.
- **Evidence:** No `sync_runs` row with a live-source SUCCESS; §9, §20.
- **Impact:** The system's core function is unproven.
- **Solution:** After C-1, trigger each source individually. Confirm `items_extracted` > 0, `/system/freshness` flips to FRESH, and row counts reconcile against Graph and Orion totals.
- **Affected:** `telemetry_sources.py`, `sync_service.py`, both clients.
- **Risk:** Medium — first real contact may surface schema mismatches.

**C-4 — Re-enable TLS verification for SolarWinds**
- **Problem:** Certificate validation disabled; Basic credentials over unverified TLS.
- **Evidence:** `InsecureRequestWarning` for `gnoc.coforge.com` in the pytest run.
- **Solution:** Install the internal CA bundle and set `verify=<ca_path>`.
- **Affected:** `src/sync/solarwinds_client.py`.
- **Risk:** Medium — will fail loudly if the certificate chain is wrong, which is the point.

**C-5 — Remove the hardcoded `SECRET_KEY` default**
- **Problem:** A missing env var silently promotes a published literal to the live key.
- **Evidence:** `config.py:29`.
- **Solution:** Declare without a default so Pydantic fails at startup.
- **Affected:** `core/config.py`, deployment configs.
- **Risk:** Low — will refuse to boot without the variable, which is correct.

### HIGH

**H-1 — Eliminate the fabricated-data fallback (B-06)**
`create_engine_for_url()` returning `None` causes `_init_offline_cis()` to serve
200 invented CIs with a hardcoded 83.08% rate. A database outage must produce
503, not a convincing dashboard. Affects `core/database.py`,
`repositories/ci_repository.py`.

**H-2 — Whitelist `sort_by` (B-08)**
`getattr(ConfigurationItem, sort_by, …)` resolves arbitrary class attributes →
500. Apply the same whitelist treatment as `page_size`. Affects
`repositories/ci_repository.py:217`.

**H-3 — Retire the legacy freshness header (B-13)**
Point `middleware.get_last_sync_timestamp()` at `FreshnessRepository`, or remove
the headers so `/system/freshness` is unambiguously authoritative. Two
mechanisms that can disagree is worse than one.

**H-4 — Make `/ready` truthful (B-03)**
Query `alembic_version` against the head revision instead of returning
`migration_head: True`.

**H-5 — Establish a real migration baseline**
Remove `create_db_and_tables()` from the lifespan, generate a migration
reflecting current models, and verify `alembic upgrade head` on an empty
database.

**H-6 — Resolve documentation drift (§11.2)**
The README asserts 25,987 devices and "100% Verified Invariants" against a
database holding 27,412. Regenerate from live data or remove the exactness claim.

**H-7 — Add integration tests for both clients**
Cases T-05 through T-08. Record real responses with the existing
`pytest-recording` plugin so CI need not reach production.

### MEDIUM

**M-1** — Fix `executive_digest` fleet total; add the network-CI term (B-01).
**M-2** — Reimplement `stale_inactive_devices_count` from `lastSyncDateTime` across the full dataset (B-02).
**M-3** — Replace the two tautological invariants; add a `compliance_breakdown` reconciliation (B-04, B-05).
**M-4** — Correct the frontend base path and remove the silent `catch {}` fallback (B-09, B-10).
**M-5** — Push storage aggregation into SQL, or cache the summary. Currently 27k JSON blobs per request.
**M-6** — Add a `ci_status_history` retention or partitioning policy.
**M-7** — Introduce tombstoning for CIs absent from the source.
**M-8** — Investigate the 87 `u`-marked subtests; make their outcome visible.
**M-9** — Narrow CORS to the real origin; remove `allow_credentials` or the wildcard.
**M-10** — Reconcile the two project directories.
**M-11** — Decide the authoritative analytics implementation and retire or clearly subordinate the other.
**M-12** — Add a rejected-metric counter to `SyncRun` so silent `_safe_float` drops become visible.

### LOW

**L-1** — Remove `app/services/ci_service.py.bak` from version control.
**L-2** — Move the 405 guard after routing so unknown paths return 404.
**L-3** — Normalise `"Linux ()"` and similar malformed `operatingSystem` values.
**L-4** — Add 429 to the SolarWinds retry `status_forcelist`.
**L-5** — Trigger a sync at startup rather than waiting a full interval.
**L-6** — Remove `itom_server.log`, `__pycache__/` and `.pytest_cache/` from the repository.
**L-7** — Justify or remove `firestore_sync.py` given the air-gapped claim.
**L-8** — Make `sort_by` and `search` wildcard behaviour explicit in the API contract.

---

## Appendix A — Evidence Index

**Runtime evidence** (produced by the operator, pasted to the auditor):

```
Test:     python -m pytest tests/ -q
Result:   278 passed, 3 failed, 3 warnings, 41 subtests, 24.14s

Test:     curl http://localhost:8000/api/v1/system/freshness
Actual:   overall_status STALE, oldest_age_seconds 322005,
          last_synchronized_at 2026-09-06T18:49:35.647603+00:00
Result:   PASS — correctly identified 3.7-day-old data

Test:     curl http://localhost:8000/api/v1/intune/summary
Actual:   total 27412, compliant 22735, rate 82.94,
          storage 36.6/35.4, coverage 99.4, sample 27248
Result:   PASS — all four breakdowns reconcile to 27,412

Test:     curl "…/api/v1/cmdb/cis?page=1&page_size=5"
Expected: 422
Actual:   {"detail":"page_size must be one of [10, 25, 50, 100]"}
Result:   PASS
```

**Static evidence:** 31 source files read in full or in relevant part across
`app/`, `src/sync/`, `src/automation/`, `alembic/`, `tests/`, plus
`docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env.example`,
`README.md`, `PROJECT.md`.

**Independent computations:** all arithmetic in §7 and §11 was recomputed by the
auditor from the observed values, not taken from application output.

---

*This audit made no modifications to source code, tests, configuration, schema
or API contracts. No destructive external operation was performed.*
