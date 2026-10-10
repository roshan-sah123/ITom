# ITOM Operations Analytics — API Contracts & Data Dictionary

## 1. Overview
This document defines the formal data contracts, API schemas, payload specifications, and type interfaces across the ITOM Operations Analytics ecosystem.

---

## 2. Microsoft Graph Intune Telemetry Ingestion Contract

### 2.1 Azure AD OAuth 2.0 Token Endpoint
- **URL**: `POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`
- **Content-Type**: `application/x-www-form-urlencoded`
- **Request Parameters**:
  | Field | Type | Description |
  |---|---|---|
  | `client_id` | string (UUID) | Azure AD App Registration Client ID |
  | `client_secret` | string | Azure AD App Registration Secret (from `.env`) |
  | `scope` | string | `https://graph.microsoft.com/.default` |
  | `grant_type` | string | `client_credentials` |

- **Response Body (`200 OK`)**:
  ```json
  {
    "token_type": "Bearer",
    "expires_in": 3599,
    "ext_expires_in": 3599,
    "access_token": "eyJ0eXAiOiJKV1QiLC..."
  }
  ```

### 2.2 Managed Devices Endpoint
- **URL**: `GET https://graph.microsoft.com/v1.0/deviceManagement/managedDevices`
- **Headers**:
  - `Authorization`: `Bearer {access_token}`
  - `Accept`: `application/json`
  - `ConsistencyLevel`: `eventual`
- **OData Query Parameters**:
  - `$select`: `id,deviceName,operatingSystem,osVersion,complianceState,userPrincipalName,model,manufacturer,serialNumber,lastSyncDateTime,totalStorageSpaceInBytes,freeStorageSpaceInBytes`
  - `$top`: `1000` (configurable)

- **Response Schema (`200 OK`)**:
  ```json
  {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#deviceManagement/managedDevices",
    "@odata.nextLink": "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices?$select=...&$skiptoken=X'...",
    "value": [
      {
        "id": "4d0a62f4-a48d-48e9-b844-0a0a7ce03e14",
        "deviceName": "LAP-NJ-81003082",
        "operatingSystem": "Windows",
        "osVersion": "10.0.26200.8457",
        "complianceState": "compliant",
        "userPrincipalName": "user.name@example.com",
        "model": "Dell Pro 14 PC14250",
        "manufacturer": "Dell Inc.",
        "serialNumber": "J02XDJ4",
        "lastSyncDateTime": "2026-06-02T14:34:54Z",
        "totalStorageSpaceInBytes": 508759539712,
        "freeStorageSpaceInBytes": 359286460416
      }
    ]
  }
  ```

---

## 3. SolarWinds Orion SWIS API v3 Contract

### 3.1 SWQL Query Endpoint
- **URL**: `POST https://{solarwinds_server}:{solarwinds_port}/SolarWinds/InformationService/v3/Json/Query`
- **Authentication**: HTTP Basic / NTLM over TLS (Port 17774)
- **Headers**:
  - `Content-Type`: `application/json`
  - `Accept`: `application/json`

- **Request Body**:
  ```json
  {
    "query": "SELECT NodeID, IPAddress, Caption, Status, CPULoad, PercentMemoryUsed, SystemUpTime, MachineType FROM Orion.Nodes"
  }
  ```

- **Response Schema (`200 OK`)**:
  ```json
  {
    "results": [
      {
        "NodeID": 101,
        "IPAddress": "10.200.14.22",
        "Caption": "SRV-US-APP-01",
        "Status": 1,
        "CPULoad": 14.5,
        "PercentMemoryUsed": 32.1,
        "SystemUpTime": 2489100,
        "MachineType": "Windows 2022 Server"
      }
    ]
  }
  ```

---

## 4. Local Web Server REST API Contracts (`scripts/start_server.py`)

All REST endpoints are strictly **read-only** and return JSON payloads with CORS (`Access-Control-Allow-Origin: *`) and anti-caching headers (`Cache-Control: no-cache, no-store`).

### 4.1 `GET /api/cmdb/summary`
Returns the aggregated CMDB summary and breakdown metrics.

**Response Schema (`200 OK`)**:
```json
{
  "source": "SolarWinds",
  "metadata": {
    "generated_at": "2026-09-01T22:00:00Z",
    "total_configuration_items": 1548,
    "active_monitored_cis": 1548,
    "mode": "live",
    "connection_status": "Connected to SolarWinds SWIS v3"
  },
  "metrics": {
    "total_cis": 1548,
    "high_health_cis": 1357,
    "medium_health_cis": 150,
    "low_health_cis": 41,
    "avg_cpu_load_pct": 16.2,
    "avg_memory_used_pct": 22.6
  },
  "type_breakdown": {
    "Access Switch": 612,
    "Distribution Switch": 340,
    "Core Switch": 210,
    "Firewall": 200,
    "Router": 186
  },
  "sample_devices": [ ... ]
}
```

