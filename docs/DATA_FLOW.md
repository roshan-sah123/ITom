# ITOM Operations Analytics — End-to-End Telemetry Data Flow

This document details the complete data lifecycle, extraction pipelines, transformation engines, mathematical validation gates, persistence models, and presentation rendering flows across the ITOM platform.

---

## 1. High-Level Telemetry Lifecycle

The telemetry lifecycle moves through five distinct, sequentially validated stages:

```
[ External APIs ] ──▶ [ Ingestion & ETL ] ──▶ [ Invariant Gates ] ──▶ [ Atomic Store ] ──▶ [ Server / Browser ]
 • Graph OData         • OEM Normalizer        • verify_intune        • data/*.json        • start_server.py
 • SWIS v3 SWQL        • Health Classifier     • verify_solarwinds    • exports/*.csv      • ops_analytics.js
```

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                             STAGE 1: UPSTREAM INGESTION                                 │
│  • Microsoft Graph API (OAuth 2.0 Client Credentials -> /deviceManagement/managedDevices│
│  • SolarWinds Orion SWIS API (Basic/NTLM Auth -> /SolarWinds/InformationService/v3/Query│
└───────────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │ Raw JSON Streams
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                       STAGE 2: NORMALIZATION & TRANSFORMATION                           │
│  • Case-insensitive OEM string mapping ("LENOVO" -> "Lenovo", "Dell Inc." -> "Dell")   │
│  • Node Health Tier classification (High: Up & CPU<75% & RAM<80%, Med: Warn, Low: Crit)│
│  • CMDB CI relational normalization & Executive Fleet consolidation                     │
└───────────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │ Transformed In-Memory Objects
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                     STAGE 3: MATHEMATICAL INVARIANT VALIDATION                          │
│  • Intune Invariant Gate: Assert sum(OS) == 25,987 && sum(Compliance) == 25,987         │
│  • SolarWinds Invariant Gate: Assert sum(Status) == 1,548 && sum(Health Tiers) == 1,548 │
│  • CMDB Invariant Gate: Assert sum(CI Types) == 1,548 && Orphaned CIs == 0              │
│  • (Halts with exit code 1 immediately if any equation fails)                           │
└───────────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │ Validated Payload Payloads
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                       STAGE 4: ATOMIC PERSISTENCE & EXPORTS                             │
│  • data/intune_summary.json (Fast payload with KPI metrics & 25 sample rows)            │
│  • data/solarwinds_summary.json (Fast payload with Node KPIs & sample rows)             │
│  • data/cmdb_summary.json & exports/cmdb_network_cis_complete.csv (RFC 4180)            │
│  • data/executive_digest.json (28,955 consolidated fleet digest)                        │
└───────────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │ Local File Read / REST API
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         STAGE 5: HTTP DAEMON & DOM RENDERING                            │
│  • scripts/start_server.py serves static JSON & dynamic REST routes (/api/cmdb/*)       │
│  • services.js asynchronously fetches payloads with fallback caching                    │
│  • Chart.js renders doughnut & bar visualizers with canvas lifecycle management         │
│  • Table rows rendered with strict escapeHtml() XSS sanitization, search & pagination    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Detailed Sequence Flow

```
[Azure / Graph]   [SolarWinds]   [run_sync.py]   [Payload Gen]   [data/*.json]   [HTTP Server]   [Browser DOM]
       │               │               │               │               │               │               │
       │─── 1. Poll ───│               │               │               │               │               │
       │◀── 2. Devices │               │               │               │               │               │
       │               │─── 3. SWQL ──▶│               │               │               │               │
       │               │◀── 4. Nodes ──│               │               │               │               │
       │               │               │── 5. Ingest ─▶│               │               │               │
       │               │               │               │── 6. Norm ───▶│               │               │
       │               │               │               │── 7. Verify ──│               │               │
       │               │               │               │── 8. Write ──▶│               │               │
       │               │               │               │               │◀── 9. Read ───│               │
       │               │               │               │               │               │◀── 10. Fetch ─│
       │               │               │               │               │               │─── 11. JSON ─▶│
       │               │               │               │               │               │       │       │
       │               │               │               │               │               │       ▼       │
       │               │               │               │               │               │ 12. Render UI │
```

---

## 3. Step-by-Step Data Transformation Stages

### Stage 1: API Extraction & Streaming
1. **Microsoft Graph Intune Pipeline (`src/sync/graph_client.py`)**:
   - Acquires OAuth 2.0 bearer token from `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`.
   - Streams `/deviceManagement/managedDevices` with `$select` parameters requesting 12 core fields (`deviceName`, `operatingSystem`, `complianceState`, `manufacturer`, `storage`, etc.).
   - Follows `@odata.nextLink` tokens with automatic exponential backoff retry on HTTP 429/503.
   - Writes raw payload to `data/intune_ops_analytics.json` (25,987 device objects).
2. **SolarWinds SWIS Pipeline (`src/sync/solarwinds_client.py`)**:
   - Queries SWIS v3 endpoint `/SolarWinds/InformationService/v3/Json/Query`.
   - Executes SWQL: `SELECT NodeID, IPAddress, Caption, Status, CPULoad, PercentMemoryUsed, SystemUpTime, MachineType FROM Orion.Nodes`.
   - Writes raw extraction to `data/solarwinds_nodes.json` (1,548 node objects).

### Stage 2: Normalization & Transformation
1. **Hardware OEM Normalization**:
   - Firmware strings are cleaned case-insensitively:
     - `"LENOVO"` / `"Lenovo"` -> `"Lenovo"`
     - `"Dell Inc."` / `"DELL"` -> `"Dell"`
     - `"Hewlett-Packard"` / `"HP"` / `"hp inc."` -> `"HP"`
     - `"Apple"` / `"Apple Inc."` -> `"Apple"`
     - All others -> `"Other"`
2. **SolarWinds Health Classification**:
   - Each node is evaluated across status, CPU, and RAM metrics:
     - **High Health**: `Status == 1 (Up)` AND `CPULoad < 75%` AND `PercentMemoryUsed < 80%`.
     - **Medium Health**: `Status == 2 (Warning)` OR (`CPULoad` between 75–90% OR `PercentMemoryUsed` between 80–90%).
     - **Low/Critical Health**: `Status in (0, 3, 9, Down, Critical)` OR `CPULoad > 90%` OR `PercentMemoryUsed > 90%`.
3. **CMDB Configuration Item Categorization (`src/sync/cmdb_generator.py`)**:
   - Maps raw hardware models into standardized enterprise CI Types: `Access Switch`, `Distribution Switch`, `Core Switch`, `Router`, `Firewall`, and `Server`.
   - Validates that 100% of CIs map to monitored Orion node identifiers with 0 orphans.
4. **Executive Fleet Consolidation (`src/automation/executive_digest.py`)**:
   - Aggregates multi-domain numbers into a unified enterprise summary:
     - Endpoints: 25,987
     - Servers: 1,548
     - Network Core: 1,420
     - Total Fleet: 28,955 assets.

### Stage 3: Mathematical Invariant Gates
Before saving summary artifacts, validation checks run:
* **Intune 6-Point Gate (`tests/verify_intune_data.py`)**:
  - $\sum \text{OS Counts} = 25,334 + 602 + 24 + 2 + 1 + 24 = 25,987$
  - $\sum \text{Compliance States} = 21,589 + 3,422 + 935 + 31 + 10 = 25,987$
  - $\sum \text{Manufacturers} = 15,716 + 8,610 + 959 + 604 + 98 = 25,987$
  - $\text{Compliance Rate} = (21589 / 25987) \times 100 = 83.08\%$
  - $\text{Storage Utilization} = (3733536.2 / 9995826.5) \times 100 = 37.4\%$
* **SolarWinds Invariant Gate (`tests/verify_solarwinds_data.py`)**:
  - $\sum \text{Health Tiers} = 1,357 + 150 + 41 = 1,548$
  - $\sum \text{Status Breakdown} = 1,370 + 25 + 35 + 6 + 112 = 1,548$

### Stage 4: Atomic Persistence & RFC 4180 Exports
- Atomic file write: JSON payloads are written to temporary files and renamed atomically to prevent partial reads during concurrent HTTP requests.
- RFC 4180 CSV generation: `exports/cmdb_network_cis_complete.csv`, `exports/intune_devices_complete.csv`, and `exports/solarwinds_nodes_complete.csv` are generated with proper double-quote escaping and headers.

### Stage 5: Web Server Daemon & REST Routing
- `scripts/start_server.py` runs a multi-threaded HTTP daemon on port `8080`.
- Routes:
  - Static files: `index.html`, `ops_analytics.html`, `data/*.json`, `exports/*.csv`, `js/*.js`, `style.css`.
  - Dynamic REST API:
    - `/api/cmdb/summary` -> JSON summary.
    - `/api/cmdb/items?type=...` -> Filtered items.
    - `/api/cmdb/servers` -> Server CIs.
    - `/api/cmdb/network-devices` -> Network CIs.
    - `/api/cmdb/health` -> Health status.
- Anti-caching headers (`Cache-Control: no-cache, no-store`, `Pragma: no-cache`) are automatically attached to prevent stale dashboard views.

### Stage 6: Browser Ingestion & Zero-Build DOM Painting
1. **Fetch & Parsing**:
   - `services.js` fetches `/data/intune_summary.json` and `/data/solarwinds_summary.json`.
2. **Chart.js Initialization**:
   - Doughnut and bar charts are created using design system tokens (`#0B0B0B`, `#F97316`, `#10B981`, `#F59E0B`, `#EF4444`).
   - Old Chart instances are safely destroyed via `destroyChartSafe()` prior to re-rendering.
3. **DOM Table Rendering**:
   - All cell values pass through `escapeHtml()` in `utils.js` before string concatenation.
   - Dynamic search filters table rows with a 200ms debounce.
   - Pagination renders `10`, `25`, `50`, or `100` rows per page with active page buttons.

---

## 4. Resilience & Error Handling Flow

| Failure Point | System Reaction | Recovery Action |
| :--- | :--- | :--- |
| **Graph API 401 Unauthorized** | Token expired during paginated stream. | Automatically requests fresh OAuth token and retries current page. |
| **Graph API 429 Rate Limit** | Microsoft Graph throttling triggered. | Inspects `Retry-After` header and performs jittered exponential backoff. |
| **SolarWinds Unreachable** | SWIS endpoint down or VPN disconnected. | Logs error and gracefully uses cached snapshot `data/solarwinds_nodes.json`. |
| **Invariant Gate Failure** | Ingested data fails mathematical checks. | Aborts sync with exit code 1; old verified `summary.json` files remain intact. |
| **Browser Network Disconnect** | Client loses connection to local server. | `services.js` catches fetch error and displays friendly toast notification without breaking UI layout. |
