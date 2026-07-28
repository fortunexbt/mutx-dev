from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
import uuid
import logging
from typing import Optional

from src.api.database import get_db
from src.api.models import User, Webhook, WebhookDeliveryLog
from src.api.services.webhook_handler import WebhookEventType as WebhookEvent
from src.api.models.schemas import (
    WebhookCreate,
    WebhookUpdate,
    WebhookResponse,
    WebhookListResponse,
    WebhookDeliveryListResponse,
    WebhookRetryRequest,
)
from src.api.auth.dependencies import get_current_user_or_api_key
from src.api.security import encrypt_secret_value
from src.api.services.auth import Role, check_role
from src.api.services.webhook_service import (
    UnsafeWebhookDestinationError,
    ensure_safe_webhook_destination,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


def _serialize_webhook(
    webhook: Webhook,
    total_deliveries: Optional[int] = None,
    successful_deliveries: Optional[int] = None,
    failed_deliveries: Optional[int] = None,
) -> WebhookResponse:
    return WebhookResponse(
        id=webhook.id,
        user_id=webhook.user_id,
        name=getattr(webhook, "name", None),
        url=webhook.url,
        events=webhook.events or [],
        secret=None,
        has_secret=bool(webhook.secret),
        is_active=webhook.is_active,
        circuit_open=getattr(webhook, "consecutive_failures", 0) >= 5,  # CIRCUIT_BREAKER_THRESHOLD
        consecutive_failures=getattr(webhook, "consecutive_failures", 0),
        created_at=webhook.created_at,
        total_deliveries=total_deliveries,
        successful_deliveries=successful_deliveries,
        failed_deliveries=failed_deliveries,
    )


def _validate_webhook_events(events: list[str]) -> None:
    allowed_events = [e.value for e in WebhookEvent]
    for event in events:
        if event == "*":
            continue

        if event not in allowed_events:
            if not any(
                event.startswith(p.split(".")[0] + ".*") for p in allowed_events if "." in p
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid event: {event}. Supported events: {allowed_events} and '*'",
                )


async def _validate_webhook_url(url: str) -> None:
    try:
        await ensure_safe_webhook_destination(url)
    except UnsafeWebhookDestinationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _get_owned_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
    *,
    not_found_detail: str = "Webhook not found",
    forbidden_detail: str = "Not authorized to access this webhook",
) -> Webhook:
    result = await db.execute(select(Webhook).where(Webhook.id == webhook_id))
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(status_code=404, detail=not_found_detail)
    if webhook.user_id != current_user.id:
        raise HTTPException(status_code=403, detail=forbidden_detail)

    return webhook


async def get_webhook_auth(
    authorization: Optional[str] = Header(None, description="Bearer token for JWT auth"),
    x_api_key: Optional[str] = Header(
        None, alias="X-API-Key", description="API key for webhook management"
    ),
    session: AsyncSession = Depends(get_db),
    *,
    request: Request,
) -> User:
    """Authenticate webhook management requests via JWT or API key."""
    user = await get_current_user_or_api_key(
        request=request,
        authorization=authorization,
        x_api_key=x_api_key,
        session=session,
    )
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication. Provide valid JWT Bearer token or X-API-Key header.",
        )
    return user


async def get_webhook_reader(
    current_user: User = Depends(get_webhook_auth),
) -> User:
    """Require an owner principal with a persisted read-capable role."""

    if not check_role(current_user.roles or [], [Role.VIEWER, Role.DEVELOPER]):
        raise HTTPException(status_code=403, detail="Insufficient webhook read permissions")
    return current_user


async def get_webhook_developer(
    current_user: User = Depends(get_webhook_auth),
) -> User:
    """Require a persisted developer role for webhook mutations and delivery."""

    if not check_role(current_user.roles or [], [Role.DEVELOPER]):
        raise HTTPException(status_code=403, detail="Insufficient webhook mutation permissions")
    return current_user


@router.post("/", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    webhook_data: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_webhook_developer),
):
    """Register a new webhook endpoint."""
    await _validate_webhook_url(webhook_data.url)
    _validate_webhook_events(webhook_data.events)

    webhook = Webhook(
        user_id=current_user.id,
        name=webhook_data.name,
        url=webhook_data.url,
        events=webhook_data.events,
        secret=encrypt_secret_value(webhook_data.secret),
        is_active=webhook_data.is_active,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    logger.info(f"Webhook created: {webhook.id} for user {current_user.id}")
    return _serialize_webhook(webhook)


@router.get("/", response_model=WebhookListResponse)
async def list_webhooks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_webhook_reader),
):
    """List all webhooks registered by the authenticated user."""
    filters = [Webhook.user_id == current_user.id]

    total_stmt = select(func.count()).select_from(Webhook).where(*filters)
    total = (await db.execute(total_stmt)).scalar_one()

    result = await db.execute(select(Webhook).where(*filters).offset(skip).limit(limit))
    webhooks = result.scalars().all()
    return WebhookListResponse(
        items=[_serialize_webhook(w) for w in webhooks],
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(webhooks),
    )


