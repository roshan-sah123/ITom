# ITOM Portal — Enterprise Operations Analytics & Telemetry

Production-grade Centralized Operations Analytics & Infrastructure Management Portal integrating **Microsoft Intune Graph Telemetry**, **SolarWinds Orion SWIS API v3**, and enterprise **CMDB Configuration Items**.

---

## 📊 Live Telemetry Overview (100% Verified Invariants)

| Domain | Total Monitored Units | Primary Breakdown | Health & Compliance | API Source |
| :--- | :--- | :--- | :--- | :--- |
| **Microsoft Intune** | **25,987 Endpoints** | Windows (25,334), macOS (602), Linux (24), iOS (2), Android (1), Unspecified (24) | **83.08%** Compliant (21,589 devices)<br/>**37.4%** Fleet Avg Storage Used | Microsoft Graph v1.0 OData |
| **SolarWinds Orion** | **1,548 Server Nodes** | Up (1,370), Warning (25), Critical (35), Down (6), Unmanaged (112) | **87.66%** High Health (1,357 nodes)<br/>**9.69%** Medium (150)<br/>**2.65%** Low/Critical (41) | Orion SWIS v3 REST |
| **CMDB Network CIs** | **1,548 Verified CIs** | Access Switches (612), Core Switches (210), Distribution (340), Routers (186), Firewalls (200) | **100%** Relational Integrity<br/>**0** Orphaned Records | SolarWinds SWIS / CMDB Normalizer |
| **Executive Digest** | **28,955 Fleet Assets** | Endpoints (25,987), Servers (1,548), Network Infrastructure (1,420) | **92.4%** Fleet Operational Health<br/>Enterprise-Wide Coverage | Multi-Domain Normalizer |

---

## 🚀 Quick Start (On-Premise Server / Workstation)

### Option 1: 1-Click Launch (Windows)
Double-click [`start_server.bat`](start_server.bat) in the project root.

### Option 2: Command Line (Windows / Linux / macOS)
```bash
# Start multi-threaded server supervisor with background 10-minute auto-sync
python scripts/start_server.py
```

