# ITOM Portal — Enterprise Operations Analytics & Telemetry

Production-grade Centralized Operations Analytics & Infrastructure Management Portal integrating **Microsoft Intune Graph Telemetry** and **SolarWinds Orion SWIS API v3**.

---

## 📊 Live Telemetry Overview (100% Verified Invariants)

| Domain | Total Monitored Units | Primary Metrics | Health & Compliance | API Source |
| :--- | :--- | :--- | :--- | :--- |
| **Microsoft Intune** | **26,771 Endpoints** | Windows (26,118), macOS (602), Linux (24), iOS (2), Android (1) | **83.37%** Compliant (22,318 devices)<br/>**36.8%** Fleet Avg Storage Used | Microsoft Graph v1.0 OData |
| **SolarWinds Orion** | **1,568 Server Nodes** | Windows (276), Cisco (492), Linux (5), Other (795) | **85.78%** High Health (1,345 nodes)<br/>**8.48%** Warning (133)<br/>**5.74%** Critical (90) | Orion SWIS v3 REST |

---

## 🚀 Quick Start (On-Premise Server / Workstation)

### Option 1: 1-Click Launch (Windows)
Double-click [`start_server.bat`](start_server.bat) in the project root.

### Option 2: Command Line
```powershell
python -m http.server 8080 --bind 0.0.0.0
```

### Access URLs:
* 🌐 **Enterprise Launcher**: [http://localhost:8080/](http://localhost:8080/)
* 💻 **OPS Analytics (Intune)**: [http://localhost:8080/ops_analytics.html#intune](http://localhost:8080/ops_analytics.html#intune)
* 📡 **OPS Analytics (SolarWinds)**: [http://localhost:8080/ops_analytics.html#solarwinds](http://localhost:8080/ops_analytics.html#solarwinds)

---

## 🖥️ Deploying to Dedicated Linux VM (24/7 Production)

To deploy the portal onto your company virtual machine (`<YOUR_SERVER_IP>`) so it runs independently 24/7:

```powershell
# Run the automated deployment engine (requires active VPN/LAN connection)
python scripts/deploy_to_vm.py --host <YOUR_SERVER_IP> --user <YOUR_SSH_USER> --port 8080
```

This script automatically:
1. Transfers portal frontend, datasets, and scripts via SSH/SCP.
2. Creates and enables the **`itom-portal.service`** `systemd` daemon.
3. Configures auto-restart on system reboot and serves the application on port `8080`.

---

## 🔄 Telemetry Extraction & Sync Pipelines

To fetch fresh live data from enterprise APIs and recalculate dashboard payloads:

```powershell
# 1. Live Extraction from Microsoft Graph Intune API (26,771 devices)
python scripts/fetch_intune_data.py

# 2. Live Extraction from SolarWinds Orion SWIS API (1,568 server nodes)
python scripts/fetch_solarwinds_data.py

# 3. End-to-End Orchestrated Pipeline (Extraction + Invariant Validation)
python scripts/run_sync.py
```

---

## 📁 Clean Project Directory Structure

```
├── data/                                 # Authoritative telemetry datasets
│   ├── intune_ops_analytics.json         # Raw Intune extraction (26,771 devices)
│   ├── intune_summary.json               # Precomputed fast dashboard payload
│   ├── solarwinds_nodes.json             # Raw SolarWinds extraction (1,568 nodes)
│   └── solarwinds_summary.json           # Precomputed fast server summary
├── docs/                                 # Engineering documentation
│   ├── API_CONTRACTS.md                  # REST & SWIS interface contracts
│   ├── ARCHITECTURE.md                   # 3-Tier clean architecture specification
│   ├── MRD_Module_1_OPS_Analytics.md     # Product & business requirements
│   └── SYNC_STRATEGY.md                  # Telemetry sync & rate-limit strategy
├── exports/                              # RFC 4180 CSV export files
│   ├── intune_devices_complete.csv       # Complete Intune dataset export
│   └── solarwinds_nodes_complete.csv     # Complete SolarWinds dataset export
├── scripts/                              # Production pipeline utilities
│   ├── deploy_to_vm.py                   # Automated VM deployment engine
│   ├── fetch_intune_data.py              # Microsoft Graph extraction CLI
│   ├── fetch_solarwinds_data.py          # SolarWinds SWIS extraction CLI
│   ├── generate_dashboard_payload.py     # Invariant aggregator & normalizer
│   ├── run_sync.py                       # Master synchronization pipeline
│   └── test_solarwinds_connection.py     # SWIS connectivity test utility
├── src/                                  # Source code
│   ├── frontend/                         # Modular frontend assets (HTML/CSS/JS)
│   └── sync/                             # API clients & aggregation engines
│       ├── graph_client.py               # Azure AD OAuth 2.0 & Graph API client
│       ├── payload_generator.py          # Mathematical aggregation engine
│       └── solarwinds_client.py          # SWIS REST client & health classifier
├── tests/                                # Test suites & verification gates
│   ├── run_e2e_tests.py                  # End-to-end verification runner
│   ├── test_payload_generator.py         # OEM normalization & math unit tests
│   ├── verify_intune_data.py             # Intune 6-point invariant gate
│   └── verify_solarwinds_data.py         # SolarWinds health closure test
├── index.html                            # Enterprise portal launcher
├── ops_analytics.html                    # Multi-domain analytics dashboard
├── app.js                                # Portal search & quick launch controller
├── ops_analytics.js                      # Dashboard Chart.js & state controller
├── style.css                             # Dark design system (#0B0B0B canvas)
├── start_server.bat                      # 1-Click on-premise local server launcher
├── requirements.txt                      # Python dependencies (requests, urllib3)
└── README.md                             # This documentation
```

---

## 🧪 Testing & Invariant Certification

Run all automated test suites to certify 100% data accuracy:

```powershell
# Run full E2E test suite
python tests/run_e2e_tests.py

# Verify Microsoft Intune mathematical invariants
python tests/verify_intune_data.py

# Verify SolarWinds Orion health classification invariants
python tests/verify_solarwinds_data.py
```

---

## 🔒 Security & IT Audit Compliance

* **Zero Cloud Footprint**: Operates 100% on-premise. No company telemetry is synchronized to external Google Cloud or Firebase services.
* **Zero Hardcoded Secrets**: All API secrets are read strictly at runtime from `.env` (which is excluded via `.gitignore`).
* **XSS Sanitization**: All hostnames, serial numbers, and user principals are sanitized via `escapeHtml()` before rendering.
