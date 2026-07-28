"""Payment and subscription management routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import get_current_user
from src.api.models.models import User
from src.api.models.payment_schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalRequest,
    CustomerPortalResponse,
    SubscriptionStatus,
)
from src.api.services.stripe_service import (
    cancel_subscription,
    create_checkout_session,
    create_customer_portal,
    dispatch_webhook_event,
    get_subscription_status,
    StripeUnavailableError,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def checkout(
    payload: CheckoutSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Stripe Checkout session for subscription signup."""
    try:
        result = await create_checkout_session(
            db=db,
            user=current_user,
            plan_id=payload.plan_id,
            price_id=payload.price_id,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
    except StripeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Checkout session creation failed")
        raise HTTPException(status_code=500, detail="Failed to create checkout session") from exc

    return CheckoutSessionResponse(**result)


@router.post("/portal", response_model=CustomerPortalResponse)
async def customer_portal(
    payload: CustomerPortalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Stripe Customer Portal session for managing subscriptions."""
    try:
        result = await create_customer_portal(
            db=db,
            user=current_user,
            return_url=payload.return_url,
        )
    except StripeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Portal session creation failed")
        raise HTTPException(status_code=500, detail="Failed to create portal session") from exc

    return CustomerPortalResponse(**result)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events.

    This endpoint does NOT require auth — Stripe authenticates via signature.
    """
    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = verify_webhook_signature(body, sig_header)
    except StripeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature") from exc

    try:
        await dispatch_webhook_event(event, db)
    except StripeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Webhook handler error for event %s", event.type)
        raise HTTPException(status_code=500, detail="Failed to process webhook") from exc

    return {"received": True}


@router.get("/subscription", response_model=SubscriptionStatus)
async def get_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current subscription status for the authenticated user."""
    result = await get_subscription_status(db, user_id=current_user.id)
    return SubscriptionStatus(**result)


@router.post("/cancel")
async def cancel(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel the current subscription at period end."""
    try:
        result = await cancel_subscription(db, user_id=current_user.id)
    except StripeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Subscription cancellation failed")
        raise HTTPException(status_code=500, detail="Failed to cancel subscription") from exc

    return result
