"""
Tests for /policies endpoints.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from src.api.models import User, UserSetting
from src.api.routes.approvals import APPROVAL_KEY_PREFIX, _list_approval_settings
from src.api.routes.policies import (
    _policy_approval_dedupe_key,
    _redact_secret_text,
    evaluate_policies_and_request_approval,
)
from src.api.services.approval import ApprovalRequest
from src.api.services.policy_store import (
    Policy,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
    PolicyStore,
    Rule,
)


@pytest.mark.parametrize(
    ("value", "secret"),
    [
        (
            r'{"password": "two \"word\" passphrase", "ticket": "OPS-42"}',
            r"two \"word\" passphrase",
        ),
        ("Authorization: Bearer bearer-value", "bearer-value"),
        ("Set-Cookie: sid=session-secret; Path=/; HttpOnly", "session-secret"),
        ("credentials=service-account-secret", "service-account-secret"),
        ("DATABASE_PASSWORD=database-secret", "database-secret"),
        ("tenantRefreshToken=refresh-secret", "refresh-secret"),
        ("callback=https://example.test/?token=url-secret", "url-secret"),
        ("token=eyJheader.payload.signature", "eyJheader.payload.signature"),
        ("key sk-abcdefghijklmnopqrstuvwxyz", "sk-abcdefghijklmnopqrstuvwxyz"),
        ("AWS key AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
        (
            "-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----",
            "private-material",
        ),
    ],
)
def test_policy_approval_secret_text_redaction(value: str, secret: str):
    safe_value, redacted = _redact_secret_text(value)

    assert redacted is True
    assert secret not in safe_value
    assert "[REDACTED]" in safe_value


def test_policy_approval_secret_text_redaction_preserves_safe_text():
    value = "Deployment preview for OPS-42 is ready."

    safe_value, redacted = _redact_secret_text(value)

    assert safe_value == value
    assert redacted is False


def test_policy_approval_dedupe_key_is_keyed_against_offline_secret_guessing(monkeypatch):
    context = PolicyEvaluationContext(
        input="Deploy with password=hunter2",
        tool="deploy_database",
        tool_args={"password": "hunter2"},
        run_id="run-keyed-dedupe",
    )
    result = PolicyEvaluationResult(
        decision="require_approval",
        reason="Approval required",
        evaluated_policy_count=1,
    )
    user = User(id=uuid.uuid4(), email="reviewer@example.com")

    monkeypatch.setattr(
        "src.api.routes.policies.get_settings",
        lambda: SimpleNamespace(
            secret_encryption_key="first-dedicated-encryption-key-material",
            jwt_secret="unused-jwt-secret-material",
        ),
    )
    first_key = _policy_approval_dedupe_key(context, result, user)

    monkeypatch.setattr(
        "src.api.routes.policies.get_settings",
        lambda: SimpleNamespace(
            secret_encryption_key="second-dedicated-encryption-key-material",
            jwt_secret="unused-jwt-secret-material",
        ),
    )
    second_key = _policy_approval_dedupe_key(context, result, user)

    assert first_key.startswith("policy-approval:v2:")
    assert first_key != second_key
    assert "hunter2" not in first_key


class TestPolicyStore:
    """Unit tests for PolicyStore."""

    def test_rule_rejects_empty_patterns(self):
        with pytest.raises(ValueError):
            Rule(type="block", pattern="", action="reject", scope="input")

    @pytest.mark.asyncio
    async def test_get_policy_not_found(self):
        store = PolicyStore()
        result = await store.get_policy("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_policy_creates_new(self):
        store = PolicyStore()
        policy = Policy(
            id=str(uuid.uuid4()),
            name="test-policy",
            rules=[
                Rule(
                    type="block",
                    pattern="*.exe",
                    action="reject",
                    scope="input",
                )
            ],
            enabled=True,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        result = await store.upsert_policy(policy)
        assert result.name == "test-policy"
        assert result.version == 1
        assert len(result.rules) == 1

    @pytest.mark.asyncio
    async def test_upsert_policy_increments_version(self):
        store = PolicyStore()
        policy = Policy(
            id=str(uuid.uuid4()),
            name="test-policy",
            rules=[],
            enabled=True,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await store.upsert_policy(policy)
        policy2 = Policy(
            id=str(uuid.uuid4()),
            name="test-policy",
            rules=[Rule(type="warn", pattern="*.bat", action="log", scope="input")],
            enabled=True,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        result = await store.upsert_policy(policy2)
        assert result.version == 2
        assert len(result.rules) == 1

    @pytest.mark.asyncio
    async def test_list_policies(self):
        store = PolicyStore()
        for i in range(3):
            await store.upsert_policy(
                Policy(
                    id=str(uuid.uuid4()),
                    name=f"policy-{i}",
                    rules=[],
                    enabled=True,
                    version=1,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
        policies = await store.list_policies()
        assert len(policies) == 3

    @pytest.mark.asyncio
    async def test_delete_policy(self):
        store = PolicyStore()
        await store.upsert_policy(
            Policy(
                id=str(uuid.uuid4()),
                name="to-delete",
                rules=[],
                enabled=True,
                version=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        deleted = await store.delete_policy("to-delete")
        assert deleted is True
        assert await store.get_policy("to-delete") is None

    @pytest.mark.asyncio
    async def test_delete_policy_not_found(self):
        store = PolicyStore()
        result = await store.delete_policy("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_reload_client_registration(self):
        store = PolicyStore()
        client = _DummySSEClient()
        store.register_reload_client(client)
        assert client in store._reload_clients
        store.unregister_reload_client(client)
        assert client not in store._reload_clients

    @pytest.mark.asyncio
    async def test_upsert_notifies_reload_clients(self):
        store = PolicyStore()
        client = _DummySSEClient()
        store.register_reload_client(client)

        await store.upsert_policy(
            Policy(
                id=str(uuid.uuid4()),
                name="observed-policy",
                rules=[],
                enabled=True,
                version=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

        assert len(client.sent) == 1
        assert "observed-policy" in client.sent[0]
        assert "reload" in client.sent[0]

    @pytest.mark.asyncio
    async def test_evaluate_blocks_matching_input_rule(self):
        store = PolicyStore()
        await store.upsert_policy(
            Policy(
                id=str(uuid.uuid4()),
                name="block-secrets",
                rules=[
                    Rule(
                        type="block",
                        pattern="*password*",
                        action="reject",
                        scope="input",
                    )
                ],
                enabled=True,
                version=1,
            )
        )

        result = await store.evaluate(
            PolicyEvaluationContext(input="please print the password", run_id="run-1")
        )

        assert result.decision == "block"
        assert result.run_id == "run-1"
        assert result.evaluated_policy_count == 1
        assert [match.policy_name for match in result.matches] == ["block-secrets"]

    @pytest.mark.asyncio
    async def test_evaluate_ignores_disabled_policies(self):
        store = PolicyStore()
        await store.upsert_policy(
            Policy(
                id=str(uuid.uuid4()),
                name="disabled-block",
                rules=[
                    Rule(type="block", pattern="*", action="reject", scope="tool"),
                ],
                enabled=False,
                version=1,
            )
        )

        result = await store.evaluate(PolicyEvaluationContext(tool="deploy"))

        assert result.decision == "allow"
        assert result.matches == []
        assert result.evaluated_policy_count == 0

    @pytest.mark.asyncio
    async def test_evaluate_does_not_match_wildcards_against_absent_scopes(self):
        store = PolicyStore()
        await store.upsert_policy(
            Policy(
                id=str(uuid.uuid4()),
                name="scope-specific-catchalls",
                rules=[
                    Rule(type="block", pattern="*", action="reject", scope="output"),
                    Rule(type="block", pattern="*", action="reject", scope="tool"),
                ],
                enabled=True,
                version=1,
            )
        )

        result = await store.evaluate(PolicyEvaluationContext(input="input only"))

        assert result.decision == "allow"
        assert result.matches == []

    @pytest.mark.asyncio
    async def test_evaluate_requires_approval_for_matching_tool_rule(self):
        store = PolicyStore()
        await store.upsert_policy(
            Policy(
                id=str(uuid.uuid4()),
                name="deploy-approval",
                rules=[
                    Rule(
                        type="warn",
                        pattern="terraform_*",
                        action="require_approval",
                        scope="tool",
                    )
                ],
                enabled=True,
                version=1,
            )
        )

        result = await store.evaluate(
            PolicyEvaluationContext(
                tool="terraform_apply",
                tool_args={"workspace": "production"},
                agent_id="agent-1",
                session_id="session-1",
            )
        )

        assert result.decision == "require_approval"
        assert result.agent_id == "agent-1"
        assert result.session_id == "session-1"
        assert result.matches[0].action == "require_approval"

    @pytest.mark.asyncio
    async def test_evaluate_never_downgrades_a_block_rule_to_approval(self):
        store = PolicyStore()
        await store.upsert_policy(
            Policy(
                id=str(uuid.uuid4()),
                name="block-wins",
                rules=[
                    Rule(
                        type="block",
                        pattern="*production*",
                        action="require_approval",
                        scope="tool",
                    )
                ],
                enabled=True,
                version=1,
            )
        )

        result = await store.evaluate(PolicyEvaluationContext(tool="deploy_production"))

        assert result.decision == "block"


class _DummySSEClient:
    """Minimal async send-capable stand-in for EventSourceResponse."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


