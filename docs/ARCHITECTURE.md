# ITOM OPS Analytics & Microsoft Intune Integration — System Architecture

## 1. Executive Summary
The IT Operations Management (ITOM) Operations Analytics module provides centralized, real-time observability across enterprise endpoint devices, network infrastructure, servers, and Digital Employee Experience (DEX) metrics. This document describes the modular 3-tier architecture, data ingestion pipelines, aggregation engine, security model, and synchronization mechanisms.

---

## 2. Architectural Overview

The system is structured as a decoupled, 3-tier architecture adhering to Clean Architecture principles:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PRESENTATION TIER                                │
│                                                                             │
│   ┌───────────────────────────────┐     ┌───────────────────────────────┐   │
│   │     ITOM Portal Launcher      │     │    OPS Analytics Dashboard    │   │
│   │    (index.html / app.js)      │────▶│ (ops_analytics.html / .js)   │   │
│   │  • Search & Quick Launch (/)  │     │  • 5 Interactive Tab Views    │   │
│   │  • Deep Link Tab Routing      │     │  • Chart.js Visualizations    │   │
│   │  • Notification Center        │     │  • Live Table & CSV Export    │   │
│   └───────────────────────────────┘     └───────────────────────────────┘   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP Fetch / Async Streams
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA & ETL TIER                                  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Automated Sync Orchestration                     │   │
│   │                        (scripts/run_sync.py)                        │   │
│   └──────────────────┬───────────────────────────────┬──────────────────┘   │
│                      │                               │                      │
│                      ▼                               ▼                      │
│   ┌─────────────────────────────────────┐ ┌─────────────────────────────┐   │
│   │          Graph API Client           │ │      Payload Generator      │   │
│   │     (src/sync/graph_client.py)      │ │(src/sync/payload_generator) │   │
│   │ • Azure AD OAuth 2.0 Client Creds   │ │ • Case-Insensitive OEM Norm │   │
│   │ • Resilient Exponential Retries     │ │ • Compliance Rate Invariant │   │
│   │ • Paginated Device Streaming        │ │ • Storage Aggregation       │   │
│   └──────────────────┬──────────────────┘ └──────────────┬──────────────┘   │
│                      │                                   │                  │
└──────────────────────┼───────────────────────────────────┼──────────────────┘
                       │                                   │
                       ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STORAGE & PERSISTENCE TIER                          │
│                                                                             │
│   ┌─────────────────────────┐  ┌───────────────────────┐  ┌─────────────┐   │
│   │ intune_ops_analytics    │  │  intune_summary.json  │  │  Firestore  │   │
│   │   (25,987 Raw JSON)     │  │  (Optimized Payload)  │  │ (Cloud Sync)│   │
│   └─────────────────────────┘  └───────────────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Tier Breakdown & Clean Architecture

### 3.1 Presentation Tier (`src/frontend/` & Root Entrypoints)
- **`index.html` & `app.js`**: Enterprise launcher providing system-wide navigation, fast search indexing, keyboard accessibility (`/` focus, `Esc` clear), deep-link routing bridges to dashboard tabs (`#overview`, `#intune`, `#solarwinds`, `#network`, `#dex`), and interactive notifications.
- **`ops_analytics.html` & `ops_analytics.js`**: Multi-domain dashboard featuring:
  - **Overview**: Executive consolidated health pane.
  - **Microsoft Intune (Live)**: 25,987 endpoint telemetry, live KPI cards, OS distribution doughnut, compliance bar charts, manufacturer OEM distribution, real-time searchable device table, and RFC 4180 CSV dataset export.
  - **SolarWinds (Pending)**: Orion health monitoring bridge (`orion-swis.internal.corp:17774`).
  - **Network & CMDB**: Building-wise network topologies and CMDB asset linkage.
  - **DEX Metrics**: Digital Employee Experience ratings and endpoint resource utilization.
- **`style.css`**: Design system tokens (`#0B0B0B` dark canvas, `#F97316` brand accent, `#22C55E` success indicators, `#EF4444` danger alerts).
- **Dual-Directory Alignment**: Files are maintained under `src/frontend/` for modular separation and at root for static hosting environments (Firebase Hosting / CDN distribution).

### 3.2 Ingestion & ETL Tier (`src/sync/` & `scripts/`)
- **`src/sync/graph_client.py`**:
  - Encapsulates authentication against Azure AD / Microsoft Entra ID via OAuth 2.0 Client Credentials Grant.
  - Implements proactive token caching with automatic expiry detection (60s buffer).
  - Handles transient network anomalies, 429 Rate Limits, and 5xx errors via exponential backoff retry strategies with jitter.
  - Streams paginated OData responses (`@odata.nextLink`) from `/deviceManagement/managedDevices`.
