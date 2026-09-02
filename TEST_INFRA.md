# E2E Test Infrastructure & Verification Architecture

## 1. Testing Philosophy & Standards
- **Opaque-Box Requirement-Driven Testing**: Every test verifies observable behavior and contract fulfillment without dependence on private internal implementation details.
- **5-Tier Verification Hierarchy**:
  - **Tier 1**: Core Feature Coverage (Happy path, schema invariants, REST contracts).
  - **Tier 2**: Boundary Value Analysis & Corner Cases (Empty results, max page sizes, invalid parameters, timeouts).
  - **Tier 3**: Cross-Feature Interaction Matrix (Pairwise integration across DB, API, Middleware, and Background Ingestion).
  - **Tier 4**: Real-World Enterprise Workload Scenarios (End-to-end user journeys and multi-agent workflows).
  - **Tier 5**: Adversarial Hardening & Stress Testing (SQL injection guards, XSS validation, mutate verb rejection, state race conditions).
- **Zero-Hallucination Policy**: Absolute enforcement of authoritative dataset invariants (25,987 Intune devices, 1,548 SolarWinds server nodes, 1,543 active CIs). No fabricated or mock metrics allowed in reporting.

---

## 2. Feature Inventory & Coverage Mapping Matrix

| # | Feature | Requirement Source | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 | Target Test Modules |
|---|---------|-------------------|:------:|:------:|:------:|:------:|:------:|---------------------|
| 1 | Obsidian Dark UI Design Tokens | ORIGINAL_REQUEST §R1 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_tab_navigation.py`, `verify_adversarial_security.py` |
| 2 | Unified 3-Zone Telemetry Table | ORIGINAL_REQUEST §R1 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_tab_navigation.py`, `test_tier5_adversarial_stress.py` |
| 3 | Interactive Chart.js Drill-Downs | ORIGINAL_REQUEST §R1 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_tab_navigation.py`, `test_tier5_adversarial_stress.py` |
| 4 | Strict XSS Sanitization & DOM Safety | ORIGINAL_REQUEST §R1 | ✓ | ✓ | ✓ | ✓ | ✓ | `verify_adversarial_security.py`, `test_tier5_adversarial_stress.py` |
| 5 | Accessibility & Screen Reader A11y | ORIGINAL_REQUEST §R1 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_tab_navigation.py` |
| 6 | Sub-50ms Dashboard Initial Paint | Acceptance Criteria | ✓ | ✓ | ✓ | ✓ | ✓ | `verify_stress_performance.py` |
| 7 | Dual-Asset Synchronicity | Codebase Survey | ✓ | ✓ | ✓ | ✓ | ✓ | `test_zero_build_compliance.py` |
| 8 | PostgreSQL 16 Relational Models | ORIGINAL_REQUEST §R2 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_database_persistence.py` |
| 9 | Alembic Async Migration Pipeline | ORIGINAL_REQUEST §R2 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_database_persistence.py` |
| 10 | High-Performance Indexing & Trigrams | Backend Survey | ✓ | ✓ | ✓ | ✓ | ✓ | `test_database_persistence.py`, `test_fastapi_backend.py` |
| 11 | Historical Status Delta Tracking | ORIGINAL_REQUEST §R2 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_database_persistence.py`, `test_background_sync_security.py` |
| 12 | Database Ingestion & Seeding Invariants | Acceptance Criteria | ✓ | ✓ | ✓ | ✓ | ✓ | `test_database_persistence.py`, `verify_intune_data.py`, `verify_solarwinds_data.py` |
| 13 | Modular FastAPI Async Backend | ORIGINAL_REQUEST §R2 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_fastapi_backend.py` |
| 14 | Paginated REST API Endpoints | ORIGINAL_REQUEST §R2 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_fastapi_backend.py` |
| 15 | Response Freshness Middleware | ORIGINAL_REQUEST §R2 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_fastapi_backend.py` |
| 16 | Decoupled APScheduler Sync Engine | ORIGINAL_REQUEST §R3 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_background_sync_security.py` |
| 17 | Multi-Worker Advisory Locks | ORIGINAL_REQUEST §R3 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_background_sync_security.py` |
| 18 | Read-Only SWQL Validation & 405 Guards | ORIGINAL_REQUEST §R3 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_background_sync_security.py` |
| 19 | Volatile Delta Detection (SHA-256) | ORIGINAL_REQUEST §R3 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_background_sync_security.py` |
| 20 | Docker Multi-Stage API Image | ORIGINAL_REQUEST §R4 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_docker_infra_compliance.py` |
| 21 | Multi-Container Docker Compose | ORIGINAL_REQUEST §R4 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_docker_infra_compliance.py` |
| 22 | NGINX Reverse Proxy Configuration | ORIGINAL_REQUEST §R4 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_docker_infra_compliance.py` |
| 23 | E2E Regression & Integration Test Suite | Acceptance Criteria | ✓ | ✓ | ✓ | ✓ | ✓ | `run_e2e_tests.py` |
| 24 | Adversarial Security & Coverage Hardening | Acceptance Criteria | ✓ | ✓ | ✓ | ✓ | ✓ | `verify_adversarial_security.py`, `test_background_sync_security.py` |

---

## 3. Test Architecture & Directory Structure

```
tests/
├── __init__.py
├── run_e2e_tests.py                      # Master E2E and integration test runner (Tiers 1-5)
│
├── [Core Integration & Backend Verification]
├── test_database_persistence.py          # PostgreSQL 16 models, Alembic migrations, CRUD, history, seed invariants
├── test_fastapi_backend.py               # FastAPI REST routes, pagination, freshness headers, sub-20ms latency
├── test_background_sync_security.py     # APScheduler 10m sync, advisory locks, delta hashing, SWQL 405 guards
├── test_docker_infra_compliance.py       # Multi-stage Dockerfile, Docker Compose 3-tier stack, NGINX config, healthz/ready
│
├── [Data Invariants & Ingestion Verification]
├── verify_intune_data.py                 # Intune 25,987 endpoint mathematical reconciliation
├── verify_solarwinds_data.py             # SolarWinds 1,548 node telemetry invariant verification
├── test_payload_generator.py             # Normalization, storage math, sample record generator
│
├── [UI & Navigation Verification]
├── test_tab_navigation.py                # Tab controller, router, search filter, CSV export, keyboard hotkeys
├── test_zero_build_compliance.py         # Zero-build dual-asset mirror verification
│
├── [Enterprise Scenarios & Adversarial Hardening]
├── test_e2e_scenarios.py                 # Tier 4 real-world operational workflows
├── test_tier5_adversarial_stress.py      # Tier 5 URL hash, DOM security, search fuzzing, table scale
├── test_tier5_adversarial.py             # Tier 5 mathematical fuzzing & authoritative dataset reconciliation
├── verify_adversarial_security.py        # Tier 5 XSS sanitization, CSV RFC 4180 escaping, secret scans
└── verify_stress_performance.py          # Sub-50ms dashboard paint and query benchmark
```

---

## 4. Real-World Enterprise Workload Scenarios (Tier 4)

1. **Scenario 1: Executive Overview & Critical Resource Drill-Down**
   - Executive inspects fleet overview, switches between Intune and SolarWinds tabs, clicks high-severity chart slice, filters table to degraded servers, and verifies sub-50ms render.
2. **Scenario 2: Compliance Audit & Triage Flow**
   - Security auditor isolates non-compliant endpoints (4,398 devices), searches by OS version, verifies 100% XSS cell sanitization, and exports RFC 4180 compliant CSV.
3. **Scenario 3: Deep-Link Route & Launcher Bridge Navigation**
   - User activates URL hash deep link (`#solarwinds`), presses `/` hotkey for search, toggles pagination sizing (10/25/50/100), and resets view state via `Esc`.
