# Master Plan: SolarWinds + Microsoft Intune Production Platform Evaluation

## Objective
Perform an end-to-end production evaluation of the multi-domain ITOM platform (SolarWinds Orion + Microsoft Intune) without rebuilding the system, validating live data extractions, mathematical invariants, UI presentation, security/secrets hygiene, and delivering a comprehensive 14-section evaluation report.

## Milestone Decomposition

### Survey Phase (3 Parallel Explorers)
- **Explorer 1 (API & Data Pipelines)**: Investigate `scripts/fetch_solarwinds_data.py`, `scripts/fetch_intune_data.py`, `src/sync/`, `.env`, raw datasets in `data/`.
- **Explorer 2 (Transformation & Invariants & Tests)**: Investigate `scripts/generate_dashboard_payload.py`, `tests/verify_intune_data.py`, `tests/verify_solarwinds_data.py`, `tests/run_e2e_tests.py`, and mathematical invariants.
- **Explorer 3 (Presentation Tier & Security & Documentation)**: Investigate `ops_analytics.html`, `ops_analytics.js`, `index.html`, `app.js`, XSS protections, CSV export, docs (`README.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/SYNC_STRATEGY.md`).

### Execution & Verification Phases
- **R1: Live API Data Extraction & Freshness Verification**
  - Worker runs SWIS and Intune extractors.
  - Verify response status, latency, freshness timestamps, device counts.
- **R2: Data Transformation & Mathematical Invariant Validation**
  - Worker runs `scripts/generate_dashboard_payload.py`.
  - Validate 6-point invariants (population sum, OS closure, OEM closure, compliance rate exactness, binary GiB storage, SolarWinds health classification closure).
- **R3: Dashboard & Presentation Tier Verification**
  - Verify UI components, KPI stat cards, charts, searchable device tables, RFC 4180 CSV export, `escapeHtml()` sanitization.
- **R4: Security, Codebase & Documentation Audit**
  - Check for hardcoded credentials, unhandled errors, dead code, doc alignment.
- **R5: Production Evaluation & Comprehensive 14-Section Report**
  - Run full test suite (`tests/run_e2e_tests.py`, etc.).
  - Generate comprehensive 14-section System Evaluation Report with old vs fresh comparisons.
- **Auditing & Challenger Verification**
  - Independent Challenger and Forensic Auditor runs to ensure 100% genuine execution, zero mocking/hallucination, and clean audit verdict.
