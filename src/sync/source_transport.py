"""Sanitized, per-request source proxy routing helpers."""
from urllib.parse import urlparse

from requests.utils import should_bypass_proxies


def proxy_request_options(url: str, config) -> dict:
    """Return safe requests kwargs, honoring configured no-proxy destinations."""
    no_proxy = [entry.strip() for entry in (config.SOURCE_NO_PROXY or "").split(",") if entry.strip()]
    hostname = urlparse(url).hostname or ""
    bypass = bool(no_proxy and should_bypass_proxies(url, no_proxy=",".join(no_proxy)))
    mode = (config.SOURCE_PROXY_MODE or "inherit").strip().lower()
    if mode not in {"inherit", "explicit", "direct"}:
        raise ValueError("SOURCE_PROXY_MODE must be inherit, explicit, or direct")
    if mode == "direct" or bypass or not config.SOURCE_PROXY_INHERIT:
        if mode != "direct" and not config.SOURCE_ALLOW_DIRECT:
            raise RuntimeError(f"Direct source access is not permitted for configured destination {hostname}")
        return {"proxies": {"http": "", "https": ""}}
    return {}


def proxy_diagnostics(url: str, config) -> dict:
    no_proxy = [entry.strip() for entry in (config.SOURCE_NO_PROXY or "").split(",") if entry.strip()]
    bypass = bool(no_proxy and should_bypass_proxies(url, no_proxy=",".join(no_proxy)))
    return {
        "proxy_inheritance_enabled": bool(config.SOURCE_PROXY_INHERIT),
        "proxy_mode": config.SOURCE_PROXY_MODE,
        "explicit_proxy_configured": bool(config.SOURCE_HTTP_PROXY or config.SOURCE_HTTPS_PROXY),
        "destination_matches_no_proxy": bypass,
    }
