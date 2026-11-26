# Current ITOM frontend

- All new UI work belongs in `frontend-revamp/`, the current Figma-based React and TypeScript application.
- Edit `frontend-revamp/src/App.tsx`, `src/Inventory.tsx`, `src/data.ts`, `src/api.ts`, and `src/index.css` as appropriate. Build with `npm --prefix frontend-revamp run build`; deployed static assets live in `frontend/`.
- The old HTML/CSS/JavaScript UI and its historical tests are preserved locally in `not-in-use/legacy-frontend/`. This directory is ignored by Git, excluded from Docker builds, and outside the served frontend. Do not use, restore, import, or change it for current work unless the user explicitly requests it.
- Older notes or skills referring to `frontend/js/`, `frontend/css/`, standalone legacy pages, or a zero-build editable frontend describe the retired implementation. Follow the user's current-UI direction and the React source above.
- Preserve source-backed data, freshness, and unavailable states. Do not invent telemetry or modify backend ingestion merely to change presentation.
- Frontend data checks: `npm --prefix frontend-revamp test`. Current browser checks: `python -m pytest tests/browser/test_figma_revamp.py --run-browser -q`. Backend/API checks continue in `tests/` with isolated databases.

## Platform and safety

- Follow `docs/PLATFORM_EXECUTION_LEDGER.md` for the modular boundaries, isolated 8081 workflow, checks, and release gates.
- Never redirect experimental work to production databases or source credentials. SolarWinds remains read-only; preserve incomplete-snapshot and freshness semantics.
- Use the relevant `.agents/skills/` for architecture, PostgreSQL, connectors, backend security/deployment, testing, and frontend work. Preserve unrelated worktree changes.