class TestPolicyRoutes:
    """Integration tests for /v1/policies routes."""

    @pytest.mark.asyncio
    async def test_create_policy(self, client: AsyncClient):
        response = await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "my-policy",
                "rules": [
                    {"type": "block", "pattern": "*.exe", "action": "reject", "scope": "input"}
                ],
                "enabled": True,
                "version": 1,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "my-policy"
        assert data["version"] == 1

    @pytest.mark.asyncio
    async def test_create_policy_duplicate_conflict(self, client: AsyncClient):
        payload = {
            "id": str(uuid.uuid4()),
            "name": "duplicate-policy",
            "rules": [],
            "enabled": True,
            "version": 1,
        }
        r1 = await client.post("/v1/policies", json=payload)
        assert r1.status_code == 201
        r2 = await client.post("/v1/policies", json=payload)
        assert r2.status_code == 409

    @pytest.mark.asyncio
    async def test_list_policies(self, client: AsyncClient):
        # Create two policies
        for name in ["list-policy-a", "list-policy-b"]:
            await client.post(
                "/v1/policies",
                json={
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "rules": [],
                    "enabled": True,
                    "version": 1,
                },
            )
        response = await client.get("/v1/policies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = {p["name"] for p in data}
        assert "list-policy-a" in names
        assert "list-policy-b" in names

    @pytest.mark.asyncio
    async def test_get_policy_by_name(self, client: AsyncClient):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "get-policy-test",
                "rules": [
                    {"type": "allow", "pattern": "*.txt", "action": "pass", "scope": "output"}
                ],
                "enabled": True,
                "version": 1,
            },
        )
        response = await client.get("/v1/policies/get-policy-test")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "get-policy-test"
        assert len(data["rules"]) == 1

    @pytest.mark.asyncio
    async def test_evaluate_policies_route(self, client: AsyncClient):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "route-evaluate-policy",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*delete_user*",
                        "action": "require_approval",
                        "scope": "tool",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )

        response = await client.post(
            "/v1/policies/evaluate",
            json={
                "tool": "delete_user",
                "tool_args": {"user_id": "user-123"},
                "run_id": "run-123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "require_approval"
        assert data["run_id"] == "run-123"
        assert data["matches"][0]["policy_name"] == "route-evaluate-policy"

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_creates_linked_approval(self, client: AsyncClient):
        policy_id = str(uuid.uuid4())
        await client.post(
            "/v1/policies",
            json={
                "id": policy_id,
                "name": "approval-bridge-policy",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*deploy_database*",
                        "action": "require_approval",
                        "scope": "tool",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )

        response = await client.post(
            "/v1/policies/evaluate-and-request-approval",
            json={
                "tool": "deploy_database",
                "tool_args": {"target": "production"},
                "run_id": "run-policy-approval",
                "session_id": "session-policy-approval",
                "agent_id": "agent-policy-approval",
            },
        )

        assert response.status_code == 200
        data = response.json()
        approval = data["approval_request"]
        payload = approval["payload"]

        assert data["decision"] == "require_approval"
        assert data["approval_created"] is True
        assert approval["status"] == "PENDING"
        assert approval["agent_id"] == "agent-policy-approval"
        assert approval["session_id"] == "session-policy-approval"
        assert approval["action_type"] == "deploy_database"
        assert payload["policy_decision"] == "require_approval"
        assert payload["context"]["run_id"] == "run-policy-approval"
        assert payload["context"]["tool_args"] == {"target": "production"}
        assert payload["context"]["input"] is None
        assert payload["context"]["output"] is None
        assert payload["context_redaction"] == {
            "policy": "secret-values-v1",
            "marker": "[REDACTED]",
            "applied": False,
        }
        assert payload["policy_matches"][0]["policy_id"] == policy_id
        assert payload["policy_matches"][0]["policy_name"] == "approval-bridge-policy"
        assert payload["policy_matches"][0]["policy_version"] == 1

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_preserves_scoped_context_and_redacts_secrets(
        self, client: AsyncClient
    ):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "approval-input-context-policy",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*deploy production*",
                        "action": "require_approval",
                        "scope": "input",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )

        response = await client.post(
            "/v1/policies/evaluate-and-request-approval",
            json={
                "input": (
                    "Deploy production with password=hunter2 after review; "
                    "Authorization: Bearer bearer-value"
                ),
                "output": "Deployment preview is ready for approval.",
                "tool": "deploy_database",
                "tool_args": {
                    "target": "production",
                    "api_key": "sk-this-must-never-be-stored",
                    "nested": {
                        "region": "eu-west-1",
                        "auth_token": "token-value",
                        "clientSecret": "camel-case-secret",
                    },
                },
                "metadata": {
                    "ticket": "OPS-42",
                    "authorization": "Bearer bearer-value",
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()["approval_request"]["payload"]
        expected_input = (
            "Deploy production with password=[REDACTED] after review; Authorization: [REDACTED]"
        )
        assert payload["context"]["input"] == expected_input
        assert payload["context"]["output"] == "Deployment preview is ready for approval."
        assert payload["context"]["tool_args"] == {
            "target": "production",
            "api_key": "[REDACTED]",
            "nested": {
                "region": "eu-west-1",
                "auth_token": "[REDACTED]",
                "clientSecret": "[REDACTED]",
            },
        }
        assert payload["context"]["metadata"] == {
            "ticket": "OPS-42",
            "authorization": "[REDACTED]",
        }
        assert payload["context_redaction"] == {
            "policy": "secret-values-v1",
            "marker": "[REDACTED]",
            "applied": True,
        }

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_preserves_output_scoped_context(
        self, client: AsyncClient
    ):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "approval-output-context-policy",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*customer export*",
                        "action": "require_approval",
                        "scope": "output",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )

        response = await client.post(
            "/v1/policies/evaluate-and-request-approval",
            json={
                "input": "Prepare a summary.",
                "output": "Customer export prepared with token=secret-value",
            },
        )

        assert response.status_code == 200
        payload = response.json()["approval_request"]["payload"]
        assert payload["context"]["input"] == "Prepare a summary."
        assert payload["context"]["output"] == "Customer export prepared with token=[REDACTED]"
        assert payload["context_redaction"]["applied"] is True

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_dedupes_pending_approval(
        self, client: AsyncClient
    ):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "approval-dedupe-policy",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*rotate_secret*",
                        "action": "require_approval",
                        "scope": "tool",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )
        payload = {
            "tool": "rotate_secret",
            "run_id": "run-dedupe",
            "session_id": "session-dedupe",
            "agent_id": "agent-dedupe",
        }

        first = await client.post("/v1/policies/evaluate-and-request-approval", json=payload)
        second = await client.post("/v1/policies/evaluate-and-request-approval", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        first_data = first.json()
        second_data = second.json()
        assert first_data["approval_created"] is True
        assert second_data["approval_created"] is False
        assert first_data["approval_request"]["id"] == second_data["approval_request"]["id"]
        assert first_data["approval_dedupe_key"] == second_data["approval_dedupe_key"]

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_dedupes_concurrent_requests(
        self,
        test_engine,
        test_user: User,
    ):
        store = PolicyStore()
        await store.upsert_policy(
            Policy(
                id=str(uuid.uuid4()),
                name="approval-concurrent-dedupe-policy",
                rules=[
                    Rule(
                        type="warn",
                        pattern="*rotate_secret*",
                        action="require_approval",
                        scope="tool",
                    )
                ],
                enabled=True,
                version=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        context = PolicyEvaluationContext(
            tool="rotate_secret",
            run_id="run-concurrent-dedupe",
            session_id="session-concurrent-dedupe",
            agent_id="agent-concurrent-dedupe",
        )
        session_factory = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        async def evaluate_with_new_session():
            async with session_factory() as session:
                return await evaluate_policies_and_request_approval(
                    context=context,
                    store=store,
                    db=session,
                    user=test_user,
                )

        first, second = await asyncio.gather(
            evaluate_with_new_session(),
            evaluate_with_new_session(),
        )

        assert sorted((first.approval_created, second.approval_created)) == [False, True]
        assert first.approval_request is not None
        assert second.approval_request is not None
        assert first.approval_request.id == second.approval_request.id
        assert first.approval_dedupe_key == second.approval_dedupe_key

        async with session_factory() as session:
            approvals, total = await _list_approval_settings(session)
        assert total == 1
        assert [approval.id for approval in approvals] == [first.approval_request.id]

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_keys_distinct_action_context(
        self, client: AsyncClient
    ):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "approval-distinct-context-policy",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*kubectl*",
                        "action": "require_approval",
                        "scope": "tool",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )
        base_payload = {
            "tool": "kubectl",
            "run_id": "run-distinct-context",
            "session_id": "session-distinct-context",
            "agent_id": "agent-distinct-context",
        }

        first = await client.post(
            "/v1/policies/evaluate-and-request-approval",
            json={**base_payload, "tool_args": {"command": "delete pod api-1"}},
        )
        second = await client.post(
            "/v1/policies/evaluate-and-request-approval",
            json={**base_payload, "tool_args": {"command": "delete pod api-2"}},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        first_data = first.json()
        second_data = second.json()
        assert first_data["approval_created"] is True
        assert second_data["approval_created"] is True
        assert first_data["approval_request"]["id"] != second_data["approval_request"]["id"]
        assert first_data["approval_dedupe_key"] != second_data["approval_dedupe_key"]

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_dedupes_beyond_first_page(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "approval-deep-dedupe-policy",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*rotate_key*",
                        "action": "require_approval",
                        "scope": "tool",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )
        payload = {
            "tool": "rotate_key",
            "tool_args": {"key": "production-api"},
            "run_id": "run-deep-dedupe",
            "session_id": "session-deep-dedupe",
            "agent_id": "agent-deep-dedupe",
        }
        first = await client.post("/v1/policies/evaluate-and-request-approval", json=payload)
        assert first.status_code == 200

        for index in range(205):
            request = ApprovalRequest(
                agent_id="agent-noise",
                session_id=f"session-noise-{index}",
                action_type="noise",
                payload={"index": index},
                requester=test_user.email,
            )
            db_session.add(
                UserSetting(
                    user_id=test_user.id,
                    key=f"{APPROVAL_KEY_PREFIX}{request.id}",
                    value=request.model_dump(mode="json"),
                )
            )
        await db_session.commit()

        second = await client.post("/v1/policies/evaluate-and-request-approval", json=payload)

        assert second.status_code == 200
        first_data = first.json()
        second_data = second.json()
        assert first_data["approval_created"] is True
        assert second_data["approval_created"] is False
        assert first_data["approval_request"]["id"] == second_data["approval_request"]["id"]

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_does_not_create_for_non_approval_decisions(
        self, client: AsyncClient
    ):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "approval-noncreate-warn",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*log_only*",
                        "action": "log",
                        "scope": "tool",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "approval-noncreate-block",
                "rules": [
                    {
                        "type": "block",
                        "pattern": "*delete_cluster*",
                        "action": "reject",
                        "scope": "tool",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )

        cases = [
            ({"tool": "safe_status_check"}, "allow"),
            ({"tool": "log_only"}, "warn"),
            ({"tool": "delete_cluster"}, "block"),
        ]
        for payload, expected_decision in cases:
            response = await client.post(
                "/v1/policies/evaluate-and-request-approval",
                json=payload,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["decision"] == expected_decision
            assert data["approval_created"] is False
            assert data["approval_request"] is None

    @pytest.mark.asyncio
    async def test_evaluate_and_request_approval_handles_missing_optional_context(
        self, client: AsyncClient
    ):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "approval-missing-context-policy",
                "rules": [
                    {
                        "type": "warn",
                        "pattern": "*needs_review*",
                        "action": "require_approval",
                        "scope": "tool",
                    }
                ],
                "enabled": True,
                "version": 1,
            },
        )

        response = await client.post(
            "/v1/policies/evaluate-and-request-approval",
            json={"tool": "needs_review"},
        )

        assert response.status_code == 200
        data = response.json()
        approval = data["approval_request"]
        assert data["decision"] == "require_approval"
        assert approval["agent_id"] == ""
        assert approval["session_id"] == ""
        assert approval["action_type"] == "needs_review"
        assert approval["payload"]["context"]["run_id"] is None

    @pytest.mark.asyncio
    async def test_get_policy_not_found(self, client: AsyncClient):
        response = await client.get("/v1/policies/does-not-exist")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_policy(self, client: AsyncClient):
        await client.post(
            "/v1/policies",
            json={
                "id": str(uuid.uuid4()),
                "name": "to-delete-test",
                "rules": [],
                "enabled": True,
                "version": 1,
            },
        )
        response = await client.delete("/v1/policies/to-delete-test")
        assert response.status_code == 204
        # Confirm it's gone
        get_resp = await client.get("/v1/policies/to-delete-test")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_policy_not_found(self, client: AsyncClient):
        response = await client.delete("/v1/policies/never-existed")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reload_endpoint_policy_not_found(self, client: AsyncClient):
        response = await client.post("/v1/policies/nonexistent/reload")
        assert response.status_code == 404

    # NOTE: testing the SSE streaming endpoint (200 + text/event-stream) via
    # client.post() is blocked — httpx reads the full response body before
    # returning, so an infinite SSE stream hangs forever.  The SSE generator
    # logic (event format, version-change detection, cancellation handling) is
    # fully exercised by TestPolicyStore.test_upsert_notifies_reload_clients.
