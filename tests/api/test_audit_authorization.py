"""Focused authorization tests for the audit API."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.api.auth import oidc
from src.api.auth.jwt import create_access_token
from src.api.models.models import ExternalAuthIdentity, User


class _EmptyAuditLog:
    async def query(self, _filters):
        return []

    async def get_trace(self, _trace_id):
        return []

    async def export_evidence(self, *, run_id=None, session_id=None):
        if run_id is None and session_id is None:
            raise ValueError("Either run_id or session_id is required")
        return {
            "schema_version": "1.0",
            "algorithm": "sha256",
            "run_id": run_id,
            "session_id": session_id,
            "event_count": 0,
            "chain_root": None,
            "verified": True,
            "errors": [],
            "events": [],
        }


@pytest.fixture
def empty_audit_log(monkeypatch: pytest.MonkeyPatch) -> _EmptyAuditLog:
    from src.api.routes import audit as audit_routes

    audit_log = _EmptyAuditLog()

    async def get_empty_audit_log() -> _EmptyAuditLog:
        return audit_log

    monkeypatch.setattr(audit_routes, "get_audit_log", get_empty_audit_log)
    return audit_log


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["ADMIN", "AUDIT_ADMIN"])
async def test_persisted_audit_roles_authorize_dashboard_tokens(
    client_no_auth,
    db_session,
    test_user,
    empty_audit_log,
    role: str,
) -> None:
    test_user.roles = [role]
    db_session.add(test_user)
    await db_session.commit()
    token, _ = create_access_token(test_user.id)

    response = await client_no_auth.get(
        "/v1/audit/events",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"events": [], "total": None}


@pytest.mark.asyncio
async def test_viewer_is_forbidden_from_audit(
    client_no_auth,
    test_user,
    empty_audit_log,
) -> None:
    assert test_user.roles == ["VIEWER"]
    token, _ = create_access_token(test_user.id)

    response = await client_no_auth.get(
        "/v1/audit/events",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer invalid-token"},
    ],
)
async def test_missing_or_invalid_audit_credentials_return_401(
    client_no_auth,
    empty_audit_log,
    headers: dict[str, str],
) -> None:
    response = await client_no_auth.get("/v1/audit/events", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_role_changes_and_revocation_apply_to_an_existing_token(
    client_no_auth,
    db_session,
    test_user,
    empty_audit_log,
) -> None:
    token, _ = create_access_token(test_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    assert (await client_no_auth.get("/v1/audit/events", headers=headers)).status_code == 403

    test_user.roles = ["AUDIT_ADMIN"]
    db_session.add(test_user)
    await db_session.commit()
    assert (await client_no_auth.get("/v1/audit/events", headers=headers)).status_code == 200

    test_user.roles = ["VIEWER"]
    db_session.add(test_user)
    await db_session.commit()
    assert (await client_no_auth.get("/v1/audit/events", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_sso_creates_dashboard_principal_without_trusting_claimed_roles(
    client_no_auth,
    db_session,
    empty_audit_log,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api.routes import auth as auth_routes
    from src.api.services import auth as auth_service

    for name, value in {
        "okta_client_id": "mutx-client",
        "okta_client_secret": "client-secret",
        "okta_domain": "https://id.example.com",
        "public_api_url": "https://api.mutx.dev",
    }.items():
        monkeypatch.setattr(auth_routes.settings, name, value, raising=False)

    async def consume_state(*_args, **_kwargs) -> bool:
        return True

    async def exchange_token(**_kwargs) -> dict[str, str]:
        return {"id_token": "signed-id-token", "access_token": "opaque-access-token"}

    async def verify_token(**_kwargs) -> oidc.TokenPayload:
        return oidc.TokenPayload(
            sub="sso-subject",
            email="sso-audit@example.com",
            email_verified=True,
            roles=["ADMIN", "AUDIT_ADMIN"],
            exp=datetime.fromtimestamp(4_102_444_800, tz=timezone.utc),
        )

    monkeypatch.setattr(auth_routes, "consume_oauth_state", consume_state)
    monkeypatch.setattr(auth_routes, "_exchange_code_for_token", exchange_token)
    monkeypatch.setattr(auth_service, "verify_oauth_token", verify_token)

    callback = await client_no_auth.get(
        "/v1/auth/sso/okta/callback",
        params={"code": "authorization-code", "state": "valid-state"},
    )

    assert callback.status_code == 200
    token = callback.json()["access_token"]
    identity_result = await db_session.execute(
        select(ExternalAuthIdentity).where(
            ExternalAuthIdentity.provider == "okta",
            ExternalAuthIdentity.provider_user_id == "sso-subject",
        )
    )
    identity = identity_result.scalar_one()
    user = await db_session.get(User, identity.user_id)
    assert user is not None
    assert user.roles == ["VIEWER"]

    me = await client_no_auth.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["roles"] == ["VIEWER"]

    audit = await client_no_auth.get(
        "/v1/audit/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert audit.status_code == 403
