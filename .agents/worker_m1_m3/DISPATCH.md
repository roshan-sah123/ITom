# Task Assignment: Milestone 1–3 Implementation (Core Cleanup, Frontend Modularization, Secrets Hygiene)

## Working Directory
`c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m1_m3`

## Inputs
- Authoritative User Request: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md`
- Master Project Plan: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\PROJECT.md`
- Guidelines: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\GEMINI.md`
- Survey Reports:
  - Frontend: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\survey_explorer_1\handoff.md`
  - Backend & Invariants: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\survey_explorer_2\handoff.md`
  - Tests & Docs: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\survey_explorer_3\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Detailed Objectives:
1. **Milestone 1 (Dead Code & Noise Removal)**:
   - Safely remove `scripts/cron_daemon.py` (confirming `scripts/start_server.py` daemon handles background sync).
   - In `src/sync/cmdb_generator.py` and `scripts/fetch_cmdb_data.py`, clean up obsolete references to `analytics.db` / `--db`.
   - Synchronize static files between root and `src/frontend/` (copy `logo.png` to `src/frontend/` if missing, ensure `src/frontend/js/app.js` contains the VP Domain Modal handlers).
2. **Milestone 2 (Frontend Separation & Modularization)**:
   - Create modular helper scripts in `src/frontend/js/` (and root `js/` if needed): `constants.js`, `utils.js`, `services.js`, while maintaining zero-build browser compatibility.
   - In `ops_analytics.js` (and `src/frontend/js/ops_analytics.js`), fix the tab label text to include `'CMDB Network CIs'` for the CMDB/network tab so header synchronization tests pass.
   - Verify all DOM table renderings and dynamic strings are sanitized using `escapeHtml()`.
   - Verify table search, column sorting, pagination, and CSV exports function flawlessly.
3. **Milestone 3 (Environment & Secret Hygiene)**:
   - Standardize `.env.example` with clean placeholders and zero real secrets/hostnames.
   - Ensure `.gitignore` and `.dockerignore` properly exclude `.env`, `data/*.json`, `exports/*.csv`, logs, caches.
   - Ensure `tests/verify_adversarial_security.py` secret scanning excludes `.env` (since `.env` is gitignored local config), achieving 100% test pass rate (113/113 tests).
4. **Verification**:
   - Run `python tests/run_e2e_tests.py` and verify all 113+ tests pass with exit code 0.
   - Document all file modifications, test commands, and verification outputs in `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m1_m3\handoff.md`.
