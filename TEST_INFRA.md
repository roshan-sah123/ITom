# E2E Test Infra: ITOM Platform Enterprise Transformation

## Test Philosophy
- Opaque-box, requirement-driven testing. No dependency on private implementation details.
- Comprehensive 5-tier methodology: Category-Partition (Tier 1), Boundary Value Analysis (Tier 2), Pairwise Combinatorial (Tier 3), Real-World Scenarios (Tier 4), and Adversarial Stress & Security Testing (Tier 5).
- Zero-Hallucination Policy verification across all database records, metrics, and API responses.

---

## Feature Inventory & Test Coverage Mapping
| # | Feature | Requirement Source | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|-------------------|:------:|:------:|:------:|:------:|
| 1 | PostgreSQL 16 & SQLAlchemy 2.0 Async Models | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | Alembic Migration Pipeline | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 3 | Zero-Loss Bulk Database Seeding & Invariants | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 4 | FastAPI Clean Architecture App & Lifespan | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 5 | Paginated CMDB Endpoints & Sub-20ms Query | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 6 | Intune Telemetry Endpoints & Compliance Math | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 7 | SolarWinds Telemetry Endpoints & Health Tiers | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 8 | Dynamic Freshness Response Headers (FRESH vs STALE) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 9 | APScheduler 10-Minute Background Ingestion Engine | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 10 | Read-Only SWQL Validation (HTTP 405 on Mutations) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 11 | Delta Change Detection & `ci_status_history` Audit | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 12 | Ingestion Run Audit (`sync_runs`, `sync_error_logs`) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 13 | Multi-Stage Dockerfile & Non-Root User | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 14 | Docker Compose 3-Tier Multi-Container Stack | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 15 | Nginx Reverse Proxy & Static Host | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 16 | Healthcheck & Readiness Probes (`/healthz`, `/ready`) | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |

---

## Test Architecture
- **Master Test Runner**: `python tests/run_e2e_tests.py` (executes all existing 119 E2E tests + newly integrated backend/DB suites).
- **Backend Test Suite**: `tests/test_fastapi_backend.py` & `tests/test_database_persistence.py` (exercises async database, Alembic, repositories, services, and endpoints using httpx AsyncClient / TestClient).
- **Security & Read-Only Test Suite**: `tests/test_readonly_security.py` (verifies HTTP 405 on POST/PUT/DELETE, SQL injection prevention, SWQL keyword blocking).
- **Data Parity & Invariant Test Suite**: `tests/verify_intune_data.py`, `tests/verify_solarwinds_data.py`, and `tests/test_database_invariants.py`.

---

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Full Database Seed & Migration Validation | Alembic migrations, PostgreSQL connection pool, bulk streaming upsert of 25,987 Intune devices and 1,543 SolarWinds CIs | High |
| 2 | Live CMDB Search & Paginated Navigation | `/api/v1/cmdb/cis` with text query, vendor filter, health tier filter, and sub-20ms pagination | Medium |
| 3 | Freshness SLA State Transition | Synchronized state ($\le 15\text{m} \rightarrow \text{FRESH}$) transitioning to stale state ($> 15\text{m} \rightarrow \text{STALE}$) | Medium |
| 4 | Background Sync Ingestion with Delta History | APScheduler sync run triggering delta change detection and writing snapshot to `ci_status_history` and `sync_runs` | High |
| 5 | Mutation Attack Rejection (Read-Only Guard) | Exploitative POST/PUT/DELETE attempts against SolarWinds/Intune endpoints returning HTTP 405 | Medium |

---

## Coverage Thresholds
- **Tier 1 (Feature Coverage)**: $\ge 5$ test cases per feature (16 features $\times 5 = \ge 80$ tests).
- **Tier 2 (Boundary & Corner Cases)**: $\ge 5$ test cases per feature (empty results, max page sizes, invalid parameters, timeouts).
- **Tier 3 (Cross-Feature Combinations)**: Pairwise integration across DB, API, Middleware, and Background Ingestion.
- **Tier 4 (Real-World Scenarios)**: $\ge 5$ comprehensive end-to-end integration workflows.
- **Tier 5 (Adversarial Coverage Hardening)**: White-box stress testing, injection probes, malformed JSON, and concurrency races.
- **Target Pass Rate**: 100.0% with zero failures.
