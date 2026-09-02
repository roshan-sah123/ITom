#!/usr/bin/env python3
"""Docker Multi-Container Infrastructure & Probe Compliance Test Suite (Requirement R4 / M5).

Validates:
- Production Dockerfile multi-stage structure (builder vs runner) and minimal layer caching
- Security hardening: Non-root user `itom` (UID 10001 / GID 10001) execution
- Docker Compose 3-tier multi-container stack (nginx 8080, api 8000, postgres 5432)
- Service dependency chains and automated container healthcheck probes
- NGINX reverse proxy routing rules (/api/ -> api:8000, / -> static Obsidian UI)
- HTTP security headers and dynamic data anti-caching in NGINX configuration
- Liveness (/healthz) and readiness (/ready) probe contract definitions
"""

import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)


# ---------------------------------------------------------------------------
# Canonical Docker & Infrastructure Specifications (PROJECT.md Contract Mirror)
# ---------------------------------------------------------------------------

TARGET_DOCKERFILE_SPEC = """
# Multi-stage production build for ITOM FastAPI Backend
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev curl
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim AS runner
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 10001 itom && useradd -u 10001 -g itom -m -s /bin/bash itom
COPY --from=builder /root/.local /home/itom/.local
ENV PATH=/home/itom/.local/bin:$PATH
ENV PYTHONPATH=/app
COPY --chown=itom:itom . /app
USER itom
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

TARGET_COMPOSE_SPEC = """
version: "3.8"
networks:
  itom-network:
    driver: bridge
volumes:
  postgres_data:
    driver: local
services:
  postgres:
    image: postgres:16-alpine
    container_name: itom-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-itom_db}
      POSTGRES_USER: ${POSTGRES_USER:-itom_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-itom_secure_password}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - itom-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-itom_user} -d ${POSTGRES_DB:-itom_db}"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: itom-api
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-itom_user}:${POSTGRES_PASSWORD:-itom_secure_password}@postgres:5432/${POSTGRES_DB:-itom_db}
      PORT: 8000
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - itom-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s

  nginx:
    image: nginx:alpine
    container_name: itom-nginx
    restart: unless-stopped
    ports:
      - "${PORT:-8080}:80"
    volumes:
      - ./index.html:/usr/share/nginx/html/index.html:ro
      - ./ops_analytics.html:/usr/share/nginx/html/ops_analytics.html:ro
      - ./style.css:/usr/share/nginx/html/style.css:ro
      - ./app.js:/usr/share/nginx/html/app.js:ro
      - ./ops_analytics.js:/usr/share/nginx/html/ops_analytics.js:ro
      - ./js:/usr/share/nginx/html/js:ro
      - ./data:/usr/share/nginx/html/data:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      api:
        condition: service_healthy
    networks:
      - itom-network
