import hmac

from fastapi import HTTPException, Request

from app.api.v1.endpoints.location_reviews import local_client
from app.core.config import settings


def require_local_module(request: Request, label: str):
    if not local_client(request):
        raise HTTPException(403, f"{label} is local-only until authenticated access is configured.")
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
