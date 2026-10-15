# ITOM project guidance

Use the current source and runtime configuration as authority. Do not treat old fleet counts, screenshots, or architecture examples as requirements.

## Skills

- [Backend engineering](skills/backend-engineering/SKILL.md): FastAPI, SQLite/PostgreSQL, source integrity, and private deployment.
- [Frontend engineering](skills/frontend-engineering/SKILL.md): active portal structure, evidence states, accessibility, and interactions.
- [Telemetry sync](skills/itom-telemetry-sync/SKILL.md): source checks, ingestion reconciliation, and freshness.
- [Test-driven development](skills/test-driven-development/SKILL.md): reproduce behavior bugs before fixing them.

## Rules

- [Source-backed metrics](rules/zero-hallucination.md)
- [Telemetry reconciliation](rules/multi-domain-telemetry.md)
- [UI direction](rules/ui-design-tokens.md)
- [Security and secrets](rules/security-and-secrets.md)

Keep instructions specific to this repository. Maintain deployment procedures in [the deployment guide](../docs/DEPLOYMENT.md); avoid duplicating them in skills or task reports.
