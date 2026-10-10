---
name: Telemetry Sync / Invariant Issue
about: Report a synchronization failure, rate limit, data drift, or invariant gate violation
title: '[SYNC-ERR] <domain>: <concise description of failure>'
labels: ['telemetry-sync', 'data-integrity', 'p0-critical']
assignees: ''
---

## 📡 Telemetry Source & Pipeline
- **Telemetry Domain**: [ ] Microsoft Intune (Graph API)  [ ] SolarWinds Orion (SWIS v3)  [ ] CMDB CIs  [ ] Executive Fleet Digest
- **Execution Context**: [ ] Backend scheduler (`app/workers/scheduler.py`)  [ ] Manual CLI (`scripts/run_live_sync.py`)  [ ] CI Workflow
- **Pipeline Stage**: [ ] Extraction / Authentication  [ ] Normalization  [ ] Invariant Verification Gate  [ ] Persistence

## 🚨 Invariant or Assertion Violated
Describe the exact discrepancy or invariant failure.
- **Expected Invariant Count / Metric**: [source snapshot count and expected reconciliation]
- **Observed Extracted Count / Metric**: [observed count and missing/rejected records]
- **Assertion Failure Output**:
```text
Paste exact python traceback or AssertionError here
```

## 🔍 Upstream API Details
- **API Status Code**: [e.g. HTTP 401 Unauthorized, HTTP 429 Too Many Requests, HTTP 503 Timeout]
- **API Response Headers / Error Body**:
```json
{
  "error": "Paste sanitized API error response here (ensure zero secrets)"
}
```

## 🛠️ Reproduction Steps
```bash
# Command executed
python scripts/fetch_intune_data.py
# or
python tests/verify_intune_data.py
```

## 📋 Remediation Status
- [ ] Upstream API connectivity verified
- [ ] `.env` credentials verified
- [ ] Normalization engine inspected for unmapped categorical values
- [ ] Deterministic payload generation tested locally
