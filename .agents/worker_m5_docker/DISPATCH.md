# DISPATCH: Worker - Milestone 5: Local Server Docker Compose Infrastructure

## Objective
Implement production-grade local server infrastructure with multi-stage Dockerfile for FastAPI, 3-tier Docker Compose stack (`nginx`, `api`, `postgres` 16), and NGINX reverse proxy configuration with healthchecks and security headers.

## Scope & Instructions
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\PROJECT.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\ORIGINAL_REQUEST.md`
- Read `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\GEMINI.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
- `Dockerfile`
- `docker-compose.yml`
- `nginx.conf`

## Tasks
1. Implement multi-stage `Dockerfile`:
   - Stage 1: Build dependencies with Python 3.11-slim and wheels.
   - Stage 2: Runtime image with non-root user `itom` (UID 10001), working directory `/app`, and container healthcheck querying `http://localhost:8000/healthz`.
2. Implement `docker-compose.yml`:
   - `postgres`: image `postgres:16-alpine`, port 5432, healthcheck using `pg_isready -U itom_user -d itom_db`, named volume `postgres_data`.
   - `api`: built from `Dockerfile`, port 8000, depends_on `postgres` with `condition: service_healthy`, environment variables from `.env`, healthcheck `/healthz`.
   - `nginx`: image `nginx:alpine`, port 8080 (and 80), volume mounts for static frontend and `nginx.conf`, depends_on `api` with `condition: service_healthy`.
   - Custom bridge network `itom-network`.
3. Implement `nginx.conf`:
   - Upstream `api_backend` targeting `api:8000`.
   - Reverse proxy routing `/api/` to `http://api_backend/api/` with `proxy_pass`, `Host`, and `X-Forwarded-*` headers.
   - Static file serving for `/` from `/usr/share/nginx/html`.
   - Gzip compression, cache control (no-cache for API/dynamic JSON, caching for static assets), and security headers (`X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `X-XSS-Protection: 1; mode=block`).
4. Run verification tests:
   ```powershell
   python tests/test_docker_infra_compliance.py
   python tests/run_e2e_tests.py
   ```
5. Document all changes, test commands, and passing output in `c:\Users\Roshan.Sah\Documents\antigravity\optimistic-pasteur\.agents\worker_m5_docker\handoff.md`.
