"""Stripe integration service for subscriptions, checkout, and webhooks."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription import Subscription, Payment
from src.api.models.models import User, UserSetting

logger = logging.getLogger(__name__)
STRIPE_TRIAL_CLAIM_KEY = "billing:stripe-trial:v1"


class StripeUnavailableError(RuntimeError):
    """Raised when the Stripe integration cannot serve requests."""


class _MissingStripe:
    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            "stripe package is not installed; install project dependencies to use payments"
        )


try:
    import stripe
except ModuleNotFoundError:
    stripe = _MissingStripe()


def _require_stripe() -> Any:
    if isinstance(stripe, _MissingStripe):
        raise StripeUnavailableError(
            "stripe package is not installed; install project dependencies to use payments"
        )
    return stripe


def _configured_plan_prices() -> dict[str, str]:
    plan_prices = {
        "starter": os.getenv("STRIPE_STARTER_PRICE_ID", "").strip(),
        "pro": os.getenv("STRIPE_PRO_PRICE_ID", "").strip(),
        "enterprise": os.getenv("STRIPE_ENTERPRISE_PRICE_ID", "").strip(),
    }
    return {plan: price_id for plan, price_id in plan_prices.items() if price_id}


# Lazy config — reads from env at call time so tests can monkeypatch
def _get_secret_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise StripeUnavailableError("STRIPE_SECRET_KEY not configured")
    return key


def _get_webhook_secret() -> str:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise StripeUnavailableError("STRIPE_WEBHOOK_SECRET not configured")
    return secret


def _configured_trial_days() -> int:
    """Return the server-controlled trial duration; zero disables paid-plan trials."""
    raw_value = os.getenv("STRIPE_TRIAL_DAYS", "7").strip()
    try:
        trial_days = int(raw_value)
    except ValueError as exc:
        raise StripeUnavailableError("STRIPE_TRIAL_DAYS must be an integer from 0 to 30") from exc
    if not 0 <= trial_days <= 30:
        raise StripeUnavailableError("STRIPE_TRIAL_DAYS must be an integer from 0 to 30")
    return trial_days


async def _claim_checkout_trial(
    db: AsyncSession,
    *,
    user: User,
    plan_id: str,
) -> bool:
    """Atomically reserve the user's only paid-plan trial before contacting Stripe."""
    prior_subscription = await db.scalar(
        select(Subscription.id).where(Subscription.user_id == user.id).limit(1)
    )
    if prior_subscription is not None:
        return False

    prior_claim = await db.scalar(
        select(UserSetting.id).where(
            UserSetting.user_id == user.id,
            UserSetting.key == STRIPE_TRIAL_CLAIM_KEY,
        )
    )
    if prior_claim is not None:
        return False

    db.add(
        UserSetting(
            user_id=user.id,
            key=STRIPE_TRIAL_CLAIM_KEY,
            value={
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "plan_id": plan_id,
            },
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


# Map Stripe price IDs to internal plan names
def _price_id_to_plan(price_id: str | None) -> str | None:
    if not price_id:
        return None

    for plan, configured_price_id in _configured_plan_prices().items():
        if price_id == configured_price_id:
            return plan

    return None


def _resolve_checkout_plan_and_price(
    *,
    plan_id: str | None,
    price_id: str | None,
) -> tuple[str, str]:
    configured_prices = _configured_plan_prices()

    if plan_id:
        resolved_price_id = configured_prices.get(plan_id)
        if not resolved_price_id:
            raise StripeUnavailableError(f"Stripe price for plan '{plan_id}' is not configured")
        return plan_id, resolved_price_id

    if price_id:
        resolved_plan = _price_id_to_plan(price_id)
        if not resolved_plan:
            raise ValueError("Unsupported Stripe price")
        return resolved_plan, price_id

    raise ValueError("Either plan_id or price_id is required")


def _subscription_price_id(subscription_data: dict[str, Any]) -> str | None:
    items = subscription_data.get("items", {}).get("data", [])
    if not items:
        return None
    return items[0].get("price", {}).get("id")


def _unix_to_datetime(timestamp: int | None) -> datetime | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _should_grant_plan_access(status: str | None) -> bool:
    return status in {"active", "trialing", "past_due"}


async def _sync_user_plan(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    plan: str,
    status: str | None,
) -> None:
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    if not user:
        return

    user.plan = plan.upper() if _should_grant_plan_access(status) else "FREE"


async def _resolve_subscription_user_id(
    db: AsyncSession,
    subscription_data: dict[str, Any],
) -> uuid.UUID | None:
    user_id_str = subscription_data.get("metadata", {}).get("user_id")
    if user_id_str:
        try:
            return uuid.UUID(user_id_str)
        except ValueError:
            logger.warning("Ignoring invalid Stripe subscription metadata user_id: %s", user_id_str)

    stripe_customer = subscription_data.get("customer")
    if not stripe_customer:
        return None

    existing_result = await db.execute(
        select(Subscription)
        .where(Subscription.stripe_customer_id == stripe_customer)
        .order_by(Subscription.created_at.desc())
    )
    existing_subscription = existing_result.scalars().first()
    if existing_subscription:
        return existing_subscription.user_id

    customer = _require_stripe().Customer.retrieve(stripe_customer, api_key=_get_secret_key())
    customer_user_id = customer.get("metadata", {}).get("user_id")
    if not customer_user_id:
        return None

    try:
        return uuid.UUID(customer_user_id)
    except ValueError:
        logger.warning(
            "Ignoring invalid Stripe customer metadata user_id for customer %s",
            stripe_customer,
        )
        return None


async def _get_or_create_customer(
    db: AsyncSession,
    user: User,
) -> tuple[str, str | None]:
    """Return (stripe_customer_id, existing_subscription_id) for a user.

    Creates a Stripe Customer if the user doesn't have one yet.
    """
    sub = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    existing = sub.scalars().first()
    if existing:
        return existing.stripe_customer_id, existing.stripe_subscription_id

    customer = _require_stripe().Customer.create(
        email=user.email,
        name=user.name,
        metadata={"user_id": str(user.id)},
        api_key=_get_secret_key(),
    )
    return customer.id, None


# ── Checkout ──────────────────────────────────────────────────────────


async def create_checkout_session(
    db: AsyncSession,
    user: User,
    price_id: str | None,
    success_url: str,
    cancel_url: str,
    plan_id: str | None = None,
) -> dict[str, str]:
    """Create a Stripe Checkout Session for subscription signup."""
    stripe_client = _require_stripe()
    resolved_plan_id, resolved_price_id = _resolve_checkout_plan_and_price(
        plan_id=plan_id,
        price_id=price_id,
    )
    trial_days = _configured_trial_days()
    trial_claimed = trial_days > 0 and await _claim_checkout_trial(
        db,
        user=user,
        plan_id=resolved_plan_id,
    )
    customer_id, _ = await _get_or_create_customer(db, user)

    params: dict[str, Any] = {
        "customer": customer_id,
        "client_reference_id": str(user.id),
        "mode": "subscription",
        "line_items": [{"price": resolved_price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "user_id": str(user.id),
            "plan_id": resolved_plan_id,
        },
        "api_key": _get_secret_key(),
    }

    subscription_data: dict[str, Any] = {
        "metadata": {
            "user_id": str(user.id),
            "plan_id": resolved_plan_id,
            "price_id": resolved_price_id,
        }
    }
    if trial_claimed:
        subscription_data["trial_period_days"] = trial_days

    params["subscription_data"] = subscription_data

    session = stripe_client.checkout.Session.create(**params)
    return {"checkout_url": session.url, "session_id": session.id}


# ── Customer Portal ──────────────────────────────────────────────────


async def create_customer_portal(
    db: AsyncSession,
    user: User,
    return_url: str,
) -> dict[str, str]:
    """Create a Stripe Customer Portal session."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    sub = result.scalars().first()
    if not sub:
        raise ValueError("No subscription found for user")

    session = _require_stripe().billing_portal.Session.create(
        customer=sub.stripe_customer_id,
        return_url=return_url,
        api_key=_get_secret_key(),
    )
    return {"portal_url": session.url}


# ── Webhook handlers ─────────────────────────────────────────────────


def verify_webhook_signature(payload: bytes, sig_header: str) -> stripe.Event:
    """Verify and parse a Stripe webhook event."""
    return _require_stripe().Webhook.construct_event(payload, sig_header, _get_webhook_secret())


async def handle_checkout_complete(session_data: dict[str, Any], db: AsyncSession) -> None:
    """Handle checkout.session.completed — create subscription, upgrade user."""
    user_id_str = session_data.get("metadata", {}).get("user_id") or session_data.get(
        "client_reference_id"
    )
    if not user_id_str:
        logger.error("checkout.session.completed: no user_id in metadata")
        return

    user_id = uuid.UUID(user_id_str)
    stripe_sub = session_data.get("subscription")
    stripe_customer = session_data.get("customer")

    if not stripe_sub or not stripe_customer:
        logger.error("checkout.session.completed: missing subscription or customer ID")
        return

    # Fetch subscription details from Stripe
    sub_details = _require_stripe().Subscription.retrieve(stripe_sub, api_key=_get_secret_key())
    sub_status = sub_details.get("status")
    price_id = _subscription_price_id(sub_details)
    plan = _price_id_to_plan(price_id) or session_data.get("metadata", {}).get("plan_id")
    if not plan:
        logger.error(
            "checkout.session.completed: could not resolve plan for subscription %s",
            stripe_sub,
        )
        return

    # Create or update subscription record
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub)
    )
    existing = result.scalars().first()

    if existing:
        existing.status = sub_status
        existing.plan = plan
        existing.current_period_start = _unix_to_datetime(sub_details.get("current_period_start"))
        existing.current_period_end = _unix_to_datetime(sub_details.get("current_period_end"))
        existing.cancel_at_period_end = sub_details.get("cancel_at_period_end", False)
        existing.trial_end = _unix_to_datetime(sub_details.get("trial_end"))
    else:
        new_sub = Subscription(
            user_id=user_id,
            stripe_customer_id=stripe_customer,
            stripe_subscription_id=stripe_sub,
            plan=plan,
            status=sub_status,
            current_period_start=_unix_to_datetime(sub_details.get("current_period_start")),
            current_period_end=_unix_to_datetime(sub_details.get("current_period_end")),
            cancel_at_period_end=sub_details.get("cancel_at_period_end", False),
        )
        if sub_details.get("trial_end"):
            new_sub.trial_end = _unix_to_datetime(sub_details["trial_end"])
            new_sub.status = "trialing"
        db.add(new_sub)

    await _sync_user_plan(db, user_id=user_id, plan=plan, status=sub_status)

    await db.commit()
    logger.info("Subscription created/upgraded: user=%s plan=%s", user_id, plan)


async def handle_subscription_updated(sub_data: dict[str, Any], db: AsyncSession) -> None:
    """Handle customer.subscription.updated — sync status and period."""
    stripe_sub_id = sub_data.get("id")
    if not stripe_sub_id:
        return

    resolved_plan = _price_id_to_plan(_subscription_price_id(sub_data)) or sub_data.get(
        "metadata", {}
    ).get("plan_id")
    stripe_customer = sub_data.get("customer")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = result.scalars().first()
    if not sub:
        user_id = await _resolve_subscription_user_id(db, sub_data)
        if not user_id or not stripe_customer or not resolved_plan:
            logger.warning(
                "subscription.updated: no local record or user mapping for %s", stripe_sub_id
            )
            return

        sub = Subscription(
            user_id=user_id,
            stripe_customer_id=stripe_customer,
            stripe_subscription_id=stripe_sub_id,
            plan=resolved_plan,
            status=sub_data.get("status", "active"),
            current_period_start=_unix_to_datetime(sub_data.get("current_period_start")),
            current_period_end=_unix_to_datetime(sub_data.get("current_period_end")),
            cancel_at_period_end=sub_data.get("cancel_at_period_end", False),
            trial_end=_unix_to_datetime(sub_data.get("trial_end")),
        )
        db.add(sub)
    else:
        sub.status = sub_data.get("status", sub.status)
        sub.cancel_at_period_end = sub_data.get("cancel_at_period_end", False)
        sub.current_period_start = _unix_to_datetime(sub_data.get("current_period_start"))
        sub.current_period_end = _unix_to_datetime(sub_data.get("current_period_end"))
        sub.trial_end = _unix_to_datetime(sub_data.get("trial_end"))
        if resolved_plan:
            sub.plan = resolved_plan

    await _sync_user_plan(db, user_id=sub.user_id, plan=sub.plan, status=sub.status)

    await db.commit()
    logger.info("Subscription updated: %s status=%s", stripe_sub_id, sub.status)


async def handle_subscription_deleted(sub_data: dict[str, Any], db: AsyncSession) -> None:
    """Handle customer.subscription.deleted — downgrade user to FREE."""
    stripe_sub_id = sub_data.get("id")
    if not stripe_sub_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = result.scalars().first()
    if not sub:
        return

    sub.status = "canceled"

    user_result = await db.execute(select(User).where(User.id == sub.user_id))
    user = user_result.scalars().first()
    if user:
        user.plan = "FREE"

    await db.commit()
    logger.info("Subscription canceled: user=%s", sub.user_id)


async def handle_invoice_paid(invoice_data: dict[str, Any], db: AsyncSession) -> None:
    """Handle invoice.paid — create payment record."""
    stripe_invoice_id = invoice_data.get("id")
    stripe_sub_id = invoice_data.get("subscription")
    stripe_customer = invoice_data.get("customer")
    amount = invoice_data.get("amount_paid", invoice_data.get("total", 0))
    currency = invoice_data.get("currency", "usd")

    if not stripe_invoice_id:
        return

    existing_payment_result = await db.execute(
        select(Payment).where(Payment.stripe_invoice_id == stripe_invoice_id)
    )
    existing_payment = existing_payment_result.scalars().first()
    if existing_payment:
        existing_payment.amount_cents = amount
        existing_payment.currency = currency
        existing_payment.status = "paid"
        await db.commit()
        logger.info("Payment already recorded for invoice=%s", stripe_invoice_id)
        return

    # Find user by subscription or customer
    user_id = None
    subscription_id: uuid.UUID | None = None
    subscription_record: Subscription | None = None

    if stripe_sub_id:
        sub_result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        sub = sub_result.scalars().first()
        if sub:
            user_id = sub.user_id
            subscription_id = sub.id
            subscription_record = sub

    if not user_id and stripe_customer:
        sub_result = await db.execute(
            select(Subscription)
            .where(Subscription.stripe_customer_id == stripe_customer)
            .order_by(Subscription.created_at.desc())
        )
        sub = sub_result.scalars().first()
        if sub:
            user_id = sub.user_id
            subscription_id = sub.id
            subscription_record = sub

    if not user_id:
        logger.warning("invoice.paid: could not resolve user for invoice %s", stripe_invoice_id)
        return

    payment = Payment(
        user_id=user_id,
        subscription_id=subscription_id,
        stripe_invoice_id=stripe_invoice_id,
        amount_cents=amount,
        currency=currency,
        status="paid",
    )
    db.add(payment)
    if subscription_record:
        subscription_record.status = "active"
        await _sync_user_plan(
            db,
            user_id=subscription_record.user_id,
            plan=subscription_record.plan,
            status=subscription_record.status,
        )
    await db.commit()
    logger.info("Payment recorded: invoice=%s amount=%d", stripe_invoice_id, amount)


async def handle_invoice_payment_failed(invoice_data: dict[str, Any], db: AsyncSession) -> None:
    """Handle invoice.payment_failed — mark subscription past_due."""
    stripe_sub_id = invoice_data.get("subscription")
    if not stripe_sub_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = result.scalars().first()
    if sub:
        sub.status = "past_due"
        await db.commit()
        logger.info("Subscription past_due: %s", stripe_sub_id)


async def dispatch_webhook_event(event: stripe.Event, db: AsyncSession) -> None:
    """Route a verified Stripe webhook event to the right handler."""
    handler_map = {
        "checkout.session.completed": handle_checkout_complete,
        "customer.subscription.created": handle_subscription_updated,
        "customer.subscription.updated": handle_subscription_updated,
        "customer.subscription.deleted": handle_subscription_deleted,
        "invoice.paid": handle_invoice_paid,
        "invoice.payment_failed": handle_invoice_payment_failed,
    }

    handler = handler_map.get(event.type)
    if not handler:
        logger.debug("Unhandled webhook event type: %s", event.type)
        return

    await handler(event.data.object, db)


# ── Query helpers ────────────────────────────────────────────────────


async def get_subscription_status(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Return current subscription status for a user."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
    )
    sub = result.scalars().first()

    if not sub:
        return {
            "plan": "FREE",
            "status": None,
            "current_period_end": None,
            "cancel_at_period_end": None,
            "trial_end": None,
        }

    return {
        "plan": sub.plan,
        "status": sub.status,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        "cancel_at_period_end": sub.cancel_at_period_end,
        "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
    }


async def cancel_subscription(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict[str, str]:
    """Cancel subscription at period end via Stripe."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status.in_(["active", "trialing"]))
        .order_by(Subscription.created_at.desc())
    )
    sub = result.scalars().first()

    if not sub:
        raise ValueError("No active subscription found")

    _require_stripe().Subscription.modify(
        sub.stripe_subscription_id,
        cancel_at_period_end=True,
        api_key=_get_secret_key(),
    )

    sub.cancel_at_period_end = True
    await db.commit()

    return {"status": "canceling", "message": "Subscription will cancel at period end"}