### 4.2 `GET /api/cmdb/items`
Returns filtered Configuration Item records.

**Query Parameters**:
- `type` (optional): Filter by CI type (e.g. `Server`, `Access Switch`, `Firewall`).
- `status` (optional): Filter by status (e.g. `Up`, `Warning`, `Critical`, `Down`).
- `vendor` (optional): Filter by vendor (e.g. `Cisco`, `Dell`, `HP`).

**Response Schema (`200 OK`)**:
```json
{
  "source": "SolarWinds",
  "mode": "live",
  "total_items": 200,
  "items": [
    {
      "ci_id": "CI-100201",
      "node_id": 201,
      "caption": "FW-US-EDGE-01",
      "ci_type": "Firewall",
      "status": "Up",
      "ip_address": "10.100.1.1",
      "vendor": "Cisco",
      "cpu_load": 12.0,
      "memory_used": 28.4
    }
  ]
}
```

### 4.3 `GET /api/cmdb/servers`
Returns all server-class configuration items.

### 4.4 `GET /api/cmdb/network-devices`
Returns all network hardware configuration items (Switches, Routers, Firewalls).

### 4.5 `GET /api/cmdb/health`
Returns system status, API connection state, and high-level health counters.

**Response Schema (`200 OK`)**:
```json
{
  "status": "healthy",
  "source": "SolarWinds",
  "source_api": "SolarWinds Information Service (SWIS) v3",
  "mode": "live",
  "connection_status": "Connected",
  "last_refreshed": "2026-09-01T22:00:00Z",
  "total_cis": 1548,
  "active_monitored_cis": 1548,
  "high_health_cis": 1357,
  "low_health_cis": 41
}
```

### 4.6 Read-Only Mutation Guard
Any mutating HTTP verb (`POST`, `PUT`, `DELETE`, `PATCH`) to `/api/cmdb/*` is rejected:

**Response (`405 Method Not Allowed`)**:
```json
{
  "error": "Forbidden: SolarWinds CMDB API is strictly READ-ONLY.",
  "allowed_methods": ["GET"]
}
```

---

## 5. Telemetry Summary Payloads (`data/*.json`)

