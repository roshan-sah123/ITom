# ITOM Multi-Domain Telemetry & Quality Gate Skill (Auditor Copy)

## 1. Scope & Standards
This skill enforces enterprise multi-domain telemetry hygiene, zero-hallucination metric reconciliation, and atomic releases across the ITOM Portal platform.

### Authoritative Telemetry Invariants
* **Microsoft Intune**:
  * **25,987 Endpoints**: Windows (25,334), macOS (602), Linux (24), iOS (2), Android (1).
  * **Compliance Breakdown**: Compliant (21,589), Non-Compliant (3,422), ConfigManager (935), Unknown (31), InGracePeriod (10).
  * **Fleet Storage Utilization**: 37.4% average disk utilization across fleet (~9,761.55 TB total).
* **SolarWinds Orion**:
  * **1,548 Server Nodes**: High Health (1,357), Medium Health (150), Low/Critical (41).
  * **Status Breakdown**: Up (1,370), Warning (25), Critical (35), Down (6), Unmanaged/Unknown (112).
  * **Performance Metrics**: Fleet CPU (16.2%), RAM (22.6%), Network Latency (42.5 ms).
