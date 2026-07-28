"""
Policy management routes — CRUD + SSE hot-reload endpoint.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import re
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import get_current_user
from src.api.config import get_settings
from src.api.database import get_db
from src.api.models import User
from src.api.routes.approvals import (
    ApprovalCreate,
    _list_approval_settings,
    create_approval_record,
)
from src.api.services.approval import ApprovalRequest, ApprovalStatus
from src.api.services.policy_store import (
    Policy,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
    PolicyStore,
    get_policy_store,
)

router = APIRouter(prefix="/policies", tags=["policies"])
logger = logging.getLogger(__name__)

APPROVAL_CONTEXT_REDACTION_MARKER = "[REDACTED]"
APPROVAL_CONTEXT_REDACTION_POLICY = "secret-values-v1"
_POLICY_APPROVAL_DEDUPE_KEY_CONTEXT = b"mutx.policy-approval-dedupe.v2"
_SENSITIVE_CONTEXT_KEYS = frozenset(
    {
        "access_key",
        "access_key_id",
        "api_key",
        "apikey",
        "auth_token",
        "authorization",
        "client_secret",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "secret_access_key",
        "set_cookie",
        "token",
    }
)
_SENSITIVE_CONTEXT_KEY_SUFFIXES = (
    "_api_key",
    "_credential",
    "_password",
    "_private_key",
    "_secret",
    "_token",
)
_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?" r"-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.DOTALL,
)
_CONTEXT_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?P<prefix>[\"']?(?P<label>\b[a-z][a-z0-9_-]*\b)[\"']?\s*[:=]\s*)"
    r"(?:(?P<quote>[\"'])(?P<quoted>(?:\\.|(?!(?P=quote)).)*)(?P=quote)|"
    r"(?P<bare>(?:Bearer\s+)?[^\s,;}]+))"
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_SECRET_TOKEN_PATTERNS = (
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{16,})\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)
_SQLITE_POLICY_APPROVAL_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _require_store() -> PolicyStore:
    return await get_policy_store()


def _is_sensitive_context_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    snake_case_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = re.sub(r"[^a-z0-9]+", "_", snake_case_key.casefold()).strip("_")
    return normalized in _SENSITIVE_CONTEXT_KEYS or normalized.endswith(
        _SENSITIVE_CONTEXT_KEY_SUFFIXES
    )


def _redact_secret_text(value: str) -> tuple[str, bool]:
    redacted = _PRIVATE_KEY_PATTERN.sub(APPROVAL_CONTEXT_REDACTION_MARKER, value)

    chunks: list[str] = []
    cursor = 0
    search_from = 0
    while match := _CONTEXT_ASSIGNMENT_PATTERN.search(redacted, search_from):
        if not _is_sensitive_context_key(match.group("label")):
            # Resume inside a safe assignment so a nested query-string secret,
            # such as ``callback=https://host/?token=...``, is still found.
            search_from = match.start() + 1
            continue
        quote = match.group("quote") or ""
        chunks.append(redacted[cursor : match.start()])
        chunks.append(f"{match.group('prefix')}{quote}{APPROVAL_CONTEXT_REDACTION_MARKER}{quote}")
        cursor = match.end()
        search_from = match.end()
    if chunks:
        chunks.append(redacted[cursor:])
        redacted = "".join(chunks)
    redacted = _BEARER_TOKEN_PATTERN.sub(
        rf"\1{APPROVAL_CONTEXT_REDACTION_MARKER}",
        redacted,
    )
    for pattern in _SECRET_TOKEN_PATTERNS:
        redacted = pattern.sub(APPROVAL_CONTEXT_REDACTION_MARKER, redacted)
    return redacted, redacted != value


def _redact_approval_context_value(value: object) -> tuple[object, bool]:
    """Preserve evaluated context while masking recognized secret values."""
    if isinstance(value, dict):
        result: dict = {}
        redacted = False
        for key, item in value.items():
            if _is_sensitive_context_key(key):
                result[key] = APPROVAL_CONTEXT_REDACTION_MARKER
                redacted = True
                continue
            safe_item, item_redacted = _redact_approval_context_value(item)
            result[key] = safe_item
            redacted = redacted or item_redacted
        return result, redacted
    if isinstance(value, list):
        result = []
        redacted = False
        for item in value:
            safe_item, item_redacted = _redact_approval_context_value(item)
            result.append(safe_item)
            redacted = redacted or item_redacted
        return result, redacted
    if isinstance(value, str):
        return _redact_secret_text(value)
    return value, False


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------


@router.get("", response_model=list[Policy])
async def list_policies(
    store: Annotated[PolicyStore, Depends(_require_store)],
    _user: Annotated[User, Depends(get_current_user)],
):
    """List all stored policies."""
    return await store.list_policies()


@router.post("", response_model=Policy, status_code=status.HTTP_201_CREATED)
async def create_policy(
    policy: Policy,
    store: Annotated[PolicyStore, Depends(_require_store)],
    _user: Annotated[User, Depends(get_current_user)],
):
    """Create a new policy."""
    existing = await store.get_policy(policy.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Policy '{policy.name}' already exists",
        )
    return await store.upsert_policy(policy)


@router.post("/evaluate", response_model=PolicyEvaluationResult)
async def evaluate_policies(
    context: PolicyEvaluationContext,
    store: Annotated[PolicyStore, Depends(_require_store)],
    _user: Annotated[User, Depends(get_current_user)],
):
    """Evaluate enabled stored policies against a pending action context."""
    return await store.evaluate(context)


class PolicyApprovalEvaluationResult(PolicyEvaluationResult):
    """Policy evaluation result plus optional linked approval request."""

    approval_request: ApprovalRequest | None = None
    approval_created: bool = False
    approval_dedupe_key: str | None = None


def _policy_approval_dedupe_key(
    context: PolicyEvaluationContext,
    result: PolicyEvaluationResult,
    user: User,
) -> str:
    key_payload = {
        "user_id": str(user.id),
        "run_id": context.run_id,
        "session_id": context.session_id,
        "agent_id": context.agent_id,
        "tool": context.tool,
        "input": context.input,
        "output": context.output,
        "tool_args": context.tool_args or {},
        "metadata": context.metadata,
        "matches": [match.model_dump(mode="json") for match in result.matches],
    }
    serialized = json.dumps(
        key_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    settings = get_settings()
    key_material = settings.secret_encryption_key or settings.jwt_secret
    purpose_key = hmac.new(
        key_material.encode("utf-8"),
        _POLICY_APPROVAL_DEDUPE_KEY_CONTEXT,
        hashlib.sha256,
    ).digest()
    digest = hmac.new(
        purpose_key,
        serialized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"policy-approval:v2:{digest}"


async def _find_existing_policy_approval(
    db: AsyncSession,
    *,
    dedupe_key: str,
) -> ApprovalRequest | None:
    limit = 200
    offset = 0
    while True:
        approvals, total = await _list_approval_settings(db, offset=offset, limit=limit)
        for approval in approvals:
            if approval.status != ApprovalStatus.PENDING:
                continue
            if approval.payload.get("policy_approval_dedupe_key") == dedupe_key:
                return approval

        offset += limit
        if offset >= total:
            return None


@asynccontextmanager
async def _policy_approval_creation_lock(
    db: AsyncSession,
    *,
    dedupe_key: str,
) -> AsyncIterator[None]:
    """Serialize lookup-and-create for one evaluated action.

    PostgreSQL advisory transaction locks coordinate all API workers without a
    schema migration. SQLite is only supported for tests and local development,
    where an in-process lock provides the same critical section.
    """
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        lock_id = int.from_bytes(
            hashlib.sha256(dedupe_key.encode()).digest()[:8],
            byteorder="big",
            signed=True,
        )
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        yield
        return

    lock = _SQLITE_POLICY_APPROVAL_LOCKS.get(dedupe_key)
    if lock is None:
        lock = asyncio.Lock()
        _SQLITE_POLICY_APPROVAL_LOCKS[dedupe_key] = lock
    async with lock:
        yield


def _approval_payload(
    context: PolicyEvaluationContext,
    result: PolicyEvaluationResult,
    dedupe_key: str,
) -> dict:
    safe_context, context_redacted = _redact_approval_context_value(
        {
            "run_id": context.run_id,
            "session_id": context.session_id,
            "agent_id": context.agent_id,
            "tool": context.tool,
            "input": context.input,
            "output": context.output,
            "tool_args": context.tool_args or {},
            "metadata": context.metadata,
        }
    )
    return {
        "policy_approval_dedupe_key": dedupe_key,
        "policy_decision": result.decision,
        "policy_reason": result.reason,
        "policy_matches": [match.model_dump(mode="json") for match in result.matches],
        "context": safe_context,
        "context_redaction": {
            "policy": APPROVAL_CONTEXT_REDACTION_POLICY,
            "marker": APPROVAL_CONTEXT_REDACTION_MARKER,
            "applied": context_redacted,
        },
    }


@router.post("/evaluate-and-request-approval", response_model=PolicyApprovalEvaluationResult)
async def evaluate_policies_and_request_approval(
    context: PolicyEvaluationContext,
    store: Annotated[PolicyStore, Depends(_require_store)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Evaluate policies and create one linked approval when approval is required."""
    result = await store.evaluate(context)
    response = PolicyApprovalEvaluationResult(**result.model_dump())
    if result.decision != "require_approval":
        return response

    dedupe_key = _policy_approval_dedupe_key(context, result, user)
    response.approval_dedupe_key = dedupe_key
    async with _policy_approval_creation_lock(db, dedupe_key=dedupe_key):
        existing = await _find_existing_policy_approval(db, dedupe_key=dedupe_key)
        if existing is not None:
            response.approval_request = existing
            return response

        approval = await create_approval_record(
            ApprovalCreate(
                agent_id=context.agent_id or "",
                session_id=context.session_id or context.run_id or "",
                action_type=context.tool or "policy.require_approval",
                payload=_approval_payload(context, result, dedupe_key),
            ),
            db,
            user,
        )
        response.approval_request = approval
        response.approval_created = True
    return response


