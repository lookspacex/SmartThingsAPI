from __future__ import annotations

import datetime as dt
import base64
import hashlib
import secrets
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import SmartThingsToken
from app.oauth_state import build_state, parse_state
from app.security import get_current_user

router = APIRouter(prefix="/oauth/smartthings", tags=["smartthings-oauth"])

def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

def _is_json_requested(request: Request, format: Optional[str]) -> bool:
    if isinstance(format, str) and format.lower() == "json":
        return True
    # Prefer HTML redirects for browsers/webviews by default.
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return False
    return "application/json" in accept

def _done_url(request: Request, *, status: str, params: dict[str, Any]) -> str:
    base = str(request.base_url).rstrip("/")
    query = urlencode({**params, "status": status}, doseq=True)
    return f"{base}/oauth/smartthings/done?{query}"


@router.get("/authorize")
def authorize(user=Depends(get_current_user)) -> RedirectResponse:
    """
    Redirect user to SmartThings OAuth authorize page.
    Requires the caller to be authenticated to *our* service (X-API-Key).
    """
    if not settings.smartthings_client_id or not settings.smartthings_redirect_uri:
        raise HTTPException(status_code=500, detail="SmartThings OAuth is not configured")

    # PKCE support (some SmartThings OAuth flows require it; harmless if ignored).
    pkce_verifier = secrets.token_urlsafe(48)
    pkce_challenge = _pkce_challenge(pkce_verifier)
    state = build_state(user_id=user.id, pkce_verifier=pkce_verifier)
    params = {
        "client_id": settings.smartthings_client_id,
        "response_type": "code",
        "redirect_uri": settings.smartthings_redirect_uri,
        "scope": settings.smartthings_oauth_scope,
        "state": state,
        "code_challenge": pkce_challenge,
        "code_challenge_method": "S256",
    }
    # RedirectResponse will encode params properly if we build the URL ourselves:
    req = requests.Request("GET", settings.smartthings_oauth_authorize_url, params=params).prepare()
    return RedirectResponse(url=str(req.url), status_code=302)


@router.get("/callback")
def callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    format: Optional[str] = Query(None, description="Use format=json to return JSON instead of redirect"),
    db: Session = Depends(get_db),
) -> Any:
    """
    OAuth redirect URI target.
    Exchanges code for tokens and stores them for the user embedded in the signed state.
    """
    if not settings.smartthings_client_id or not settings.smartthings_client_secret or not settings.smartthings_redirect_uri:
        raise HTTPException(status_code=500, detail="SmartThings OAuth is not configured")

    # SmartThings may redirect back with error params instead of code.
    if error:
        if _is_json_requested(request, format):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": error,
                    "error_description": error_description or "",
                },
            )
        return RedirectResponse(
            url=_done_url(
                request,
                status="error",
                params={"code": error, "message": error_description or ""},
            ),
            status_code=302,
        )

    if not code:
        if _is_json_requested(request, format):
            raise HTTPException(status_code=400, detail="Missing OAuth query parameter: code")
        return RedirectResponse(
            url=_done_url(request, status="error", params={"code": "missing_code", "message": "Missing OAuth code"}),
            status_code=302,
        )
    if not state:
        if _is_json_requested(request, format):
            raise HTTPException(status_code=400, detail="Missing OAuth query parameter: state")
        return RedirectResponse(
            url=_done_url(request, status="error", params={"code": "missing_state", "message": "Missing OAuth state"}),
            status_code=302,
        )

    try:
        payload = parse_state(state)
        user_id = payload["userId"]
    except Exception as e:
        if _is_json_requested(request, format):
            raise HTTPException(status_code=400, detail=f"Invalid state: {e}") from e
        return RedirectResponse(
            url=_done_url(request, status="error", params={"code": "invalid_state", "message": str(e)}),
            status_code=302,
        )

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.smartthings_redirect_uri,
    }
    pkce_verifier = payload.get("pkceVerifier")
    if isinstance(pkce_verifier, str) and pkce_verifier:
        data["code_verifier"] = pkce_verifier
    try:
        resp = requests.post(
            settings.smartthings_oauth_token_url,
            data=data,
            auth=(settings.smartthings_client_id, settings.smartthings_client_secret),
            timeout=settings.smartthings_timeout_s,
        )
    except requests.RequestException as e:
        if _is_json_requested(request, format):
            raise HTTPException(status_code=502, detail=f"Failed to reach SmartThings token endpoint: {e}") from e
        return RedirectResponse(
            url=_done_url(request, status="error", params={"code": "token_endpoint_unreachable", "message": str(e)}),
            status_code=302,
        )

    if resp.status_code < 200 or resp.status_code >= 300:
        detail: Any
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        if _is_json_requested(request, format):
            raise HTTPException(status_code=resp.status_code, detail=detail)
        msg = detail if isinstance(detail, str) else ""
        return RedirectResponse(
            url=_done_url(
                request,
                status="error",
                params={"code": "token_exchange_failed", "upstreamStatus": int(resp.status_code), "message": msg},
            ),
            status_code=302,
        )

    token_json = resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        if _is_json_requested(request, format):
            raise HTTPException(status_code=500, detail="Token response missing access_token")
        return RedirectResponse(
            url=_done_url(request, status="error", params={"code": "missing_access_token", "message": "No access_token"}),
            status_code=302,
        )

    refresh_token = token_json.get("refresh_token", "") or ""
    token_type = token_json.get("token_type", "Bearer") or "Bearer"
    scope = token_json.get("scope", "") or ""
    expires_in = token_json.get("expires_in")
    expires_at = None
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(expires_in))

    existing = db.query(SmartThingsToken).filter(SmartThingsToken.user_id == user_id).one_or_none()
    if existing:
        existing.access_token = access_token
        existing.refresh_token = refresh_token
        existing.token_type = token_type
        existing.scope = scope
        existing.expires_at = expires_at
    else:
        db.add(
            SmartThingsToken(
                user_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_type=token_type,
                scope=scope,
                expires_at=expires_at,
            )
        )
    db.commit()

    if _is_json_requested(request, format):
        return {"userId": user_id, "stored": True}
    return RedirectResponse(
        url=_done_url(request, status="ok", params={"userId": user_id, "stored": "true"}),
        status_code=302,
    )


@router.get("/done", response_class=HTMLResponse)
def done(
    status: str = Query(..., description="ok|error"),
    userId: Optional[str] = Query(None),
    stored: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    message: Optional[str] = Query(None),
    upstreamStatus: Optional[int] = Query(None),
) -> HTMLResponse:
    # Human-friendly landing page for WebView; native apps can intercept the URL and close the view.
    safe_status = status if status in {"ok", "error"} else "error"
    title = "SmartThings Authorization"
    if safe_status == "ok":
        body = f"""
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
  <body>
    <h3>{title}</h3>
    <p>Status: <b>OK</b></p>
    <p>You can close this window.</p>
    <pre>{{
  "status": "ok",
  "userId": "{userId or ""}",
  "stored": {str((stored or "").lower() == "true").lower()}
}}</pre>
  </body>
</html>
""".strip()
        return HTMLResponse(content=body, status_code=200)

    details: dict[str, Any] = {"status": "error"}
    if code:
        details["code"] = code
    if message:
        details["message"] = message
    if upstreamStatus is not None:
        details["upstreamStatus"] = upstreamStatus

    body = f"""
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
  <body>
    <h3>{title}</h3>
    <p>Status: <b>ERROR</b></p>
    <p>You can close this window.</p>
    <pre>{details}</pre>
  </body>
</html>
""".strip()
    return HTMLResponse(content=body, status_code=200)
