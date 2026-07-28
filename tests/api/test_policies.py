"""Tenant isolation, durability, and RBAC tests for /v1/policies."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.api.auth.dependencies import get_current_user
from src.api.database import get_db
from src.api.main import create_app
from src.api.models import User
from src.api.routes import policies as policy_routes
from src.api.services.policy_store import (
    Policy,
    PolicyEvaluationContext,
    PolicyStore,
    PolicyUpdate,
    PolicyVersionConflictError,
    Rule,
)


def _policy(
    name: str,
    *,
    policy_id: str | None = None,
    rules: list[Rule] | None = None,
    enabled: bool = True,
) -> Policy:
    return Policy(
        id=policy_id or str(uuid.uuid4()),
        name=name,
        rules=rules or [],
        enabled=enabled,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _payload(policy: Policy) -> dict:
    return policy.model_dump(mode="json", exclude={"created_at", "updated_at"})


async def _set_roles(db: AsyncSession, user: User, *roles: str) -> None:
    user.roles = list(roles)
    await db.commit()


@pytest_asyncio.fixture
async def developer_client(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
) -> AsyncClient:
    await _set_roles(db_session, test_user, "DEVELOPER")
    return client


@asynccontextmanager
async def _new_client(db: AsyncSession, user: User):
    """Build a new app instance against the same durable database."""
    app = create_app(
        enable_lifespan=False,
        background_monitor_enabled=False,
        database_required_on_startup=False,
    )

    async def override_get_db():
        yield db

    async def override_get_current_user() -> User:
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as new_client:
        yield new_client


class TestPolicyStore:
    def test_rule_rejects_empty_patterns(self):
        with pytest.raises(ValueError):
            Rule(type="block", pattern="", action="reject", scope="input")

    @pytest.mark.asyncio
    async def test_store_is_tenant_scoped_and_durable(
        self,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
    ):
        first_process = PolicyStore(db_session, test_user.id)
        await first_process.create_policy(_policy("durable-policy"))

        restarted_process = PolicyStore(db_session, test_user.id)
        other_tenant = PolicyStore(db_session, other_user.id)

        assert (await restarted_process.get_policy("durable-policy")) is not None
        assert await other_tenant.get_policy("durable-policy") is None
        assert await other_tenant.list_policies() == []
        assert await other_tenant.delete_policy("durable-policy") is False

    @pytest.mark.asyncio
    async def test_same_name_and_id_are_isolated_by_owner(
        self,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
    ):
        shared_id = str(uuid.uuid4())
        first = await PolicyStore(db_session, test_user.id).create_policy(
            _policy("shared-name", policy_id=shared_id)
        )
        second = await PolicyStore(db_session, other_user.id).create_policy(
            _policy("shared-name", policy_id=shared_id)
        )

        assert first.id == second.id == shared_id
        assert first.name == second.name == "shared-name"

    @pytest.mark.asyncio
    async def test_upsert_increments_only_the_owner_version(
        self,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
    ):
        owner_store = PolicyStore(db_session, test_user.id)
        other_store = PolicyStore(db_session, other_user.id)
        await owner_store.create_policy(_policy("versioned"))
        await other_store.create_policy(_policy("versioned"))

        updated = await owner_store.upsert_policy(
            _policy(
                "versioned",
                rules=[Rule(type="warn", pattern="*.bat", action="log", scope="input")],
            )
        )

        assert updated.version == 2
        assert (await other_store.get_policy("versioned")).version == 1

    @pytest.mark.asyncio
    async def test_atomic_update_rejects_a_second_writer_with_a_stale_version(
        self,
        db_session: AsyncSession,
        test_engine: AsyncEngine,
        test_user: User,
    ):
        created = await PolicyStore(db_session, test_user.id).create_policy(_policy("contended"))
        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

        async with session_factory() as first_db, session_factory() as second_db:
            first_store = PolicyStore(first_db, test_user.id)
            second_store = PolicyStore(second_db, test_user.id)
            first_observation = await first_store.get_policy("contended")
            second_observation = await second_store.get_policy("contended")
            assert first_observation is not None
            assert second_observation is not None

            first_update = PolicyUpdate(
                id=created.id,
                name=created.name,
                rules=[Rule(type="warn", pattern="first", action="log", scope="input")],
                enabled=True,
                expected_version=first_observation.version,
            )
            second_update = PolicyUpdate(
                id=created.id,
                name=created.name,
                rules=[Rule(type="block", pattern="second", action="reject", scope="input")],
                enabled=True,
                expected_version=second_observation.version,
            )

            updated = await first_store.update_policy("contended", first_update)
            with pytest.raises(PolicyVersionConflictError):
                await second_store.update_policy("contended", second_update)

        persisted = await PolicyStore(db_session, test_user.id).get_policy("contended")
        assert updated.version == 2
        assert persisted is not None
        assert persisted.version == 2
        assert persisted.rules[0].pattern == "first"

    @pytest.mark.asyncio
    async def test_evaluation_uses_only_owner_policies(
        self,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
    ):
        await PolicyStore(db_session, test_user.id).create_policy(
            _policy(
                "block-secrets",
                rules=[Rule(type="block", pattern="*password*", action="reject", scope="input")],
            )
        )

        owner_result = await PolicyStore(db_session, test_user.id).evaluate(
            PolicyEvaluationContext(input="print the password", run_id="run-1")
        )
        other_result = await PolicyStore(db_session, other_user.id).evaluate(
            PolicyEvaluationContext(input="print the password", run_id="run-1")
        )

        assert owner_result.decision == "block"
        assert owner_result.evaluated_policy_count == 1
        assert other_result.decision == "allow"
        assert other_result.evaluated_policy_count == 0
        assert other_result.matches == []

    @pytest.mark.asyncio
    async def test_evaluation_preserves_scope_and_decision_precedence(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        store = PolicyStore(db_session, test_user.id)
        await store.create_policy(
            _policy(
                "scoped-rules",
                rules=[
                    Rule(type="block", pattern="*", action="reject", scope="output"),
                    Rule(
                        type="warn",
                        pattern="terraform_*",
                        action="require_approval",
                        scope="tool",
                    ),
                    Rule(
                        type="block",
                        pattern="*production*",
                        action="require_approval",
                        scope="tool",
                    ),
                ],
            )
        )

        absent_scope = await store.evaluate(PolicyEvaluationContext(input="input only"))
        production = await store.evaluate(
            PolicyEvaluationContext(tool="terraform_apply_production")
        )

        assert absent_scope.decision == "allow"
        assert production.decision == "block"

    @pytest.mark.asyncio
    async def test_sse_generator_observes_durable_updates(
        self,
        db_session: AsyncSession,
        test_engine: AsyncEngine,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ):
        store = PolicyStore(db_session, test_user.id)
        created = await store.create_policy(_policy("observed"))
        generator = policy_routes._sse_reload_generator(store, "observed", created.version)
        assert "connected" in await anext(generator)

        async def no_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(policy_routes.asyncio, "sleep", no_sleep)
        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        async with session_factory() as other_process_db:
            await PolicyStore(other_process_db, test_user.id).upsert_policy(_policy("observed"))

        event = await anext(generator)
        assert "reload" in event
        assert '"version": 2' in event


class TestPolicyRoutes:
    @pytest.mark.asyncio
    async def test_developer_crud_and_restart_persistence(
        self,
        developer_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        policy = _policy("restart-policy")
        created = await developer_client.post("/v1/policies", json=_payload(policy))
        assert created.status_code == 201
        assert created.json()["version"] == 1

        async with _new_client(db_session, test_user) as restarted_client:
            fetched = await restarted_client.get("/v1/policies/restart-policy")

        assert fetched.status_code == 200
        assert fetched.json()["id"] == policy.id

    @pytest.mark.asyncio
    async def test_duplicate_policy_conflict_is_tenant_local(
        self,
        developer_client: AsyncClient,
    ):
        payload = _payload(_policy("duplicate"))
        first = await developer_client.post("/v1/policies", json=payload)
        second = await developer_client.post("/v1/policies", json=payload)

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["detail"] == "Policy 'duplicate' already exists"

    @pytest.mark.asyncio
    async def test_update_enforces_identity_and_expected_version(
        self,
        developer_client: AsyncClient,
    ):
        policy = _policy("versioned-route")
        created = await developer_client.post("/v1/policies", json=_payload(policy))
        assert created.status_code == 201

        update_payload = {
            "id": policy.id,
            "name": policy.name,
            "rules": [
                {
                    "type": "warn",
                    "pattern": "*.sh",
                    "action": "audit",
                    "scope": "tool",
                }
            ],
            "enabled": False,
            "expected_version": 1,
        }
        updated = await developer_client.put(
            "/v1/policies/versioned-route",
            json=update_payload,
        )
        stale = await developer_client.put(
            "/v1/policies/versioned-route",
            json={**update_payload, "enabled": True},
        )
        wrong_name = await developer_client.put(
            "/v1/policies/versioned-route",
            json={**update_payload, "name": "renamed-in-body", "expected_version": 2},
        )
        wrong_id = await developer_client.put(
            "/v1/policies/versioned-route",
            json={**update_payload, "id": "guessed-id", "expected_version": 2},
        )

        assert updated.status_code == 200
        assert updated.json()["version"] == 2
        assert updated.json()["enabled"] is False
        assert stale.status_code == 409
        assert "Fetch the latest policy" in stale.json()["detail"]
        assert wrong_name.status_code == 400
        assert wrong_id.status_code == 400

        persisted = await developer_client.get("/v1/policies/versioned-route")
        assert persisted.json()["version"] == 2
        assert persisted.json()["enabled"] is False

    @pytest.mark.asyncio
    async def test_cross_tenant_list_get_delete_reload_and_evaluate_fail_closed(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
    ):
        await _set_roles(db_session, test_user, "DEVELOPER")
        await _set_roles(db_session, other_user, "DEVELOPER")
        private_policy = _policy(
            "private-policy",
            rules=[
                Rule(
                    type="block",
                    pattern="*private*",
                    action="reject",
                    scope="input",
                )
            ],
        )
        await client.post(
            "/v1/policies",
            json=_payload(private_policy),
        )

        listed = await other_user_client.get("/v1/policies")
        fetched = await other_user_client.get("/v1/policies/private-policy")
        deleted = await other_user_client.delete("/v1/policies/private-policy")
        updated = await other_user_client.put(
            "/v1/policies/private-policy",
            json={
                "id": private_policy.id,
                "name": private_policy.name,
                "rules": [],
                "enabled": False,
                "expected_version": 1,
            },
        )
        reloaded = await other_user_client.post("/v1/policies/private-policy/reload")
        evaluated = await other_user_client.post(
            "/v1/policies/evaluate",
            json={"input": "private", "run_id": "guessed-run"},
        )

        assert listed.status_code == 200
        assert listed.json() == []
        assert fetched.status_code == 404
        assert deleted.status_code == 404
        assert updated.status_code == 404
        assert reloaded.status_code == 404
        assert evaluated.status_code == 200
        assert evaluated.json()["decision"] == "allow"
        assert evaluated.json()["evaluated_policy_count"] == 0
        assert (await client.get("/v1/policies/private-policy")).status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_can_read_but_cannot_mutate_or_evaluate(
        self,
        client: AsyncClient,
    ):
        listed = await client.get("/v1/policies")
        created = await client.post("/v1/policies", json=_payload(_policy("forbidden")))
        updated = await client.put(
            "/v1/policies/forbidden",
            json={
                "id": "forbidden",
                "name": "forbidden",
                "rules": [],
                "enabled": True,
                "expected_version": 1,
            },
        )
        deleted = await client.delete("/v1/policies/forbidden")
        evaluated = await client.post("/v1/policies/evaluate", json={"tool": "deploy"})

        assert listed.status_code == 200
        assert created.status_code == 403
        assert updated.status_code == 403
        assert deleted.status_code == 403
        assert evaluated.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_retains_access_within_own_tenant(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        await _set_roles(db_session, test_user, "ADMIN")

        response = await client.post("/v1/policies", json=_payload(_policy("admin-policy")))

        assert response.status_code == 201