4. **Scenario 4: Relational Persistence & Historical State Audit**
   - Background sync detects server state transition (Up -> Critical, CPULoad 45% -> 96%), writes new state snapshot to `ci_status_history`, and queries audit trail via REST API.
5. **Scenario 5: Multi-Worker Sync Concurrency & Mutation Attack Rejection**
   - Two concurrent workers trigger telemetry ingestion (Session 1 acquires advisory lock `1048576`, Session 2 skips cleanly). Adversarial client attempts `DELETE /api/v1/cmdb/cis` and receives `HTTP 405 Method Not Allowed`.

---

## 5. Execution & CI/CD Commands

### Master Test Suite Run
```bash
# Run all 184+ tests across all tiers
python tests/run_e2e_tests.py

# Run in verbose mode
python tests/run_e2e_tests.py --verbose

# Run with TAP formatted output
python tests/run_e2e_tests.py --tap
```

### Pytest Execution
```bash
# Run full suite with pytest
pytest tests/ -v

# Run targeted new backend suites
pytest tests/test_database_persistence.py tests/test_fastapi_backend.py tests/test_background_sync_security.py tests/test_docker_infra_compliance.py -v
```

---

## 6. Coverage & Quality Gates

- **Total Test Cases**: $\ge 184$ tests (119 existing E2E + 65 new integration/security tests).
- **Pass Rate Threshold**: Strictly **100.0%** (0 failures, 0 errors).
- **Mathematical Invariant Rule**: 25,987 Intune devices and 1,548 SolarWinds nodes reconciled with zero mock values.
- **Security Rule**: 0 XSS vulnerabilities, 0 exposed credentials, 100% rejection of mutating upstream verbs.
