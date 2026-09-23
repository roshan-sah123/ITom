"""Ensure the local service removes only the known-bad sandbox proxy."""
from scripts.local_itom_supervisor import service_environment


def test_service_environment_removes_refused_loopback_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://corporate-proxy.example:8080")

    env = service_environment()

    assert "HTTP_PROXY" not in env
    assert env["HTTPS_PROXY"] == "http://corporate-proxy.example:8080"
