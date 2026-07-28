import ast
import asyncio
import runpy
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import pytest
from httpx import AsyncClient

from src.api.auth.jwt import create_access_token
from src.api.services.agent_runtime import AgentRuntime, RuntimeConfig
from src.api.services.audit_log import AuditEvent, AuditEventType, AuditLog, AuditQuery
from src.api.services.governance_runtime import GovernanceRuntime
from src.api.integrations.langchain_agent import (
    AgentConfig,
    AgentRegistry,
    LangChainAgent,
    LLMProvider,
    ToolDefinition,
)
from src.security import PolicyDecision, PolicyEngine
from src.security.policy import PolicyRule, PolicySet
from src.security.receipts import ReceiptGenerator


def _governance_for(
    decision: PolicyDecision,
    audit_log: AuditLog,
) -> GovernanceRuntime:
    engine = PolicyEngine()
    policy = PolicySet(
        id=f"test-{decision.value}",
        name=f"Test {decision.value}",
        default_decision=PolicyDecision.DENY,
    )
    policy.add_rule(
        PolicyRule(
            id=f"rule-{decision.value}",
            name=f"Rule {decision.value}",
            tool_pattern="test_tool",
            action=decision,
            reason=f"Test {decision.value} decision",
        )
    )
    engine.add_policy(policy, set_default=True)

    async def get_test_audit_log() -> AuditLog:
        return audit_log

    return GovernanceRuntime(
        policy_engine=engine,
        audit_log_factory=get_test_audit_log,
        install_default_policy=False,
    )


@pytest.mark.asyncio
async def test_runtime_security_denial_blocks_handler_and_emits_evidence(tmp_path: Path) -> None:
    audit_log = AuditLog(str(tmp_path / "deny.db"))
    await audit_log.initialize()
    governance = _governance_for(PolicyDecision.DENY, audit_log)
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False), governance=governance)
    handler_called = False

    async def handler(_parameters: dict[str, object]) -> str:
        nonlocal handler_called
        handler_called = True
        return "should not execute"

    runtime.tool_handler.register_handler("test_tool", handler)
    result = await runtime.tool_handler.execute_tool(
        "test_tool",
        {"value": "blocked"},
        agent_id="agent-1",
        session_id="session-1",
        run_id="run-1",
        actor_id="user-1",
        actor_display="Test Operator",
    )

    assert handler_called is False
    assert result["decision"] == "deny"
    assert governance.receipt_generator.get_receipt(result["receipt_id"]) is not None

    events = await audit_log.query(AuditQuery(run_id="run-1"))
    assert len(events) == 1
    event = events[0]
    assert event.actor_id == "user-1"
    assert event.actor_display == "Test Operator"
    assert event.policy_refs == ["test-deny", "rule-deny"]
    assert event.policy_decision_id
    assert event.integrity_hash == result["integrity_hash"]
    assert len(event.integrity_hash) == 64
    await audit_log.close()


@pytest.mark.asyncio
async def test_governed_runtime_signs_receipt_before_audit_persistence(tmp_path: Path) -> None:
    audit_log = AuditLog(str(tmp_path / "signed-receipt.db"))
    await audit_log.initialize()
    governance = _governance_for(PolicyDecision.DENY, audit_log)
    key_id = "mutx-platform-runtime-test"
    private_key = bytes.fromhex("01" * 32)
    public_key = ReceiptGenerator.public_key_bytes(private_key)
    governance.receipt_generator = ReceiptGenerator(
        signing_private_key=private_key,
        signing_key_id=key_id,
        trusted_public_keys={key_id: public_key},
        signing_required=True,
    )
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False), governance=governance)

    result = await runtime.tool_handler.execute_tool(
        "test_tool",
        {},
        agent_id="agent-signed",
        session_id="session-signed",
        run_id="run-signed",
    )

    receipt = governance.receipt_generator.get_receipt(result["receipt_id"])
    assert receipt is not None
    assert receipt.signer_key_id == key_id
    assert governance.receipt_generator.verify(receipt) == (True, "")
    events = await audit_log.query(AuditQuery(run_id="run-signed"))
    assert events[0].payload["receipt_hash"] == receipt.compute_hash()
    await audit_log.close()


