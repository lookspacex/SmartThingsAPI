from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import get_smartthings_client
from app.security import get_current_user
from app.smartthings_client import SmartThingsClient

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_devices(client: SmartThingsClient = Depends(get_smartthings_client)) -> Any:
    return client.list_devices()


@router.get("/{device_id}")
def get_device(device_id: str, client: SmartThingsClient = Depends(get_smartthings_client)) -> Any:
    return client.get_device(device_id)


@router.get("/{device_id}/status")
def get_device_status(device_id: str, client: SmartThingsClient = Depends(get_smartthings_client)) -> Any:
    return client.get_device_status(device_id)


@router.get("/{device_id}/capabilities")
def get_device_capabilities(device_id: str, client: SmartThingsClient = Depends(get_smartthings_client)) -> Any:
    """
    Convenience endpoint: summarize components + capabilities from GET /devices/{id}.
    Useful to confirm what an AC/TV actually supports before sending commands.
    """
    device = client.get_device(device_id)
    components = device.get("components", []) if isinstance(device, dict) else []
    summary: list[dict[str, Any]] = []
    for comp in components:
        comp_id = comp.get("id")
        caps = []
        for cap in comp.get("capabilities", []) or []:
            if isinstance(cap, dict) and "id" in cap:
                caps.append(cap["id"])
        summary.append({"component": comp_id, "capabilities": sorted(set(caps))})
    return {"deviceId": device_id, "components": summary}


class ExecuteCommandsBody(BaseModel):
    """
    Accepts: {"commands":[{component,capability,command,arguments?}, ...]}
    Keep it permissive because SmartThings command schemas vary per capability.
    """

    commands: list[dict[str, Any]] = Field(min_length=1)


@router.post("/{device_id}/commands")
def execute_commands(
    device_id: str,
    body: ExecuteCommandsBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    try:
        return client.execute_device_commands(device_id, commands=body.commands)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

