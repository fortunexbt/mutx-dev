from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.api.models import AlertType, DeploymentEvent
from src.api.models.models import AgentStatus
from src.api.services.monitoring import monitor_agent_health


@pytest.mark.asyncio
async def test_monitoring_health_uses_app_state_start_time(client: AsyncClient, test_user):
    test_user.roles = ["ADMIN"]
    client.app.state.start_time = datetime.now(timezone.utc).timestamp() - 5

    response = await client.get("/v1/monitoring/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["database"] == "healthy"
    assert payload["uptime_seconds"] >= 5


@pytest.mark.asyncio
async def test_monitor_marks_latest_deployment_failed_on_stale_heartbeat(
    db_session, test_agent, test_deployment
):
    test_agent.status = AgentStatus.RUNNING.value
    test_agent.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=121)
    test_deployment.status = "running"
    await db_session.commit()

    await monitor_agent_health(db_session)
    assert test_deployment.ended_at is not None
    assert test_deployment.ended_at.tzinfo is None
    await db_session.refresh(test_agent)
    await db_session.refresh(test_deployment)

    assert test_agent.status == AgentStatus.FAILED.value
    assert test_deployment.status == "failed"
    assert test_deployment.error_message is not None

    events = (
        (
            await db_session.execute(
                select(DeploymentEvent).where(DeploymentEvent.deployment_id == test_deployment.id)
            )
        )
        .scalars()
        .all()
    )
    assert any(event.event_type == "monitor_failed" for event in events)


@pytest.mark.asyncio
async def test_monitor_auto_heal_restores_latest_deployment(
    db_session, test_agent, test_deployment
):
    test_agent.status = AgentStatus.FAILED.value
    test_agent.updated_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    test_deployment.status = "failed"
    test_deployment.error_message = (
        "System: Agent marked as FAILED due to heartbeat timeout (120s)."
    )
    test_deployment.ended_at = datetime.now(timezone.utc)
    await db_session.commit()

    await monitor_agent_health(db_session)
    assert test_deployment.started_at is not None
    assert test_deployment.started_at.tzinfo is None
    await db_session.refresh(test_agent)
    await db_session.refresh(test_deployment)

    assert test_agent.status == AgentStatus.RUNNING.value
    assert test_deployment.status == "running"
    assert test_deployment.error_message is None
    assert test_deployment.ended_at is None

    events = (
        (
            await db_session.execute(
                select(DeploymentEvent).where(DeploymentEvent.deployment_id == test_deployment.id)
            )
        )
        .scalars()
        .all()
    )
    assert any(event.event_type == "monitor_restarted" for event in events)


@pytest.mark.asyncio
async def test_monitor_resolves_agent_down_alerts_on_recovery(
    db_session, test_agent, test_deployment
):
    from src.api.models.models import Alert

    test_agent.status = AgentStatus.FAILED.value
    test_agent.updated_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    test_deployment.status = "failed"
    alert = Alert(
        agent_id=test_agent.id,
        type=AlertType.AGENT_DOWN,
        message="Agent is down",
        resolved=False,
    )
    db_session.add(alert)
    await db_session.commit()

    await monitor_agent_health(db_session)
    await db_session.refresh(alert)

    assert alert.resolved is True
    assert alert.resolved_at is not None


@pytest.mark.asyncio
async def test_monitor_emits_webhook_events_for_failure_and_recovery(
    db_session, test_agent, test_deployment, monkeypatch
):
    webhook_calls: list[tuple[str, dict]] = []

    async def fake_trigger_agent_status_event(
        db, user_id, agent_id, old_status, new_status, agent_name
    ):
        webhook_calls.append(
            (
                "agent.status",
                {
                    "agent_id": str(agent_id),
                    "old_status": old_status,
                    "new_status": new_status,
                    "agent_name": agent_name,
                },
            )
        )

    async def fake_trigger_deployment_event(
        db, user_id, deployment_id, agent_id, event_type, status=None
    ):
        webhook_calls.append(
            (
                "deployment.event",
                {
                    "deployment_id": str(deployment_id),
                    "agent_id": str(agent_id),
                    "event_type": event_type,
                    "status": status,
                },
            )
        )

    monkeypatch.setattr(
        "src.api.services.monitoring.trigger_agent_status_event", fake_trigger_agent_status_event
    )
    monkeypatch.setattr(
        "src.api.services.monitoring.trigger_deployment_event", fake_trigger_deployment_event
    )

    test_agent.status = AgentStatus.RUNNING.value
    test_agent.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=121)
    test_deployment.status = "running"
    await db_session.commit()

    await monitor_agent_health(db_session)

    test_agent.updated_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    await db_session.commit()

    await monitor_agent_health(db_session)

    deployment_events = [
        call[1]["event_type"] for call in webhook_calls if call[0] == "deployment.event"
    ]
    agent_statuses = [call[1]["new_status"] for call in webhook_calls if call[0] == "agent.status"]

    assert "monitor_failed" in deployment_events
    assert "monitor_restarted" in deployment_events
    assert "failed" in agent_statuses
    assert "running" in agent_statuses


@pytest.mark.asyncio
async def test_monitor_status_transitions_survive_webhook_dispatch_failures(
    db_session, test_agent, test_deployment, monkeypatch
):
    async def raise_webhook_failure(*_args, **_kwargs):
        raise RuntimeError("webhook unavailable")

    monkeypatch.setattr(
        "src.api.services.monitoring.trigger_agent_status_event", raise_webhook_failure
    )
    monkeypatch.setattr(
        "src.api.services.monitoring.trigger_deployment_event", raise_webhook_failure
    )

    test_agent.status = AgentStatus.RUNNING.value
    test_agent.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=121)
    test_deployment.status = "running"
    await db_session.commit()

    await monitor_agent_health(db_session)
    await db_session.refresh(test_agent)
    await db_session.refresh(test_deployment)

    assert test_agent.status == AgentStatus.FAILED.value
    assert test_deployment.status == "failed"
