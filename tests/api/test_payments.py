from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.api.services import stripe_service


def test_missing_stripe_dependency_raises_actionable_runtime_error(monkeypatch):
    monkeypatch.setattr(stripe_service, "stripe", stripe_service._MissingStripe())

    with pytest.raises(RuntimeError, match="stripe package is not installed"):
        stripe_service._require_stripe()


@pytest.mark.asyncio
async def test_create_checkout_session_uses_server_side_plan_mapping(
    db_session,
    test_user,
    monkeypatch,
):
    captured: dict[str, object] = {}

    async def fake_get_or_create_customer(*_args, **_kwargs):
        return "cus_test", None

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_test", url="https://checkout.stripe.test/session")

    monkeypatch.setenv("STRIPE_STARTER_PRICE_ID", "price_starter")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(stripe_service, "_get_or_create_customer", fake_get_or_create_customer)
    monkeypatch.setattr(stripe_service.stripe.checkout.Session, "create", fake_create)

    result = await stripe_service.create_checkout_session(
        db=db_session,
        user=test_user,
        plan_id="pro",
        price_id=None,
        success_url="https://pico.mutx.dev/onboarding?checkout=success",
        cancel_url="https://pico.mutx.dev/pricing?checkout=canceled",
    )

    assert result == {
        "checkout_url": "https://checkout.stripe.test/session",
        "session_id": "cs_test",
    }
    assert captured["client_reference_id"] == str(test_user.id)
    assert captured["line_items"] == [{"price": "price_pro", "quantity": 1}]
    assert captured["metadata"] == {"user_id": str(test_user.id), "plan_id": "pro"}
    assert captured["subscription_data"] == {
        "metadata": {
            "user_id": str(test_user.id),
            "plan_id": "pro",
            "price_id": "price_pro",
        },
        "trial_period_days": 7,
    }


@pytest.mark.asyncio
async def test_checkout_trial_is_server_controlled_and_granted_only_once(
    db_session,
    test_user,
    monkeypatch,
):
    captured: list[dict[str, object]] = []

    async def fake_get_or_create_customer(*_args, **_kwargs):
        return "cus_test", None

    def fake_create(**kwargs):
        captured.append(kwargs)
        index = len(captured)
        return SimpleNamespace(
            id=f"cs_test_{index}",
            url=f"https://checkout.stripe.test/session/{index}",
        )

    monkeypatch.setenv("STRIPE_STARTER_PRICE_ID", "price_starter")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_TRIAL_DAYS", "7")
    monkeypatch.setattr(stripe_service, "_get_or_create_customer", fake_get_or_create_customer)
    monkeypatch.setattr(stripe_service.stripe.checkout.Session, "create", fake_create)

    for _ in range(2):
        await stripe_service.create_checkout_session(
            db=db_session,
            user=test_user,
            plan_id="starter",
            price_id=None,
            success_url="https://pico.mutx.dev/pricing?checkout=success",
            cancel_url="https://pico.mutx.dev/pricing?checkout=canceled",
        )

    assert captured[0]["subscription_data"]["trial_period_days"] == 7
    assert "trial_period_days" not in captured[1]["subscription_data"]


@pytest.mark.asyncio
async def test_handle_checkout_complete_resolves_plan_from_subscription_items(
    db_session,
    test_user,
    monkeypatch,
):
    now = int(datetime.now(timezone.utc).timestamp())

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_STARTER_PRICE_ID", "price_starter")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")
    monkeypatch.setattr(
        stripe_service.stripe.Subscription,
        "retrieve",
        lambda *_args, **_kwargs: {
            "id": "sub_test",
            "status": "active",
            "current_period_start": now,
            "current_period_end": now + 3600,
            "cancel_at_period_end": False,
            "items": {"data": [{"price": {"id": "price_pro"}}]},
        },
    )

    await stripe_service.handle_checkout_complete(
        {
            "id": "cs_test",
            "customer": "cus_test",
            "subscription": "sub_test",
            "metadata": {"user_id": str(test_user.id), "plan_id": "pro"},
        },
        db_session,
    )

    result = await db_session.execute(
        stripe_service.select(stripe_service.Subscription).where(
            stripe_service.Subscription.stripe_subscription_id == "sub_test"
        )
    )
    subscription = result.scalars().first()

    assert subscription is not None
    assert subscription.plan == "pro"
    assert subscription.stripe_customer_id == "cus_test"

    await db_session.refresh(test_user)
    assert test_user.plan == "PRO"


