# Task Assignment: Milestones 4 & 5 Implementation (Documentation Suite & GitHub Standards)

## Working Directory
`c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m4_m5`

## Inputs
- Authoritative User Request: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md`
- Master Project Plan: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\PROJECT.md`
- Guidelines: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\GEMINI.md`
- Invariant Datasets: `data/intune_summary.json`, `data/solarwinds_summary.json`, `data/cmdb_summary.json`, `data/executive_digest.json`
- Milestone 1–3 Handoffs:
  - `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m1_m3\handoff.md`
  - `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\survey_explorer_3\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Detailed Objectives:
1. **Milestone 4: 15-Minute Onboarding & Master Documentation Suite**:
   - Author `docs/ONBOARDING.md`:
     - 15–20 minute rapid ramp-up guide for new engineers.
     - Section 1: 3-Minute Mental Model & System Overview.
     - Section 2: 5-Minute Local Environment Setup (`.env`, python virtualenv/dependencies).
     - Section 3: 4-Minute Telemetry Validation & Live Extractions (`fetch_solarwinds_data.py`, `fetch_intune_data.py`, `run_sync.py`).
     - Section 4: 3-Minute Web Server & Dashboard Verification (`start_server.py`, `http://localhost:8080`).
     - Section 5: Common Development Tasks & Fast Feedback Loops.
   - Update `README.md`:
     - Reflect exact authoritative telemetry metrics (25,987 Intune endpoints, 1,548 SolarWinds nodes, 1,548 CMDB CIs, 28,955 executive digest).
     - Modernized directory layout matching `PROJECT.md`.
     - Live execution and quick-start instructions.
   - Author / Synchronize:
     - `docs/ARCHITECTURE.md`: 3-tier architecture, data flow, invariant validation gates, live API integrations.
     - `docs/DATA_FLOW.md`: Complete end-to-end lifecycle (API Poll -> Invariant Gate -> Atomic JSON Dump -> HTTP Daemon -> DOM Paint).
     - `docs/API_CONTRACTS.md`: SolarWinds SWIS SWQL queries, Microsoft Graph schemas, REST routes (`/api/cmdb/*`).
     - `docs/DEPLOYMENT.md`: On-premise air-gapped deployment, systemd (`systemd/itom.service`), Windows batch startup (`start_itom_service.bat`).
     - `docs/TROUBLESHOOTING.md`: Runbook for API timeouts, SSL certs, network routing, and invariant triage.
2. **Milestone 5: GitHub Standards & Automated CI Workflow**:
   - Create `.github/ISSUE_TEMPLATE/bug_report.md`
   - Create `.github/ISSUE_TEMPLATE/feature_request.md`
   - Create `.github/ISSUE_TEMPLATE/telemetry_sync_issue.md`
   - Create `.github/PULL_REQUEST_TEMPLATE.md`
   - Create `.github/workflows/ci.yml`: Matrix test pipeline for Python 3.10/3.11/3.12 executing `python tests/run_e2e_tests.py` and secret checks.
3. **Verification**:
   - Run `python tests/run_e2e_tests.py` and verify all tests pass.
   - Document all changes in `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m4_m5\handoff.md`.
