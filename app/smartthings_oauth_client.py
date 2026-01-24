from __future__ import annotations

import datetime as dt
from typing import Any, Optional

import requests

from app.config import settings


class SmartThingsOAuthNotConfigured(RuntimeError):
    pass


def refresh_access_token(*, refresh_token: str) -> dict[str, Any]:
    """
    Exchange refresh_token for a new access_token using SmartThings OAuth token endpoint.
    Returns the raw token JSON.
    """
    if not settings.smartthings_client_id or not settings.smartthings_client_secret:
        raise SmartThingsOAuthNotConfigured("SMARTTHINGS_CLIENT_ID/SMARTTHINGS_CLIENT_SECRET not configured")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    resp = requests.post(
        settings.smartthings_oauth_token_url,
        data=data,
        auth=(settings.smartthings_client_id, settings.smartthings_client_secret),
        timeout=settings.smartthings_timeout_s,
    )
    resp.raise_for_status()
    return resp.json()


def compute_expires_at(expires_in: Any) -> Optional[dt.datetime]:
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(expires_in))
    return None