@pytest.mark.asyncio
async def test_checkout_route_requires_auth(client_no_auth):
    response = await client_no_auth.post(
        "/v1/payments/checkout",
        json={
            "plan_id": "starter",
            "success_url": "https://pico.mutx.dev/onboarding?checkout=success",
            "cancel_url": "https://pico.mutx.dev/pricing?checkout=canceled",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_checkout_route_rejects_client_controlled_trial_duration(client):
    response = await client.post(
        "/v1/payments/checkout",
        json={
            "plan_id": "starter",
            "success_url": "https://pico.mutx.dev/pricing?checkout=success",
            "cancel_url": "https://pico.mutx.dev/pricing?checkout=canceled",
            "trial_days": 365,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_checkout_route_rejects_unsupported_price_id(client, monkeypatch):
    monkeypatch.setenv("STRIPE_STARTER_PRICE_ID", "price_starter")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")

    response = await client.post(
        "/v1/payments/checkout",
        json={
            "price_id": "price_unknown",
            "success_url": "https://pico.mutx.dev/onboarding?checkout=success",
            "cancel_url": "https://pico.mutx.dev/pricing?checkout=canceled",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported Stripe price"


@pytest.mark.asyncio
async def test_portal_returns_503_when_stripe_dependency_is_missing(client, monkeypatch):
    async def raise_missing_stripe(*_args, **_kwargs):
        raise stripe_service.StripeUnavailableError("stripe package is not installed")

    monkeypatch.setattr(
        "src.api.routes.payments.create_customer_portal",
        raise_missing_stripe,
    )

    response = await client.post(
        "/v1/payments/portal",
        json={"return_url": "https://pico.mutx.dev/settings"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "stripe package is not installed"


@pytest.mark.asyncio
async def test_cancel_returns_503_when_stripe_dependency_is_missing(client, monkeypatch):
    async def raise_missing_stripe(*_args, **_kwargs):
        raise stripe_service.StripeUnavailableError("stripe package is not installed")

    monkeypatch.setattr(
        "src.api.routes.payments.cancel_subscription",
        raise_missing_stripe,
    )

    response = await client.post("/v1/payments/cancel")

    assert response.status_code == 503
    assert response.json()["detail"] == "stripe package is not installed"


@pytest.mark.asyncio
async def test_webhook_returns_503_when_stripe_dependency_is_missing(
    client_no_auth,
    monkeypatch,
):
    def raise_missing_stripe(*_args, **_kwargs):
        raise stripe_service.StripeUnavailableError("stripe package is not installed")

    monkeypatch.setattr(
        "src.api.routes.payments.verify_webhook_signature",
        raise_missing_stripe,
    )

    response = await client_no_auth.post(
        "/v1/payments/webhook",
        content=b"{}",
        headers={"stripe-signature": "sig_test"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "stripe package is not installed"


@pytest.mark.asyncio
async def test_webhook_returns_503_when_signing_secret_is_missing(
    client_no_auth,
    monkeypatch,
):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)

    response = await client_no_auth.post(
        "/v1/payments/webhook",
        content=b"{}",
        headers={"stripe-signature": "sig_test"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "STRIPE_WEBHOOK_SECRET not configured"


@pytest.mark.asyncio
async def test_webhook_returns_503_when_handler_dependency_is_missing(
    client_no_auth,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.api.routes.payments.verify_webhook_signature",
        lambda *_args, **_kwargs: SimpleNamespace(
            type="checkout.session.completed",
            data=SimpleNamespace(object={}),
        ),
    )

    async def raise_missing_stripe(*_args, **_kwargs):
        raise stripe_service.StripeUnavailableError("stripe package is not installed")

    monkeypatch.setattr(
        "src.api.routes.payments.dispatch_webhook_event",
        raise_missing_stripe,
    )

    response = await client_no_auth.post(
        "/v1/payments/webhook",
        content=b"{}",
        headers={"stripe-signature": "sig_test"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "stripe package is not installed"


@pytest.mark.asyncio
async def test_webhook_returns_500_when_dispatch_fails(client_no_auth, monkeypatch):
    monkeypatch.setattr(
        "src.api.routes.payments.verify_webhook_signature",
        lambda *_args, **_kwargs: SimpleNamespace(
            type="invoice.paid", data=SimpleNamespace(object={})
        ),
    )

    async def raise_dispatch(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.api.routes.payments.dispatch_webhook_event", raise_dispatch)

    response = await client_no_auth.post(
        "/v1/payments/webhook",
        content=b"{}",
        headers={"stripe-signature": "sig_test"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to process webhook"


@pytest.mark.asyncio
async def test_handle_invoice_paid_is_idempotent(db_session, test_user):
    subscription = stripe_service.Subscription(
        user_id=test_user.id,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        plan="starter",
        status="active",
    )
    db_session.add(subscription)
    await db_session.commit()

    invoice_payload = {
        "id": "in_test",
        "subscription": "sub_test",
        "customer": "cus_test",
        "amount_paid": 900,
        "currency": "eur",
    }

    await stripe_service.handle_invoice_paid(invoice_payload, db_session)
    await stripe_service.handle_invoice_paid(invoice_payload, db_session)

    result = await db_session.execute(
        stripe_service.select(stripe_service.Payment).where(
            stripe_service.Payment.stripe_invoice_id == "in_test"
        )
    )
    payments = result.scalars().all()

    assert len(payments) == 1
    assert payments[0].amount_cents == 900
