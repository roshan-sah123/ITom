# Project: ITOM OPS Analytics & Microsoft Intune Integration

## Architecture
- **Presentation Tier (`src/frontend/` & root entrypoints)**:
  - `index.html` / `app.js`: Enterprise ITOM Portal Launcher with keyboard shortcuts (`/`, `Esc`), module search, and deep-linking tab bridges (`#overview`, `#intune`, `#solarwinds`, `#network`, `#dex`).
  - `ops_analytics.html` / `ops_analytics.js`: Production-grade OPS Analytics Dashboard supporting 5 discrete interactive tab views, responsive Chart.js visualizations, live telemetry KPI cards, instant client-side filtering, and RFC 4180 CSV export.
  - `style.css`: Unified dark enterprise design system (`#0B0B0B` base, `#F97316` orange accent, `#22C55E` live indicators).
- **Data & ETL Tier (`src/sync/`, `scripts/`, `data/`)**:
  - `data/intune_ops_analytics.json`: Authoritative snapshot of 25,987 Microsoft Intune managed endpoint records.
  - `data/intune_summary.json`: Precomputed, ultra-fast dashboard payload with verified metrics, breakdowns, and device samples.
  - `src/sync/graph_client.py` & `scripts/fetch_intune_data.py`: Microsoft Graph API client for Azure AD OAuth 2.0 and paginated device extraction.
  - `src/sync/payload_generator.py` & `scripts/generate_dashboard_payload.py`: Aggregation engine computing verified fleet metrics with case-insensitive normalization.
  - `src/sync/run_sync.py`: Automated end-to-end sync trigger and validation pipeline.
- **Testing & Verification Tier (`tests/`)**:
  - `tests/verify_intune_data.py`: Multi-agent data verification suite asserting mathematical invariants across 25,987 devices.
  - `tests/test_payload_generator.py`: Unit tests for data transformations and case-insensitive aggregation.
  - `tests/test_tab_navigation.py`: E2E / headless tests for tab switching, URL hash routing, and UI responsiveness.
  - `tests/test_e2e_scenarios.py`: Real-world integration workload tests across ITOM operational scenarios.
  - `tests/test_tier5_adversarial_stress.py`: Tier 5 UI & routing adversarial stress test suite (23 tests).
  - `tests/test_tier5_adversarial.py`: Tier 5 data invariant & sync fuzzing test suite (22 tests).
  - `tests/run_e2e_tests.py`: Master test runner with colorized TAP/xUnit test reporting.

## Feature Inventory
Every feature identified during the Survey phase is mapped to an implementation milestone below:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Interactive Tab Controller | Seamless tab switching between Overview, Intune Live, SolarWinds, Network, and DEX | M3 | R1, Survey |
| 2 | Deep-Linking & History | URL hash routing (`#overview`, `#intune`, `#solarwinds`, `#network`, `#dex`) & back/forward navigation | M3 | R1, Survey |
| 3 | Launcher Module Bridge | Portal launcher in `app.js` routing cards directly to tab views with animated overlay | M3 | R1, Survey |
| 4 | Visual State Indicators | Pulsing live status dot, active tab highlight, compliance state badges | M3 | R1, Survey |
| 5 | Live Intune KPI Cards | Total Managed (25,987), Compliance Rate (83.08%), Fleet Storage (37.4%), SolarWinds health | M2, M3 | R1, R2 |
| 6 | Chart.js Visualizations | Interactive OS doughnut, compliance bar, and manufacturer distribution charts | M2, M3 | R1, R2 |
| 7 | Searchable Device Table | Fast client-side filtering matching deviceName, UPN, serial, model, OS | M3 | R1 |
| 8 | Complete CSV Dataset Export | Client-side RFC 4180 CSV export capability for complete device telemetry | M3 | R1, FR-006 |
| 9 | Multi-Domain Overview Panel | Unified executive pane aggregating telemetry across all 5 operational sections | M3 | R1, MRD |
| 10 | SolarWinds Operational Panel | Orion server health, node availability, gateway status (`orion-swis.internal.corp:17774`) | M3 | R1, MRD |
| 11 | Network & CMDB Panel | Building-wise network infrastructure, switch/router uplinks, and CMDB audit status | M3 | R1, MRD |
| 12 | DEX Metrics Panel | Digital Employee Experience score, endpoint performance utilization, impact ratings | M3 | R1, MRD |
| 13 | Intune Data Verification | Invariant checking on 25,987 devices (OS, compliance, manufacturer, storage) | M2, E2E | R2 |
| 14 | Automated Verification Script | `tests/verify_intune_data.py` asserting strict mathematical consistency | M2, E2E | R2 |
| 15 | Payload Generator Fix | Case-insensitive manufacturer matching (`LENOVO` -> `Lenovo`, 959 devices) | M2 | Survey Defect 1 |
| 16 | Modular Codebase Layout | Restructure codebase into clean `src/`, `scripts/`, `data/`, `docs/`, `tests/` folders | M1 | R3 |
| 17 | Production Documentation | Architectural specs, sync guide, and module documentation with docstrings | M1, M4 | R3, R4 |
| 18 | Automated Data Sync Strategy | Scheduled sync workflow (GitHub Actions / Cloud Scheduler / Cloud Functions into Hosting/Firestore) | M4 | R4 |
| 19 | Sync CLI & Automation Tools | `scripts/run_sync.py` and `src/sync/` modules for automated data refresh | M4 | R4 |
| 20 | E2E Testing Suite (Tiers 1-4) | Comprehensive opaque-box test suite across all 20 features and requirements | E2E | Project Spec |
| 21 | Adversarial Hardening (Tier 5) | White-box adversarial testing and edge-case boundary hardening | M5 | Project Spec |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| **E2E** | E2E Testing Track | Test infrastructure, test runner, `tests/verify_intune_data.py`, Tiers 1-4 tests (`TEST_READY.md`) | None | DONE |
| **M1** | Code Structure & Architecture | Clean 5-folder layout (`src/`, `scripts/`, `data/`, `docs/`, `tests/`), docstrings, hosting compatibility | None | DONE |
| **M2** | Intune Data Pipeline & Invariants | Payload generator fix (Lenovo case normalization), summary sync, verified 25,987 metrics | M1 | DONE |
| **M3** | Tab Navigation & Multi-Domain UI | 5 tab views (`ops_analytics.html`), tab switching controller, deep-linking, launcher bridge, search & CSV | M1, M2 | DONE |
| **M4** | Automated Refresh & Sync Strategy | Sync architecture design, `src/sync/` automation scripts, CI/CD / cron workflow, documentation | M1, M2 | DONE |
| **M5** | Final Integration & Adversarial Verification | 100% pass on E2E test suite (Tiers 1-4) + Phase 2 Adversarial Coverage Hardening (Tier 5) + Forensic Audit | E2E, M3, M4 | DONE |

