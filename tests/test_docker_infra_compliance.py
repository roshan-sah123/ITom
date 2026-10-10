"""Read actual deployment files; do not compare against copied specifications."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_routes_public_traffic_through_nginx():
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    assert set(services) == {"postgres", "api", "nginx"}
    assert "ports" not in services["api"] and "ports" not in services["postgres"]
    assert services["nginx"]["ports"]
    assert "./frontend:/usr/share/nginx/html:ro" in services["nginx"]["volumes"]
    assert services["api"]["depends_on"]["postgres"]["condition"] == "service_healthy"


def test_image_runs_current_asgi_application_as_non_root():
    source = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER itom" in source
    assert '"app.main:app"' in source
    assert '"--port", "8000"' in source


def test_image_excludes_local_secrets_and_databases():
    patterns = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for pattern in (".env", ".env.*", "data/*.db", "data/*.json", "outputs/", "scratch/"):
        assert pattern in patterns


def test_proxy_preserves_versioned_api_routes():
    source = (ROOT / "nginx.conf").read_text(encoding="utf-8")
    assert "location /api/" in source
    assert "proxy_pass http://api:8000/api/;" in source


def test_ci_runs_whole_offline_suite():
    workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["offline-tests"]["steps"]
    runs = "\n".join(step.get("run", "") for step in steps)
    assert "requirements-test.txt" in runs
    assert "python -m pytest tests/" in runs
