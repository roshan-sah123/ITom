"""Portal sign-in endpoints for Microsoft Entra ID single sign-on."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.entra_auth import (
    CALLBACK_PATH,
    clear_session_cookie,
    client_id,
    issue_session,
    read_session,
    require_same_origin,
    set_session_cookie,
    tenant_id,
    validate_id_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_token: str = Field(min_length=20, max_length=16384)


@router.get("/config")
def auth_config(response: Response):
    """Public sign-in settings for the browser; these IDs are not secrets."""
    response.headers["Cache-Control"] = "no-store"
    if not settings.AUTH_ENABLED:
        return {"enabled": False}
    config = {"enabled": True, "tenant_id": tenant_id(), "client_id": client_id(), "redirect_path": CALLBACK_PATH}
    if settings.ENTRA_REDIRECT_URI:
        config["redirect_uri"] = settings.ENTRA_REDIRECT_URI
    return config


@router.get("/me")
def current_user(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not settings.AUTH_ENABLED:
        return {"enabled": False}
    session = read_session(request)
    if session is None:
        return {"enabled": True, "authenticated": False}
    return {"enabled": True, "authenticated": True, "name": session["name"], "username": session["username"]}


@router.post("/session")
def create_session(body: SessionInput, request: Request, response: Response):
    """Exchange a verified Microsoft ID token for a signed, HttpOnly portal session."""
    if not settings.AUTH_ENABLED:
        raise HTTPException(404, "Single sign-on is not enabled.")
    require_same_origin(request)
    claims = validate_id_token(body.id_token)
    set_session_cookie(request, response, issue_session(claims))
    response.headers["Cache-Control"] = "no-store"
    return {"enabled": True, "name": claims.get("name") or "", "username": claims.get("preferred_username") or ""}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    require_same_origin(request)
    clear_session_cookie(request, response)
    response.headers["Cache-Control"] = "no-store"
