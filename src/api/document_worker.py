import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from src.api import database
from src.api.config import get_settings
from src.api.logging_config import setup_json_logging
from src.api.services.document_jobs import (
    claim_next_document_job,
    execute_document_job,
    update_document_queue_depth,
)

logger = logging.getLogger(__name__)


@dataclass
class DocumentWorkerRuntimeState:
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    total_failures: int = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def run_document_worker(
    *,
    poll_seconds: float | None = None,
    runtime_state: DocumentWorkerRuntimeState | None = None,
) -> None:
    """Consume document jobs until cancelled without owning the shared DB engine."""
    settings = get_settings()
    resolved_poll_seconds = (
        float(settings.document_worker_poll_seconds) if poll_seconds is None else poll_seconds
    )
    state = runtime_state or DocumentWorkerRuntimeState()
    state.started_at = _utcnow()
    state.stopped_at = None
    logger.info("Starting document worker loop")

    try:
        while True:
            sleep_before_next_poll = False
            try:
                async with database.async_session_maker() as session:
                    claimed = await claim_next_document_job(session)
                    if claimed is None:
                        sleep_before_next_poll = True
                    else:
                        await execute_document_job(session, claimed_job=claimed)
                    await update_document_queue_depth(session)

                state.last_success_at = _utcnow()
                state.last_error = None
                state.consecutive_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                state.last_failure_at = _utcnow()
                state.last_error = str(exc)
                state.consecutive_failures += 1
                state.total_failures += 1
                sleep_before_next_poll = True
                logger.exception("Document worker iteration failed; retrying: %s", exc)

            if sleep_before_next_poll:
                await asyncio.sleep(resolved_poll_seconds)
    finally:
        state.stopped_at = _utcnow()
        logger.info("Document worker loop stopped")


async def _run() -> None:
    settings = get_settings()
    setup_json_logging(
        log_level=settings.log_level,
        json_format=settings.json_logging,
        log_file=settings.log_file,
    )

    if not settings.documents_enabled:
        logger.info("Document worker is disabled by configuration")
        return

    await database.init_db()

    try:
        await run_document_worker(poll_seconds=settings.document_worker_poll_seconds)
    finally:
        await database.dispose_engine()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