- **`src/sync/payload_generator.py`**:
  - Implements the mathematical aggregation engine over the 25,987 device dataset.
  - Normalizes vendor strings case-insensitively (`"LENOVO"` -> `"Lenovo"`, `"Dell Inc."` -> `"Dell"`, `"Hewlett-Packard"` -> `"HP"`, `"Apple"` -> `"Apple"`, others -> `"Other"`).
  - Calculates fleet compliance rate with 100% mathematical precision:
    $$\text{Compliance Rate} = \frac{\text{Compliant Devices}}{\text{Total Managed Devices}} \times 100 = \frac{21589}{25987} \times 100 \approx 83.08\%$$
  - Aggregates disk utilization across valid storage-reporting endpoints:
    $$\text{Average Storage Used} = \frac{\text{Total Storage GB} - \text{Free Storage GB}}{\text{Total Storage GB}} \times 100 \approx 37.4\%$$
  - Formats sample device records for sub-10ms browser rendering.
  - Executes assertion gates verifying that sums of all subsets equal the total managed population.
- **`src/sync/firestore_sync.py`**:
  - Connects to Google Cloud Firestore / Firebase Firestore.
  - Provides dual-mode execution (live cloud connection or offline fallback cache).
  - Commits summary metrics and batch device records using atomic Firestore batch operations (chunks of up to 500 documents).

### 3.3 Storage Tier (`data/`)
- **`data/intune_ops_analytics.json`**: Authoritative raw snapshot containing 25,987 device records extracted from Microsoft Intune.
- **`data/intune_summary.json`**: Ultra-fast precomputed JSON payload loaded asynchronously by client browsers to guarantee instantaneous dashboard startup without expensive server-side compute.

---

## 4. Telemetry Data Flow

The following sequence illustrates the automated ingestion, transformation, and presentation lifecycle:

```
[Azure AD / Entra ID]       [MS Graph API]        [Sync Pipeline]        [Persistence]         [Client Browser]
        │                         │                      │                      │                     │
        │─── 1. Client Creds ────▶│                      │                      │                     │
        │◀── 2. Bearer Token ─────│                      │                      │                     │
        │                         │                      │                      │                     │
        │                         │◀── 3. GET /devices ──│                      │                     │
        │                         │─── 4. Page 1..N ────▶│                      │                     │
        │                         │                      │                      │                     │
        │                         │                      │── 5. Normalize OEM ─▶│                     │
        │                         │                      │── 6. Invariant Gate ─│                     │
        │                         │                      │                      │                     │
        │                         │                      │── 7. Write Summary ─▶│ (intune_summary)    │
        │                         │                      │── 8. Batch Sync ────▶│ (Firestore)         │
        │                         │                      │                      │                     │
        │                         │                      │                      │◀── 9. Fetch Payload │
        │                         │                      │                      │─── 10. JSON Stream ─▶
        │                         │                      │                      │                     │
        │                         │                      │                      │    [Render Charts & │
        │                         │                      │                      │     Interactive UI] │
```

---

## 5. Mathematical Invariants & Verification Guarantees

The ingestion and summary pipeline enforces strict invariant equations. Any violation raises an immediate assertion error and halts deployment:

1. **Total Population Invariant**:
   $$\sum \text{Compliance States} = \text{Compliant} (21,589) + \text{Non-Compliant} (3,422) + \text{Other} (976) = 25,987$$
2. **Operating System Invariant**:
   $$\sum \text{OS Counts} = \text{Windows} (25,334) + \text{macOS} (602) + \text{Linux} (24) + \text{iOS} (2) + \text{Android} (1) + \text{Unspecified} (24) = 25,987$$
3. **Manufacturer Invariant**:
   $$\sum \text{Manufacturers} = \text{Dell} (15,716) + \text{HP} (8,610) + \text{Lenovo} (959) + \text{Apple} (604) + \text{Other} (98) = 25,987$$
4. **Compliance Rate Invariant**:
   $$\text{Rate} = \text{round}\left(\frac{21589}{25987} \times 100, 2\right) = 83.08\%$$
5. **Storage Utilization Invariant**:
   $$\text{Storage Used} = \text{round}\left(\frac{9,995,826.50 - 6,262,290.30}{9,995,826.50} \times 100, 1\right) = 37.4\%$$

---

## 6. Resilience & Error Handling

- **Token Refresh**: Automatic in-flight token renewal upon receiving HTTP 401 Unauthorized during long-running paginated queries.
- **Exponential Backoff**: Jittered exponential delay algorithm on HTTP 429 (Rate Limit Exceeded) and 503 (Service Unavailable).
- **Graceful UI Fallbacks**: When API endpoints or local summary files are temporarily unreachable, frontend error states inform operators without crashing DOM events.
- **Offline Mocking**: `FirestoreSyncService` and `GraphClient` operate deterministically in isolated unit testing and air-gapped staging environments.

---

## 7. Security & Compliance

- **Zero Hardcoded Secrets**: Azure AD tenant credentials, client secrets, and Firebase keys are read exclusively from environment variables or secure Secret Managers.
- **Principle of Least Privilege**: Ingestion requires only read-only Graph application permissions (`DeviceManagementManagedDevices.Read.All`).
- **Data Minimization**: High-frequency dashboard queries consume precomputed, sanitized payloads rather than raw telemetry containing sensitive device identifiers.
