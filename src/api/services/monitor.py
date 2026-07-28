import asyncio
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.api import database as database_module
from src.api.metrics import set_background_monitor_failure_metrics
from src.api.models import Agent, AgentLog, AgentStatus
from src.api.services.monitoring import STALE_THRESHOLD_SECONDS, monitor_agent_health
from src.api.services.self_healer import RecoveryAction, get_self_healing_service
from src.api.time_utils import as_utc, utc_now

logger = logging.getLogger(__name__)


@dataclass
class MonitorRuntimeState:
    heartbeat_file: Path | None = None
    started_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0

    def mark_started(self, started_at: datetime | None = None) -> None:
        if self.heartbeat_file is not None:
            self.heartbeat_file.unlink(missing_ok=True)
        self.started_at = started_at or datetime.now(timezone.utc)
        self.last_error = None
        self.consecutive_failures = 0

    def mark_success(self, succeeded_at: datetime | None = None) -> None:
        success_time = succeeded_at or datetime.now(timezone.utc)
        if self.heartbeat_file is not None:
            temporary_file = self.heartbeat_file.with_name(
                f".{self.heartbeat_file.name}.{os.getpid()}.tmp"
            )
            temporary_file.write_text(f"{success_time.timestamp():.6f}\n", encoding="utf-8")
            os.replace(temporary_file, self.heartbeat_file)
        self.last_success_at = success_time
        self.last_error = None
        self.consecutive_failures = 0

    def mark_error(self, error: Exception | str, failed_at: datetime | None = None) -> None:
        self.last_error_at = failed_at or datetime.now(timezone.utc)
        self.last_error = str(error)
        self.consecutive_failures += 1


_default_monitor_runtime_state = MonitorRuntimeState()


def get_monitor_runtime_state() -> MonitorRuntimeState:
    return _default_monitor_runtime_state


def heartbeat_is_fresh(
    heartbeat_file: str | Path,
    max_age_seconds: int,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a successful monitor cycle heartbeat is recent and plausible."""

    try:
        recorded_timestamp = float(Path(heartbeat_file).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False

    current_time = now or datetime.now(timezone.utc)
    age_seconds = current_time.timestamp() - recorded_timestamp
    return -5 <= age_seconds <= max_age_seconds


def _agent_heartbeat_check(agent_id: str):
    async def _check() -> bool:
        async with database_module.async_session_maker() as session:
            result = await session.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
            agent = result.scalar_one_or_none()

            if not agent:
                return False

            last_heartbeat = agent.last_heartbeat or agent.created_at
            if not last_heartbeat:
                return False

            last_heartbeat = as_utc(last_heartbeat)

            return (datetime.now(timezone.utc) - last_heartbeat) <= timedelta(
                seconds=STALE_THRESHOLD_SECONDS,
            )

    return _check


async def _recover_agent_to_running(agent_id: str, metadata):
    async with database_module.async_session_maker() as session:
        result = await session.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
        agent = result.scalar_one_or_none()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found for recovery")

        if agent.status == AgentStatus.STOPPED.value:
            logger.info(
                "Skipping self-healing recovery for explicitly stopped agent",
                extra={"agent_id": agent_id, "metadata": metadata},
            )
            return

        previous_status = agent.status
        agent.status = AgentStatus.RUNNING.value
        agent.last_heartbeat = utc_now()
        session.add(
            AgentLog(
                agent_id=agent.id,
                level="warning",
                message="Self-healing recovery handler restored agent status to RUNNING",
                timestamp=datetime.now(timezone.utc),
            )
        )
        await session.commit()

        logger.info(
            "Self-healing recovery completed",
            extra={
                "agent_id": agent_id,
                "previous_status": previous_status,
                "metadata": metadata,
            },
        )


async def _sync_self_healing_agents(session, self_healing):
    """Register live agents for self-healing checks and prune removed agents."""
    result = await session.execute(
        select(Agent.id).where(
            Agent.status.notin_(
                [
                    AgentStatus.DELETING.value,
                    AgentStatus.STOPPED.value,
                ]
            )
        )
    )
    active_agents = {str(agent_id) for agent_id in result.scalars().all()}

    tracked_agents = set(self_healing.health_check_scheduler.get_all_health().keys())

    for agent_id in active_agents - tracked_agents:
        self_healing.register_agent(
            agent_id,
            health_check_fn=_agent_heartbeat_check(agent_id),
        )

    for agent_id in tracked_agents - active_agents:
        self_healing.unregister_agent(agent_id)


async def start_background_monitor(
    runtime_state: MonitorRuntimeState | None = None,
    *,
    max_consecutive_failures: int | None = None,
):
    """Main loop for the background service.

    This loop intentionally runs only real runtime monitoring and self-healing.
    Synthetic demo activity is disabled here to keep monitor behavior truthful
    and observable.
    """

    logger.info("Starting background agent monitor...")
    monitor_state = runtime_state or get_monitor_runtime_state()
    monitor_state.mark_started()
    set_background_monitor_failure_metrics(monitor_state.consecutive_failures)
    self_healing = get_self_healing_service()

    await self_healing.start()

    if hasattr(self_healing, "register_recovery_handler"):
        self_healing.register_recovery_handler(
            RecoveryAction.RESTART,
            _recover_agent_to_running,
        )
        self_healing.register_recovery_handler(
            RecoveryAction.ROLLBACK,
            _recover_agent_to_running,
        )
    try:
        while True:
            try:
                async with database_module.async_session_maker() as session:
                    try:
                        # Run real monitoring and self-healing logic.
                        await monitor_agent_health(session)
                        if hasattr(self_healing, "health_check_scheduler"):
                            await _sync_self_healing_agents(session, self_healing)
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        raise

                if hasattr(self_healing, "health_check_scheduler"):
                    for agent_id in self_healing.health_check_scheduler.get_all_health():
                        await self_healing.check_and_recover(agent_id)

                monitor_state.mark_success()
                set_background_monitor_failure_metrics(monitor_state.consecutive_failures)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                monitor_state.mark_error(e)
                set_background_monitor_failure_metrics(monitor_state.consecutive_failures)
                logger.exception("Error in background monitor")
                if (
                    max_consecutive_failures is not None
                    and monitor_state.consecutive_failures >= max_consecutive_failures
                ):
                    raise RuntimeError(
                        "Background monitor exceeded the configured consecutive failure limit "
                        f"({max_consecutive_failures})"
                    ) from e
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(5)  # Run every 5 seconds
    except asyncio.CancelledError:
        logger.info("Background agent monitor cancellation requested")
        raise
    finally:
        try:
            await self_healing.stop()
        except Exception:
            logger.exception("Failed to stop self-healing service cleanly")
