from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

# ---------------------------------------------------------------------------
# REST API response contracts
#
# These TypedDicts are the canonical schema for CF REST responses and must
# stay in sync with the FastAPI backend (undef-terminal SessionRuntimeStatus
# and hijack route responses).  Any field added to the FastAPI schema must
# also be added here, with an appropriate CF default documented inline.
# ---------------------------------------------------------------------------


class SessionStatusItem(TypedDict):
    """Shape of each item in GET /api/sessions.

    Mirrors ``undef-terminal`` ``SessionRuntimeStatus``/``SessionStatus`` (TS).
    CF-only fields: ``hijacked``.
    CF fields with synthetic defaults: ``display_name`` (= worker_id),
    ``connector_type`` ("unknown"), ``lifecycle_state`` ("running"/"idle"),
    ``auto_start`` (False), ``tags`` ([]), ``recording_enabled`` (False),
    ``recording_path`` (None), ``last_error`` (None).
    """

    session_id: str
    display_name: str
    connector_type: str
    lifecycle_state: str
    input_mode: str
    connected: bool
    auto_start: bool
    tags: list
    recording_enabled: bool
    recording_path: str | None
    last_error: str | None
    # CF-specific extras (not in FastAPI schema; clients must tolerate them)
    hijacked: bool


class HijackAcquireResponse(TypedDict):
    ok: bool
    worker_id: str
    hijack_id: str
    lease_expires_at: float
    owner: str


class HijackHeartbeatResponse(TypedDict):
    ok: bool
    worker_id: str
    hijack_id: str
    lease_expires_at: float


class HijackStepResponse(TypedDict):
    ok: bool
    worker_id: str
    hijack_id: str
    lease_expires_at: float | None


class HijackReleaseResponse(TypedDict):
    ok: bool
    worker_id: str
    hijack_id: str


FrameType = Literal[
    "snapshot_req",
    "snapshot",
    "term",
    "input",
    "control",
    "hijack_state",
    "analysis",
    "error",
    "worker_connected",
    "worker_disconnected",
    # Browser-originated frames (heartbeat/ping keepalives, WS-level hijack requests).
    # The CF backend routes hijack through REST; these arrive via WS from hijack.js.
    "heartbeat",
    "ping",
    "hijack_request",
    "hijack_release",
    "hijack_step",
    "hello",
]


class ProtocolError(ValueError):
    pass


class Frame(TypedDict, total=False):
    type: FrameType
    ts: float
    data: str
    screen: str
    action: str
    owner: str | None
    hijacked: bool
    lease_expires_at: float | None
    formatted: str
    message: str


@dataclass(slots=True)
class MessageLimits:
    max_ws_message_bytes: int = 1_048_576
    max_input_chars: int = 10_000


def parse_frame(raw: str, *, limits: MessageLimits | None = None) -> Frame:
    active_limits = limits or MessageLimits()
    if len(raw.encode("utf-8")) > active_limits.max_ws_message_bytes:
        raise ProtocolError("message too large")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid json") from exc
    if not isinstance(value, dict):
        raise ProtocolError("frame must be an object")
    frame_type = value.get("type")
    if not isinstance(frame_type, str):
        raise ProtocolError("missing frame type")

    normalized: Frame = {"type": frame_type, "ts": float(value.get("ts", time.time()))}

    if frame_type == "input":
        data = str(value.get("data", ""))
        if len(data) > active_limits.max_input_chars:
            raise ProtocolError("input too large")
        normalized["data"] = data
    elif frame_type == "snapshot":
        normalized["screen"] = str(value.get("screen", ""))
    elif frame_type == "term":
        normalized["data"] = str(value.get("data", ""))
    elif frame_type == "control":
        normalized["action"] = str(value.get("action", ""))
        normalized["owner"] = str(value.get("owner", "")) if value.get("owner") is not None else None
    elif frame_type == "analysis":
        normalized["formatted"] = str(value.get("formatted", ""))
    elif frame_type == "hijack_state":
        normalized["hijacked"] = bool(value.get("hijacked", False))
        normalized["owner"] = str(value.get("owner", "")) if value.get("owner") is not None else None
        lease_expires_at = value.get("lease_expires_at")
        normalized["lease_expires_at"] = float(lease_expires_at) if lease_expires_at is not None else None
    elif frame_type in {
        "snapshot_req",
        "error",
        "worker_connected",
        "worker_disconnected",
        "heartbeat",
        "ping",
        "hijack_request",
        "hijack_release",
        "hijack_step",
        "hello",
    }:
        pass
    else:
        raise ProtocolError(f"unsupported frame type: {frame_type}")

    return normalized


def frame_json(frame_type: FrameType, **kwargs: Any) -> str:
    payload = {"type": frame_type, "ts": time.time(), **kwargs}
    return json.dumps(payload, ensure_ascii=True)