@pytest.mark.asyncio
async def test_runtime_security_defer_fails_closed_without_a_durable_resume_binding(
    tmp_path: Path,
) -> None:
    audit_log = AuditLog(str(tmp_path / "defer.db"))
    await audit_log.initialize()
    governance = _governance_for(PolicyDecision.DEFER, audit_log)
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False), governance=governance)
    handler_called = False

    def handler(_parameters: dict[str, object]) -> str:
        nonlocal handler_called
        handler_called = True
        return "should not execute"

    runtime.tool_handler.register_handler("test_tool", handler)
    result = await runtime.tool_handler.execute_tool(
        "test_tool",
        {},
        agent_id="agent-2",
        session_id="session-2",
        run_id="run-2",
    )

    assert handler_called is False
    assert result["decision"] == "defer"
    assert result["resumable"] is False
    assert "approval_id" not in result
    assert "no durable canonical approval resume binding" in result["error"]

    events = await audit_log.query(AuditQuery(run_id="run-2"))
    assert events[0].approval_id is None
    assert events[0].payload["outcome"] == "blocked_no_resume_binding"
    await audit_log.close()


@pytest.mark.asyncio
async def test_runtime_security_allow_executes_and_hash_chains_events(tmp_path: Path) -> None:
    audit_log = AuditLog(str(tmp_path / "allow.db"))
    await audit_log.initialize()
    governance = _governance_for(PolicyDecision.ALLOW, audit_log)
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False), governance=governance)
    calls: list[dict[str, object]] = []

    def handler(parameters: dict[str, object]) -> str:
        calls.append(parameters)
        return "executed"

    runtime.tool_handler.register_handler("test_tool", handler)
    for value in (1, 2):
        result = await runtime.tool_handler.execute_tool(
            "test_tool",
            {"value": value},
            agent_id="agent-3",
            session_id="session-3",
            run_id="run-3",
        )
        assert result == "executed"

    assert calls == [{"value": 1}, {"value": 2}]
    metrics = governance.telemetry_exporter.get_metrics_summary()
    assert metrics["total_evaluations"] == 2
    assert metrics["permits"] == 2
    receipts = governance.receipt_generator.get_receipts_for_session("session-3")
    assert receipts[0].prior_action_hashes == []
    assert receipts[1].prior_action_hashes == [receipts[0].action_hash]
    export = await audit_log.export_evidence(run_id="run-3")
    assert export["verified"] is True
    assert export["event_count"] == 4
    for previous, current in zip(export["events"], export["events"][1:]):
        assert current["previous_hash"] == previous["integrity_hash"]
    assert export["chain_root"] == export["events"][-1]["integrity_hash"]
    await audit_log.close()


@pytest.mark.asyncio
async def test_runtime_security_modify_passes_only_modified_args(tmp_path: Path) -> None:
    audit_log = AuditLog(str(tmp_path / "modify.db"))
    await audit_log.initialize()
    governance = _governance_for(PolicyDecision.MODIFY, audit_log)
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False), governance=governance)
    calls: list[dict[str, object]] = []

    def handler(parameters: dict[str, object]) -> str:
        calls.append(parameters)
        return "executed"

    result = await runtime.tool_handler.execute_tool(
        "test_tool",
        {"value": 7},
        agent_id="agent-modify",
        session_id="session-modify",
        run_id="run-modify",
        handler_override=handler,
    )

    assert result == "executed"
    assert calls == [{"value": 7}]
    await audit_log.close()


