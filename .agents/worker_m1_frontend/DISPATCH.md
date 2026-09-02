# DISPATCH: Worker - Milestone 1: Frontend UI/UX Polish & Accessibility

## Objective
Implement frontend polish for Obsidian design tokens, accessibility attributes on table wrappers, and ensure dual-asset synchronicity between `./` and `src/frontend/`.

## Scope & Instructions
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\PROJECT.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\GEMINI.md`
- Read skill: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\skills\frontend-engineering\SKILL.md`
- Read survey handoff: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\explorer_survey_frontend\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
- `style.css` and `src/frontend/style.css`
- `ops_analytics.html` and `src/frontend/ops_analytics.html`
- `index.html` and `src/frontend/index.html`
- `ops_analytics.js` and `src/frontend/ops_analytics.js`
- `js/*` and `src/frontend/js/*`

## Tasks
1. In `style.css` and `src/frontend/style.css`: Ensure canonical Obsidian dark-mode tokens are declared in `:root` (`--bg-canvas: #0B0B0B;`, `--bg-surface-1: #141414;`, `--bg-surface-elevated: #16161A;`, `--border-subtle: #222222;`, `--accent-orange: #F97316;`, `--accent-green: #10B981;`, `--accent-warning: #F59E0B;`, `--accent-critical: #EF4444;`).
2. In `ops_analytics.html` and `src/frontend/ops_analytics.html`: Add `role="region"` and `aria-label="Operational Telemetry Grid - [Intune Devices / SolarWinds Nodes / CMDB Items]"` to the table container wrappers (`.table-responsive`).
3. Ensure exact asset parity between root files (`index.html`, `ops_analytics.html`, `style.css`, `ops_analytics.js`, `app.js`, `js/*`) and `src/frontend/*`.
4. Run verification tests:
   ```powershell
   python -m unittest tests/test_tab_navigation.py -v
   python -m unittest tests/test_zero_build_compliance.py -v
   python -m unittest tests/verify_adversarial_security.py -v
   ```
5. Document all changes, test commands, and passing output in `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m1_frontend\handoff.md`.
