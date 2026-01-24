from __future__ import annotations

from typing import Any, Literal, Optional, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_smartthings_client
from app.security import get_current_user
from app.smartthings_client import SmartThingsClient

router = APIRouter(prefix="/tv", tags=["tv"], dependencies=[Depends(get_current_user)])


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


class VolumeBody(BaseModel):
    level: int = Field(ge=0, le=100)
    component: str = "main"
    capability: str = "audioVolume"
    command: str = "setVolume"


@router.post("/{device_id}/volume")
def set_volume(
    device_id: str,
    body: VolumeBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": body.command,
                "arguments": [body.level],
            }
        ],
    )


class VolumeStepBody(BaseModel):
    direction: Literal["up", "down"]
    component: str = "main"
    capability: str = "audioVolume"
    command_up: str = "volumeUp"
    command_down: str = "volumeDown"


@router.post("/{device_id}/volume-step")
def volume_step(
    device_id: str,
    body: VolumeStepBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    cmd = body.command_up if body.direction == "up" else body.command_down
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": cmd,
            }
        ],
    )


class MuteBody(BaseModel):
    mute: bool
    component: str = "main"
    capability: str = "audioMute"
    command_mute: str = "mute"
    command_unmute: str = "unmute"


@router.post("/{device_id}/mute")
def set_mute(
    device_id: str,
    body: MuteBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    cmd = body.command_mute if body.mute else body.command_unmute
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": cmd,
            }
        ],
    )


class ChannelBody(BaseModel):
    # Devices vary: some accept int, some accept string (e.g. "7-1")
    channel: Union[str, int]
    component: str = "main"
    capability: str = "tvChannel"
    command: str = "setChannel"


@router.post("/{device_id}/channel")
def set_channel(
    device_id: str,
    body: ChannelBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": body.command,
                "arguments": [body.channel],
            }
        ],
    )


class ChannelStepBody(BaseModel):
    direction: Literal["up", "down"]
    component: str = "main"
    capability: str = "tvChannel"
    command_up: str = "channelUp"
    command_down: str = "channelDown"


@router.post("/{device_id}/channel-step")
def channel_step(
    device_id: str,
    body: ChannelStepBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    cmd = body.command_up if body.direction == "up" else body.command_down
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": cmd,
            }
        ],
    )


class InputSourceBody(BaseModel):
    source: str
    component: str = "main"
    capability: str = "mediaInputSource"
    command: str = "setInputSource"


@router.post("/{device_id}/input-source")
def set_input_source(
    device_id: str,
    body: InputSourceBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": body.command,
                "arguments": [body.source],
            }
        ],
    )


class KeyBody(BaseModel):
    """
    TV 遥控按键（不同设备 payload 可能不同，所以允许自定义）

    默认会发送：
      capability=remoteControl, command=send, arguments=[{"keyCode": "<KEY_...>"}]

    兼容不同电视的差异：
    - payload_style="keyCodeObject"（默认）：[{"keyCode": key}]
    - payload_style="string"： [key]
    - payload_style="custom"：使用你传入的 arguments 原样发送
    """

    key: str
    component: str = "main"
    capability: str = "remoteControl"
    command: str = "send"
    payload_style: Literal["keyCodeObject", "string", "custom"] = "keyCodeObject"
    arguments: Optional[list[Any]] = None


@router.post("/{device_id}/key")
def send_key(
    device_id: str,
    body: KeyBody,
    client: SmartThingsClient = Depends(get_smartthings_client),
) -> Any:
    if body.payload_style == "custom":
        args = body.arguments if body.arguments is not None else []
    elif body.payload_style == "string":
        args = [body.key] if body.arguments is None else body.arguments
    else:
        args = [{"keyCode": body.key}] if body.arguments is None else body.arguments
    return client.execute_device_commands(
        device_id,
        commands=[
            {
                "component": body.component,
                "capability": body.capability,
                "command": body.command,
                "arguments": args,
            }
        ],
    )

