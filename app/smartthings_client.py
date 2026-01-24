from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from app.http_errors import UpstreamHTTPError


class SmartThingsClient:
    def __init__(self, *, token: str, base_url: str, timeout_s: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
    ) -> Any:
        try:
            resp = self._session.request(
                method=method,
                url=self._url(path),
                params=params,
                json=json_body,
                timeout=self._timeout_s,
            )
        except requests.RequestException as e:
            raise UpstreamHTTPError(
                status_code=502,
                message="Failed to reach SmartThings API",
                details=str(e),
            ) from e

        if 200 <= resp.status_code < 300:
            if not resp.content:
                return None
            # SmartThings returns JSON for most endpoints
            try:
                return resp.json()
            except ValueError:
                return resp.text

        # error payloads are usually JSON
        details: Any
        try:
            details = resp.json()
        except ValueError:
            details = {"raw": resp.text}

        msg = f"SmartThings API error ({resp.status_code})"
        raise UpstreamHTTPError(status_code=resp.status_code, message=msg, details=details)

    # Public API wrappers
    def list_locations(self) -> Any:
        return self._request("GET", "/locations")

    def list_devices(self) -> Any:
        return self._request("GET", "/devices")

    def get_device(self, device_id: str) -> Any:
        return self._request("GET", f"/devices/{device_id}")

    def get_device_status(self, device_id: str) -> Any:
        return self._request("GET", f"/devices/{device_id}/status")

    def execute_device_commands(self, device_id: str, commands: list[dict[str, Any]]) -> Any:
        body = {"commands": commands}
        return self._request("POST", f"/devices/{device_id}/commands", json_body=body)

