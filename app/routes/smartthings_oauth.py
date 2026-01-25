from __future__ import annotations

import datetime as dt
import base64
import hashlib
import secrets
from typing import Any, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
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
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
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
        raise HTTPException(
            status_code=400,
            detail={
                "error": error,
                "error_description": error_description or "",
            },
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth query parameter: code")
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth query parameter: state")

    try:
        payload = parse_state(state)
        user_id = payload["userId"]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid state: {e}") from e

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
        raise HTTPException(status_code=502, detail=f"Failed to reach SmartThings token endpoint: {e}") from e

    if resp.status_code < 200 or resp.status_code >= 300:
        detail: Any
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    token_json = resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise HTTPException(status_code=500, detail="Token response missing access_token")

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

    return {"userId": user_id, "stored": True}

