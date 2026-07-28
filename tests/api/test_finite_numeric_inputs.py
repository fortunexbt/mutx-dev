"""Regression coverage for externally reachable finite-number boundaries."""

import math

import pytest
from sqlalchemy import func, select

from src.api.models import (
    Agent,
    AgentLog,
    AgentMetric,
    AgentResourceUsage,
    AnalyticsEvent,
    Metrics,
    UsageEvent,
)


NON_FINITE_JSON_TOKENS = [
    pytest.param("NaN", id="nan"),
    pytest.param("1e309", id="overflow-to-positive-infinity"),
    pytest.param("Infinity", id="positive-infinity"),
    pytest.param("-Infinity", id="negative-infinity"),
]


@pytest.fixture(autouse=True)
def developer_principal(test_user):
    test_user.roles = ["DEVELOPER"]


def json_headers() -> dict[str, str]:
    return {"content-type": "application/json"}


def test_recursive_json_validator_reports_the_nested_path():
    from src.api.models.numeric import NonFiniteNumberError, reject_non_finite_floats

    with pytest.raises(NonFiniteNumberError, match=r"\$\.outer\[0\]\.inner"):
        reject_non_finite_floats({"outer": [{"inner": float("nan")}]})


@pytest.mark.asyncio
async def test_analytics_properties_reject_nested_non_finite_before_persistence(db_session):
    from src.api.models.numeric import NonFiniteNumberError
    from src.api.services.analytics import log_analytics_event

    with pytest.raises(NonFiniteNumberError, match=r"\$\.properties\.outer\[0\]\.inner"):
        await log_analytics_event(
            db_session,
            event_name="numeric poison",
            event_type="numeric.poison",
            properties={"outer": [{"inner": float("inf")}]},
        )

    persisted = await db_session.scalar(
        select(func.count())
        .select_from(AnalyticsEvent)
        .where(AnalyticsEvent.event_type == "numeric.poison")
    )
    assert persisted == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_token", NON_FINITE_JSON_TOKENS)
async def test_usage_rejects_non_finite_credits_before_persistence(
    client,
    db_session,
    numeric_token: str,
):
    response = await client.post(
        "/v1/usage/events",
        content=('{"event_type":"numeric-poison","credits_used":' + numeric_token + "}"),
        headers=json_headers(),
    )

    assert response.status_code == 422
    persisted = await db_session.scalar(
        select(func.count())
        .select_from(UsageEvent)
        .where(UsageEvent.event_type == "numeric-poison")
    )
    assert persisted == 0

    analytics = await client.get("/v1/analytics/costs")
    assert analytics.status_code == 200
    assert math.isfinite(analytics.json()["total_credits_used"])


@pytest.mark.asyncio
@pytest.mark.parametrize("credits_used", [0.0, 2.5])
async def test_usage_accepts_representative_valid_values(client, credits_used: float):
    response = await client.post(
        "/v1/usage/events",
        json={"event_type": "finite-usage", "credits_used": credits_used},
    )

    assert response.status_code == 201
    assert response.json()["credits_used"] == credits_used


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_token", NON_FINITE_JSON_TOKENS)
async def test_usage_rejects_non_finite_numbers_anywhere_in_metadata(
    client,
    db_session,
    numeric_token: str,
):
    response = await client.post(
        "/v1/usage/events",
        content=(
            '{"event_type":"nested-usage","metadata":{"outer":[{"inner":' + numeric_token + "}]}}"
        ),
        headers=json_headers(),
    )

    assert response.status_code == 422
    persisted = await db_session.scalar(
        select(func.count()).select_from(UsageEvent).where(UsageEvent.event_type == "nested-usage")
    )
    assert persisted == 0


