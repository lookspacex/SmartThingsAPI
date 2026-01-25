from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional

from app.config import settings


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def _sign(payload_b64: str) -> str:
    mac = hmac.new(settings.oauth_state_secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(mac)


def build_state(*, user_id: str, ttl_s: int = 15 * 60, pkce_verifier: Optional[str] = None) -> str:
    payload: dict[str, Any] = {"userId": user_id, "exp": int(time.time()) + int(ttl_s)}
    if pkce_verifier:
        # NOTE: signed (integrity protected) but not encrypted. For higher security,
        # store verifier server-side and reference it from state instead.
        payload["pkceVerifier"] = pkce_verifier
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig_b64 = _sign(payload_b64)
    return f"{payload_b64}.{sig_b64}"


def parse_state(state: str) -> dict[str, Any]:
    try:
        payload_b64, sig_b64 = state.split(".", 1)
    except ValueError as e:
        raise ValueError("Invalid state format") from e

    expected = _sign(payload_b64)
    if not hmac.compare_digest(expected, sig_b64):
        raise ValueError("Invalid state signature")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    exp = int(payload.get("exp", 0))
    if exp and time.time() > exp:
        raise ValueError("State expired")
    return payload

