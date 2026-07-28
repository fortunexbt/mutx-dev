from __future__ import annotations

import asyncio
import re
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import get_current_user, get_current_user_optional, require_plan
from src.api.models import User
from src.api.models.pico_onboarding import (
    GeneratePackageRequest as OnboardingGeneratePackageRequest,
    PicoChatRequest,
    PicoChatResponse,
    PicoOnboardingSessionResponse,
)
from src.api.models.pico_tutor import (
    PicoTutorOpenAIConnectionRequest,
    PicoTutorOpenAIConnectionStatus,
    PicoTutorRequest,
    PicoTutorResponse,
)
from src.api.services.pico_coach import handle_coach_chat
from src.api.services.pico_package_builder import build_onboarding_package
from src.api.services.pico_package_generator import generate_package_zip
from src.api.services.pico_onboarding_sessions import (
    PicoChatTurnClaim,
    PicoOnboardingGenerationBusyError,
    PicoOnboardingIdempotencyConflictError,
    PicoOnboardingSessionAbandonedError,
    PicoOnboardingSessionChangedError,
    PicoOnboardingSessionExpiredError,
    PicoOnboardingSessionNotFoundError,
    abandon_onboarding_session,
    abort_chat_turn,
    complete_chat_turn,
    get_latest_onboarding_session,
    get_onboarding_session,
    maintain_chat_turn_claim,
    prepare_chat_turn,
    record_package_generation,
)
from src.api.services.pico_progress import get_pico_progress, upsert_pico_progress
from src.api.services.pico_tutor import generate_pico_tutor_reply
from src.api.services.pico_tutor_openai import (
    PicoTutorOpenAIConnectionError,
    connect_pico_tutor_openai,
    disconnect_pico_tutor_openai,
    get_pico_tutor_openai_connection_status,
    resolve_pico_tutor_api_key,
)

router = APIRouter(prefix="/pico", tags=["pico"])

_SESSION_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


def _raise_session_http_error(exc: Exception) -> NoReturn:
    if isinstance(exc, PicoOnboardingSessionAbandonedError):
        raise HTTPException(
            status_code=410,
            detail="This onboarding session was reset. Start a new session to continue.",
        ) from exc
    if isinstance(exc, PicoOnboardingSessionExpiredError):
        raise HTTPException(
            status_code=410,
            detail="This onboarding session has expired. Start a new session to continue.",
        ) from exc
    raise HTTPException(status_code=404, detail="Session not found") from exc


def _safe_download_filename(value: str, *, fallback: str = "pico-agent-package.zip") -> str:
    basename = value.replace("\\", "/").rsplit("/", 1)[-1]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", basename).strip(".-")[:120]
    if not safe:
        safe = fallback
    if not safe.lower().endswith(".zip"):
        safe = f"{safe}.zip"
    return safe


# ---------------------------------------------------------------------------
# Progress (existing — unchanged)
# ---------------------------------------------------------------------------


class PicoProgressPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


@router.get("/progress", response_model=dict[str, Any])
async def pico_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_pico_progress(db, user=current_user)


