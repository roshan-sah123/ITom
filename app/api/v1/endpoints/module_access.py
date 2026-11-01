import hmac
import hashlib
import secrets
import time
import logging
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.endpoints.location_reviews import local_client
from app.core.config import settings

router = APIRouter(prefix="/modules/access", tags=["Module access"])
COOKIE = "itom_module_access"
SESSION_SECONDS = 8 * 60 * 60
logger = logging.getLogger("itom.module_access")


def shared_request(request: Request):
    expected = settings.MODULE_SHARED_ORIGIN.rstrip("/")
    parsed = urlsplit(expected)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.path
            or parsed.query or parsed.fragment or parsed.username or parsed.password
            or request.url.netloc != parsed.netloc):
        logger.warning("Shared module host rejected: received=%r configured=%r", request.url.netloc, parsed.netloc)
        raise HTTPException(403, "Shared modules are available only on the configured portal domain.")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != expected:
        raise HTTPException(403, "Use this portal origin for module requests.")
    if request.headers.get("sec-fetch-site") not in (None, "none", "same-origin"):
        raise HTTPException(403, "Cross-origin module requests are forbidden.")
    if request.method not in {"GET", "HEAD"} and not origin:
        raise HTTPException(403, "Module writes require this portal Origin.")
    if not settings.MODULE_NETWORK_ACCESS and (not settings.MODULE_SHARED_ACCESS_KEY or not settings.SECRET_KEY):
        logger.error("Shared module access key/session secret is not configured")
        raise HTTPException(503, "Shared module access is not configured.")


def signature(payload: str) -> str:
    secret = settings.SECRET_KEY
    if not secret:
        logger.error("Shared module session secret is unavailable")
        raise HTTPException(503, "Shared module access is not configured.")
    material = f"{settings.MODULE_SHARED_ORIGIN}\n{settings.MODULE_SHARED_ACCESS_KEY}\n{payload}"
    return hmac.new(secret.encode(), material.encode(), hashlib.sha256).hexdigest()


def authorized(request: Request) -> bool:
    cookie = request.cookies.get(COOKIE, "")
    parts = cookie.split(".")
    if len(parts) != 3:
        return False
    expiry, nonce, supplied = parts
    if not expiry.isdigit() or len(expiry) > 12 or len(nonce) != 32 or len(supplied) != 64:
        return False
    if not all(char in "0123456789abcdef" for char in nonce + supplied) or not expiry.isascii():
        return False
    remaining = int(expiry) - time.time()
    return 0 < remaining <= SESSION_SECONDS and hmac.compare_digest(signature(f"{expiry}.{nonce}"), supplied)


def require_local_module(request: Request, label: str):
    if not local_client(request):
        if not settings.MODULE_SHARED_ORIGIN:
            raise HTTPException(403, f"{label} is local-only until authenticated access is configured.")
        shared_request(request)
        if not settings.MODULE_NETWORK_ACCESS and not authorized(request):
            raise HTTPException(401, "Enter the shared module access key to open this workspace.")
        return
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, f"Use this portal origin for {label} requests.")
    if request.headers.get("sec-fetch-site") not in (None, "none", "same-origin"):
        raise HTTPException(403, f"Cross-origin {label} requests are forbidden.")
    if request.method not in {"GET", "HEAD"} and not origin:
        raise HTTPException(403, f"{label} writes require this portal Origin.")


def require_inventory_key(request: Request, label: str):
    require_local_module(request, label)
    token = settings.CMDB_INVENTORY_ADMIN_TOKEN
    if not token:
        raise HTTPException(503, "Configure CMDB_INVENTORY_ADMIN_TOKEN to enable validation/administration.")
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if scheme.casefold() != "bearer" or not hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8")):
        raise HTTPException(401, "A valid CMDB admin key is required.", headers={"WWW-Authenticate": "Bearer"})


class AccessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=256)


@router.get("")
def access_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if local_client(request):
        return {"authorized": True, "local": True}
    shared_request(request)
    if settings.MODULE_NETWORK_ACCESS:
        return {"authorized": True, "local": False, "network": True}
    return {"authorized": authorized(request), "local": False}


@router.post("")
def sign_in(body: AccessInput, request: Request, response: Response):
    shared_request(request)
    key = settings.MODULE_SHARED_ACCESS_KEY
    if not key or not hmac.compare_digest(body.key.encode(), key.encode()):
        logger.warning("Shared module sign-in rejected")
        raise HTTPException(401, "The shared module access key is incorrect.")
    payload = f"{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(16)}"
    response.set_cookie(COOKIE, f"{payload}.{signature(payload)}", max_age=SESSION_SECONDS,
                        path="/api/v1", httponly=True, secure=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"authorized": True, "local": False}


@router.delete("", status_code=204)
def sign_out(request: Request, response: Response):
    shared_request(request)
    response.delete_cookie(COOKIE, path="/api/v1", secure=True, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
