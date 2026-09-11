# ITOM Portal Backend — Complete Guide

**For:** anyone who needs to run, test, or hand over this backend
**Written:** 10 September 2026
**Reading time:** 10 minutes

Plain English. Every command can be copied and pasted.

---

## 1. What this backend does

In one sentence:

> It pulls device data from Microsoft Intune and SolarWinds Orion, stores it in
> a database, and serves it to the dashboard through a web API.

Three jobs:

| Job | What happens |
|---|---|
| **Fetch** | Every 10 minutes it asks Microsoft and SolarWinds "what do you have?" |
| **Store** | It saves the answers, and records anything that changed |
| **Serve** | The dashboard asks the API for numbers and gets them back |

**Current size:** 30,773 devices — 29,191 from Intune, 1,582 from SolarWinds,
across 71 sites.

---

## 2. How the pieces fit together

```
   Microsoft Intune              SolarWinds Orion
   (28,617 devices)              (1,579 nodes)
          |                             |
          +-------------+---------------+
                        |
                  FETCH (every 10 min)
                        |
                        v
              +-------------------+
              |    Database       |   configuration_items
              |                   |   ci_status_history
              +-------------------+   sync_runs
                        |
                        v
                  Web API (port 8000)
                        |
                        v
                    Dashboard
```

### The folders that matter

| Folder | What lives there |
|---|---|
| `app/api/` | The web endpoints — the URLs the dashboard calls |
| `app/services/` | The logic — fetching, deciding what changed |
| `app/repositories/` | The database questions — counting, grouping |
| `app/models/` | The table shapes |
| `src/sync/` | The two API clients — Microsoft and SolarWinds |
| `scripts/` | Tools you run by hand |
| `tests/` | 278 automated checks |

**Rule of thumb:** endpoints call services, services call repositories,
repositories call the database. Data flows one way.

---

## 3. Running it — the four commands you need

### Start the server

```powershell
python -m uvicorn app.main:app --port 8000
```

Leave that window open. To stop it: `Ctrl+C`.

**Safer for now** — only your machine can reach it:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Check it is alive

```powershell
curl.exe http://localhost:8000/healthz
```

### Check the data is recent

```powershell
curl.exe http://localhost:8000/api/v1/system/freshness
```

Look at `overall_status`:

| Value | Meaning | What to do |
|---|---|---|
| `FRESH` | Synced recently | Nothing |
| `STALE` | Too long since a sync | Run a sync (below) |
| `UNKNOWN` | Never synced | Run a sync |

### Fetch fresh data by hand

```powershell
python scripts/run_live_sync.py --source solarwinds
python scripts/run_live_sync.py --source intune
```

SolarWinds takes ~4 seconds. Intune takes ~80 seconds (28,617 devices).

---

## 4. Before you fetch — check the connection

If a sync fails, run this first. It tests the credentials without changing
anything:

```powershell
python scripts/check_live_connectivity.py
```

You want to see:

```
INTUNE       REACHABLE
SOLARWINDS   REACHABLE
```

If one says NOT REACHABLE, the message tells you why — expired password,
blocked network, missing permission.

**Want to see what would be fetched, without saving it?**

```powershell
python scripts/run_live_sync.py --source solarwinds --dry-run
```

---

## 5. The endpoints — what the dashboard calls

Base address: `http://localhost:8000/api/v1`

> ⚠️ It is `/api/v1/`, not `/api/`. Leaving out `v1` gives "Not Found".

### Is the data trustworthy?

```powershell
curl.exe http://localhost:8000/api/v1/system/freshness
```

### The headline numbers

```powershell
curl.exe http://localhost:8000/api/v1/intune/summary
curl.exe http://localhost:8000/api/v1/solarwinds/summary
curl.exe http://localhost:8000/api/v1/cmdb/summary
```

You get totals, compliance rate, health counts, and ready-made breakdowns for
charts (by status, by health, by operating system, by vendor, by location).

### Site-by-site view

```powershell
curl.exe "http://localhost:8000/api/v1/analytics/locations?source_system=SOLARWINDS"
```

Add `&sort_by=risk` to put the worst sites first.

### The device list

```powershell
curl.exe "http://localhost:8000/api/v1/cmdb/cis?page=1&page_size=25"
```

Filters you can add: `search`, `source_system`, `ci_type`, `vendor`,
`health_tier`, `status`, `sort_by`, `sort_order`.

**Page size must be 10, 25, 50 or 100.** Anything else returns an error.

### Sync history

```powershell
curl.exe http://localhost:8000/api/v1/sync/runs/latest
```

### See everything in a browser

Open **http://localhost:8000/docs** — every endpoint listed, clickable, with
a "Try it out" button.

---

## 6. Running the tests

```powershell
python -m pytest tests/ -q
```

**Expect: 278 passed, 3 failed.**

