"""Microsoft Entra ID single sign-on: ID token validation and signed portal sessions."""

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import jwt
import requests
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from src.sync.source_transport import proxy_request_options

logger = logging.getLogger("itom.auth")

SESSION_COOKIE = "itom_session"
CALLBACK_PATH = "/oauth2callback"
_PUBLIC_PATHS = {
    "/health", "/healthz", "/ready", "/ready/modules",
    "/api/v1/health", "/api/v1/healthz", "/api/v1/ready", "/api/v1/ready/modules",
}
_PROTECTED_PREFIXES = ("/api/", "/docs", "/redoc", "/openapi.json")
_KEY_TTL_SECONDS = 3600
_KEY_REFRESH_FLOOR_SECONDS = 300


def tenant_id() -> str:
    return (settings.ENTRA_TENANT_ID or "").strip().lower()


def client_id() -> str:
    return (settings.ENTRA_CLIENT_ID or "").strip().lower()


class SigningKeys:
    """Entra signing keys, cached and refreshed at most every five minutes for unknown key IDs."""

    def __init__(self) -> None:
        self._keys: Dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def get(self, kid: str) -> Any:
        with self._lock:
            age = time.time() - self._fetched_at
            if age > _KEY_TTL_SECONDS or (kid not in self._keys and age > _KEY_REFRESH_FLOOR_SECONDS):
                self._refresh()
            key = self._keys.get(kid)
        if key is None:
            raise HTTPException(401, "Microsoft sign-in token was signed by an unknown key.")
        return key

    def _refresh(self) -> None:
        url = f"https://login.microsoftonline.com/{tenant_id()}/discovery/v2.0/keys"
        response = requests.get(url, timeout=10, **proxy_request_options(url, settings))
        response.raise_for_status()
        self._keys = {
            item["kid"]: jwt.PyJWK(item).key
            for item in response.json().get("keys", [])
            if item.get("kid") and item.get("kty") == "RSA"
        }
        self._fetched_at = time.time()

    def clear(self) -> None:
        with self._lock:
            self._keys, self._fetched_at = {}, 0.0


signing_keys = SigningKeys()


def validate_id_token(token: str) -> Dict[str, Any]:
    """Return verified claims for an Entra ID token issued to this app in the configured tenant."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise HTTPException(401, "Microsoft sign-in token is not a supported ID token.")
        key = signing_keys.get(header["kid"])
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=client_id(),
            issuer=f"https://login.microsoftonline.com/{tenant_id()}/v2.0",
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "tid"]},
            leeway=60,
        )
    except HTTPException:
        raise
    except (requests.RequestException, RuntimeError):
        logger.exception("Microsoft signing keys are unavailable")
        raise HTTPException(503, "Microsoft sign-in keys are unavailable. Try again shortly.")
    except jwt.PyJWTError as error:
        logger.warning("Rejected Microsoft sign-in token: %s", type(error).__name__)
        raise HTTPException(401, "Microsoft sign-in token is invalid or expired. Sign in again.")
    if str(claims.get("tid", "")).lower() != tenant_id():
        raise HTTPException(403, "This account does not belong to the configured organization.")
    return claims


def _signature(body: str) -> str:
    material = f"itom-session\n{tenant_id()}\n{client_id()}\n{body}"
    return hmac.new((settings.SECRET_KEY or "").encode(), material.encode(), hashlib.sha256).hexdigest()


def issue_session(claims: Dict[str, Any]) -> str:
    now = int(time.time())
    payload = {
        "sub": claims.get("oid") or claims["sub"],
        "name": str(claims.get("name") or "")[:128],
        "username": str(claims.get("preferred_username") or claims.get("email") or "")[:256],
        "iat": now,
        "exp": now + settings.AUTH_SESSION_HOURS * 3600,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    return f"{body}.{_signature(body)}"


def read_session(request: Request) -> Optional[Dict[str, Any]]:
    value = request.cookies.get(SESSION_COOKIE, "")
    body, _, supplied = value.partition(".")
    if not body or len(value) > 4096 or len(supplied) != 64:
        return None
    if not hmac.compare_digest(_signature(body), supplied):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, UnicodeDecodeError):
        return None
    now = time.time()
    if not isinstance(payload, dict) or not isinstance(payload.get("exp"), int):
        return None
    if not now < payload["exp"] <= now + settings.AUTH_SESSION_HOURS * 3600:
        return None
    return payload


def _is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    origin = request.headers.get("origin", "").lower()
    return request.url.scheme == "https" or forwarded == "https" or origin.startswith("https://")


def set_session_cookie(request: Request, response: Response, value: str) -> None:
    response.set_cookie(SESSION_COOKIE, value, max_age=settings.AUTH_SESSION_HOURS * 3600, path="/",
                        httponly=True, secure=_is_https(request), samesite="strict")


def clear_session_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=_is_https(request), samesite="strict")


def require_same_origin(request: Request) -> None:
    """Session changes must come from this portal's own pages.

    Only the host is compared: a TLS-terminating proxy (IIS) forwards HTTPS
    requests to the app over HTTP while preserving the Host header.
    """
    origin = urlsplit(request.headers.get("origin", ""))
    host = request.headers.get("host", "").lower()
    if origin.scheme not in ("http", "https") or not host or origin.netloc.lower() != host:
        raise HTTPException(403, "Sign-in requests must come from this portal.")


def requires_session(path: str) -> bool:
    if path in _PUBLIC_PATHS or path.startswith("/api/v1/auth/"):
        return False
    return path.startswith(_PROTECTED_PREFIXES)


class EntraAuthMiddleware:
    """Reject API and API-documentation requests without a valid portal session when SSO is enabled."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] == "http" and settings.AUTH_ENABLED and scope.get("method") != "OPTIONS"
                and requires_session(scope["path"]) and read_session(Request(scope)) is None):
            response = JSONResponse(
                {"error": "Authentication required", "detail": "Sign in with your organizational Microsoft account."},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