@router.get("/{name}", response_model=Policy)
async def get_policy(
    name: str,
    store: Annotated[PolicyStore, Depends(_require_store)],
    _user: Annotated[User, Depends(get_current_user)],
):
    """Fetch a single policy by name."""
    policy = await store.get_policy(name)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    name: str,
    store: Annotated[PolicyStore, Depends(_require_store)],
    _user: Annotated[User, Depends(get_current_user)],
):
    """Delete a policy by name."""
    deleted = await store.delete_policy(name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")


# ------------------------------------------------------------------
# SSE hot-reload
# ------------------------------------------------------------------


class _SSEClient:
    """Async send-capable stand-in for EventSourceResponse (used for tracking)."""

    async def send(self, payload: str) -> None:
        pass


async def _sse_reload_generator(
    store: PolicyStore,
    policy_name: str,
    initial_version: int,
    sse_client: _SSEClient,
):
    """
    Yield SSE events as long as the policy version has not changed.
    Exits when the policy is updated or deleted.
    """
    try:
        # Send initial connected comment
        yield 'data: {"event":"connected","policy":"' + policy_name + '"}\n\n'
        while True:
            await asyncio.sleep(5)
            current = await store.get_policy(policy_name)
            if current is None:
                # Policy was deleted — send end signal and exit
                yield 'data: {"event":"deleted","policy":"' + policy_name + '"}\n\n'
                break
            if current.version != initial_version:
                # Version changed — send reload event and exit
                yield f"data: {json.dumps({'event': 'reload', 'policy': policy_name, 'version': current.version})}\n\n"
                break
    except asyncio.CancelledError:
        # Client disconnected gracefully
        pass
    finally:
        store.unregister_reload_client(sse_client)


@router.post("/{name}/reload")
async def reload_policy(
    name: str,
    store: Annotated[PolicyStore, Depends(_require_store)],
    _user: Annotated[User, Depends(get_current_user)],
):
    """
    SSE endpoint that pushes a 'reload' event when the named policy is
    updated (version increments) or deleted.

    The stream stays open and monitors the policy version, exiting when
    a change is detected so clients can re-fetch the policy.
    """
    policy = await store.get_policy(name)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

    initial_version = policy.version

    async def event_generator():
        client = _SSEClient()
        store.register_reload_client(client)
        try:
            async for chunk in _sse_reload_generator(store, name, initial_version, client):
                yield chunk
        finally:
            store.unregister_reload_client(client)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
