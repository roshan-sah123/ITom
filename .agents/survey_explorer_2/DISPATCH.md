# Task Assignment: Backend/ETL Pipelines, Scripts, Invariants & Environment Survey

## Working Directory
`c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\survey_explorer_2`

## Inputs
- Authoritative User Request: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md`
- Project Guidelines: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\GEMINI.md`
- Domain Skill: `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\skills\itom-telemetry-sync\SKILL.md`

## Objectives
1. Perform an exhaustive survey of backend/ETL sync pipelines (`src/sync/`), automation scripts (`scripts/`), data directories (`data/`), server startup (`start_server.bat`, python http servers).
2. Document all live integrations: SolarWinds SWIS v3 API (`scripts/fetch_solarwinds_data.py`), Microsoft Graph Intune API (`scripts/fetch_intune_data.py`), pipeline orchestrator (`scripts/run_sync.py`), mathematical invariant validation rules (Intune 25,987; SolarWinds 1,548).
3. Identify orphaned experimental scripts, scratch files, obsolete configs, duplicate logic in `scripts/` or `src/`.
4. Audit environment configuration (`.env`, `.env.example`) and `.gitignore` for secret hygiene and proper ignore rules.
5. Write comprehensive findings to `.agents/survey_explorer_2/handoff.md`.
