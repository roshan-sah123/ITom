"""Check local service environment and service-aware readiness probes."""
from scripts import local_itom_supervisor as supervisor


def test_service_environment_removes_refused_loopback_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://corporate-proxy.example:8080")

    env = supervisor.service_environment()

    assert "HTTP_PROXY" not in env
    assert env["HTTPS_PROXY"] == "http://corporate-proxy.example:8080"


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.body


class FakeOpener:
    def __init__(self, responses):
        self.responses = responses

    def open(self, request, timeout):
        assert timeout == 3
        from urllib.parse import urlparse

        return FakeResponse(self.responses[urlparse(request.full_url).path])


def test_single_port_readiness_requires_database_migrations_and_portal(monkeypatch):
    monkeypatch.setattr(
        supervisor,
        "build_opener",
        lambda *_args: FakeOpener({
            "/ready": b'{"status":"ready","database":"connected","migration_head":true}',
            "/": b"<title>Coforge ITOM Operations Portal</title>",
        }),
    )
    assert supervisor.service_is_ready(supervisor.LOCAL_PORT)

    monkeypatch.setattr(
        supervisor,
        "build_opener",
        lambda *_args: FakeOpener({
            "/ready": b'{"status":"not_ready","database":"connected","migration_head":false}',
            "/": b"<title>Coforge ITOM Operations Portal</title>",
        }),
    )
    assert not supervisor.service_is_ready(supervisor.LOCAL_PORT)


def test_single_port_readiness_rejects_a_non_portal_root(monkeypatch):
    monkeypatch.setattr(
        supervisor,
        "build_opener",
        lambda *_args: FakeOpener({
            "/ready": b'{"status":"ready","database":"connected","migration_head":true}',
            "/": b"<title>Unrelated website</title>",
        }),
    )
    assert not supervisor.service_is_ready(supervisor.LOCAL_PORT)
