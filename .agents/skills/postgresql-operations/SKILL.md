---
name: postgresql-operations
description: Use for ITOM PostgreSQL isolation, migrations, backup, rollback, and deployment verification.
---

# PostgreSQL Operations

- Read `docs/PLATFORM_EXECUTION_LEDGER.md` before using the experimental Windows cluster. It is a separate loopback listener with separate telemetry and module databases.
- Confirm database identity, role, migration heads, and production separation before writes. Do not copy production data or credentials into experiments.
- Apply the primary and module Alembic chains to their respective databases; test rollback and database-aware backups before a production release.
- Keep credentials and database files out of Git and static hosting. Never print connection URLs or secrets. Do not change production without approval.