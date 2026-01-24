from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class UpstreamHTTPError(Exception):
    status_code: int
    message: str
    details: Optional[Any] = None

