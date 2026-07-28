import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models.models import Lead, User
from src.api.models.schemas import (
    LeadCaptureResponse,
    LeadCreate,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
)
from src.api.services.leads_service import notify_new_lead

router = APIRouter(prefix="/leads", tags=["leads"])
contacts_router = APIRouter(prefix="/contacts", tags=["contacts"])
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_notification_tasks: set[asyncio.Task[None]] = set()


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_lead_payload(payload: LeadCreate) -> dict[str, str | bool | None]:
    return {
        "company": _normalize_optional_text(payload.company),
        "email": str(payload.email).lower().strip(),
        "interest": _normalize_optional_text(payload.interest),
        "locale": _normalize_optional_text(payload.locale).lower() if payload.locale else None,
        "message": _normalize_optional_text(payload.message),
        "name": _normalize_optional_text(payload.name),
        "product_updates_consent": payload.product_updates_consent is True,
        "source": _normalize_optional_text(payload.source) or "direct",
        "tier": _normalize_optional_text(payload.tier),
    }


def _lead_content_hash(content: dict[str, str | bool | None]) -> str:
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validated_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Idempotency-Key must be 16-128 characters using letters, numbers, dot, "
                "underscore, colon, or hyphen."
            ),
        )
    return normalized


def _assert_matching_replay(lead: Lead, expected_hash: str) -> None:
    if lead.content_hash != expected_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Idempotency-Key was already used for different lead content.",
        )


async def _claim_notification(db: AsyncSession, lead: Lead) -> bool:
    scheduled_at = datetime.now(timezone.utc)
    result = await db.execute(
        update(Lead)
        .where(Lead.id == lead.id, Lead.notification_scheduled_at.is_(None))
        .values(notification_scheduled_at=scheduled_at)
        .returning(Lead.id)
    )
    claimed = result.scalar_one_or_none() is not None
    await db.commit()
    if claimed:
        lead.notification_scheduled_at = scheduled_at
    else:
        await db.refresh(lead, attribute_names=["notification_scheduled_at"])
    return claimed


def _schedule_notification(lead: Lead) -> None:
    task = asyncio.create_task(
        notify_new_lead(
            lead_id=str(lead.id),
            email=lead.email,
            source=lead.source,
            name=lead.name,
            company=lead.company,
            message=lead.message,
            tier=lead.tier,
            interest=lead.interest,
            locale=lead.locale,
            product_updates_consent=lead.product_updates_consent,
        )
    )
    _notification_tasks.add(task)
    task.add_done_callback(_notification_tasks.discard)


def _capture_response(lead: Lead, *, replayed: bool) -> LeadCaptureResponse:
    notification_scheduled = lead.notification_scheduled_at is not None
    return LeadCaptureResponse(
        id=lead.id,
        email=lead.email,
        name=lead.name,
        company=lead.company,
        message=lead.message,
        source=lead.source,
        tier=lead.tier,
        interest=lead.interest,
        locale=lead.locale,
        product_updates_consent=lead.product_updates_consent,
        notification_scheduled_at=lead.notification_scheduled_at,
        created_at=lead.created_at,
        replayed=replayed,
        notification_scheduled=notification_scheduled,
        follow_up="best-effort" if notification_scheduled else "unavailable",
        message_to_submitter=(
            "Your request was saved. Automated confirmation and team notification are "
            "best-effort and are not guaranteed."
        ),
    )


@router.post("", response_model=LeadCaptureResponse, status_code=status.HTTP_201_CREATED)
@contacts_router.post("", response_model=LeadCaptureResponse, status_code=status.HTTP_201_CREATED)
async def capture_lead(
    payload: LeadCreate,
    idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Capture a new contact lead.
    Public endpoint for landing pages and onboarding.
    Writes to the DB then fires async notifications (Discord, Resend).
    """
    idempotency_key = _validated_idempotency_key(idempotency_key_header)
    content = _normalize_lead_payload(payload)
    content_hash = _lead_content_hash(content)
    replayed = False

    if idempotency_key:
        existing_result = await db.execute(
            select(Lead).where(Lead.idempotency_key == idempotency_key)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            _assert_matching_replay(existing, content_hash)
            claimed = await _claim_notification(db, existing)
            if claimed:
                _schedule_notification(existing)
            return _capture_response(existing, replayed=True)

    lead = Lead(**content, idempotency_key=idempotency_key, content_hash=content_hash)
    db.add(lead)
    try:
        await db.commit()
        await db.refresh(lead)
    except IntegrityError:
        await db.rollback()
        if not idempotency_key:
            raise
        existing_result = await db.execute(
            select(Lead).where(Lead.idempotency_key == idempotency_key)
        )
        lead = existing_result.scalar_one_or_none()
        if lead is None:
            raise
        _assert_matching_replay(lead, content_hash)
        replayed = True

    claimed = await _claim_notification(db, lead)
    if claimed:
        _schedule_notification(lead)

    return _capture_response(lead, replayed=replayed)


@router.get("", response_model=LeadListResponse)
@contacts_router.get("", response_model=LeadListResponse)
async def list_leads(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """
    List captured leads.
    Restricted to persisted administrators.
    """

    base_query = select(Lead)
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(base_query.order_by(Lead.created_at.desc()).offset(skip).limit(limit))
    leads = result.scalars().all()

    return LeadListResponse(
        items=leads,
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + len(leads)) < total,
    )


@router.get("/{lead_id}", response_model=LeadResponse)
@contacts_router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Get a specific lead by ID."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadResponse)
@contacts_router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Update a specific lead/contact."""

    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    if "email" in updates and updates["email"] is not None:
        lead.email = updates["email"].lower().strip()
    if "name" in updates:
        lead.name = _normalize_optional_text(updates["name"])
    if "company" in updates:
        lead.company = _normalize_optional_text(updates["company"])
    if "message" in updates:
        lead.message = _normalize_optional_text(updates["message"])
    if "source" in updates:
        lead.source = _normalize_optional_text(updates["source"])
    if "tier" in updates:
        lead.tier = _normalize_optional_text(updates["tier"])
    if "interest" in updates:
        lead.interest = _normalize_optional_text(updates["interest"])
    if "locale" in updates:
        lead.locale = _normalize_optional_text(updates["locale"])
        if lead.locale:
            lead.locale = lead.locale.lower()
    if "product_updates_consent" in updates:
        lead.product_updates_consent = updates["product_updates_consent"] is True

    await db.commit()
    await db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
@contacts_router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Delete a specific lead/contact."""

    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    await db.delete(lead)
    await db.commit()
    return None
