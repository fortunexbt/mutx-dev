"""Sessions API routes."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any, Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import require_roles
from src.api.database import get_db
from src.api.models import User
from src.api.services.assistant_control_plane import (
    list_gateway_sessions,
)
from src.api.services.session_ownership import (
    OwnedSession,
    filter_and_claim_owned_sessions,
    forget_owned_session,
    get_owned_session_agent,
    require_live_owned_gateway_session,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)

VALID_THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh"]
VALID_VERBOSE_LEVELS = ["off", "on", "full"]
VALID_REASONING_LEVELS = ["off", "on", "stream"]

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 18789


# --- Gateway client ---


async def _call_gateway(
    method: str,
    path: str,
    json: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> Any:
    """Make an HTTP request to the local OpenClaw gateway.

    Returns parsed JSON response.
    Raises HTTPException on gateway errors or connection failure.
    """
    import os
    import aiohttp

    host = os.environ.get("OPENCLAW_GATEWAY_HOST", DEFAULT_GATEWAY_HOST)
    port = int(os.environ.get("OPENCLAW_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)))
    base_url = f"http://{host}:{port}"

    try:
        async with aiohttp.ClientSession() as session:
            kwargs: dict[str, Any] = {"timeout": aiohttp.ClientTimeout(total=10)}
            if json is not None:
                kwargs["json"] = json
            if params is not None:
                kwargs["params"] = params

            async with session.request(method, f"{base_url}{path}", **kwargs) as resp:
                response_data: Any = None
                if resp.content_type and "application/json" in resp.content_type:
                    response_data = await resp.json()

                if resp.status == 404:
                    raise HTTPException(status_code=404, detail="Session not found on gateway")
                if resp.status >= 500:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Gateway error: {resp.status}",
                    )
                if resp.status >= 400:
                    detail = (
                        response_data.get("detail") or response_data.get("message")
                        if isinstance(response_data, dict)
                        else None
                    )
                    raise HTTPException(
                        status_code=resp.status,
                        detail=detail or f"Gateway rejected request: {resp.status}",
                    )
                if response_data is not None:
                    return response_data
                return {"status": resp.status}
    except aiohttp.ClientConnectorError:
        raise HTTPException(
            status_code=503,
            detail="OpenClaw gateway is not reachable. Ensure the gateway is running on the operator host.",
        )
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail=f"Gateway request failed: {exc}") from exc


# --- Local session discovery (Claude/Codex/Hermes) ---


def _parse_timestamp(ts: str | int | float) -> float:
    """Parse various timestamp formats to epoch float for sorting."""
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        from datetime import datetime

        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(ts[:26], fmt).timestamp()
            except ValueError:
                continue
        # ISO format with timezone
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return 0.0


def get_local_claude_sessions() -> list[dict[str, Any]]:
    """Discover Claude sessions from ~/.claude/projects/."""
    import json
    from pathlib import Path

    sessions: list[dict[str, Any]] = []
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.is_dir():
        return sessions

    try:
        for project_dir in claude_dir.iterdir():
            if not project_dir.is_dir():
                continue
            project_name = project_dir.name.lstrip("-").replace("-", "/")
            # Strip leading path segments to get a readable project name
            parts = project_name.split("/")
            if len(parts) > 2:
                project_name = "/".join(parts[-2:])

            for session_file in project_dir.glob("*.jsonl"):
                try:
                    stat = session_file.stat()
                    session_id = session_file.stem
                    workspace = None
                    agent_ids: set[str] = set()
                    with session_file.open() as transcript:
                        for _ in range(20):
                            line = transcript.readline()
                            if not line:
                                break
                            try:
                                entry = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(entry, dict):
                                continue
                            if workspace is None and isinstance(entry.get("cwd"), str):
                                workspace = entry["cwd"]
                            if isinstance(entry.get("agent_id"), str):
                                agent_ids.add(entry["agent_id"])
                    sessions.append(
                        {
                            "id": f"claude:{session_id}",
                            "source": "claude",
                            "project": project_name,
                            "agent_id": next(iter(agent_ids)) if len(agent_ids) == 1 else None,
                            "workspace": workspace,
                            "status": "available",
                            "last_activity": stat.st_mtime,
                            "created_at": stat.st_ctime,
                            "size_bytes": stat.st_size,
                            "file_path": str(session_file),
                        }
                    )
                except OSError:
                    continue
    except Exception as exc:
        logger.warning("Failed to scan Claude sessions: %s", exc)

    return sessions


def get_local_codex_sessions() -> list[dict[str, Any]]:
    """Discover Codex sessions from ~/.codex/session_index.jsonl."""
    import json
    from pathlib import Path

    sessions: list[dict[str, Any]] = []
    codex_index = Path.home() / ".codex" / "session_index.jsonl"
    if not codex_index.is_file():
        return sessions

    try:
        with open(codex_index) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    session_id = entry.get("id", "")
                    thread_name = entry.get("thread_name", "Untitled")
                    updated_at = entry.get("updated_at", "")
                    sessions.append(
                        {
                            "id": f"codex:{session_id}",
                            "source": "codex",
                            "name": thread_name,
                            "agent_id": entry.get("agent_id"),
                            "assistant_id": entry.get("assistant_id"),
                            "workspace": entry.get("workspace") or entry.get("cwd"),
                            "status": "available",
                            "last_activity": _parse_timestamp(updated_at),
                            "created_at": _parse_timestamp(entry.get("created_at", updated_at)),
                        }
                    )
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception as exc:
        logger.warning("Failed to scan Codex sessions: %s", exc)

    return sessions


def get_local_hermes_sessions() -> list[dict[str, Any]]:
    """Discover Hermes sessions from ~/.hermes/sessions/sessions.json."""
    import json
    from pathlib import Path

    sessions: list[dict[str, Any]] = []
    sessions_file = Path.home() / ".hermes" / "sessions" / "sessions.json"
    if not sessions_file.is_file():
        return sessions

    try:
        with open(sessions_file) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return sessions

        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            session_id = entry.get("session_id", key)
            updated_at = entry.get("updated_at", "")
            sessions.append(
                {
                    "id": f"hermes:{session_id}",
                    "source": "hermes",
                    "session_key": key,
                    "agent_id": entry.get("agent_id"),
                    "assistant_id": entry.get("assistant_id"),
                    "workspace": entry.get("workspace"),
                    "display_name": entry.get("display_name", "Untitled"),
                    "platform": entry.get("platform", "unknown"),
                    "chat_type": entry.get("chat_type", "unknown"),
                    "status": "available",
                    "last_activity": _parse_timestamp(updated_at),
                    "created_at": _parse_timestamp(entry.get("created_at", updated_at)),
                    "input_tokens": entry.get("input_tokens", 0),
                    "output_tokens": entry.get("output_tokens", 0),
                    "estimated_cost_usd": entry.get("estimated_cost_usd", 0.0),
                }
            )
    except Exception as exc:
        logger.warning("Failed to scan Hermes sessions: %s", exc)

    return sessions


def merge_and_dedupe_sessions(
    gateway_sessions: list[dict[str, Any]],
    claude_sessions: list[dict[str, Any]],
    codex_sessions: list[dict[str, Any]],
    hermes_sessions: list[dict[str, Any]],
    *,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    all_sessions = gateway_sessions + claude_sessions + codex_sessions + hermes_sessions

    seen: dict[str, dict[str, Any]] = {}
    for session in all_sessions:
        session_id = session.get("id", "")
        if not session_id:
            continue
        # Local sessions already include their source prefix in the id
        # (e.g. "claude:abc123"), so use id directly as the dedup key.
        key = str(session_id)
        existing = seen.get(key)
        current_activity = session.get("last_activity", 0)
        existing_activity = existing.get("last_activity", 0) if existing else 0
        if not existing or current_activity > existing_activity:
            seen[key] = session

    sorted_sessions = sorted(
        seen.values(), key=lambda session: session.get("last_activity", 0), reverse=True
    )
    return sorted_sessions[:limit] if limit is not None else sorted_sessions


# --- Schemas ---


class SessionActionRequest(BaseModel):
    session_key: str
    level: Optional[str] = None
    label: Optional[str] = None


class SessionActionResponse(BaseModel):
    session_key: str
    action: str
    applied: bool
    detail: Optional[str] = None


# --- Session Lifecycle (MC v2.0 parity) ---


class SessionState(str, Enum):
    """Session lifecycle states aligned with MC v2.0 / OpenClaw gateway."""

    active = "active"
    paused = "paused"
    terminated = "terminated"
    offline = "offline"
    error = "error"


VALID_CONTROL_ACTIONS: list[str] = ["pause", "resume", "kill"]


class SessionControlRequest(BaseModel):
    """Request body for session lifecycle control (pause/resume/kill)."""

    action: Literal["pause", "resume", "kill"]


class SessionControlResponse(BaseModel):
    """Response from a session lifecycle control action."""

    session_key: str
    action: str
    previous_state: Optional[str] = None
    current_state: Optional[str] = None
    detail: Optional[str] = None


class SessionTranscriptResponse(BaseModel):
    """Full session transcript (conversation history)."""

    session_key: str
    messages: list[dict[str, Any]]
    total_count: int


# --- Routes ---


class SessionListResponse(BaseModel):
    sessions: list[dict[str, Any]]


def _discover_sessions() -> list[dict[str, Any]]:
    # Ownership must be resolved before deduplication or truncation. Otherwise a
    # foreign session that reuses an ID could crowd out the owner's real record.
    return (
        list_gateway_sessions()
        + get_local_claude_sessions()
        + get_local_codex_sessions()
        + get_local_hermes_sessions()
    )


async def _resolve_owned_session(
    db: AsyncSession,
    current_user: User,
    session_key: str,
) -> OwnedSession:
    return await require_live_owned_gateway_session(
        db,
        user=current_user,
        session_key=session_key,
        gateway_sessions=list_gateway_sessions(),
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    agent_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
) -> SessionListResponse:
    """List sessions unambiguously owned by the authenticated persisted principal."""
    required_agent_id = None
    if agent_id is not None:
        agent = await get_owned_session_agent(db, user=current_user, agent_id=agent_id)
        required_agent_id = agent.id

    sessions = await filter_and_claim_owned_sessions(
        db,
        user=current_user,
        sessions=_discover_sessions(),
        required_agent_id=required_agent_id,
    )
    visible_sessions = merge_and_dedupe_sessions(sessions, [], [], [])
    return SessionListResponse(sessions=visible_sessions)


@router.post("", response_model=SessionActionResponse)
async def session_action(
    request: SessionActionRequest,
    action: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
) -> SessionActionResponse:
    """Apply a session action (set-thinking, set-verbose, set-reasoning, set-label).

    Validates input, then forwards the action to the OpenClaw gateway.
    """
    valid_actions = ["set-thinking", "set-verbose", "set-reasoning", "set-label"]
    if action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be: {', '.join(valid_actions)}",
        )

    if action == "set-thinking" and request.level not in VALID_THINKING_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid thinking level. Must be: {', '.join(VALID_THINKING_LEVELS)}",
        )
    if action == "set-verbose" and request.level not in VALID_VERBOSE_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verbose level. Must be: {', '.join(VALID_VERBOSE_LEVELS)}",
        )
    if action == "set-reasoning" and request.level not in VALID_REASONING_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid reasoning level. Must be: {', '.join(VALID_REASONING_LEVELS)}",
        )
    if action == "set-label" and (request.label is None or len(request.label) > 100):
        raise HTTPException(
            status_code=400,
            detail="Label must be a string up to 100 characters",
        )

    owned_session = await _resolve_owned_session(db, current_user, request.session_key)

    # Map action to gateway endpoint
    gateway_path_map = {
        "set-thinking": "/api/sessions/thinking",
        "set-verbose": "/api/sessions/verbose",
        "set-reasoning": "/api/sessions/reasoning",
        "set-label": "/api/sessions/label",
    }

    # Forge payload for gateway
    body: dict[str, Any] = {"session": owned_session.canonical_key}
    if action == "set-label":
        body["label"] = request.label
    else:
        body["level"] = request.level

    result = await _call_gateway("PATCH", gateway_path_map[action], json=body)
    return SessionActionResponse(
        session_key=request.session_key,
        action=action,
        applied=True,
        detail=result.get("message") or result.get("detail"),
    )


@router.delete("", response_model=SessionActionResponse)
async def delete_session(
    request: SessionActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
) -> SessionActionResponse:
    """Delete a session from the OpenClaw gateway.

    Requires session_key to identify the session to delete.
    """
    owned_session = await _resolve_owned_session(db, current_user, request.session_key)

    await _call_gateway(
        "DELETE",
        f"/api/sessions/{quote(owned_session.canonical_key, safe='')}",
    )
    await forget_owned_session(
        db,
        user=current_user,
        canonical_key=owned_session.canonical_key,
    )
    return SessionActionResponse(
        session_key=request.session_key,
        action="delete",
        applied=True,
    )


# --- Session Lifecycle Control (MC v2.0 parity) ---


# Valid state transitions for session control actions.
# Maps action → (allowed_from_states, resulting_state).
_STATE_TRANSITIONS: dict[str, tuple[list[str], str]] = {
    "pause": (["active"], "paused"),
    "resume": (["paused"], "active"),
    "kill": (["active", "paused"], "terminated"),
}


@router.post("/{session_key:path}/control", response_model=SessionControlResponse)
async def session_control(
    session_key: str,
    request: SessionControlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
) -> SessionControlResponse:
    """Control session lifecycle: pause, resume, or kill a session.

    Forwards the action to the OpenClaw gateway's ``POST /control`` endpoint.
    The gateway handles the actual state transition; MUTX validates the request
    and enriches the response with state information.
    """
    action = request.action
    owned_session = await _resolve_owned_session(db, current_user, session_key)

    # Forward to the gateway control endpoint (MC v2.0 pattern).
    # The gateway expects POST /api/sessions/{key}/control with {"action": ...}.
    result = await _call_gateway(
        "POST",
        f"/api/sessions/{quote(owned_session.canonical_key, safe='')}/control",
        json={"action": action},
    )

    # Determine the resulting state from the transition map.
    _, resulting_state = _STATE_TRANSITIONS[action]

    return SessionControlResponse(
        session_key=session_key,
        action=action,
        current_state=resulting_state,
        detail=result.get("message") or result.get("detail") or "ok",
    )


@router.get("/{session_key:path}/transcript", response_model=SessionTranscriptResponse)
async def session_transcript(
    session_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
) -> SessionTranscriptResponse:
    """Retrieve the full session transcript (conversation history).

    Proxies to the OpenClaw gateway's ``GET /api/sessions/:key/history`` endpoint.
    """
    owned_session = await _resolve_owned_session(db, current_user, session_key)
    data = await _call_gateway(
        "GET",
        f"/api/sessions/{quote(owned_session.canonical_key, safe='')}/history",
    )

    # The gateway may return a list of messages directly or wrap them.
    messages: list[dict[str, Any]]
    if isinstance(data, list):
        messages = data
    elif isinstance(data, dict):
        messages = data.get("messages", data.get("history", []))
        if not isinstance(messages, list):
            messages = []
    else:
        messages = []

    return SessionTranscriptResponse(
        session_key=session_key,
        messages=messages,
        total_count=len(messages),
    )
