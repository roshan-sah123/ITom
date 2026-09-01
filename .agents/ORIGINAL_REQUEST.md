# Original User Request

## Initial Request — 2026-09-01T22:11:49+05:30

Transform the ITOM telemetry and operations platform into an organized, maintainable, production-grade codebase with a 15–20 minute onboarding guide, structured documentation, clean frontend/service separation, and zero dead code, while strictly preserving 100% working functionality.

### Requirements:
1. R1. Full Codebase Audit & Noise/Dead Code Removal:
   - Audit all files across frontend (`src/frontend/`, root static assets), backend/ETL pipelines (`src/sync/`, `scripts/`), tests (`tests/`), and docs (`docs/`).
   - Safely remove orphaned experimental scripts, unused scratch files, duplicate definitions, and obsolete configurations after confirming zero dependency or route references.
   - Preserve all working live integrations (SolarWinds SWIS v3 API, Microsoft Graph Intune API), mathematical invariant gates, and server startup scripts (`start_server.bat`).
2. R2. Clean Frontend Separation & Service Layer Modularization:
   - Organize the frontend presentation layer into clear, logical responsibilities: UI components, data services/API client, utility helpers, and constants without breaking zero-build runtime compatibility.
   - Ensure all dynamic DOM rendering is strictly sanitized against XSS via `escapeHtml()`, and table searches, sorting, pagination, and RFC 4180 CSV exports operate with zero regression.
3. R3. Environment Configuration & Secret Hygiene:
   - Ensure `.env.example` contains sanitized, descriptive placeholders with zero corporate hostnames, IPs, or credentials.
   - Verify `.gitignore` excludes `.env`, `data/*.json`, `exports/*.csv`, cache directories, and local logs.
4. R4. Complete 15-Minute Onboarding & Architecture Documentation:
   - Author a developer-first `docs/ONBOARDING.md` structured to ramp up a new engineer in 15–20 minutes.
   - Create and synchronize comprehensive documentation: `README.md`, `docs/ARCHITECTURE.md`, `docs/DATA_FLOW.md`, `docs/API_CONTRACTS.md`, `docs/DEPLOYMENT.md`, `docs/TROUBLESHOOTING.md`.
5. R5. GitHub Repository Hygiene & Standards:
   - Standardize GitHub issue templates (`.github/ISSUE_TEMPLATE/`), pull request template (`.github/PULL_REQUEST_TEMPLATE.md`), and lightweight automated CI validation workflow (`.github/workflows/ci.yml`).

### Acceptance Criteria:
- 100% of automated test suites pass (`tests/run_e2e_tests.py` exits with code 0 across all 113+ tests).
- Local web server starts on `http://localhost:8080/` with zero broken assets, script errors, or 404s.
- All live extraction scripts (`scripts/fetch_solarwinds_data.py`, `scripts/fetch_intune_data.py`, `scripts/run_sync.py`) execute cleanly.
- Zero dead code, orphaned scratch files, or unused duplicate functions.
- Presentation logic and data fetching cleanly separated with robust error handling.
- Zero secrets, passwords, or company internal telemetry committed to Git.
- `README.md` and `docs/ONBOARDING.md` allow a new engineer to understand the architecture, data flow, and run the system within 15–20 minutes.
- All documentation reflects the exact working codebase (zero hallucinated features).
- Comprehensive Phase 19 Final Organization Report produced.