@router.post("/progress", response_model=dict[str, Any])
async def pico_progress_update(
    payload: PicoProgressPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await upsert_pico_progress(
        db,
        user=current_user,
        payload=payload.model_dump(),
        replace=False,
    )


# ---------------------------------------------------------------------------
# Tutor (existing — unchanged)
# ---------------------------------------------------------------------------


@router.post("/tutor", response_model=PicoTutorResponse)
async def pico_tutor(
    payload: PicoTutorRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await generate_pico_tutor_reply(
        payload,
        db=db,
        current_user=current_user,
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.get(
    "/tutor/openai",
    response_model=PicoTutorOpenAIConnectionStatus,
)
async def pico_tutor_openai_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_pico_tutor_openai_connection_status(db, user=current_user)


@router.put(
    "/tutor/openai",
    response_model=PicoTutorOpenAIConnectionStatus,
)
async def pico_tutor_openai_connect(
    payload: PicoTutorOpenAIConnectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await connect_pico_tutor_openai(
            db,
            user=current_user,
            api_key=payload.apiKey,
        )
    except PicoTutorOpenAIConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/tutor/openai",
    response_model=PicoTutorOpenAIConnectionStatus,
)
async def pico_tutor_openai_disconnect(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await disconnect_pico_tutor_openai(db, user=current_user)


# ---------------------------------------------------------------------------
# Onboarding coach
# ---------------------------------------------------------------------------


@router.get("/session", response_model=PicoOnboardingSessionResponse)
async def pico_onboarding_session(
    session_id: str | None = Query(
        default=None,
        max_length=36,
        pattern=_SESSION_ID_PATTERN,
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PicoOnboardingSessionResponse | Response:
    """Resume an exact session, or the user's most recently active session."""
    try:
        record = (
            await get_onboarding_session(
                db,
                user=current_user,
                session_id=session_id,
            )
            if session_id
            else await get_latest_onboarding_session(db, user=current_user)
        )
    except (
        PicoOnboardingSessionNotFoundError,
        PicoOnboardingSessionExpiredError,
        PicoOnboardingSessionAbandonedError,
    ) as exc:
        _raise_session_http_error(exc)

    if record is None:
        return Response(status_code=204)
    return record.as_response()


@router.delete("/session", status_code=204)
async def pico_onboarding_session_start_over(
    session_id: str | None = Query(
        default=None,
        max_length=36,
        pattern=_SESSION_ID_PATTERN,
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Durably abandon an exact or latest session before starting over."""
    try:
        await abandon_onboarding_session(
            db,
            user=current_user,
            session_id=session_id,
        )
    except PicoOnboardingSessionNotFoundError as exc:
        _raise_session_http_error(exc)
    return Response(status_code=204)


@router.post("/chat", response_model=PicoChatResponse)
async def pico_coach_chat(
    payload: PicoChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Continue a durable user session, or provide honest one-turn anonymous coaching."""
    if current_user is None:
        if payload.session_id is not None:
            raise HTTPException(status_code=401, detail="Sign in to resume an onboarding session")
        api_key, _ = await resolve_pico_tutor_api_key(db, user=None)
        response = await handle_coach_chat(
            request=payload,
            history=[],
            api_key=api_key,
        )
        return response.model_copy(
            update={
                "session_id": None,
                "session_persisted": False,
            }
        )

    # Resolve the API key before reserving the turn so no database transaction is
    # left open while the model call is in flight.
    api_key, _ = await resolve_pico_tutor_api_key(db, user=current_user)

    try:
        prepared = await prepare_chat_turn(
            db,
            user=current_user,
            message=payload.message,
            session_id=payload.session_id,
            request_id=payload.request_id,
        )
    except PicoOnboardingIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="This request ID is already bound to different onboarding content.",
        ) from exc
    except PicoOnboardingGenerationBusyError as exc:
        raise HTTPException(
            status_code=409,
            detail="Another onboarding turn is still being generated. Retry shortly.",
            headers={"Retry-After": "1"},
        ) from exc
    except (
        PicoOnboardingSessionNotFoundError,
        PicoOnboardingSessionExpiredError,
        PicoOnboardingSessionAbandonedError,
    ) as exc:
        _raise_session_http_error(exc)

    if isinstance(prepared, PicoChatResponse):
        return prepared
    claim: PicoChatTurnClaim = prepared

    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        maintain_chat_turn_claim(
            db,
            user=current_user,
            claim=claim,
            stop=heartbeat_stop,
        )
    )
    try:
        response = await handle_coach_chat(
            request=payload,
            history=claim.history,
            api_key=api_key,
        )
    except BaseException:
        heartbeat_stop.set()
        await heartbeat_task
        await db.rollback()
        await abort_chat_turn(db, user=current_user, claim=claim)
        raise
    heartbeat_stop.set()
    await heartbeat_task

    try:
        return await complete_chat_turn(
            db,
            user=current_user,
            claim=claim,
            user_message=payload.message,
            response=response,
        )
    except PicoOnboardingIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="This request ID is already bound to different onboarding content.",
        ) from exc
    except PicoOnboardingGenerationBusyError as exc:
        raise HTTPException(
            status_code=409,
            detail="The onboarding turn lost its generation claim. Retry shortly.",
            headers={"Retry-After": "1"},
        ) from exc
    except (
        PicoOnboardingSessionNotFoundError,
        PicoOnboardingSessionExpiredError,
        PicoOnboardingSessionAbandonedError,
    ) as exc:
        _raise_session_http_error(exc)


# ---------------------------------------------------------------------------
# Package generation
# ---------------------------------------------------------------------------


@router.post("/generate-package", dependencies=[Depends(require_plan("starter"))])
async def pico_generate_package(
    payload: OnboardingGeneratePackageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Generate a package from this user's exact durable onboarding session."""
    try:
        record = await get_onboarding_session(
            db,
            user=current_user,
            session_id=payload.session_id,
        )
    except (
        PicoOnboardingSessionNotFoundError,
        PicoOnboardingSessionExpiredError,
        PicoOnboardingSessionAbandonedError,
    ) as exc:
        _raise_session_http_error(exc)

    state = record.onboarding_state
    if not state.ready:
        raise HTTPException(
            status_code=422,
            detail="Not enough information to generate a package. "
            "Complete the onboarding chat first.",
        )

    zip_bytes, filename = build_onboarding_package(state, session_id=record.session_id)
    filename = _safe_download_filename(filename)
    try:
        state_sha256 = await record_package_generation(
            db,
            user=current_user,
            session_id=record.session_id,
            filename=filename,
            state=state,
            expected_revision=record.revision,
        )
    except PicoOnboardingSessionChangedError as exc:
        raise HTTPException(
            status_code=409,
            detail="The onboarding session changed while its package was being prepared. Retry now.",
            headers={"Retry-After": "0"},
        ) from exc
    except (
        PicoOnboardingSessionNotFoundError,
        PicoOnboardingSessionExpiredError,
        PicoOnboardingSessionAbandonedError,
    ) as exc:
        _raise_session_http_error(exc)

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Pico-Onboarding-Session": record.session_id,
            "X-Pico-Onboarding-State-SHA256": state_sha256,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---------------------------------------------------------------------------
# Legacy package generation (kept for backward compat, will deprecate)
# ---------------------------------------------------------------------------


class LegacyGeneratePackageRequest(BaseModel):
    agent_name: str
    pain_points: list[str] | None = None
    model: str | None = None


@router.post("/generate-package-legacy", dependencies=[Depends(require_plan("starter"))])
async def pico_generate_package_legacy(
    payload: LegacyGeneratePackageRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Legacy package generator — kept for backward compatibility."""
    if not payload.agent_name.strip():
        raise HTTPException(status_code=422, detail="agent_name is required")

    zip_bytes = generate_package_zip(
        agent_name=payload.agent_name.strip(),
        pain_points=payload.pain_points,
        model=payload.model,
        user_email=current_user.email if hasattr(current_user, "email") else None,
    )

    filename = _safe_download_filename(payload.agent_name.strip())
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
