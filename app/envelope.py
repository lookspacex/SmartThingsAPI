from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def is_enveloped(payload: Any) -> bool:
    # Target schema:
    #   {"code": 200, "msg": "", "data": {...}}
    return isinstance(payload, dict) and "code" in payload and "msg" in payload and "data" in payload


def _filtered_headers(headers: Iterable[Tuple[bytes, bytes]]) -> Dict[str, str]:
    """
    Starlette headers are raw (bytes, bytes). We keep most headers but drop those that will be re-generated.
    """
    drop = {b"content-length"}
    out: Dict[str, str] = {}
    for k, v in headers:
        lk = k.lower()
        if lk in drop:
            continue
        try:
            out[k.decode("latin-1")] = v.decode("latin-1")
        except Exception:
            # best-effort: skip undecodable headers
            continue
    return out


class EnvelopeMiddleware(BaseHTTPMiddleware):
    """
    Wrap JSON responses into a stable envelope for clients:

    - Success:
        {"code": 200, "msg": "", "data": <original_json>}
    - Error (fallback if an error slips through without exception handlers):
        {"code": <http_status>, "msg": "Request failed", "data": <original_json>}

    We avoid double-wrapping by detecting an existing envelope.
    """

    def __init__(self, app, *, exclude_prefixes: Optional[list[str]] = None) -> None:
        super().__init__(app)
        # Exclude docs/openapi, plus SmartApp webhook which must return raw lifecycle JSON.
        self.exclude_prefixes = exclude_prefixes or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/smartthings/smartapp",
        ]

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return response

        # Skip redirects / empty responses
        if response.status_code in (301, 302, 303, 307, 308) or response.status_code == 204:
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Read and replace the body (body_iterator is a stream).
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Try decode JSON; if it fails, return original (but we must restore response body)
        try:
            payload = json.loads(body.decode("utf-8")) if body else None
        except Exception:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=_filtered_headers(response.raw_headers),
                media_type=content_type,
            )

        if is_enveloped(payload):
            wrapped = payload
        else:
            if response.status_code < 400:
                wrapped = {"code": 200, "msg": "", "data": payload}
            else:
                # Fallback: if some error slipped through without our handlers
                wrapped = {"code": int(response.status_code), "msg": "Request failed", "data": payload}

        return JSONResponse(
            content=wrapped,
            status_code=response.status_code,
            headers=_filtered_headers(response.raw_headers),
        )