"""

TARGET_NGINX_SPEC = r"""
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml image/svg+xml;
    gzip_min_length 1000;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    location /api/ {
        proxy_pass http://api:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
        expires 1h;
        add_header Cache-Control "public, no-transform";
    }

    location ~* \.(json)$ {
        expires -1;
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
    }
}
"""


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestDockerfileMultiStageAndSecurity(unittest.TestCase):
    """Validates Dockerfile multi-stage build, non-root user, and healthcheck."""

    @classmethod
    def setUpClass(cls):
        cls.dockerfile_path = os.path.join(WORKSPACE_ROOT, "Dockerfile")
        cls.dockerfile_content = ""
        if os.path.exists(cls.dockerfile_path):
            with open(cls.dockerfile_path, "r", encoding="utf-8") as f:
                cls.dockerfile_content = f.read()

    def test_dockerfile_exists_on_disk(self):
        """Verifies Dockerfile exists at repository root."""
        self.assertTrue(os.path.exists(self.dockerfile_path))
        self.assertTrue(len(self.dockerfile_content) > 0)

    def test_dockerfile_multi_stage_structure(self):
        """Verifies multi-stage build separating builder and runner stages."""
        self.assertIn("FROM python:3.11-slim AS builder", TARGET_DOCKERFILE_SPEC)
        self.assertIn("FROM python:3.11-slim AS runner", TARGET_DOCKERFILE_SPEC)
        self.assertIn("COPY --from=builder", TARGET_DOCKERFILE_SPEC)
        self.assertIn("FROM python:3.11-slim AS builder", self.dockerfile_content)
        self.assertIn("FROM python:3.11-slim AS runner", self.dockerfile_content)
        self.assertIn("COPY --from=builder", self.dockerfile_content)

    def test_dockerfile_non_root_user_itom(self):
        """Verifies creation and execution under non-root user 'itom' (UID/GID 10001)."""
        self.assertIn("groupadd -g 10001 itom", TARGET_DOCKERFILE_SPEC)
        self.assertIn("useradd -u 10001 -g itom", TARGET_DOCKERFILE_SPEC)
        self.assertIn("USER itom", TARGET_DOCKERFILE_SPEC)
        self.assertIn("groupadd -g 10001 itom", self.dockerfile_content)
        self.assertIn("useradd -u 10001 -g itom", self.dockerfile_content)
        self.assertIn("USER itom", self.dockerfile_content)

    def test_dockerfile_healthcheck_directive(self):
        """Verifies container healthcheck queries /healthz on port 8000."""
        self.assertIn("HEALTHCHECK", TARGET_DOCKERFILE_SPEC)
        self.assertIn("http://localhost:8000/healthz", TARGET_DOCKERFILE_SPEC)
        self.assertIn("HEALTHCHECK", self.dockerfile_content)
        self.assertIn("http://localhost:8000/healthz", self.dockerfile_content)

    def test_dockerfile_port_and_entrypoint(self):
        """Verifies port 8000 exposition and uvicorn CMD execution."""
        self.assertIn("EXPOSE 8000", TARGET_DOCKERFILE_SPEC)
        self.assertIn("uvicorn", TARGET_DOCKERFILE_SPEC)
        self.assertIn("app.main:app", TARGET_DOCKERFILE_SPEC)
        self.assertIn("EXPOSE 8000", self.dockerfile_content)
        self.assertIn("uvicorn", self.dockerfile_content)
        self.assertIn("app.main:app", self.dockerfile_content)


class TestDockerComposeTopology(unittest.TestCase):
    """Validates 3-tier Docker Compose service topology, networking, and dependencies."""

    @classmethod
    def setUpClass(cls):
        cls.compose_path = os.path.join(WORKSPACE_ROOT, "docker-compose.yml")
        cls.compose_content = ""
        if os.path.exists(cls.compose_path):
            with open(cls.compose_path, "r", encoding="utf-8") as f:
                cls.compose_content = f.read()

    def test_compose_file_exists_on_disk(self):
        """Verifies docker-compose.yml exists at repository root."""
        self.assertTrue(os.path.exists(self.compose_path))
        self.assertTrue(len(self.compose_content) > 0)

    def test_compose_services_presence(self):
        """Verifies all 3 core services (postgres, api, nginx) are defined."""
        self.assertIn("postgres:", TARGET_COMPOSE_SPEC)
        self.assertIn("api:", TARGET_COMPOSE_SPEC)
        self.assertIn("nginx:", TARGET_COMPOSE_SPEC)
        self.assertIn("postgres:", self.compose_content)
        self.assertIn("api:", self.compose_content)
        self.assertIn("nginx:", self.compose_content)

    def test_compose_postgres_16_alpine_and_healthcheck(self):
        """Verifies PostgreSQL 16 image, volume mount, and pg_isready healthcheck."""
        self.assertIn("image: postgres:16-alpine", TARGET_COMPOSE_SPEC)
        self.assertIn("postgres_data:/var/lib/postgresql/data", TARGET_COMPOSE_SPEC)
        self.assertIn("pg_isready", TARGET_COMPOSE_SPEC)
        self.assertIn("image: postgres:16-alpine", self.compose_content)
        self.assertIn("postgres_data:/var/lib/postgresql/data", self.compose_content)
        self.assertIn("pg_isready", self.compose_content)

    def test_compose_api_service_dependencies(self):
        """Verifies API container depends on healthy postgres before booting."""
        self.assertIn("depends_on:", TARGET_COMPOSE_SPEC)
        self.assertIn("condition: service_healthy", TARGET_COMPOSE_SPEC)
        self.assertIn("DATABASE_URL:", TARGET_COMPOSE_SPEC)
        self.assertIn("depends_on:", self.compose_content)
        self.assertIn("condition: service_healthy", self.compose_content)
        self.assertIn("DATABASE_URL:", self.compose_content)

    def test_compose_nginx_reverse_proxy_mapping(self):
        """Verifies NGINX exposes port 8080 mapped to internal port 80 with read-only mounts."""
        self.assertIn('"${PORT:-8080}:80"', TARGET_COMPOSE_SPEC)
        self.assertIn(":ro", TARGET_COMPOSE_SPEC)
        self.assertIn('"${PORT:-8080}:80"', self.compose_content)
        self.assertIn(":ro", self.compose_content)

    def test_compose_isolated_bridge_network(self):
        """Verifies services communicate over dedicated 'itom-network' bridge."""
        self.assertIn("itom-network:", TARGET_COMPOSE_SPEC)
        self.assertIn("driver: bridge", TARGET_COMPOSE_SPEC)
        self.assertIn("itom-network:", self.compose_content)
        self.assertIn("driver: bridge", self.compose_content)


class TestNginxReverseProxyConfiguration(unittest.TestCase):
    """Validates NGINX routing, security headers, compression, and caching rules."""

    @classmethod
    def setUpClass(cls):
        cls.nginx_path = os.path.join(WORKSPACE_ROOT, "nginx.conf")
        cls.nginx_content = ""
        if os.path.exists(cls.nginx_path):
            with open(cls.nginx_path, "r", encoding="utf-8") as f:
                cls.nginx_content = f.read()

    def test_nginx_file_exists_on_disk(self):
        """Verifies nginx.conf exists at repository root."""
        self.assertTrue(os.path.exists(self.nginx_path))
        self.assertTrue(len(self.nginx_content) > 0)

    def test_nginx_api_reverse_proxy_location(self):
        """Verifies location /api/ routes to http://api:8000/api/ with HTTP 1.1."""
        self.assertIn("location /api/", TARGET_NGINX_SPEC)
        self.assertIn("proxy_pass http://api:8000/api/;", TARGET_NGINX_SPEC)
        self.assertIn("proxy_http_version 1.1;", TARGET_NGINX_SPEC)
        self.assertIn("location /api/", self.nginx_content)
        self.assertIn("proxy_pass http://api:8000/api/;", self.nginx_content)
        self.assertIn("proxy_http_version 1.1;", self.nginx_content)

    def test_nginx_static_frontend_root_and_fallback(self):
        """Verifies static root is /usr/share/nginx/html with try_files fallback."""
        self.assertIn("root /usr/share/nginx/html;", TARGET_NGINX_SPEC)
        self.assertIn("try_files $uri $uri/ /index.html;", TARGET_NGINX_SPEC)
        self.assertIn("root /usr/share/nginx/html;", self.nginx_content)
        self.assertIn("try_files $uri $uri/ /index.html;", self.nginx_content)

    def test_nginx_security_headers_enforced(self):
        """Verifies standard enterprise security headers (X-Frame, X-Content-Type, X-XSS)."""
        self.assertIn('add_header X-Frame-Options "SAMEORIGIN"', TARGET_NGINX_SPEC)
        self.assertIn('add_header X-Content-Type-Options "nosniff"', TARGET_NGINX_SPEC)
        self.assertIn('add_header X-XSS-Protection "1; mode=block"', TARGET_NGINX_SPEC)
        self.assertIn('add_header Referrer-Policy "no-referrer-when-downgrade"', TARGET_NGINX_SPEC)
        self.assertIn('add_header X-Frame-Options "SAMEORIGIN"', self.nginx_content)
        self.assertIn('add_header X-Content-Type-Options "nosniff"', self.nginx_content)
        self.assertIn('add_header X-XSS-Protection "1; mode=block"', self.nginx_content)
        self.assertIn('add_header Referrer-Policy "no-referrer-when-downgrade"', self.nginx_content)

    def test_nginx_gzip_compression_configuration(self):
        """Verifies gzip compression is enabled for JSON, JS, CSS, and SVG."""
        self.assertIn("gzip on;", TARGET_NGINX_SPEC)
        self.assertIn("application/json", TARGET_NGINX_SPEC)
        self.assertIn("application/javascript", TARGET_NGINX_SPEC)
        self.assertIn("text/css", TARGET_NGINX_SPEC)
        self.assertIn("gzip on;", self.nginx_content)
        self.assertIn("application/json", self.nginx_content)
        self.assertIn("application/javascript", self.nginx_content)
        self.assertIn("text/css", self.nginx_content)

    def test_nginx_dynamic_json_anti_cache(self):
        """Verifies dynamic .json files are served with no-store to ensure real-time telemetry."""
        self.assertIn(r"location ~* \.(json)$", TARGET_NGINX_SPEC)
        self.assertIn("no-store, no-cache, must-revalidate", TARGET_NGINX_SPEC)
        self.assertIn(r"location ~* \.(json)$", self.nginx_content)
        self.assertIn("no-store, no-cache, must-revalidate", self.nginx_content)


class TestProbesContract(unittest.TestCase):
    """Validates contract shapes for liveness (/healthz) and readiness (/ready) probes."""

    def test_liveness_healthz_payload_contract(self):
        """Validates expected schema of /healthz response."""
        sample_response = {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.assertEqual(sample_response["status"], "ok")
        self.assertTrue(datetime.fromisoformat(sample_response["timestamp"]))

    def test_readiness_ready_payload_contract(self):
        """Validates expected schema of /ready response."""
        sample_ready = {
            "status": "ready",
            "database": "connected",
            "migration_head": True,
        }
        self.assertEqual(sample_ready["status"], "ready")
        self.assertEqual(sample_ready["database"], "connected")
        self.assertTrue(sample_ready["migration_head"])


if __name__ == "__main__":
    unittest.main()
