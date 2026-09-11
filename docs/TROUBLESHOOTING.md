# ITOM Operations Analytics — Operational Troubleshooting Runbook

This runbook provides diagnostic decision trees, root-cause analyses, and step-by-step remediation procedures for resolving telemetry extraction failures, server issues, invariant discrepancies, and frontend rendering problems.

---

## 1. Quick Triage Decision Tree

```
Symptom Observed:
├── 🔴 Invariant test gate fails (AssertionError in verify_intune or verify_solarwinds)
│   └── ➔ Go to [Section 3: Invariant Gate & Data Discrepancies](#3-invariant-gate--data-discrepancies)
├── 🔴 Web server fails to start (Port 8080 in use / Address already in use)
│   └── ➔ Go to [Section 4: Web Server & Port Conflicts](#4-web-server--port-conflicts)
├── 🔴 Microsoft Graph API returns 401 / 403 / 429 during extraction
│   └── ➔ Go to [Section 2.1: Microsoft Graph API Issues](#21-microsoft-graph-api-issues)
├── 🔴 SolarWinds SWIS connection timeout or SSL certificate error
│   └── ➔ Go to [Section 2.2: SolarWinds SWIS API Issues](#22-solarwinds-swis-api-issues)
├── 🔴 Frontend shows blank charts or CORS error
│   └── ➔ Go to [Section 5: Frontend & Browser Issues](#5-frontend--browser-rendering-issues)
└── 🔴 CSV export displays malformed columns in Excel
    └── ➔ Go to [Section 6: CSV Export & Formatting](#6-csv-export--formatting-issues)
```

---

## 2. Upstream API Extraction Issues

### 2.1 Microsoft Graph API Issues

#### Symptom: `HTTP 401 Unauthorized`
* **Root Cause**: Invalid `AZURE_CLIENT_SECRET`, expired secret, or incorrect `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` in `.env`.
* **Remediation**:
  1. Check Azure Portal -> **App Registrations** -> Find your application.
  2. Verify if the Client Secret has expired. If so, generate a new client secret.
  3. Update `.env` with the new value:
     ```ini
     AZURE_TENANT_ID=<your_tenant_id>
     AZURE_CLIENT_ID=<your_client_id>
     AZURE_CLIENT_SECRET=<your_fresh_client_secret>
     ```
  4. Re-test authentication:
     ```bash
     python scripts/fetch_intune_data.py
     ```

#### Symptom: `HTTP 403 Forbidden`
* **Root Cause**: Missing required Application Permission `DeviceManagementManagedDevices.Read.All` or Admin Consent was not granted.
* **Remediation**:
  1. In Azure Portal, navigate to **API Permissions** -> **Add a permission** -> **Microsoft Graph** -> **Application permissions**.
  2. Select `DeviceManagementManagedDevices.Read.All`.
  3. Click **Grant admin consent for <Your Organization>**.

#### Symptom: `HTTP 429 Too Many Requests` (Throttling)
* **Root Cause**: Tenant rate limit reached during high-frequency extraction.
* **Remediation**:
  - The built-in client (`src/sync/graph_client.py`) automatically applies jittered exponential backoff based on the `Retry-After` header.
  - If persistent, increase page size to reduce total HTTP request volume: `$top=1000`.

---

### 2.2 SolarWinds SWIS API Issues

#### Symptom: `InsecureRequestWarning: Unverified HTTPS request` or SSL Handshake Failure
* **Root Cause**: SolarWinds Orion SWIS on port `17774` utilizes a self-signed internal certificate.
* **Remediation**:
  - `src/sync/solarwinds_client.py` is configured to bypass self-signed validation using `verify=False` while suppressing urllib3 warning noise.
  - Ensure the internal root CA is installed on the host machine if strict certificate checking is enforced by corporate policy.

#### Symptom: `Connection timed out` or `Port 17774 Unreachable`
* **Root Cause**: Host is not connected to corporate VPN, or enterprise firewall blocks TCP port `17774`.
* **Remediation**:
  1. Verify VPN connection (e.g. GlobalProtect / AnyConnect).
  2. Test TCP port connectivity:
     ```powershell
     # PowerShell
     Test-NetConnection -ComputerName orion-swis.internal.corp -Port 17774
     ```
  3. Run the standalone connection test utility:
     ```bash
     python scripts/test_solarwinds_connection.py
     ```

---

## 3. Invariant Gate & Data Discrepancies