Those 3 failures are frontend file problems, not backend. They were failing
before any of this work started:

| Test | Why it fails |
|---|---|
| `test_css_style_drift_guard` | Two `style.css` files no longer match |
| `test_modular_frontend_files_exist` | `frontend/ops_analytics.html` was moved |
| `test_utils_module_exports...` | Test expects an old function name |

Run one file only:

```powershell
python -m pytest tests/test_step1_summaries.py -v
```

---

## 7. When something goes wrong

### "Not Found" from an endpoint that should exist

The server is running old code. Stop it (`Ctrl+C`) and start it again. Python
loads files once at startup — editing a file does nothing until you restart.

### Freshness says STALE and stays STALE

The background timer is not fetching. Run a sync by hand:

```powershell
python scripts/run_live_sync.py --source intune
```

If the manual sync works but the automatic one does not, the scheduler is the
problem, not the connection.

### A summary endpoint returns 503

That domain has no data in the database. This is deliberate — the endpoint
refuses to invent numbers. Run a sync.

### A sync says FAILED

Also deliberate. The old version could not fail, so it reported success while
doing nothing. Now a real problem shows as a real failure. Check why:

```powershell
python scripts/check_live_connectivity.py
```

### Stop every server on the machine

```powershell
Get-NetTCPConnection -LocalPort 8000,8080 -State Listen -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## 8. How to check the numbers are right

You do not have to trust the API. Every breakdown must add up to the total.

Take `/api/v1/intune/summary`. Add up `status_breakdown`:

```
Compliant 23,776 + Noncompliant 4,414 + Configmanager 920
        + Ingraceperiod 10 + Unknown 68  =  29,188
```

That must equal `total_managed_devices`. Same for `health_breakdown`,
`os_distribution` and `vendor_distribution` — all four sum to the same number.

If one does not, something is wrong and you should say so.

The same applies per site: each site's `status_breakdown` adds up to its own
`total_cis`.

---

## 9. What your frontend engineer needs to know

Four things:

**1. The address is `/api/v1/`.** Their current code calls `/api/cmdb/summary`,
which does not exist. It must be `/api/v1/cmdb/summary`.

**2. Never fall back to a file when a call fails.** There is code that quietly
loads an old JSON file when the API errors. Remove it. Otherwise the dashboard
shows week-old numbers while looking perfectly healthy.

**3. Check freshness before showing numbers.** Call `/system/freshness` once on
page load. If it is not `FRESH`, show a banner.

**4. Two known gaps in the data:**
   - Location analytics cover **SolarWinds only**. Intune devices have no site
     information, so all 29,191 appear as "unlocated".
   - **577 devices no longer exist** in Intune or Orion but are still stored
     here. Percentages are roughly 2% off.

Full detail: `HANDOVER/API_CONTRACT_FOR_FRONTEND.md`.

---

## 10. Known issues — be honest about these

| Issue | Impact | Priority |
|---|---|---|
| Credentials not rotated | The `.env` file was in a cloud-synced folder | **Do first** |
| `/sync/trigger` has no password | Anyone who can reach the port can trigger fetches | High if networked |
| 577 stale devices | Deleted devices still counted | Medium |
| 10 sites split by capitalisation | "BANGALORE" and "Bangalore" counted separately — 482 devices affected | Medium |
| Network roles lost | SolarWinds now stores "Cisco Catalyst 9300" instead of "Access Switch" | Medium |
| Device names have spaces | `" HYD-QE-PAFW2 "` — sorting behaves oddly | Low |
| `location` has no index | Site queries scan all 30,773 rows | Low now, higher later |

---

## 11. The daily routine

**Morning:**

```powershell
python -m uvicorn app.main:app --port 8000
curl.exe http://localhost:8000/api/v1/system/freshness
```

If STALE, run a sync. If FRESH, you are done — the timer handles it.

**After changing any code:**

```powershell
python -m pytest tests/ -q
```

Then restart the server. Always restart. Python will not pick up changes
otherwise.

**Before handing anything to anyone:**

```powershell
python scripts/check_live_connectivity.py
python -m pytest tests/ -q
curl.exe http://localhost:8000/api/v1/system/freshness
```

Three green results means it works.

---

## 12. One thing worth understanding

The most important change made to this system was not a feature. It was this:

**The backend now admits when it does not know.**

It used to return 83.08% compliance no matter what — with an empty database,
with both APIs down, with data from three weeks ago. A completely broken system
and a healthy one produced identical output. There was no way to tell them
apart.

Now:

- No data → **503**, not a fake number
- Old data → **STALE**, not a false "fresh"
- Failed fetch → **FAILED**, not a silent success

So when you see `STALE` or `503`, that is the system working correctly. Do not
treat those as bugs to hide. They are the reason you can trust the numbers when
it says `FRESH`.
