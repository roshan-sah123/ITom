import pytest

from app.core.config import Settings
from src.sync.source_transport import proxy_request_options, proxy_diagnostics


def test_direct_proxy_mode_is_explicit_and_sanitized():
    config = Settings(_env_file=None, SOURCE_PROXY_MODE="direct")
    assert proxy_request_options("https://graph.microsoft.com/v1.0", config)["proxies"]["https"] == ""
    diagnostic = proxy_diagnostics("https://graph.microsoft.com/v1.0", config)
    assert diagnostic["proxy_mode"] == "direct"
    assert "proxy" not in str(diagnostic).lower() or "configured" in str(diagnostic).lower()


def test_no_proxy_requires_explicit_direct_permission():
    config = Settings(_env_file=None, SOURCE_NO_PROXY="graph.microsoft.com")
    with pytest.raises(RuntimeError):
        proxy_request_options("https://graph.microsoft.com/v1.0", config)
    allowed = Settings(_env_file=None, SOURCE_NO_PROXY="graph.microsoft.com", SOURCE_ALLOW_DIRECT=True)
    assert proxy_request_options("https://graph.microsoft.com/v1.0", allowed)["proxies"]["https"] == ""
