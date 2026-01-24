from __future__ import annotations

from typing import Any, Dict

import requests
from fastapi import APIRouter, HTTPException, Request

from app.config import settings

router = APIRouter(prefix="/smartthings", tags=["smartapp"])


@router.post("/smartapp")
async def smartapp_webhook(request: Request) -> Dict[str, Any]:
    """
    SmartThings SmartApp webhook endpoint (lifecycle handler).

    This endpoint must NOT be wrapped by our client-facing response envelope.
    See EnvelopeMiddleware exclusions in app/envelope.py.
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}") from e

    lifecycle = body.get("lifecycle")

    # PING lifecycle
    if lifecycle == "PING":
        ping_data = body.get("pingData") or {}
        challenge = ping_data.get("challenge")
        if not challenge:
            raise HTTPException(status_code=400, detail="Missing pingData.challenge")
        return {"pingData": {"challenge": challenge}}

    # CONFIRMATION lifecycle:
    # SmartThings sends a confirmationUrl that must be called (HTTP GET) before it expires.
    if lifecycle == "CONFIRMATION":
        confirmation_data = body.get("confirmationData") or {}
        confirmation_url = confirmation_data.get("confirmationUrl")
        if not confirmation_url:
            raise HTTPException(status_code=400, detail="Missing confirmationData.confirmationUrl")

        try:
            # Best-effort: call immediately so the workspace verification passes.
            requests.get(confirmation_url, timeout=settings.smartthings_timeout_s)
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Failed to call confirmationUrl: {e}") from e

        # Response body for CONFIRMATION can be empty.
        return {}

    # For other lifecycles (CONFIGURATION/INSTALL/UPDATE/UNINSTALL/EVENT),
    # we return an empty 200 for now. You can extend this later.
    return {}

