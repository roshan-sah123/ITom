# Antigravity Workspace Customizations (`.agents/`)

This directory houses repository-scoped agent customizations, domain skills, and architectural rules for the **ITOM Portal** platform. It follows the official Google Antigravity Customization Architecture.

---

## 1. Directory Structure

```text
.agents/
├── README.md                      # Workspace customizations documentation (this file)
├── .gitignore                     # Prevents ephemeral agent runs/scratchpads from committing
├── rules/                         # Workspace-level behavioral constraints & invariants
│   ├── zero-hallucination.md      # Strict zero-mock policy on executive metrics
│   ├── multi-domain-telemetry.md  # Dynamic sync telemetry reconciliation & baseline reference invariants
│   ├── ui-design-tokens.md        # Current evidence-first portal UI direction tokens
│   └── security-and-secrets.md    # Credential management, XSS escaping, read-only limits
└── skills/                        # Modular procedural runbooks & capabilities
    ├── backend-engineering/
    │   └── SKILL.md               # FastAPI, PostgreSQL 16, SQLAlchemy 2.0 Async, Alembic
    ├── frontend-engineering/
    │   └── SKILL.md               # Current ITOM portal UI, architecture, and interaction patterns
    ├── itom-telemetry-sync/
    │   └── SKILL.md               # SolarWinds SWIS & Intune Graph sync runbooks
    └── test-driven-development/
        └── SKILL.md               # Red-Green-Refactor test-driven engineering pattern
```

---

## 2. Workspace Skills

Skills extend the agent's procedural capabilities. Each skill is self-contained within its own directory and defined by a `SKILL.md` file featuring standard YAML frontmatter (`name`, `description`).

| Skill | Description | Path |
| :--- | :--- | :--- |
| **`backend-engineering`** | Asynchronous FastAPI patterns, PostgreSQL 16 relational data persistence, time-series history, read-only external integrations, and background synchronization. | [`skills/backend-engineering/SKILL.md`](skills/backend-engineering/SKILL.md) |
| **`frontend-engineering`** | Current ITOM operations UI, existing frontend architecture, responsive data views, and source-backed interaction states. | [`skills/frontend-engineering/SKILL.md`](skills/frontend-engineering/SKILL.md) |
| **`itom-telemetry-sync`** | Multi-domain telemetry extraction, periodic reconciliation against live sync runs, and deployment quality gates. | [`skills/itom-telemetry-sync/SKILL.md`](skills/itom-telemetry-sync/SKILL.md) |
| **`test-driven-development`** | Test-driven development (TDD) workflow enforcing failing tests before implementation, minimal code passes, and refactoring proof. | [`skills/test-driven-development/SKILL.md`](skills/test-driven-development/SKILL.md) |

---

## 3. Workspace Rules (`rules/`)

Rules are modular constraints for agent interactions in this repository:

* **[`zero-hallucination.md`](rules/zero-hallucination.md)**: Strict prohibition against simulated, mock, or synthetic numbers in executive analytics. Requires empirical grounding from live API extractions or PostgreSQL persistence.
* **[`multi-domain-telemetry.md`](rules/multi-domain-telemetry.md)**: Dynamic telemetry reconciliation with the latest synchronization run (`last_synchronized_at`, `sync_runs`), utilizing baseline extractions (Intune ~25,987, SolarWinds ~1,548) as reference invariants.
* **[`ui-design-tokens.md`](rules/ui-design-tokens.md)**: Keeps the UI direction aligned with the active evidence-first portal and stylesheet tokens.
* **[`security-and-secrets.md`](rules/security-and-secrets.md)**: Mandates environment variable isolation for all secrets, strict `escapeHtml()` sanitization on tabular cells, and HTTP 405 guards on read-only integrations.

---

## 4. Best Practices for Adding Customizations

1. **Keep Skills Modular**: Focus each skill on a clear domain or runbook. Use YAML frontmatter with a third-person descriptive summary.
2. **Progressive Disclosure**: Keep `SKILL.md` files concise. Store bulky schemas, examples, or scripts in `examples/`, `references/`, or `scripts/` subdirectories.
3. **No Scratch Commits**: Ephemeral agent runs, task artifacts, and scratch directories are ignored by `.agents/.gitignore`. Never check temporary agent session logs into version control.
