# ITOM Operations Analytics & Telemetry Platform — System Architecture

## 1. Executive Summary & Architecture Overview

The IT Operations Management (ITOM) Operations Analytics platform provides centralized, real-time observability across enterprise endpoints, server infrastructure, network devices, and Configuration Management Database (CMDB) Configuration Items (CIs).

The platform adheres to **Clean Architecture** and **Zero-Build** principles:
- **Presentation Layer**: Pure vanilla HTML5/CSS3/ES6+ and Universal Module Definition (UMD) helpers that run directly in any standard browser without Node.js transpilation or bundling.
- **Service & Ingestion Layer**: Resilient Python connectors for Microsoft Graph Intune API and SolarWinds Orion SWIS API v3, mathematical normalization engines, and a multi-threaded server supervisor (`scripts/start_server.py`) with integrated REST routing and background sync daemon.
- **Persistence & Storage Layer**: Optimized JSON snapshots, RFC 4180 CSV exports, and optional Cloud Firestore integration.
- **Mathematical Invariant Gates**: Hard validation enforcing strict reconciliation across all domains before any payload is rendered or published.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            1. PRESENTATION TIER                             │
│                                                                             │
│   ┌───────────────────────────────┐     ┌───────────────────────────────┐   │
│   │     ITOM Portal Launcher      │     │    OPS Analytics Dashboard    │   │
│   │    (index.html / app.js)      │────▶│ (ops_analytics.html / .js)   │   │
│   │  • System-Wide Search (/)     │     │  • 5 Interactive Tab Views    │   │
│   │  • Domain Drilldown Modal     │     │  • Responsive Chart.js Canvas │   │
│   │  • Deep Link Tab Routing      │     │  • Debounced Table Search     │   │
│   │  • Notification System        │     │  • RFC 4180 CSV Data Export   │   │
│   └──────────────┬────────────────┘     └──────────────┬────────────────┘   │
│                  │                                     │                    │
│                  └──────────────────┬──────────────────┘                    │
│                                     ▼                                       │
│          ┌──────────────────────────────────────────────────────┐           │
│          │ UMD Modular Helpers (constants.js, utils.js, services)│          │
│          │ • Theme tokens & Invariants  • escapeHtml() XSS Guard│           │
│          │ • Resilient HTTP Fetchers    • CSV Generation Engine │           │
│          └──────────────────────────────────────────────────────┘           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP GET / REST Routes
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       2. SERVICE & INGESTION TIER                           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │        Multi-Threaded Server Supervisor (scripts/start_server.py)    │   │
│   │  • Static File Server (Port 8080)   • REST Router (/api/cmdb/*)     │   │
│   │  • 10-Minute Auto-Sync Daemon       • Read-Only Mutation Block (405)│   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                      │
│                ┌─────────────────────┴─────────────────────┐                │
│                ▼                                           ▼                │
│   ┌─────────────────────────┐                 ┌─────────────────────────┐   │
│   │  Graph API Client       │                 │  SolarWinds SWIS Client │   │
│   │(src/sync/graph_client)  │                 │(src/sync/solarwinds_cli)│   │
│   │• Azure AD OAuth 2.0     │                 │• SWIS v3 REST & SWQL    │   │
│   │• Paginated Device Stream│                 │• Health Tier Classifier │   │
│   └────────────┬────────────┘                 └────────────┬────────────┘   │
│                │                                           │                │
│                ▼                                           ▼                │
│   ┌─────────────────────────┐                 ┌─────────────────────────┐   │
│   │  Payload Generator      │                 │  CMDB & Digest Engine   │   │
│   │(src/sync/payload_gen)   │                 │(cmdb_generator, digest) │   │
│   │• Case-Insensitive OEM   │                 │• CI Type Categorization │   │
│   │• Invariant Math Gate    │                 │• Fleet Digest Consol.   │   │
│   └────────────┬────────────┘                 └────────────┬────────────┘   │
└────────────────┼───────────────────────────────────────────┼────────────────┘
                 │                                           │
                 ▼                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       3. PERSISTENCE & EXPORT TIER                          │
│                                                                             │
│   ┌─────────────────────────┐  ┌───────────────────────┐  ┌─────────────┐   │
│   │    Raw JSON Datasets    │  │  Summary Fast Payloads │  │  CSV Exports│   │
│   │ • intune_ops_analytics  │  │ • intune_summary.json │  │ • intune    │   │
│   │ • solarwinds_nodes      │  │ • solarwinds_summary  │  │ • solarwinds│   │
│   │                         │  │ • cmdb_summary.json   │  │ • cmdb      │   │
│   │                         │  │ • executive_digest    │  │             │   │
│   └─────────────────────────┘  └───────────────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Multi-Domain Telemetry Scope & Metrics

The platform reconciles metrics across four authoritative operational domains:

### 2.1 Microsoft Intune Managed Endpoints (25,987 Devices)
* **Total Managed Endpoints**: 25,987
* **Operating System Breakdown**:
  * Windows: 25,334 (97.49%)
  * macOS: 602 (2.32%)
  * Linux: 24 (0.09%)
  * Unspecified: 24 (0.09%)
  * iOS: 2 (0.01%)
  * Android: 1 (0.004%)
* **Compliance Policy Breakdown**:
  * Compliant: 21,589 (83.08%)
  * Non-Compliant: 3,422 (13.17%)
  * ConfigManager Managed: 935 (3.60%)
  * Unknown: 31 (0.12%)
  * In Grace Period: 10 (0.04%)
* **Hardware OEM Normalization**:
  * Dell: 15,716 (60.48%)
  * HP: 8,610 (33.13%)
  * Lenovo: 959 (3.69%)
  * Apple: 604 (2.32%)
  * Other: 98 (0.38%)
* **Fleet Storage Utilization**:
  * Average Storage Used: **37.4%** across 25,937 valid storage-reporting devices (~9,761.55 TB total fleet capacity).

### 2.2 SolarWinds Orion Server Infrastructure (1,548 Nodes)
* **Total Monitored Nodes**: 1,548
* **Health Tiers (Multi-Metric Evaluation)**:
  * **High Health** (`Up` AND `CPU < 75%` AND `RAM < 80%`): 1,357 nodes (87.66%)
  * **Medium Health** (`Warning` OR `CPU/RAM 75–90%`): 150 nodes (9.69%)
  * **Low/Critical Health** (`Down`/`Critical` OR `CPU/RAM > 90%`): 41 nodes (2.65%)
* **Node Operational Status**:
  * Up: 1,370 (88.50%)
  * Warning: 25 (1.61%)
  * Critical: 35 (2.26%)
  * Down: 6 (0.39%)
  * Unmanaged / Unknown: 112 (7.23%)
* **Fleet Performance Invariants**:
  * Average CPU Load: **16.2%**
  * Average Memory Utilization: **22.6%**
  * Average Network Latency: **42.5 ms**

### 2.3 CMDB Network Configuration Items (1,548 CIs)
* **Total Configuration Items**: 1,548
* **CI Type Distribution**:
  * Access Switches: 612
  * Distribution Switches: 340
  * Core Switches: 210
  * Firewalls: 200
  * Routers: 186
* **Relational Integrity**: 100% mapped to monitored nodes with **0** orphaned records.

### 2.4 Executive Fleet Digest (28,955 Monitored Assets)
* **Total Monitored Fleet**: 28,955 assets (25,987 Intune + 1,548 SolarWinds + 1,420 Network Core).
* **Consolidated Operational Health**: 92.4% fleet health index.

---

## 3. Tier Breakdown & Detailed Components

### 3.1 Presentation Tier (`src/frontend/` & Served Root)
1. **Zero-Build Architecture**: The presentation tier requires no bundlers, compilation, or npm install commands. Assets are pure HTML5, CSS3, and modern ES6+ JavaScript.
2. **Modular Helper Architecture**:
   - `constants.js`: Holds immutable design tokens (`THEME`), chart color palettes (`CHART_PALETTES`), invariant numbers (`INVARIANTS`), tab definitions (`VALID_TABS`), and storage keys (`STORAGE`).
   - `utils.js`: Core utility functions including DOM XSS sanitizer (`escapeHtml()`), input debouncer (`debounce()`), and localized formatters (`formatNumber()`, `formatBytes()`, `bytesToGB()`, `formatDate()`).
   - `services.js`: Resilient HTTP client (`fetchJson()`), data loaders (`loadIntuneTelemetry()`, `loadSolarWindsTelemetry()`, `loadCmdbTelemetry()`, `loadExecutiveDigest()`), and RFC 4180 compliant CSV export engine (`exportToCsv()`).
3. **Enterprise Launcher (`index.html` & `app.js`)**:
   - Universal search indexing with keyboard shortcut (`/` to search, `Esc` to clear).
   - Domain drilldown modal for VP-level executive inspection.
   - Deep-linking bridge to dashboard tabs (`#overview`, `#intune`, `#solarwinds`, `#cmdb`, `#dex`).
4. **Operations Analytics Dashboard (`ops_analytics.html` & `ops_analytics.js`)**:
   - Dynamic tab switching with tab-aware header telemetry badges.
   - Chart.js visualizers with automatic memory destruction guards (`destroyChartSafe()`) preventing canvas memory leaks.
   - Debounced multi-field searching, column sorting, pagination controls (`[10, 25, 50, 100]`), and instant CSV dataset download.

### 3.2 Service & Ingestion Tier (`src/sync/`, `src/automation/`, `scripts/`)
1. **`scripts/start_server.py`**:
   - Multi-threaded HTTP server based on `socketserver.ThreadingMixIn` and `HTTPServer`.
   - Socket reuse configuration (`SO_REUSEADDR` / `SO_REUSEPORT`) for rapid restarts.
   - Built-in background daemon thread (`run_sync_daemon()`) executing `scripts/run_sync.py` every 10 minutes.
   - Read-only REST API endpoints:
     - `GET /api/cmdb/summary` -> Returns full CMDB summary.
     - `GET /api/cmdb/items?type=&status=&vendor=` -> Returns filtered CI items.
     - `GET /api/cmdb/servers` -> Returns server CI subset.
     - `GET /api/cmdb/network-devices` -> Returns network hardware CI subset.
     - `GET /api/cmdb/health` -> Returns system health and connectivity status.
   - Rejects mutating requests (`POST`, `PUT`, `DELETE`, `PATCH`) with HTTP 405 Method Not Allowed.
2. **`src/sync/graph_client.py`**:
   - Azure AD / Entra ID OAuth 2.0 Client Credentials Grant.
   - Automatic bearer token caching and proactive renewal (60s buffer).
   - Jittered exponential backoff for HTTP 429 and 5xx responses.
   - Paginated OData streaming for 25,987+ devices.
3. **`src/sync/solarwinds_client.py`**:
   - SolarWinds Information Service (SWIS) v3 REST client.
   - Executes SWQL queries against `Orion.Nodes` and calculates health tiers based on Status, CPU, and RAM thresholds.
4. **`src/sync/payload_generator.py` & `src/sync/cmdb_generator.py`**:
   - Case-insensitive vendor normalization.
   - Enforces mathematical invariant equations before writing output payloads.
5. **`src/automation/executive_digest.py`**:
   - Aggregates multi-domain metrics into a single consolidated executive digest payload (`data/executive_digest.json`).

### 3.3 Storage & Persistence Tier (`data/` & `exports/`)
1. **Raw Telemetry Store**:
   - `data/intune_ops_analytics.json` (25,987 raw records).
   - `data/solarwinds_nodes.json` (1,548 raw nodes).
2. **Precomputed Fast Summary Payloads**:
   - `data/intune_summary.json` (Intune metrics & sample table rows).
   - `data/solarwinds_summary.json` (SolarWinds metrics & sample node rows).
   - `data/cmdb_summary.json` (CMDB summary & CI rows).
   - `data/executive_digest.json` (Fleetwide summary).
3. **RFC 4180 CSV Export Files**:
   - `exports/intune_devices_complete.csv`
   - `exports/solarwinds_nodes_complete.csv`
   - `exports/cmdb_network_cis_complete.csv`

---

## 4. Mathematical Invariants & Verification Gates

The pipeline enforces hard mathematical invariant checks. Any discrepancy raises an `AssertionError` and terminates the sync pipeline:

| Invariant Gate | Verified Constraint | Mathematical Formula | Authoritative Value |
| :--- | :--- | :--- | :--- |
| **Intune Population** | $\sum \text{OS Breakdown} = \text{Total Devices}$ | $25334 + 602 + 24 + 2 + 1 + 24$ | **25,987** |
| **Intune Compliance** | $\sum \text{Compliance States} = \text{Total Devices}$ | $21589 + 3422 + 935 + 31 + 10$ | **25,987** |
| **Intune OEM Closure** | $\sum \text{Manufacturers} = \text{Total Devices}$ | $15716 + 8610 + 959 + 604 + 98$ | **25,987** |
| **Intune Compliance Rate**| $\text{Rate} = (\text{Compliant} / \text{Total}) \times 100$ | $(21589 / 25987) \times 100$ | **83.08%** |
| **Intune Storage Ratio** | $\text{Used} = (\text{Used GB} / \text{Total GB}) \times 100$ | $(3733536.2 / 9995826.5) \times 100$ | **37.4%** |
| **SolarWinds Population**| $\sum \text{Status Counts} = \text{Total Nodes}$ | $1370 + 25 + 35 + 6 + 112$ | **1,548** |
| **SolarWinds Health Closure**| $\sum \text{Health Tiers} = \text{Total Nodes}$ | $1357 + 150 + 41$ | **1,548** |
| **CMDB CI Closure** | $\sum \text{CI Types} = \text{Total CIs}$ | $612 + 340 + 210 + 200 + 186$ | **1,548** |

---

## 5. Security & IT Audit Controls

1. **Zero Hardcoded Secrets**:
   - All tenant credentials, client secrets, and passwords are exclusively read from `.env` via `os.getenv()`.
   - `.gitignore` and `.dockerignore` strictly prevent `.env`, logs, and temporary caches from entering Git commits or container images.
2. **DOM XSS Sanitization**:
   - All dynamic text interpolated into DOM innerHTML passes through `escapeHtml()`, neutralizing standard tags, event handlers, attribute breakouts, and javascript URI schemes.
3. **Strict Read-Only REST API**:
   - The embedded web server permits only HTTP `GET` requests for `/api/cmdb/*`. All mutating verbs (`POST`, `PUT`, `DELETE`, `PATCH`) return `405 Method Not Allowed`.
4. **Air-Gapped On-Premise Execution**:
   - Operates completely within the local network or internal VPN without transmitting corporate telemetry to external cloud endpoints.
