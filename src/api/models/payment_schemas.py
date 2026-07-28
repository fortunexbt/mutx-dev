"""Pydantic schemas for Stripe checkout, subscription status, customer portal, and payments."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CheckoutSessionRequest(BaseModel):
    """Request body for creating a Stripe Checkout Session."""

    model_config = ConfigDict(extra="forbid")

    plan_id: Optional[Literal["starter", "pro"]] = Field(
        None,
        description="Supported MUTX plan identifier",
    )
    price_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Stripe Price ID",
    )
    success_url: str = Field(..., min_length=1, description="URL to redirect on success")
    cancel_url: str = Field(..., min_length=1, description="URL to redirect on cancellation")

    @model_validator(mode="after")
    def validate_checkout_target(self) -> CheckoutSessionRequest:
        if not self.plan_id and not self.price_id:
            raise ValueError("Either plan_id or price_id is required")
        return self


class CheckoutSessionResponse(BaseModel):
    """Response containing the Stripe Checkout Session URL and ID."""

    checkout_url: str = Field(..., description="Stripe Checkout Session URL")
    session_id: str = Field(..., description="Stripe Checkout Session ID")


class SubscriptionStatus(BaseModel):
    """Current subscription status for a user."""

    plan: Optional[str] = Field(None, description="Subscription plan name")
    status: Optional[str] = Field(None, description="Subscription status")
    current_period_end: Optional[datetime] = Field(
        None, description="End of the current billing period"
    )
    cancel_at_period_end: Optional[bool] = Field(
        None, description="Whether the subscription cancels at period end"
    )
    trial_end: Optional[datetime] = Field(None, description="Trial period end date")


class CustomerPortalRequest(BaseModel):
    """Request body for creating a Stripe Customer Portal session."""

    return_url: str = Field(..., min_length=1, description="URL to return to after portal session")


class CustomerPortalResponse(BaseModel):
    """Response containing the Stripe Customer Portal URL."""

    portal_url: str = Field(..., description="Stripe Customer Portal URL")


class PaymentResponse(BaseModel):
    """Response schema for a payment record."""

    id: uuid.UUID = Field(..., description="Payment UUID")
    user_id: uuid.UUID = Field(..., description="User UUID")
    subscription_id: Optional[uuid.UUID] = Field(None, description="Subscription UUID")
    stripe_invoice_id: str = Field(..., description="Stripe Invoice ID")
    amount_cents: int = Field(..., description="Payment amount in cents")
    currency: str = Field(default="usd", description="ISO 4217 currency code")
    status: str = Field(..., description="Payment status")
    created_at: datetime = Field(..., description="Payment creation timestamp")