@router.get("/verify-docs")
async def webhook_verify_docs(
    current_user: User = Depends(get_webhook_reader),
):
    """Documentation for verifying webhook signatures.

    Returns instructions for consumers to verify the HMAC-SHA256 signature
    included in webhook deliveries.
    """
    return {
        "algorithm": "HMAC-SHA256",
        "header": "X-Webhook-Signature",
        "format": "sha256=<hex>",
        "verification_steps": [
            "1. Extract the value of the X-Webhook-Signature header from the incoming request.",
            "2. Remove the 'sha256=' prefix to get the hex digest.",
            "3. Compute HMAC-SHA256 of the raw request body using your webhook secret as the key.",
            "4. Compare the computed hex digest to the extracted signature using a constant-time comparison.",
            "5. If they match, the webhook is authentic.",
        ],
        "example_nodejs": (
            "const crypto = require('crypto');\n"
            "function verifySignature(payload, signature, secret) {\n"
            "  const expected = signature.replace('sha256=', '');\n"
            "  const hmac = crypto.createHmac('sha256', secret);\n"
            "  hmac.update(payload);\n"
            "  const digest = hmac.digest('hex');\n"
            "  try {\n"
            "    return crypto.timingSafeEqual(\n"
            "      Buffer.from(expected, 'hex'),\n"
            "      Buffer.from(digest, 'hex')\n"
            "    );\n"
            "  } catch { return false; }\n"
            "}"
        ),
    }


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_webhook_reader),
):
    """Get a specific webhook by ID."""
    webhook = await _get_owned_webhook(webhook_id, db, current_user)
    return _serialize_webhook(webhook)


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: uuid.UUID,
    webhook_data: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_webhook_developer),
):
    """Update an existing webhook."""
    webhook = await _get_owned_webhook(webhook_id, db, current_user)

    # Update fields if provided
    if webhook_data.url is not None:
        await _validate_webhook_url(webhook_data.url)
        webhook.url = webhook_data.url

    if webhook_data.name is not None:
        webhook.name = webhook_data.name

    if webhook_data.events is not None:
        _validate_webhook_events(webhook_data.events)
        webhook.events = webhook_data.events

    if webhook_data.is_active is not None:
        webhook.is_active = webhook_data.is_active

    # Reset circuit breaker if requested
    if webhook_data.reset_circuit:
        webhook.consecutive_failures = 0
        logger.info(f"Circuit breaker reset for webhook {webhook.id}")

    await db.commit()
    await db.refresh(webhook)

    logger.info(f"Webhook updated: {webhook.id}")
    return _serialize_webhook(webhook)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_webhook_developer),
):
    """Delete a webhook."""
    webhook = await _get_owned_webhook(webhook_id, db, current_user)

    await db.delete(webhook)
    await db.commit()

    logger.info(f"Webhook deleted: {webhook_id}")
    return None


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_webhook_developer),
):
    """Send a test event to a webhook to verify it's working."""
    webhook = await _get_owned_webhook(webhook_id, db, current_user)
    await _validate_webhook_url(webhook.url)

    # Import the delivery function
    from src.api.services.webhook_service import deliver_webhook_with_retry

    test_payload = {
        "message": "This is a test webhook from MUTX",
        "event": "test",
    }

    success = await deliver_webhook_with_retry(db, webhook, "test", test_payload)

    if success:
        return {"status": "test_delivered", "message": "Test event delivered successfully"}
    else:
        raise HTTPException(
            status_code=502,
            detail="Test event delivery failed. Check webhook URL and ensure it's reachable.",
        )


@router.get("/{webhook_id}/deliveries", response_model=WebhookDeliveryListResponse)
async def list_webhook_deliveries(
    webhook_id: uuid.UUID,
    event: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_webhook_reader),
):
    """List delivery attempts for a webhook owned by the authenticated user."""
    webhook = await _get_owned_webhook(webhook_id, db, current_user)

    filters = [WebhookDeliveryLog.webhook_id == webhook.id]
    if event is not None:
        filters.append(WebhookDeliveryLog.event == event)
    if success is not None:
        filters.append(WebhookDeliveryLog.success == success)

    total_stmt = select(func.count()).select_from(WebhookDeliveryLog).where(*filters)
    total = (await db.execute(total_stmt)).scalar_one()

    query = (
        select(WebhookDeliveryLog)
        .where(*filters)
        .order_by(WebhookDeliveryLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    deliveries = result.scalars().all()
    return WebhookDeliveryListResponse(
        webhook_id=webhook.id,
        items=deliveries,
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(deliveries),
        event=event,
        success=success,
    )


@router.post("/retry")
async def retry_webhook_delivery(
    request: WebhookRetryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_webhook_developer),
):
    """Manually retry a specific webhook delivery.

    Looks up the original delivery, re-delivers the event to the same webhook
    with no auto-retry. Links the new delivery to the original via parent_delivery_id.
    """
    # Find the original delivery
    result = await db.execute(
        select(WebhookDeliveryLog).where(WebhookDeliveryLog.id == request.delivery_id)
    )
    original = result.scalar_one_or_none()

    if not original:
        raise HTTPException(status_code=404, detail="Delivery not found")

    # Verify ownership through webhook
    webhook = await _get_owned_webhook(original.webhook_id, db, current_user)

    # Parse original payload
    import json as _json

    try:
        payload = _json.loads(original.payload)
    except (ValueError, TypeError):
        payload = {"data": original.payload}

    # Deliver with no auto-retry (single attempt), linked to original
    from src.api.services.webhook_service import (
        deliver_webhook_with_retry,
    )

    success = await deliver_webhook_with_retry(
        db,
        webhook,
        original.event,
        payload,
        parent_delivery_id=original.id,
    )

    if success:
        return {
            "status": "retry_delivered",
            "message": "Retry delivery successful",
            "original_delivery_id": str(original.id),
        }
    else:
        raise HTTPException(
            status_code=502,
            detail="Retry delivery failed. Check webhook URL and circuit breaker state.",
        )
