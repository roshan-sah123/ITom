# ITOM Platform — 15-Minute Developer Onboarding Guide

Welcome to the **ITOM Operations Analytics & Multi-Domain Telemetry Platform**. This guide is engineered to take a software engineer, SRE, or DevOps specialist from a clean environment to running, testing, and modifying the platform in **15 to 20 minutes**.

---

## ⏱️ Quick Time Budget

| Section | Topic | Estimated Time |
| :--- | :--- | :--- |
| **Section 1** | [3-Minute Mental Model & System Overview](#-section-1-3-minute-mental-model--system-overview) | 3 mins |
| **Section 2** | [5-Minute Local Environment Setup](#-section-2-5-minute-local-environment-setup) | 5 mins |
| **Section 3** | [4-Minute Telemetry Validation & Live Extractions](#-section-3-4-minute-telemetry-validation--live-extractions) | 4 mins |
| **Section 4** | [3-Minute Web Server & Dashboard Verification](#-section-4-3-minute-web-server--dashboard-verification) | 3 mins |
| **Section 5** | [Common Development Tasks & Fast Feedback Loops](#-section-5-common-development-tasks--fast-feedback-loops) | Ongoing |
| **Total** | **Full Ramp-Up & Operational Readiness** | **~15–20 mins** |

---

## 🧠 Section 1: 3-Minute Mental Model & System Overview

### What is the ITOM Platform?
The ITOM Platform is a production-grade, centralized operations observability portal designed for enterprise infrastructure. It unifies telemetry across three core pillars:
1. **Endpoint Management (Microsoft Intune)**: 25,987 managed workstations and mobile devices.
2. **Infrastructure Monitoring (SolarWinds Orion SWIS v3)**: 1,548 physical/virtual server nodes and network appliances.
3. **Configuration Management Database (CMDB)**: 1,548 mapped Configuration Items (CIs) with 100% relational integrity.
4. **Executive Fleet Digest**: Consolidated 28,955 enterprise asset inventory.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            1. PRESENTATION TIER                             │
│  Zero-Build Vanilla HTML5/CSS3/ES6+ | UMD Helpers (constants/utils/services)│
│  • Enterprise Launcher (index.html / app.js)                                │
│  • Multi-Domain Operations Analytics Dashboard (ops_analytics.html / .js)   │
│  • Interactive Chart.js visualizers | Debounced Search | RFC 4180 CSV Export│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP Fetch / REST Endpoints
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       2. SERVICE & INGESTION TIER                           │
│  • Python Multi-Threaded Daemon Server (scripts/start_server.py)             │
│    - Serves static assets & REST API (/api/cmdb/*)                          │
│    - Background 10-minute auto-sync telemetry supervisor                    │
│  • API Connectors: Microsoft Graph OAuth2 & SolarWinds SWIS v3 REST         │
│  • Math Invariant Gates (verify_intune_data.py, verify_solarwinds_data.py)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Atomic Persistence
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       3. DATA & PERSISTENCE TIER                            │
│  • JSON Telemetry Snapshots (data/intune_summary.json, solarwinds_summary)  │
│  • RFC 4180 CSV Datasets (exports/cmdb_network_cis_complete.csv, etc.)      │
│  • Optional Cloud Persistence (Google Cloud Firestore / Firebase Hosting)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Architectural Guarantees
* **Zero-Build Frontend**: No Node.js build steps, Webpack, Vite, or transpilers required. Open standard HTML/JS directly or serve via Python HTTP daemon.
* **Zero Hallucination Policy**: All metrics are calculated from authentic telemetry extracts and verified against strict mathematical invariants.
* **Zero Hardcoded Secrets**: All credentials are read from `.env` at runtime.
* **Air-Gapped Operation**: Runs completely self-contained on-premise without external cloud dependencies.

---

## 🛠️ Section 2: 5-Minute Local Environment Setup

### Prerequisites
* **Python 3.10, 3.11, or 3.12** installed on your system (`python --version`).
* **Git** installed.
* A modern web browser (Chrome, Edge, Firefox, Safari).

### Step 1: Clone Repository & Enter Directory
```bash
git clone <repository_url> itom-portal
cd itom-portal
```

### Step 2: Create and Activate Python Virtual Environment
```bash
# On Windows (PowerShell / Command Prompt)
python -m venv .venv
.venv\Scripts\activate

# On Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Python Dependencies
```bash
pip install -r requirements.txt
```
*(Dependencies are lightweight: `requests` and `urllib3` for API clients and testing.)*

### Step 4: Configure Environment Variables
Copy the sanitized environment template to `.env`:
```bash
# On Windows
copy .env.example .env

# On Linux / macOS
cp .env.example .env
```

Review `.env`:
```ini
# Microsoft Intune / Microsoft Graph API
AZURE_TENANT_ID=your_tenant_id_here
AZURE_CLIENT_ID=your_client_id_here
AZURE_CLIENT_SECRET=your_client_secret_here

# SolarWinds Orion SWIS API v3
SOLARWINDS_SERVER=orion-swis.internal.corp
SOLARWINDS_PORT=17774
SOLARWINDS_USERNAME=your_swis_username_here
SOLARWINDS_PASSWORD=your_swis_password_here

# Local Web Server Configuration
HOST=0.0.0.0
PORT=8080
SYNC_INTERVAL_SECONDS=600
```
> **Note**: For local offline development and testing, you do not need live Azure or SolarWinds credentials. The repository includes authoritative cached snapshots in `data/` that allow 100% of tests, CLI tools, and the web portal to run immediately in offline/mock mode.

---

## 🔬 Section 3: 4-Minute Telemetry Validation & Live Extractions

### Step 1: Extract & Validate SolarWinds Telemetry
Run the SolarWinds extractor to compute node health classifications and summary metrics:
```bash
python scripts/fetch_solarwinds_data.py
```
*Outputs: `data/solarwinds_nodes.json` and `data/solarwinds_summary.json`.*

### Step 2: Extract & Validate Microsoft Intune Telemetry
Run the Intune payload generator to calculate compliance and storage invariants:
```bash
python scripts/generate_dashboard_payload.py
```
*Outputs: `data/intune_summary.json` with 6 invariant checks passing.*

### Step 3: Extract CMDB Configuration Items
Generate normalized CMDB records and RFC 4180 CSV exports:
```bash
python scripts/fetch_cmdb_data.py
```
*Outputs: `data/cmdb_summary.json` and `exports/cmdb_network_cis_complete.csv`.*

### Step 4: Run the Master End-to-End Test Suite
Execute the comprehensive automated test runner to verify all 119+ test suites:
```bash
python tests/run_e2e_tests.py
```
Expected output:
```text
================================================================================
                            E2E TEST SUMMARY REPORT
================================================================================
 Total Tests Run    : 119
 Total Passed       : 119 (100.0%)
 Total Failures     : 0
 Total Errors       : 0
================================================================================
🎉 ALL E2E TEST SUITES PASSED SUCCESSFULLY (Exit Code 0)
```

---

## 🌐 Section 4: 3-Minute Web Server & Dashboard Verification

### Step 1: Launch the On-Premise HTTP Server
Launch the production HTTP supervisor (which also runs the background 10-minute auto-sync daemon):

**Option A: 1-Click Launch (Windows)**
```powershell
.\start_server.bat
```

**Option B: Command Line (Windows / Linux / macOS)**
```bash
python scripts/start_server.py
```

### Step 2: Access the Portal in Your Browser
Open your browser and navigate to:
* 🚀 **Enterprise Portal Launcher**: [http://localhost:8080/](http://localhost:8080/)
* 📊 **Operations Analytics Dashboard**: [http://localhost:8080/ops_analytics.html](http://localhost:8080/ops_analytics.html)

### Step 3: Verify Interactive Features
1. **Tab Navigation**: Click between **Intune Endpoints**, **SolarWinds Servers**, **CMDB Network**, and **Executive Overview**. Notice URL hash routing updates cleanly (`#intune`, `#solarwinds`, `#cmdb`, `#overview`).
2. **Search Filtering**: Type a hostname (e.g., `LAP-` or `SRV-`) into the search bar. The table updates with a debounced 200ms query filter.
3. **Pagination**: Switch table page sizes between `10`, `25`, `50`, and `100` items.
4. **CSV Export**: Click **Export CSV** to download a verified RFC 4180 spreadsheet.

### Step 4: Verify REST API Endpoints
Open a new terminal or browser tab and query the built-in REST endpoints:
```bash
# Check overall CMDB health and status
curl http://localhost:8080/api/cmdb/health

# Fetch summarized CI breakdown
curl http://localhost:8080/api/cmdb/summary

# Query filtered server items
curl "http://localhost:8080/api/cmdb/items?type=Server"
```

---

## ⚡ Section 5: Common Development Tasks & Fast Feedback Loops

### 1. Adding or Modifying Frontend Components
* Frontend logic resides in `src/frontend/` and root:
  - `src/frontend/js/constants.js` / `js/constants.js`: Theme tokens, invariant constants, tab definitions.
  - `src/frontend/js/utils.js` / `js/utils.js`: XSS sanitizer (`escapeHtml`), debouncers, number/byte formatters.
  - `src/frontend/js/services.js` / `js/services.js`: Telemetry loaders and CSV export engine.
  - `src/frontend/ops_analytics.js` / `ops_analytics.js`: Dashboard chart controllers, tables, and tab routing.
* **Important**: Because the portal supports both modular directory structures and zero-build static serving, keep `src/frontend/` and root mirror files synchronized.
* Test your frontend changes with the Zero-Build Compliance suite:
  ```bash
  python -m unittest tests.test_zero_build_compliance -v
  ```

### 2. Modifying Telemetry Ingest & Invariant Logic
* Ingestion clients: `src/sync/graph_client.py` (Intune), `src/sync/solarwinds_client.py` (SolarWinds).
* Normalization engines: `src/sync/payload_generator.py`, `src/sync/cmdb_generator.py`.
* Whenever you modify normalization or mathematical calculations, re-run invariant verification gates:
  ```bash
  python tests/verify_intune_data.py
  python tests/verify_solarwinds_data.py
  ```

### 3. Adding New REST API Endpoints
* Server routes are defined in `scripts/start_server.py` (`CustomHTTPHandler.do_GET`).
* Remember: The REST API is strictly **read-only**. Any `POST`, `PUT`, `DELETE`, or `PATCH` requests are blocked with HTTP 405 Method Not Allowed.

### 4. Running Security & Secret Audits
Before opening a pull request, verify that no hardcoded credentials or unescaped HTML sinks were introduced:
```bash
python -m unittest tests.verify_adversarial_security -v
```

### 5. Git Commit & Pull Request Workflow
1. Create a feature branch:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Commit your changes with descriptive messages:
   ```bash
   git commit -m "feat(telemetry): add disk latency invariant to solarwinds payload"
   ```
3. Run the full verification suite before pushing:
   ```bash
   python tests/run_e2e_tests.py
   ```

---

## 🆘 Troubleshooting Quick Reference

| Issue | Quick Fix |
| :--- | :--- |
| **Port 8080 Already in Use** | On Windows, run `start_itom_service.bat --stop` or find PID with `netstat -ano \| findstr 8080` and terminate. Or run `python scripts/start_server.py --port 8081`. |
| **ModuleNotFoundError** | Ensure virtual environment is active: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Linux). Run `pip install -r requirements.txt`. |
| **Invariant Test Failure** | Re-run payload generation `python scripts/generate_dashboard_payload.py` to regenerate `data/intune_summary.json` from `data/intune_ops_analytics.json`. |
| **CORS / Asset Loading Error** | Ensure you access the portal via HTTP server (`http://localhost:8080/`), not via `file:///` URI, so browser fetch policies allow JSON reads. |

---

## 📚 Next Steps & Deep-Dive Documentation
* 🏛️ **System Architecture**: See [docs/ARCHITECTURE.md](ARCHITECTURE.md) for 3-tier design and security boundaries.
* 🌊 **End-to-End Data Flow**: See [docs/DATA_FLOW.md](DATA_FLOW.md) for ingestion sequence and transformation pipelines.
* 📜 **API Contracts & Data Schemas**: See [docs/API_CONTRACTS.md](API_CONTRACTS.md) for REST and SWIS interfaces.
* 🚀 **Production Deployment Runbook**: See [docs/DEPLOYMENT.md](DEPLOYMENT.md) for Linux systemd and Windows background service setups.
* 🩺 **Operational Troubleshooting Guide**: See [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) for diagnostic runbooks.
