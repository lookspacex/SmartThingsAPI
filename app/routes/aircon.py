from __future__ import annotations

from typing import Any, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_smartthings_client
from app.security import get_current_user
from app.smartthings_client import SmartThingsClient

router = APIRouter(prefix="/aircon", tags=["aircon"], dependencies=[Depends(get_current_user)])


class PowerBody(BaseModel):
    on: bool
    component: str = "main"


@router.post("/{device_id}/power")
def set_power(
    device_id: str,
    body: PowerBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    cmd = "on" if body.on else "off"
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": "switch",
                "command": cmd,
            }
        ],
    )


class ModeBody(BaseModel):
    # Common values: "cool", "heat", "auto", "dry", "fanOnly"
    mode: str
    component: str = "main"
    capability: str = "airConditionerMode"
    command: str = "setAirConditionerMode"


@router.post("/{device_id}/mode")
def set_mode(
    device_id: str,
    body: ModeBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": body.command,
                "arguments": [body.mode],
            }
        ],
    )


class TemperatureBody(BaseModel):
    celsius: float = Field(ge=10, le=35)
    component: str = "main"
    capability: str = "thermostatCoolingSetpoint"
    command: str = "setCoolingSetpoint"


@router.post("/{device_id}/temperature")
def set_temperature(
    device_id: str,
    body: TemperatureBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": body.command,
                "arguments": [body.celsius],
            }
        ],
    )


class FanSpeedBody(BaseModel):
    # Many devices accept integers or strings (e.g. "low"/"medium"/"high"/"auto")
    speed: Union[str, int]
    component: str = "main"
    capability: str = "fanSpeed"
    command: str = "setFanSpeed"


@router.post("/{device_id}/fan-speed")
def set_fan_speed(
    device_id: str,
    body: FanSpeedBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": body.command,
                "arguments": [body.speed],
            }
        ],
    )