### Symptom: `AssertionError: Invariant Mismatch in tests/verify_intune_data.py`
* **Root Cause**: Raw data in `data/intune_ops_analytics.json` was refreshed without regenerating `data/intune_summary.json`.
* **Remediation**:
  1. Re-run the deterministic payload generator:
     ```bash
     python scripts/generate_dashboard_payload.py
     ```
  2. Re-run the invariant test:
     ```bash
     python tests/verify_intune_data.py
     ```

### Symptom: Unmapped Manufacturer Category Count Discrepancy
* **Root Cause**: A new OEM manufacturer (e.g., `"ASUSTeK COMPUTER INC."`) appeared in the Intune fleet that is not in the primary 4 vendors (Dell, HP, Lenovo, Apple).
* **Remediation**:
  - `src/sync/payload_generator.py` normalizes unknown vendors to the `"Other"` category, ensuring that $\sum \text{Manufacturers} == \text{Total Devices}$ remains 100% closed.

---

## 4. Web Server & Port Conflicts

### Symptom: `[Errno 98] Address already in use` or `[WinError 10048]`
* **Root Cause**: Another process (or a previous instance of `start_server.py`) is already listening on port `8080`.
* **Remediation**:

**On Windows:**
```cmd
:: Method A: Use built-in supervisor stop command
start_itom_service.bat --stop

:: Method B: Manual task termination
for /f "tokens=5" %a in ('netstat -aon ^| findstr ":8080" ^| findstr "LISTENING"') do taskkill /F /PID %a
```

**On Linux:**
```bash
# Locate and terminate process holding port 8080
sudo fuser -k 8080/tcp

# Or find PID with lsof and kill
sudo kill -9 $(sudo lsof -t -i:8080)
```

**Custom Port Override:**
You can start the server on an alternate port:
```bash
PORT=8090 python scripts/start_server.py
```

---

## 5. Frontend & Browser Rendering Issues

### Symptom: `Failed to fetch / CORS error` in Browser Console
* **Root Cause**: Opening `index.html` directly via `file:///` protocol in browser instead of through HTTP server. Browsers block `fetch()` on `file://` URLs due to CORS security policies.
* **Remediation**:
  - Always access the application through the HTTP server at `http://localhost:8080/` or `http://127.0.0.1:8080/`.

### Symptom: Canvas is already in use (Chart.js Error)
* **Root Cause**: Recreating a Chart.js instance on an existing HTML `<canvas>` element without destroying the old instance.
* **Remediation**:
  - In `ops_analytics.js`, always use the `destroyChartSafe(chartInstance, canvasElement)` helper before instantiating new charts.

### Symptom: Stale Telemetry Displayed on Dashboard
* **Root Cause**: Browser cached previous JSON summary files.
* **Remediation**:
  - Hard refresh browser with `Ctrl + F5` (Windows) or `Cmd + Shift + R` (macOS).
  - The server supervisor (`scripts/start_server.py`) automatically attaches `Cache-Control: no-cache, no-store, must-revalidate` to all JSON responses.

---

## 6. CSV Export & Formatting Issues

### Symptom: Excel Displays Characters with Broken Accents or Misaligned Columns
* **Root Cause**: CSV lacking UTF-8 Byte Order Mark (BOM) or unescaped embedded commas.
* **Remediation**:
  - The CSV engine in `js/services.js` prepends `\uFEFF` (UTF-8 BOM) and encloses all fields containing commas, quotes, or newlines in double quotes per RFC 4180.

---

## 7. Diagnostic Commands Cheat Sheet

| Purpose | Command |
| :--- | :--- |
| **Run Master Test Suite** | `python tests/run_e2e_tests.py` |
| **Verify Intune Invariants** | `python tests/verify_intune_data.py` |
| **Verify SolarWinds Invariants**| `python tests/verify_solarwinds_data.py` |
| **Verify CMDB Invariants** | `python -m unittest tests.test_cmdb_live_solarwinds -v` |
| **Test Zero-Build Compliance** | `python -m unittest tests.test_zero_build_compliance -v` |
| **Run Security & Secret Scan** | `python -m unittest tests.verify_adversarial_security -v` |
| **Test SolarWinds SWIS API** | `python scripts/test_solarwinds_connection.py` |
| **Check Port 8080 Listener** | `netstat -ano \| findstr 8080` (Windows) / `lsof -i :8080` (Linux) |
| **Check Windows Service Status**| `powershell .\register_startup_service.ps1 -Status` |
| **Check Linux systemd Logs** | `sudo journalctl -u itom.service -f` |
