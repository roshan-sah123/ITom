---
name: itom-telemetry-sync
description: Standard operating procedure for extracting, validating, and publishing multi-domain telemetry from Microsoft Intune and SolarWinds Orion into Cloud Firestore and the ITOM Portal.
---

# ITOM Multi-Domain Telemetry & Quality Gate Skill

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

---

## 2. Ingestion & Quality Gate Runbook

### Step 1: Execute Multi-Domain Extraction
```bash
# Extract & structure Intune Graph Telemetry
python scripts/fetch_intune_data.py

# Extract & structure SolarWinds SWIS Telemetry
python scripts/fetch_solarwinds_data.py
```

### Step 2: Run Verification Test Suites
```bash
# Validate Intune Invariants (25,987 devices)
python tests/verify_intune_data.py

# Validate SolarWinds Invariants (1,548 nodes)
python tests/verify_solarwinds_data.py
```

### Step 3: Production Deployment
```bash
# Deploy to Google Firebase Hosting
npx -y firebase-tools deploy --only hosting --project itom-portal-roshan
```