## Interface Contracts
### Data Payload Schema (`data/intune_summary.json`)
```typescript
interface IntuneSummaryPayload {
  metrics: {
    total_managed_devices: 25987;
    compliant_devices: 21589;
    noncompliant_devices: 3422;
    other_compliance: 976;
    compliance_rate_pct: 83.08;
    avg_storage_used_pct: 37.4;
  };
  os_breakdown: {
    Windows: 25334;
    macOS: 602;
    "Linux (ubuntu)": 24;
    "": 24;
    iOS: 2;
    Android: 1;
  };
  compliance_breakdown: {
    compliant: 21589;
    noncompliant: 3422;
    configManager: 935;
    unknown: 31;
    inGracePeriod: 10;
  };
  manufacturer_breakdown: {
    Dell: 15716;
    HP: 8610;
    Lenovo: 959;
    Apple: 604;
    Other: 98;
  };
  sample_devices: Array<{
    id: string;
    deviceName: string;
    operatingSystem: string;
    osVersion: string;
    complianceState: string;
    userPrincipalName: string;
    model: string;
    manufacturer: string;
    serialNumber: string;
    lastSync: string;
    totalStorageGB: number;
    freeStorageGB: number;
    usedStoragePct: number;
  }>;
}
```

### Tab Controller Interface (`src/frontend/js/ops_analytics.js` & `ops_analytics.js`)
```javascript
/**
 * Tab Navigation Controller Interface
 * @typedef {'overview' | 'intune' | 'solarwinds' | 'network' | 'dex'} TabId
 */

function switchTab(tabId, updateHash = true);
function getActiveTab(): TabId;
function initTabRouter();
```

## Code Layout
```
optimistic-pasteur/
├── src/
│   ├── frontend/
│   │   ├── index.html                    # ITOM Portal Launcher UI
│   │   ├── ops_analytics.html            # OPS Analytics Multi-Tab Dashboard
│   │   ├── css/
│   │   │   └── style.css                 # Dark enterprise CSS stylesheet
│   │   └── js/
│   │       ├── app.js                    # Launcher controller & deep link bridge
│   │       └── ops_analytics.js          # Tab navigation, charts & table controller
│   └── sync/
│       ├── __init__.py
│       ├── graph_client.py               # Microsoft Graph API OAuth & ingestion
│       ├── payload_generator.py          # Summary aggregation engine
│       └── firestore_sync.py             # Firestore synchronization utility
├── scripts/
│   ├── fetch_intune_data.py              # CLI executable for Graph API ingestion
│   ├── generate_dashboard_payload.py     # CLI executable for summary generation
│   └── run_sync.py                       # Automated end-to-end sync CLI
├── data/
│   ├── intune_ops_analytics.json         # Raw dataset (25,987 verified device records)
│   └── intune_summary.json               # Aggregated metrics & 100 sample device records
├── docs/
│   ├── MRD_Module_1_OPS_Analytics.md     # Product Requirements Document
│   ├── ARCHITECTURE.md                   # System Architecture & Sync Strategy Guide
│   ├── API_CONTRACTS.md                  # Interface schemas and data dictionary
│   └── SYNC_STRATEGY.md                  # Automated refresh & sync specification
├── tests/
│   ├── __init__.py
│   ├── run_e2e_tests.py                  # Master test runner (Tiers 1-5)
│   ├── verify_intune_data.py             # 25,987 device invariants verification
│   ├── test_payload_generator.py         # Unit tests for payload aggregation
│   ├── test_tab_navigation.py            # DOM / tab navigation test suite
│   ├── test_e2e_scenarios.py             # Real-world integration workload tests
│   ├── test_tier5_adversarial_stress.py  # Tier 5 UI adversarial stress tests
│   └── test_tier5_adversarial.py         # Tier 5 data invariant & sync fuzzing
├── index.html                            # Root portal launcher (for hosting compatibility)
├── ops_analytics.html                    # Root dashboard entry (for hosting compatibility)
├── app.js                                # Root JS (for hosting compatibility)
├── ops_analytics.js                      # Root JS (for hosting compatibility)
├── style.css                             # Root CSS (for hosting compatibility)
├── .firebaserc                           # Firebase project configuration
├── firebase.json                         # Firebase hosting and firestore routing
├── firestore.rules                       # Firestore database security rules
├── firestore.indexes.json                # Firestore database indexes
├── .env.example                          # Environment variables template
├── ORIGINAL_REQUEST.md                   # Authoritative user requirements
├── PROJECT.md                            # Living project tracking & architecture
├── TEST_INFRA.md                         # E2E test infrastructure specification
└── TEST_READY.md                         # E2E test readiness certificate
```