### Access URLs:
* 🌐 **Enterprise Launcher**: [http://localhost:8080/](http://localhost:8080/)
* 💻 **OPS Analytics (Intune)**: [http://localhost:8080/ops_analytics.html#intune](http://localhost:8080/ops_analytics.html#intune)
* 📡 **OPS Analytics (SolarWinds)**: [http://localhost:8080/ops_analytics.html#solarwinds](http://localhost:8080/ops_analytics.html#solarwinds)
* 🗄️ **OPS Analytics (CMDB)**: [http://localhost:8080/ops_analytics.html#cmdb](http://localhost:8080/ops_analytics.html#cmdb)
* 📋 **REST CMDB Health API**: [http://localhost:8080/api/cmdb/health](http://localhost:8080/api/cmdb/health)

---

## 📖 Developer Onboarding in 15 Minutes
See [docs/ONBOARDING.md](docs/ONBOARDING.md) for a structured 15–20 minute rapid ramp-up guide covering mental model, environment setup, live extractions, dashboard verification, and testing feedback loops.

---

## 🔄 Telemetry Extraction & Sync Pipelines

To extract fresh live data from enterprise APIs and recalculate dashboard payloads with mathematical invariant verification:

```bash
# 1. Live Extraction from Microsoft Graph Intune API (25,987 devices)
python scripts/fetch_intune_data.py

# 2. Live Extraction from SolarWinds Orion SWIS API (1,548 server nodes)
python scripts/fetch_solarwinds_data.py

# 3. Generate CMDB Configuration Items & CSV Exports (1,548 CIs)
python scripts/fetch_cmdb_data.py

# 4. End-to-End Orchestrated Sync Pipeline (Extraction + Invariant Validation)
python scripts/run_sync.py
```

---

## 📁 Repository Directory Structure

```
optimistic-pasteur/
├── .github/                              # GitHub standards & automation
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md                 # Bug report issue template
│   │   ├── feature_request.md            # Feature proposal template
│   │   └── telemetry_sync_issue.md       # Telemetry sync & invariant issue template
│   ├── PULL_REQUEST_TEMPLATE.md          # Standard PR submission template
│   └── workflows/
│       ├── ci.yml                        # Automated multi-version CI test matrix
│       ├── intune_telemetry_sync.yml     # Scheduled Intune sync workflow
│       └── telemetry-sync-cron.yml       # Telemetry sync cron definition
├── data/                                 # Authoritative telemetry datasets
│   ├── .gitkeep
│   ├── intune_ops_analytics.json         # Raw Intune extraction (25,987 devices)
│   ├── intune_summary.json               # Precomputed fast dashboard payload
│   ├── solarwinds_nodes.json             # Raw SolarWinds extraction (1,548 nodes)
│   ├── solarwinds_summary.json           # Precomputed server summary (1,548 nodes)
│   ├── cmdb_summary.json                 # Precomputed CMDB summary (1,548 CIs)
│   └── executive_digest.json             # Consolidated executive digest (28,955 fleet)
├── docs/                                 # Comprehensive documentation suite
│   ├── ONBOARDING.md                     # 15-20 minute developer ramp-up guide
│   ├── ARCHITECTURE.md                   # 3-Tier clean architecture specification
│   ├── DATA_FLOW.md                      # End-to-end data flow & transformation lifecycle
│   ├── API_CONTRACTS.md                  # REST, SWIS & Graph interface contracts
│   ├── DEPLOYMENT.md                     # On-premise, systemd & container deployment runbook
│   ├── TROUBLESHOOTING.md                # Diagnostic triage runbook & error matrix
│   ├── MRD_Module_1_OPS_Analytics.md     # Product & business requirements
│   └── SYNC_STRATEGY.md                  # Telemetry sync & rate-limit strategy
├── exports/                              # RFC 4180 CSV export files
│   ├── cmdb_network_cis_complete.csv     # Complete CMDB network CI export
│   ├── intune_devices_complete.csv       # Complete Intune dataset export
│   └── solarwinds_nodes_complete.csv     # Complete SolarWinds dataset export
├── js/                                   # Root modular JavaScript helpers (zero-build)
│   ├── constants.js                      # Design tokens, invariants, tab definitions
│   ├── utils.js                          # XSS sanitization, debouncing, formatting
│   └── services.js                       # Telemetry loaders & RFC 4180 CSV exporter
├── scripts/                              # Production pipeline utilities & daemons
│   ├── deploy_to_vm.py                   # Automated VM deployment engine
│   ├── fetch_cmdb_data.py                # CMDB extraction CLI
│   ├── fetch_intune_data.py              # Microsoft Graph extraction CLI
│   ├── fetch_solarwinds_data.py          # SolarWinds SWIS extraction CLI
│   ├── generate_dashboard_payload.py     # Invariant aggregator & normalizer
│   ├── run_sync.py                       # Master synchronization pipeline
│   ├── start_server.py                   # Multi-threaded server supervisor with auto-sync
│   └── test_solarwinds_connection.py     # SWIS connectivity test utility
├── src/                                  # Source code
│   ├── automation/                       # Automation & executive reporting engines
│   │   └── executive_digest.py           # Multi-domain fleet digest generator
│   ├── frontend/                         # Modular frontend assets (HTML/CSS/JS)
│   │   ├── index.html                    # Enterprise portal launcher
│   │   ├── ops_analytics.html            # Operations analytics dashboard
│   │   ├── css/style.css                 # Dark design tokens (#0B0B0B canvas)
│   │   └── js/                           # Frontend JavaScript modules
│   ├── models/                           # Domain models & schemas
│   │   └── cmdb_models.py                # CMDB CI data model
│   └── sync/                             # API clients & aggregation engines
│       ├── graph_client.py               # Azure AD OAuth 2.0 & Graph API client
│       ├── solarwinds_client.py          # SWIS REST client & health classifier
│       ├── payload_generator.py          # Mathematical aggregation engine
│       ├── cmdb_generator.py             # CMDB extraction & normalization engine
│       └── firestore_sync.py             # Optional Google Cloud Firestore sync client
├── systemd/                              # Linux daemon configurations
│   └── itom.service                      # Systemd unit definition for 24/7 background operation
├── tests/                                # Automated test suites & verification gates
│   ├── run_e2e_tests.py                  # Master test runner (119+ tests)
│   ├── test_cmdb_live_solarwinds.py      # CMDB CI relational invariant test
│   ├── test_e2e_scenarios.py             # Enterprise E2E scenario test
│   ├── test_zero_build_compliance.py     # Zero-build & modular asset verification
│   ├── verify_adversarial_security.py    # XSS, secret scanning & stress harness
│   ├── verify_intune_data.py             # Intune 6-point invariant gate
│   ├── verify_solarwinds_data.py         # SolarWinds health closure test
│   ├── test_tab_navigation.py            # Tab routing & deep linking test
│   └── test_payload_generator.py         # OEM normalization & math unit tests
├── .dockerignore                         # Docker build exclusion rules
├── .env.example                          # Sanitized environment configuration template
├── .gitignore                            # Git exclusion rules (protects .env and caches)
├── Dockerfile                            # Production container definition
├── docker-compose.yml                    # Container composition configuration
├── GEMINI.md                             # Architectural rules & design tokens
├── index.html                            # Root portal entrypoint (zero-build)
├── ops_analytics.html                    # Root dashboard entrypoint (zero-build)
├── app.js                                # Portal search & quick launch controller
├── ops_analytics.js                      # Dashboard Chart.js & state controller
├── style.css                             # Global dark stylesheet (#0B0B0B canvas)
├── logo.png                              # Brand emblem
├── requirements.txt                      # Python dependencies (requests, urllib3)
├── start_server.bat                      # 1-Click local server launcher
├── start_itom_service.bat                # Windows service supervisor script
└── register_startup_service.ps1          # Windows 24/7 background scheduled task installer
```

---

## 🧪 Testing & Invariant Certification

Run all automated test suites to certify 100% data accuracy and system integrity:

```bash
# Run master E2E test runner (119+ tests across 9 test groups)
python tests/run_e2e_tests.py

# Verify Microsoft Intune mathematical invariants (25,987 endpoints)
python tests/verify_intune_data.py

# Verify SolarWinds Orion health classification invariants (1,548 nodes)
python tests/verify_solarwinds_data.py

# Verify CMDB relational invariants (1,548 CIs)
python -m unittest tests.test_cmdb_live_solarwinds -v

# Verify zero-build frontend compliance & asset linkage
python -m unittest tests.test_zero_build_compliance -v

# Run adversarial security & repository secret scanner
python -m unittest tests.verify_adversarial_security -v
```

---

## 🖥️ 24/7 Production Deployment

The platform is designed to operate on-premise without external dependencies:

### On-Premise Linux VM (systemd)
```bash
# Automated deployment engine (SSH/SCP + systemd configuration)
python scripts/deploy_to_vm.py --host <SERVER_IP> --user <SSH_USER> --port 8080
```
*See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full Linux, Windows Service, Docker, and Nginx reverse proxy guides.*

### On-Premise Windows Background Service
```powershell
# Register persistent 24/7 background task in Windows Task Scheduler
powershell -ExecutionPolicy Bypass -File .\register_startup_service.ps1
```

---

## 🔒 Security & IT Audit Compliance

* **Zero Cloud Footprint Required**: Operates 100% air-gapped on-premise. No company telemetry is leaked to third-party services.
* **Zero Hardcoded Secrets**: All API secrets are read strictly at runtime from `.env` (excluded via `.gitignore` and `.dockerignore`).
* **Strict XSS Sanitization**: All hostnames, serial numbers, user principals, and dynamic DOM insertions pass through `escapeHtml()`.
* **Read-Only REST API**: Mutating HTTP verbs (`POST`, `PUT`, `DELETE`, `PATCH`) are rejected with `405 Method Not Allowed`.