@pytest.mark.asyncio
async def test_agent_runtime_langchain_bridge_preserves_execution_identity(tmp_path: Path) -> None:
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, use_span

    audit_log = AuditLog(str(tmp_path / "bridge.db"))
    await audit_log.initialize()
    governance = _governance_for(PolicyDecision.ALLOW, audit_log)
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False), governance=governance)
    runtime._bind_event_loop()
    scope_token = runtime._execution_scope.set(("run-bridge", "session-bridge"))
    span = NonRecordingSpan(
        SpanContext(
            trace_id=0x0123456789ABCDEF0123456789ABCDEF,
            span_id=0xFEDCBA9876543210,
            is_remote=False,
            trace_flags=TraceFlags.SAMPLED,
        )
    )
    try:
        with use_span(span, end_on_exit=False):
            results = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        runtime._execute_langchain_tool,
                        "agent-bridge",
                        "test_tool",
                        {"value": value},
                        lambda parameters: parameters["value"],
                    )
                    for value in ("first", "second")
                )
            )
    finally:
        runtime._execution_scope.reset(scope_token)

    assert results == ["first", "second"]
    events = await audit_log.query(AuditQuery(run_id="run-bridge"))
    assert len(events) == 4
    assert all(event.session_id == "session-bridge" for event in events)
    assert all(event.agent_id == "agent-bridge" for event in events)
    assert all(event.trace_id == "0123456789abcdef0123456789abcdef" for event in events)
    assert all(event.span_id == "fedcba9876543210" for event in events)
    receipts = governance.receipt_generator.get_receipts_for_session("session-bridge")
    assert receipts[0].prior_action_hashes == []
    assert receipts[1].prior_action_hashes == [receipts[0].action_hash]
    await audit_log.close()


@pytest.mark.asyncio
async def test_runtime_security_blocks_execution_when_authorization_audit_fails() -> None:
    class FailingAuditLog:
        async def log_with_otel_context(self, _event: AuditEvent) -> None:
            raise OSError("audit unavailable")

    async def get_failing_audit_log() -> FailingAuditLog:
        return FailingAuditLog()

    engine = PolicyEngine()
    policy = PolicySet(
        id="test-fail-closed",
        name="Test fail closed",
        default_decision=PolicyDecision.ALLOW,
    )
    engine.add_policy(policy, set_default=True)
    governance = GovernanceRuntime(
        policy_engine=engine,
        audit_log_factory=get_failing_audit_log,
        install_default_policy=False,
    )
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False), governance=governance)
    handler_called = False

    def handler(_parameters: dict[str, object]) -> str:
        nonlocal handler_called
        handler_called = True
        return "should not execute"

    result = await runtime.tool_handler.execute_tool(
        "test_tool",
        {},
        agent_id="agent-fail-closed",
        session_id="session-fail-closed",
        run_id="run-fail-closed",
        handler_override=handler,
    )

    assert handler_called is False
    assert result == {
        "error": "Tool execution blocked because authorization evidence could not be persisted",
        "decision": "allow",
        "reason": "No matching rule; default: allow",
    }


@pytest.mark.asyncio
async def test_runtime_reserved_handlers_cannot_be_overwritten() -> None:
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False))
    await runtime.start()
    original_calculator = runtime.tool_handler.get_handler("calculator")

    with pytest.raises(ValueError, match="reserved.*calculator"):
        runtime.tool_handler.register_handler(
            "calculator", lambda _parameters: "arbitrary side effect"
        )

    assert runtime.tool_handler.get_handler("calculator") is original_calculator
    await runtime.stop()


@pytest.mark.asyncio
async def test_agent_runtime_stream_runs_governed_tools_off_owner_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_log = AuditLog(str(tmp_path / "stream.db"))
    await audit_log.initialize()
    governance = _governance_for(PolicyDecision.ALLOW, audit_log)
    runtime = AgentRuntime(RuntimeConfig(vector_store_enabled=False), governance=governance)

    class StreamingAgent:
        def stream_run(self, _input_text: str):
            yield runtime._execute_langchain_tool(
                "agent-stream",
                "test_tool",
                {"value": "streamed"},
                lambda parameters: parameters["value"],
            )

    monkeypatch.setattr(AgentRegistry, "get_agent", lambda _agent_id: StreamingAgent())

    chunks = [chunk async for chunk in runtime.execute_agent_stream("agent-stream", "run")]

    assert chunks == ["streamed"]
    events = await audit_log.query(AuditQuery(agent_id="agent-stream"))
    assert [event.event_type for event in events] == [
        AuditEventType.TOOL_CALL,
        AuditEventType.POLICY_CHECK,
    ]
    await audit_log.close()


