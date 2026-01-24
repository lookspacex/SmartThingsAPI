from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.deps import get_smartthings_client
from app.security import get_current_user
from app.smartthings_client import SmartThingsClient

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(get_current_user)])


@router.get("/validate")
def validate_token(client: SmartThingsClient = Depends(get_smartthings_client)) -> Any:
    """
    SmartThings does not provide a classic "token introspection" endpoint for PAT.
    The typical validation approach is: call a simple endpoint and see if it succeeds.
    """
    data = client.list_locations()
    items = data.get("items", []) if isinstance(data, dict) else []
    return {"locations": len(items)}

