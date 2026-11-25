"""Microsoft Entra ID single sign-on: token validation, session cookie and API guard."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import entra_auth
from app.core.config import Settings, settings

TENANT = "b727a530-a0d5-4fb8-bd40-d8f9763e97db"
CLIENT = "594702a7-2bd8-4692-95bc-cbcd9f28424f"
ORIGIN = {"Origin": "http://test"}
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def id_token(key=SIGNING_KEY, **overrides):
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT, "tid": TENANT,
        "sub": "subject-1", "oid": "object-1", "name": "Test Operator",
        "preferred_username": "operator@example.com", "iat": now, "nbf": now, "exp": now + 3600,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.fixture
def sso(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "ENTRA_TENANT_ID", TENANT)
    monkeypatch.setattr(settings, "ENTRA_CLIENT_ID", CLIENT.upper())
    monkeypatch.setattr(settings, "SECRET_KEY", "s" * 48)
    monkeypatch.setattr(entra_auth.signing_keys, "_keys", {"test-kid": SIGNING_KEY.public_key()})
    monkeypatch.setattr(entra_auth.signing_keys, "_fetched_at", time.time())


async def sign_in(client, token=None):
    return await client.post("/api/v1/auth/session", json={"id_token": token or id_token()}, headers=ORIGIN)


async def test_disabled_sso_leaves_portal_open(api_client):
    assert (await api_client.get("/api/v1/auth/config")).json() == {"enabled": False}
    assert (await api_client.get("/api/v1/system/freshness")).status_code == 200
    assert (await api_client.post("/api/v1/auth/session", json={"id_token": id_token()}, headers=ORIGIN)).status_code == 404
    assert '<meta name="itom-auth" content="off" />' in (await api_client.get("/")).text


async def test_enabled_sso_shell_does_not_skip_sign_in(api_client, sso):
    for path in ("/", "/oauth2callback"):
        page = await api_client.get(path)
        assert page.status_code == 200 and "Coforge ITOM Operations Portal" in page.text
        assert "itom-auth" not in page.text


async def test_enabled_sso_requires_session_for_api_and_docs(api_client, sso):
    for path in ("/api/v1/system/freshness", "/api/v1/cmdb/summary", "/api/v1/assets/summary", "/docs", "/openapi.json"):
        response = await api_client.get(path)
        assert response.status_code == 401, path
        assert response.headers["cache-control"] == "no-store"
    for path in ("/ready", "/health", "/api/v1/health", "/", "/oauth2callback"):
        assert (await api_client.get(path)).status_code == 200, path
    config = (await api_client.get("/api/v1/auth/config")).json()
    assert config == {"enabled": True, "tenant_id": TENANT, "client_id": CLIENT, "redirect_path": "/oauth2callback"}
    assert (await api_client.get("/api/v1/auth/me")).json() == {"enabled": True, "authenticated": False}


async def test_valid_id_token_creates_http_only_session(api_client, sso):
    response = await sign_in(api_client)
    assert response.status_code == 200
    assert response.json()["username"] == "operator@example.com"
    cookie = response.headers["set-cookie"]
    assert "itom_session=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
    assert (await api_client.get("/api/v1/system/freshness")).status_code == 200
    me = (await api_client.get("/api/v1/auth/me")).json()
    assert me == {"enabled": True, "authenticated": True, "name": "Test Operator", "username": "operator@example.com"}


@pytest.mark.parametrize("token", [
    id_token(aud="00000000-0000-0000-0000-000000000000"),
    id_token(iss="https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0"),
    id_token(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200, nbf=int(time.time()) - 7200),
    id_token(key=OTHER_KEY),
])
async def test_untrusted_tokens_are_rejected(api_client, sso, token):
    response = await sign_in(api_client, token)
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert (await api_client.get("/api/v1/system/freshness")).status_code == 401


async def test_other_tenant_account_is_rejected(api_client, sso):
    response = await sign_in(api_client, id_token(tid="00000000-0000-0000-0000-000000000000"))
    assert response.status_code == 403


async def test_session_creation_requires_portal_origin(api_client, sso):
    assert (await api_client.post("/api/v1/auth/session", json={"id_token": id_token()})).status_code == 403
    foreign = {"Origin": "https://evil.example"}
    assert (await api_client.post("/api/v1/auth/session", json={"id_token": id_token()}, headers=foreign)).status_code == 403


async def test_session_behind_tls_proxy_is_accepted_and_secure(api_client, sso):
    """IIS terminates HTTPS and forwards over HTTP to the app, preserving Host."""
    proxied = {"Host": "itom.coforge.com", "Origin": "https://itom.coforge.com"}
    response = await api_client.post("/api/v1/auth/session", json={"id_token": id_token()}, headers=proxied)
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
    spoofed = {"Host": "itom.coforge.com", "Origin": "https://itom.coforge.com.evil.example"}
    assert (await api_client.post("/api/v1/auth/session", json={"id_token": id_token()}, headers=spoofed)).status_code == 403


async def test_configured_redirect_uri_is_published(api_client, sso, monkeypatch):
    monkeypatch.setattr(settings, "ENTRA_REDIRECT_URI", "https://itom.coforge.com/oauth2callback")
    config = (await api_client.get("/api/v1/auth/config")).json()
    assert config["redirect_uri"] == "https://itom.coforge.com/oauth2callback"


async def test_tampered_or_foreign_session_cookie_is_rejected(api_client, sso, monkeypatch):
    await sign_in(api_client)
    value = api_client.cookies.get("itom_session")
    body, _, signature = value.partition(".")
    api_client.cookies.set("itom_session", f"{body}x.{signature}")
    assert (await api_client.get("/api/v1/system/freshness")).status_code == 401
    api_client.cookies.set("itom_session", value)
    monkeypatch.setattr(settings, "SECRET_KEY", "t" * 48)
    assert (await api_client.get("/api/v1/system/freshness")).status_code == 401


async def test_logout_ends_session(api_client, sso):
    await sign_in(api_client)
    response = await api_client.post("/api/v1/auth/logout", headers=ORIGIN)
    assert response.status_code == 204
    assert "itom_session=" in response.headers["set-cookie"]
    assert (await api_client.get("/api/v1/system/freshness")).status_code == 401


@pytest.mark.parametrize("overrides", [
    {"ENTRA_TENANT_ID": "", "ENTRA_CLIENT_ID": CLIENT, "SECRET_KEY": "s" * 48},
    {"ENTRA_TENANT_ID": TENANT, "ENTRA_CLIENT_ID": "not-a-guid", "SECRET_KEY": "s" * 48},
    {"ENTRA_TENANT_ID": TENANT, "ENTRA_CLIENT_ID": CLIENT, "SECRET_KEY": "short"},
    {"ENTRA_TENANT_ID": TENANT, "ENTRA_CLIENT_ID": CLIENT, "SECRET_KEY": "s" * 48,
     "ENTRA_REDIRECT_URI": "http://itom.coforge.com/oauth2callback"},
    {"ENTRA_TENANT_ID": TENANT, "ENTRA_CLIENT_ID": CLIENT, "SECRET_KEY": "s" * 48,
     "ENTRA_REDIRECT_URI": "https://itom.coforge.com/other"},
])
def test_enabled_sso_requires_valid_configuration(overrides):
    with pytest.raises(ValueError):
        Settings(_env_file=None, AUTH_ENABLED=True, **overrides)
