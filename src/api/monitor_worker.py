import asyncio
import logging
import os
from pathlib import Path
import sys

from src.api.config import get_settings
from src.api.database import dispose_engine, init_db
from src.api.logging_config import setup_json_logging
from src.api.services.monitor import (
    MonitorRuntimeState,
    heartbeat_is_fresh,
    start_background_monitor,
)


async def _run() -> None:
    settings = get_settings()
    setup_json_logging(
        log_level=settings.log_level,
        json_format=settings.json_logging,
        log_file=settings.log_file,
    )
    logger = logging.getLogger(__name__)

    if not settings.background_monitor_enabled:
        logger.info("Background monitor worker is disabled by configuration")
        return

    logger.info("Initializing monitor worker database connection")
    await init_db()
    logger.info("Starting singleton monitor worker")
    runtime_state = MonitorRuntimeState(heartbeat_file=Path(settings.monitor_heartbeat_file))
    try:
        await start_background_monitor(
            runtime_state,
            max_consecutive_failures=settings.monitor_max_consecutive_failures,
        )
    finally:
        await dispose_engine()


def _healthcheck() -> int:
    heartbeat_file = os.getenv("MONITOR_HEARTBEAT_FILE", "/tmp/mutx-monitor-heartbeat")
    try:
        max_age_seconds = int(os.getenv("MONITOR_HEARTBEAT_MAX_AGE_SECONDS", "30"))
    except ValueError:
        return 1

    return 0 if heartbeat_is_fresh(heartbeat_file, max_age_seconds) else 1


def main() -> None:
    if sys.argv[1:] == ["--healthcheck"]:
        raise SystemExit(_healthcheck())
    if sys.argv[1:]:
        raise SystemExit(f"Unknown monitor worker arguments: {' '.join(sys.argv[1:])}")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