@pytest.mark.asyncio
async def test_legacy_non_finite_usage_is_nullable_and_billing_fails_closed(
    client,
    db_session,
    test_user,
):
    db_session.add(
        UsageEvent(
            user_id=test_user.id,
            event_type="legacy-poison",
            credits_used=float("inf"),
            event_metadata='{"legacy_score": Infinity}',
        )
    )
    await db_session.commit()

    events = await client.get("/v1/usage/events", params={"event_type": "legacy-poison"})
    analytics = await client.get("/v1/analytics/costs")

    assert events.status_code == 200
    item = events.json()["items"][0]
    assert item["credits_used"] is None
    assert item["metadata"]["legacy_score"] is None
    assert item["degraded"] is True
    assert analytics.status_code == 503
    assert analytics.json() == {
        "detail": "Billing data is unavailable because numeric integrity checks failed"
    }


@pytest.mark.asyncio
async def test_all_budget_aggregates_fail_closed_on_legacy_non_finite_usage(
    client,
    db_session,
    test_user,
):
    db_session.add(
        UsageEvent(
            user_id=test_user.id,
            event_type="legacy-budget-poison",
            credits_used=float("inf"),
        )
    )
    await db_session.commit()

    responses = [
        await client.get("/v1/analytics/budget"),
        await client.get("/v1/budgets"),
        await client.get("/v1/budgets/usage"),
    ]

    assert [response.status_code for response in responses] == [503, 503, 503]
    assert all(
        response.json()["detail"]
        == "Billing data is unavailable because numeric integrity checks failed"
        for response in responses
    )


@pytest.mark.asyncio
async def test_analytics_summary_survives_legacy_non_finite_latency_as_incomplete(
    client,
    db_session,
    test_agent,
):
    db_session.add(
        Metrics(
            agent_id=test_agent.id,
            latency=float("inf"),
            cpu=0.0,
            memory=0.0,
            requests=1,
        )
    )
    await db_session.commit()

    response = await client.get("/v1/analytics/summary")

    assert response.status_code == 200
    assert response.json()["avg_latency_ms"] is None
    assert response.json()["incomplete"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["cpu_usage", "memory_usage"])
async def test_ingest_metrics_rejects_non_finite_percentages_without_commit(
    client,
    db_session,
    test_agent,
    field: str,
):
    body = {
        "cpu_usage": "0.0",
        "memory_usage": "0.0",
    }
    body[field] = "1e309"
    response = await client.post(
        "/v1/ingest/metrics",
        content=(
            '{"agent_id":"'
            + str(test_agent.id)
            + '","cpu_usage":'
            + body["cpu_usage"]
            + ',"memory_usage":'
            + body["memory_usage"]
            + "}"
        ),
        headers=json_headers(),
    )

    assert response.status_code == 422
    metric_count = await db_session.scalar(select(func.count()).select_from(AgentMetric))
    assert metric_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("cpu_usage", "memory_usage"), [(0.0, 0.0), (100.0, 100.0)])
async def test_ingest_metrics_accepts_percentage_boundaries(
    client,
    test_agent,
    cpu_usage: float,
    memory_usage: float,
):
    response = await client.post(
        "/v1/ingest/metrics",
        json={
            "agent_id": str(test_agent.id),
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
        },
    )

    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["cpu_usage", "memory_usage", "uptime_seconds"])
async def test_runtime_metrics_reject_non_finite_values_without_commit(
    client,
    db_session,
    test_agent,
    field: str,
):
    from src.api.auth.dependencies import get_current_agent

    client.app.dependency_overrides[get_current_agent] = lambda: test_agent
    values = {"cpu_usage": "0", "memory_usage": "0", "uptime_seconds": "0"}
    values[field] = "-Infinity"
    response = await client.post(
        "/v1/agents/metrics",
        content=(
            '{"agent_id":"'
            + str(test_agent.id)
            + '","cpu_usage":'
            + values["cpu_usage"]
            + ',"memory_usage":'
            + values["memory_usage"]
            + ',"uptime_seconds":'
            + values["uptime_seconds"]
            + ',"timestamp":"2026-07-28T00:00:00Z"}'
        ),
        headers=json_headers(),
    )
    client.app.dependency_overrides.pop(get_current_agent, None)

    assert response.status_code == 422
    metric_count = await db_session.scalar(select(func.count()).select_from(AgentMetric))
    assert metric_count == 0


