# Repository cleanup - 2026-09-28

## Changes

- Consolidated duplicate `.gitignore` cache, bytecode, and log rules; added ignores for local virtual environments and SQLite backup snapshots.
- Removed ignore patterns that hid the tracked `Dockerfile`, `docker-compose.yml`, and `systemd/` deployment files from future Git additions.
- Tightened `.dockerignore` so image builds omit Git history, credentials, test/docs scratch areas, local databases, telemetry snapshots, backups, logs, exports, and frontend design previews. Compose bind mounts are unchanged.
- Removed the generated `.pytest_cache/` directory (about 46 KB); it is reproducible by pytest.
- Kept root-level compatibility pages/scripts and mirrored frontend files because the repository documents active launcher, deployment, and test references to them.

## Preserved

No database, backup, export, log, credential, or source files were deleted. Existing uncommitted application, test, migration, and frontend-skill changes were preserved.

## Validation and follow-up

- Reviewed `.dockerignore`, `.gitignore`, Dockerfile copy behavior, Compose mounts, and repository references.
- No application tests or image build were run as part of this folder hygiene pass. `git diff --check` still reports trailing carriage returns in pre-existing modified frontend files; cleanup-owned files use LF line endings.
- Compose still mounts the host `data/` directory into NGINX for compatibility with older static-data pages. `.dockerignore` does not alter that runtime exposure; remove or narrow the bind mount only after migrating those pages to the API.
