# Module Requirements Document (MRD)

## Module: OPS Analytics
**Product:** IT Operations Management (ITOM) Portal  
**Version:** 1.0 (Draft)  
**Priority:** P0  
**Status:** Pending Business Approval  

---

### Objective
OPS Analytics is the primary dashboard of the ITOM Portal. It provides IT Operations teams with a centralized view of infrastructure health and operational metrics by consolidating information from enterprise monitoring platforms into a single interface.

The module is intended to improve operational visibility and reduce the need to switch between multiple monitoring tools.

---

### Scope
The OPS Analytics module includes the following operational sections:

| Section | Information to Display |
| :--- | :--- |
| **Network** | Building-wise network information linked with CMDB. |
| **Endpoint** | CPU, RAM, Log Volume, Event Volume, Total Inventory. |
| **Server** | CPU, RAM, Health Classification (High / Medium / Low). |
| **SolarWinds / Intune** | Operational insights from SolarWinds and Microsoft Intune (Read-only access). |
| **DEX** | DEX Score, CPU, RAM, HDD, Utilization, Username, Email, Band, Days Since Problem. |

---

### Functional Requirements
* **FR-001**: Display Network analytics (P0).
* **FR-002**: Display Endpoint analytics (P0).
* **FR-003**: Display Server analytics (P0).
* **FR-004**: Display SolarWinds / Intune analytics (P0).
* **FR-005**: Display DEX analytics (P0).
* **FR-006**: Export displayed data in CSV format (P1).

---

### Data Sources
* **Microsoft Intune** (Real-time live telemetry extracted via Microsoft Graph API)
* **SolarWinds** (Read-only access via SWIS API / Private VM)
* **CMDB**
* Additional operational sources (TBD)

---

### UI Requirements
* Black background (`#0B0B0B`)
* Orange borders and highlights (`#F97316`)
* White text (`#FFFFFF`) and gray secondary text (`#A3A3A3`)
* Green-to-red colors for health and status indicators
* Dashboard layout consistent with the ITOM Portal design