### 5.1 Microsoft Intune Summary (`data/intune_summary.json`)
```typescript
interface IntuneSummaryPayload {
  metrics: {
    total_managed_devices: number;  // 25,987
    compliant_devices: number;      // 21,589
    noncompliant_devices: number;   // 3,422
    other_compliance: number;       // 976
    compliance_rate_pct: number;    // 83.08
    avg_storage_used_pct: number;   // 37.4
  };
  os_breakdown: {
    Windows: number;                // 25,334
    macOS: number;                  // 602
    "Linux (ubuntu)": number;       // 24
    "": number;                     // 24 (Unspecified)
    iOS: number;                    // 2
    Android: number;                // 1
  };
  compliance_breakdown: {
    compliant: number;              // 21,589
    noncompliant: number;           // 3,422
    configManager: number;          // 935
    unknown: number;                // 31
    inGracePeriod: number;          // 10
  };
  manufacturer_breakdown: {
    Dell: number;                   // 15,716
    HP: number;                     // 8,610
    Lenovo: number;                 // 959
    Apple: number;                  // 604
    Other: number;                  // 98
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

### 5.2 SolarWinds Summary (`data/solarwinds_summary.json`)
```typescript
interface SolarWindsSummaryPayload {
  metrics: {
    total_nodes: number;            // 1,548
    high_health_nodes: number;      // 1,357
    medium_health_nodes: number;    // 150
    low_health_nodes: number;       // 41
    avg_cpu_load_pct: number;       // 16.2
    avg_memory_used_pct: number;    // 22.6
    avg_latency_ms: number;         // 42.5
  };
  status_breakdown: {
    Up: number;                     // 1,370
    Warning: number;                // 25
    Critical: number;               // 35
    Down: number;                   // 6
    Unmanaged: number;              // 112
  };
  health_breakdown: {
    High: number;                   // 1,357
    Medium: number;                 // 150
    Low: number;                    // 41
  };
  sample_nodes: Array<{
    NodeID: number;
    Caption: string;
    IPAddress: string;
    Status: string;
    HealthTier: "High" | "Medium" | "Low";
    CPULoad: number;
    PercentMemoryUsed: number;
    MachineType: string;
    SystemUpTime: string;
  }>;
}
```

### 5.3 Executive Digest Payload (`data/executive_digest.json`)
```typescript
interface ExecutiveDigestPayload {
  digest_metadata: {
    generated_at: string;
    scope: "enterprise_fleet";
  };
  fleet_summary: {
    total_monitored_assets: number;  // 28,955
    endpoints: number;               // 25,987
    servers: number;                 // 1,548
    network_core: number;            // 1,420
    fleet_health_score_pct: number;  // 92.4
  };
}
```

---

## 6. RFC 4180 CSV Export Schemas

### 6.1 Intune Managed Devices (`exports/intune_devices_complete.csv`)
| Column | Header | Example | Description |
|---|---|---|---|
| 0 | `Device ID` | `4d0a62f4-a48d-48e9-b844-0a0a7ce03e14` | Intune Device GUID |
| 1 | `Device Name` | `LAP-NJ-81003082` | Hostname / NetBIOS name |
| 2 | `Operating System` | `Windows` | OS Family |
| 3 | `OS Version` | `10.0.26200.8457` | OS Build |
| 4 | `Compliance State` | `compliant` | Compliance Status |
| 5 | `User Principal Name` | `user.name@example.com` | Azure UPN |
| 6 | `Model` | `Dell Pro 14 PC14250` | Hardware Model |
| 7 | `Manufacturer` | `Dell` | Normalized OEM |
| 8 | `Serial Number` | `J02XDJ4` | Hardware Serial Tag |
| 9 | `Last Sync (UTC)` | `2026-06-02T14:34:54Z` | Last Intune Sync |
| 10 | `Total Storage (GB)` | `473.8` | Total capacity |
| 11 | `Free Storage (GB)` | `334.6` | Free capacity |
| 12 | `Used Storage (%)` | `29.4` | Used percentage |

### 6.2 SolarWinds Nodes (`exports/solarwinds_nodes_complete.csv`)
| Column | Header | Example | Description |
|---|---|---|---|
| 0 | `Node ID` | `101` | SolarWinds Node ID |
| 1 | `Caption` | `SRV-US-APP-01` | Server Hostname |
| 2 | `IP Address` | `10.200.14.22` | Primary IPv4 |
| 3 | `Status` | `Up` | Status string |
| 4 | `Health Tier` | `High` | Computed Health Tier |
| 5 | `CPU Load (%)` | `14.5` | CPU utilization |
| 6 | `Memory Used (%)` | `32.1` | RAM utilization |
| 7 | `Machine Type` | `Windows 2022 Server` | OS / Hardware info |

### 6.3 CMDB Network CIs (`exports/cmdb_network_cis_complete.csv`)
| Column | Header | Example | Description |
|---|---|---|---|
| 0 | `CI ID` | `CI-100201` | CMDB Identifier |
| 1 | `Node ID` | `201` | Linked Orion Node ID |
| 2 | `Caption` | `FW-US-EDGE-01` | Asset Caption |
| 3 | `CI Type` | `Firewall` | CI Category |
| 4 | `Status` | `Up` | Operational State |
| 5 | `IP Address` | `10.100.1.1` | Management IP |
| 6 | `Vendor` | `Cisco` | Vendor OEM |

---

## 7. Modular JavaScript Helper Contracts (Zero-Build)

### 7.1 `constants.js`
Exports design system tokens and immutable telemetry invariants:
```javascript
const THEME = {
  bg: "#0B0B0B",
  card: "#141414",
  border: "#222222",
  accent: "#F97316",
  success: "#10B981",
  warning: "#F59E0B",
  danger: "#EF4444"
};

const INVARIANTS = {
  INTUNE_TOTAL: 25987,
  SOLARWINDS_TOTAL: 1548,
  CMDB_TOTAL: 1548,
  FLEET_TOTAL: 28955
};
```

### 7.2 `utils.js`
```javascript
function escapeHtml(str);                 // Neutralizes XSS strings
function debounce(func, wait);            // Debounces frequent DOM inputs
function formatNumber(val);               // Localized thousand separators
function formatBytes(bytes, decimals);    // Human-readable byte formatting
function bytesToGB(bytes, decimals);      // Converts bytes to GiB
function formatDate(dateStr);             // Standardized ISO date formatter
```

### 7.3 `services.js`
```javascript
async function fetchJson(url, options);      // Resilient JSON fetcher with fallback
async function loadIntuneTelemetry();        // Loads Intune summary payload
async function loadSolarWindsTelemetry();   // Loads SolarWinds summary payload
async function loadCmdbTelemetry();          // Loads CMDB summary payload
async function loadExecutiveDigest();        // Loads executive fleet digest
function exportToCsv(filename, rows, headers); // RFC 4180 CSV export engine
```