@pytest.mark.asyncio
async def test_audit_log_migrates_and_hashes_legacy_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE audit_events (
                event_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                span_id TEXT,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                trace_id TEXT
            )
            """
        )
        now = datetime.now(timezone.utc)
        connection.executemany(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "00000000-0000-4000-8000-000000000001",
                    "legacy-agent",
                    "legacy-session",
                    None,
                    AuditEventType.TOOL_CALL.value,
                    '{"tool_name":"first-inserted"}',
                    (now + timedelta(minutes=1)).isoformat(),
                    None,
                ),
                (
                    "00000000-0000-4000-8000-000000000002",
                    "legacy-agent",
                    "legacy-session",
                    None,
                    AuditEventType.TOOL_CALL.value,
                    '{"tool_name":"second-inserted"}',
                    now.isoformat(),
                    None,
                ),
            ],
        )

    audit_log = AuditLog(str(db_path))
    await audit_log.initialize()
    export = await audit_log.export_evidence(session_id="legacy-session")

    assert export["verified"] is True
    assert export["event_count"] == 2
    assert len(export["events"][0]["integrity_hash"]) == 64
    assert export["events"][1]["previous_hash"] == export["events"][0]["integrity_hash"]
    assert export["events"][0]["schema_version"] == "1.0"
    await audit_log.close()


@pytest.mark.asyncio
async def test_audit_log_skips_completed_integrity_backfill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "already-hashed.db"
    audit_log = AuditLog(str(db_path))
    await audit_log.initialize()
    await audit_log.log(
        AuditEvent(
            event_id=uuid.uuid4(),
            agent_id="agent",
            session_id="session",
            run_id="run",
            event_type=AuditEventType.POLICY_CHECK,
            payload={"decision": "allow"},
            timestamp=datetime.now(timezone.utc),
        )
    )
    await audit_log.close()

    reopened_log = AuditLog(str(db_path))
    backfill_called = False

    async def unexpected_backfill() -> None:
        nonlocal backfill_called
        backfill_called = True

    monkeypatch.setattr(reopened_log, "_backfill_integrity_hashes", unexpected_backfill)
    await reopened_log.initialize()

    assert backfill_called is False
    await reopened_log.close()


@pytest.mark.asyncio
async def test_audit_evidence_export_detects_persisted_tampering(tmp_path: Path) -> None:
    audit_log = AuditLog(str(tmp_path / "tampered.db"))
    await audit_log.initialize()
    event = AuditEvent(
        event_id=uuid.uuid4(),
        agent_id="agent",
        session_id="session",
        run_id="run",
        event_type=AuditEventType.POLICY_CHECK,
        payload={"decision": "allow"},
        timestamp=datetime.now(timezone.utc),
    )
    await audit_log.log(event)

    assert audit_log._db is not None
    await audit_log._db.execute(
        "UPDATE audit_events SET payload = ? WHERE event_id = ?",
        ('{"decision":"deny"}', str(event.event_id)),
    )
    await audit_log._db.commit()

    export = await audit_log.export_evidence(run_id="run")
    assert export["verified"] is False
    assert "invalid integrity_hash" in export["errors"][0]
    await audit_log.close()


def test_audit_event_integrity_hash_detects_tampering() -> None:
    event = AuditEvent(
        event_id=uuid.uuid4(),
        agent_id="agent",
        session_id="session",
        run_id="run",
        event_type=AuditEventType.POLICY_CHECK,
        payload={"decision": "allow"},
        timestamp=datetime.now(timezone.utc),
    )
    original_hash = event.compute_integrity_hash()

    event.payload["decision"] = "deny"

    assert event.compute_integrity_hash() != original_hash


def test_langchain_example_does_not_execute_eval() -> None:
    example_path = Path(__file__).parents[2] / "examples" / "langchain_agent.py"
    tree = ast.parse(example_path.read_text())

    eval_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "eval"
    ]
    assert eval_calls == []

    namespace = runpy.run_path(str(example_path))
    evaluate = namespace["_evaluate_arithmetic"]
    assert evaluate(ast.parse("2 + 3 * 4", mode="eval")) == 14
    with pytest.raises(ValueError, match="Unsupported expression"):
        evaluate(ast.parse("__import__('os').system('id')", mode="eval"))


def test_langchain_tools_are_wrapped_by_runtime_executor() -> None:
    captured: dict[str, object] = {}

    def tool_handler(parameters: dict[str, object]) -> str:
        captured["handler_parameters"] = parameters
        return "wrapped-result"

    def tool_executor(
        agent_id: str,
        tool_name: str,
        parameters: dict[str, object],
        handler,
    ) -> object:
        captured.update(
            {
                "agent_id": agent_id,
                "tool_name": tool_name,
                "parameters": parameters,
            }
        )
        return handler(parameters)

    agent = object.__new__(LangChainAgent)
    agent.agent_id = "agent-wrapped"
    agent.config = AgentConfig(
        name="wrapped",
        provider=LLMProvider.OPENAI,
        model="test-model",
        tools=[
            ToolDefinition(
                name="test_tool",
                description="Test governed tool",
                function=tool_handler,
            )
        ],
        tool_executor=tool_executor,
    )

    tools = agent._initialize_tools()
    test_tool = next(tool for tool in tools if tool.name == "test_tool")

    assert test_tool.invoke({}) == "wrapped-result"
    assert captured == {
        "agent_id": "agent-wrapped",
        "tool_name": "test_tool",
        "parameters": {},
        "handler_parameters": {},
    }


def test_langchain_custom_tools_cannot_shadow_governed_builtins() -> None:
    agent = object.__new__(LangChainAgent)
    agent.agent_id = "agent-reserved"
    agent.config = AgentConfig(
        name="reserved",
        provider=LLMProvider.OPENAI,
        model="test-model",
        tools=[
            ToolDefinition(
                name="calculator",
                description="Attempt to shadow the allowlisted calculator",
                function=lambda _parameters: "arbitrary side effect",
            )
        ],
        tool_executor=lambda *_args: None,
    )

    with pytest.raises(ValueError, match="Custom tool names are reserved.*calculator"):
        agent._initialize_tools()


@pytest.mark.asyncio
async def test_audit_evidence_export_route_is_authenticated_and_verified(
    client_no_auth: AsyncClient,
    db_session,
    test_user,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.routes.audit as audit_route

    audit_log = AuditLog(str(tmp_path / "export.db"))
    await audit_log.initialize()
    event = AuditEvent(
        event_id=uuid.uuid4(),
        agent_id="export-agent",
        session_id="export-session",
        run_id="export-run",
        event_type=AuditEventType.POLICY_CHECK,
        payload={"decision": "allow"},
        timestamp=datetime.now(timezone.utc),
        actor_id="operator-1",
        policy_decision_id="decision-1",
        policy_refs=["policy-1", "rule-1"],
    )
    await audit_log.log(event)

    async def get_test_audit_log() -> AuditLog:
        return audit_log

    monkeypatch.setattr(audit_route, "get_audit_log", get_test_audit_log)

    unauthorized = await client_no_auth.get("/v1/audit/export?run_id=export-run")
    assert unauthorized.status_code == 401

    test_user.roles = ["AUDIT_ADMIN"]
    db_session.add(test_user)
    await db_session.commit()
    token, _ = create_access_token(test_user.id)
    response = await client_no_auth.get(
        "/v1/audit/export?run_id=export-run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    export = response.json()
    assert export["verified"] is True
    assert export["run_id"] == "export-run"
    assert export["event_count"] == 1
    assert export["chain_root"] == event.integrity_hash
    assert export["events"][0]["policy_refs"] == ["policy-1", "rule-1"]

    invalid = await client_no_auth.get(
        "/v1/audit/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert invalid.status_code == 400
    await audit_log.close()
