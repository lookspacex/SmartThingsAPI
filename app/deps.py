from __future__ import annotations

from functools import lru_cache

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import SmartThingsToken, User
from app.smartthings_client import SmartThingsClient


@lru_cache(maxsize=1)
def _get_default_smartthings_client() -> SmartThingsClient:
    if not settings.smartthings_token:
        raise RuntimeError("SMARTTHINGS_TOKEN is not configured")
    return SmartThingsClient(
        token=settings.smartthings_token,
        base_url=settings.smartthings_base_url,
        timeout_s=settings.smartthings_timeout_s,
    )


def _get_token_from_headers(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            return token
    token2 = request.headers.get("x-smartthings-token") or request.headers.get("X-SmartThings-Token")
    if token2:
        return token2.strip()
    return None


def get_smartthings_client(request: Request, db: Session = Depends(get_db)) -> SmartThingsClient:
    """
    Resolve SmartThings token in this order:
    1) Authorization: Bearer <token>
    2) X-SmartThings-Token: <token>
    3) SmartThings token stored for the authenticated user (SaaS)
    4) SMARTTHINGS_TOKEN from env/.env
    """
    token = _get_token_from_headers(request)
    if token:
        return SmartThingsClient(token=token, base_url=settings.smartthings_base_url, timeout_s=settings.smartthings_timeout_s)

    # SaaS: if request has X-API-Key, we can resolve user and fetch stored SmartThings token
    x_api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if x_api_key:
        from app.security import hash_api_key  # local import to avoid cycles

        user = db.query(User).filter(User.api_key_hash == hash_api_key(x_api_key)).one_or_none()
        if user:
            st = db.query(SmartThingsToken).filter(SmartThingsToken.user_id == user.id).one_or_none()
            if st and st.access_token:
                # Auto-refresh if token is expired / near expiry (best-effort).
                if st.expires_at is not None:
                    import datetime as dt

                    now = dt.datetime.now(dt.timezone.utc)
                    # refresh 60s before expiry to avoid races
                    if now >= (st.expires_at - dt.timedelta(seconds=60)):
                        if not st.refresh_token:
                            raise HTTPException(
                                status_code=401,
                                detail={
                                    "code": 401,
                                    "msg": "SmartThings token expired and no refresh_token is stored. Re-authorize via /oauth/smartthings/authorize.",
                                    "data": {"reason": "missing_refresh_token"},
                                },
                            )
                        try:
                            from app.smartthings_oauth_client import compute_expires_at, refresh_access_token

                            token_json = refresh_access_token(refresh_token=st.refresh_token)
                            st.access_token = token_json.get("access_token") or st.access_token
                            # SmartThings may or may not rotate refresh_token
                            st.refresh_token = token_json.get("refresh_token") or st.refresh_token
                            st.token_type = token_json.get("token_type") or st.token_type
                            st.scope = token_json.get("scope") or st.scope
                            st.expires_at = compute_expires_at(token_json.get("expires_in")) or st.expires_at
                            db.add(st)
                            db.commit()
                        except Exception as e:
                            # Map refresh failures into actionable responses for the client.
                            import requests

                            if isinstance(e, requests.HTTPError) and getattr(e, "response", None) is not None:
                                status = int(e.response.status_code)
                                try:
                                    upstream = e.response.json()
                                except ValueError:
                                    upstream = e.response.text

                                if 400 <= status < 500:
                                    # Usually invalid_grant / revoked refresh_token etc.
                                    raise HTTPException(
                                        status_code=401,
                                        detail={
                                            "code": 401,
                                            "msg": "Failed to refresh SmartThings token. User must re-authorize.",
                                            "data": {"upstream_status": status, "upstream": upstream},
                                        },
                                    ) from e

                                raise HTTPException(
                                    status_code=502,
                                    detail={
                                        "code": 502,
                                        "msg": "SmartThings token endpoint error while refreshing token.",
                                        "data": {"upstream_status": status, "upstream": upstream},
                                    },
                                ) from e

                            raise HTTPException(
                                status_code=502,
                                detail={
                                    "code": 502,
                                    "msg": "Failed to refresh SmartThings token due to network/unknown error.",
                                    "data": {"error": str(e)},
                                },
                            ) from e
                return SmartThingsClient(
                    token=st.access_token,
                    base_url=settings.smartthings_base_url,
                    timeout_s=settings.smartthings_timeout_s,
                )

    if settings.smartthings_token:
        return _get_default_smartthings_client()

    raise HTTPException(
        status_code=400,
        detail={
            "code": 400,
            "msg": "Missing SmartThings token. Provide Authorization: Bearer <PAT>, or bind via OAuth (SaaS), or set SMARTTHINGS_TOKEN.",
            "data": None,
        },
    )