@pytest.mark.asyncio
async def test_runtime_metrics_accept_percentage_and_uptime_boundaries(
    client,
    db_session,
    test_agent,
):
    from src.api.auth.dependencies import get_current_agent

    client.app.dependency_overrides[get_current_agent] = lambda: test_agent
    response = await client.post(
        "/v1/agents/metrics",
        json={
            "agent_id": str(test_agent.id),
            "cpu_usage": 0.0,
            "memory_usage": 100.0,
            "uptime_seconds": 0.0,
            "timestamp": "2026-07-28T00:00:00Z",
        },
    )
    client.app.dependency_overrides.pop(get_current_agent, None)

    assert response.status_code == 200
    metric = await db_session.scalar(select(AgentMetric))
    assert metric.cpu_usage == 0.0
    assert metric.memory_usage == 100.0


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_token", NON_FINITE_JSON_TOKENS)
async def test_agent_temperature_rejects_non_finite_values_as_422(
    client,
    db_session,
    numeric_token: str,
):
    response = await client.post(
        "/v1/agents",
        content=(
            '{"name":"poisoned-config","type":"openai","config":{"temperature":'
            + numeric_token
            + "}}"
        ),
        headers=json_headers(),
    )

    assert response.status_code == 422
    agent_count = await db_session.scalar(
        select(func.count()).select_from(Agent).where(Agent.name == "poisoned-config")
    )
    assert agent_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("temperature", [0.0, 2.0])
async def test_agent_temperature_accepts_openai_boundaries(client, temperature: float):
    response = await client.post(
        "/v1/agents",
        json={
            "name": f"finite-temperature-{temperature}",
            "type": "openai",
            "config": {"temperature": temperature},
        },
    )

    assert response.status_code == 201
    assert response.json()["config"]["temperature"] == temperature


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_token", NON_FINITE_JSON_TOKENS)
async def test_agent_config_rejects_non_finite_nested_extension_values(
    client,
    db_session,
    numeric_token: str,
):
    response = await client.post(
        "/v1/agents",
        content=(
            '{"name":"nested-config-poison","type":"langchain","config":'
            '{"chain_id":"chain-1","parameters":{"outer":[{"inner":' + numeric_token + "}]}}}"
        ),
        headers=json_headers(),
    )

    assert response.status_code == 422
    persisted = await db_session.scalar(
        select(func.count()).select_from(Agent).where(Agent.name == "nested-config-poison")
    )
    assert persisted == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_token", NON_FINITE_JSON_TOKENS)
async def test_agent_resource_cost_rejects_non_finite_values_before_commit(
    client,
    db_session,
    test_agent,
    numeric_token: str,
):
    response = await client.post(
        f"/v1/agents/{test_agent.id}/resource-usage",
        content=('{"cost_usd":' + numeric_token + ',"period_start":"2026-07-28T00:00:00Z"}'),
        headers=json_headers(),
    )

    assert response.status_code == 422
    usage_count = await db_session.scalar(select(func.count()).select_from(AgentResourceUsage))
    assert usage_count == 0


@pytest.mark.asyncio
async def test_agent_resource_cost_accepts_zero_boundary(client, test_agent):
    response = await client.post(
        f"/v1/agents/{test_agent.id}/resource-usage",
        json={"cost_usd": 0.0, "period_start": "2026-07-28T00:00:00Z"},
    )

    assert response.status_code == 201
    assert response.json()["cost_usd"] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_token", NON_FINITE_JSON_TOKENS)
async def test_agent_resource_usage_rejects_non_finite_nested_metadata(
    client,
    db_session,
    test_agent,
    numeric_token: str,
):
    response = await client.post(
        f"/v1/agents/{test_agent.id}/resource-usage",
        content=(
            '{"cost_usd":0,"period_start":"2026-07-28T00:00:00Z",'
            '"extra_metadata":{"outer":[{"inner":' + numeric_token + "}]}}"
        ),
        headers=json_headers(),
    )

    assert response.status_code == 422
    usage_count = await db_session.scalar(select(func.count()).select_from(AgentResourceUsage))
    assert usage_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_token", NON_FINITE_JSON_TOKENS)
async def test_adapter_event_rejects_non_finite_nested_payload_without_log(
    client,
    db_session,
    test_agent,
    numeric_token: str,
):
    response = await client.post(
        "/v1/events",
        content=(
            '{"event_type":"nested-event","agent_id":"'
            + str(test_agent.id)
            + '","payload":{"outer":[{"inner":'
            + numeric_token
            + "}]}}"
        ),
        headers=json_headers(),
    )

    assert response.status_code == 422
    log_count = await db_session.scalar(
        select(func.count())
        .select_from(AgentLog)
        .where(AgentLog.message == "Adapter event: nested-event")
    )
    assert log_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload_fragment",
    [
        pytest.param('"cost":{"input_tokens":0,"output_tokens":0,"cost_usd":1e309}', id="cost"),
        pytest.param(
            '"eval":{"pass":true,"score":50,"metrics":{"duration_s":Infinity}}',
            id="duration",
        ),
        pytest.param(
            '"eval":{"pass":true,"score":50,"metrics":{"convergence_score":NaN}}',
            id="convergence",
        ),
        pytest.param('"eval":{"pass":true,"score":-Infinity}', id="score"),
    ],
)
async def test_observability_run_rejects_non_finite_nested_numbers(
    client,
    payload_fragment: str,
):
    response = await client.post(
        "/v1/observability/runs",
        content=(
            '{"agent_id":"numeric-observability","status":"running",' + payload_fragment + "}"
        ),
        headers=json_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload_fragment",
    [
        pytest.param('"run_metadata":{"outer":[{"inner":Infinity}]}', id="run-metadata"),
        pytest.param(
            '"steps":[{"id":"step-1","type":"message",'
            '"started_at":"2026-07-28T00:00:00Z",'
            '"step_metadata":{"outer":[{"inner":NaN}]}}]',
            id="step-metadata",
        ),
    ],
)
async def test_observability_run_rejects_non_finite_arbitrary_json(
    client,
    payload_fragment: str,
):
    response = await client.post(
        "/v1/observability/runs",
        content=(
            '{"agent_id":"numeric-observability-metadata","status":"running",'
            + payload_fragment
            + "}"
        ),
        headers=json_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "convergence_score"),
    [(0.0, 0.0), (100.0, 1.0)],
)
async def test_observability_eval_accepts_score_boundaries(
    client,
    score: float,
    convergence_score: float,
):
    created = await client.post(
        "/v1/observability/runs",
        json={"agent_id": f"finite-eval-{score}", "status": "completed"},
    )
    assert created.status_code == 201

    response = await client.post(
        f"/v1/observability/runs/{created.json()['id']}/eval",
        json={
            "pass": True,
            "score": score,
            "metrics": {
                "cost_usd": 0.0,
                "duration_s": 0.0,
                "convergence_score": convergence_score,
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["score"] == score
    assert response.json()["metrics"]["convergence_score"] == convergence_score


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param('{"pass":true,"score":Infinity}', id="score"),
        pytest.param(
            '{"pass":true,"score":50,"metrics":{"cost_usd":1e309}}',
            id="cost",
        ),
        pytest.param(
            '{"pass":true,"score":50,"metrics":{"duration_s":NaN}}',
            id="duration",
        ),
        pytest.param(
            '{"pass":true,"score":50,"metrics":{"convergence_score":-Infinity}}',
            id="convergence",
        ),
    ],
)
async def test_observability_eval_submission_rejects_non_finite_numbers(
    client,
    payload: str,
):
    created = await client.post(
        "/v1/observability/runs",
        json={"agent_id": "non-finite-eval", "status": "completed"},
    )
    assert created.status_code == 201

    response = await client.post(
        f"/v1/observability/runs/{created.json()['id']}/eval",
        content=payload,
        headers=json_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_observability_status_cost_rejects_overflow_before_update(client):
    created = await client.post(
        "/v1/observability/runs",
        json={"agent_id": "non-finite-status", "status": "running"},
    )
    assert created.status_code == 201
    run_id = created.json()["id"]

    response = await client.patch(
        f"/v1/observability/runs/{run_id}/status",
        content='{"cost_usd":1e309}',
        headers=json_headers(),
    )

    assert response.status_code == 422
    detail = await client.get(f"/v1/observability/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["cost"] is None


def test_legacy_observability_serializers_use_null_and_degraded_markers():
    from types import SimpleNamespace

    from src.api.routes.observability import _serialize_cost, _serialize_eval

    cost = _serialize_cost(
        SimpleNamespace(
            input_tokens=1,
            output_tokens=2,
            cache_read_tokens=None,
            cache_write_tokens=None,
            total_tokens=3,
            cost_usd=float("inf"),
            model="legacy-model",
        )
    ).model_dump()
    evaluation = _serialize_eval(
        SimpleNamespace(
            task_type=None,
            eval_layer=None,
            eval_pass=False,
            score=float("nan"),
            expected_outcome=None,
            actual_outcome=None,
            metrics='{"duration_s": Infinity}',
            regression_from=None,
            detail=None,
            benchmark_id=None,
        )
    ).model_dump(by_alias=True)

    assert cost["cost_usd"] is None
    assert cost["degraded"] is True
    assert evaluation["score"] is None
    assert evaluation["metrics"]["duration_s"] is None
    assert evaluation["degraded"] is True


def test_output_serializer_preserves_negative_scores_and_marks_non_finite_as_degraded():
    from src.api.routes.rag import SearchResult

    assert SearchResult(text="negative cosine", score=-0.75).model_dump()["score"] == -0.75
    poisoned = SearchResult(text="legacy poison", score=float("nan")).model_dump()
    assert poisoned["score"] is None
    assert poisoned["degraded"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_token", NON_FINITE_JSON_TOKENS)
async def test_supervision_timeout_rejects_non_finite_values_as_422(
    client,
    test_user,
    monkeypatch,
    numeric_token: str,
):
    from src.api.routes import governance_supervision

    class Supervisor:
        async def stop_agent(self, *_args, **_kwargs):
            raise AssertionError("stop_agent must not run for invalid input")

    test_user.roles = ["ADMIN"]
    monkeypatch.setattr(governance_supervision, "get_faramesh_supervisor", Supervisor)
    response = await client.post(
        "/v1/runtime/governance/supervised/agent-1/stop",
        content='{"timeout":' + numeric_token + "}",
        headers=json_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0.001, 300.0])
async def test_supervision_timeout_accepts_positive_bounded_values(
    client,
    test_user,
    monkeypatch,
    timeout: float,
):
    from src.api.routes import governance_supervision

    class Supervisor:
        def __init__(self):
            self.timeout = None

        async def stop_agent(self, _agent_id, timeout):
            self.timeout = timeout
            return True

    supervisor = Supervisor()
    test_user.roles = ["ADMIN"]
    monkeypatch.setattr(
        governance_supervision,
        "get_faramesh_supervisor",
        lambda: supervisor,
    )
    response = await client.post(
        "/v1/runtime/governance/supervised/agent-1/stop",
        json={"timeout": timeout},
    )

    assert response.status_code == 200
    assert supervisor.timeout == timeout
