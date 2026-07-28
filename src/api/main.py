import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.api.config import get_settings
from src.api.database import dispose_engine, init_db
from src.api.document_worker import DocumentWorkerRuntimeState, run_document_worker
from src.api.exception_handlers import (
    generic_exception_handler,
    pydantic_validation_exception_handler,
    validation_exception_handler,
)
from src.api.logging_config import setup_json_logging
from src.api.metrics import (
    router as metrics_router,
    set_runtime_schema_repair_metrics,
    track_request,
)
from src.api.middleware.auth import add_authentication_middleware
from src.api.middleware.rate_limit import (
    add_rate_limiting,
    close_rate_limiting,
    start_rate_limiting,
)
from src.api.middleware.security import add_security_middleware
from src.api.middleware.tracing import add_tracing_middleware
from src.api.models.schemas import HealthResponse
from src.api.reasoning_worker import ReasoningWorkerRuntimeState, run_reasoning_worker
from src.api.routes import (
    agent_runtime,
    agents,
    analytics,
    assistant,
    api_keys,
    audit,
    auth,
    budgets,
    clawhub,
    deployments,
    governance,
    governance_credentials,
    governance_supervision,
    events,
    ingest,
    leads,
    monitoring,
    observability,
    onboarding,
    payments,
    pico,
    policies,
    approvals,
    documents,
    reasoning,
    rag,
    runtime,
    runs,
    scheduler,
    security,
    sessions,
    swarms,
    templates,
    telemetry,
    usage,
    webhooks,
)
from src.api.services.monitor import MonitorRuntimeState, start_background_monitor
from src.api.services.governance_webhook_service import (
    start_governance_webhooks,
    stop_governance_webhooks,
)
from src.api.services.audit_log import (
    get_buffered_audit_log,
    close_buffered_audit_log,
)

settings = get_settings()

setup_json_logging(
    log_level=settings.log_level,
    json_format=settings.json_logging,
    log_file=settings.log_file,
)
logger = logging.getLogger(__name__)
RELEASE_IDENTITY_FILE = Path(__file__).with_name("mutx-release.json")


def _load_release_identity(path: Path = RELEASE_IDENTITY_FILE) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("release identity is unavailable") from exc

    if not isinstance(payload, dict) or set(payload) != {"tag", "version", "sha"}:
        raise ValueError("release identity has an invalid shape")
    if not all(isinstance(payload[key], str) and payload[key] for key in payload):
        raise ValueError("release identity values must be non-empty strings")
    if len(payload["sha"]) != 40 or any(
        character not in "0123456789abcdef" for character in payload["sha"]
    ):
        raise ValueError("release identity SHA must be a full lowercase commit SHA")
    return payload


@dataclass(frozen=True)
class RouterRegistration:
    name: str
    router: APIRouter
    prefix: str | None = "/v1"
    tags: tuple[str, ...] = ()


PUBLIC_ROUTE_REGISTRATIONS: tuple[RouterRegistration, ...] = (
    # Runtime static routes must precede the dashboard agent router's
    # /agents/{agent_id} route so paths such as /agents/commands are reachable.
    RouterRegistration("agent_runtime", agent_runtime.router),
    RouterRegistration("agents", agents.router),
    RouterRegistration("assistant", assistant.router),
    RouterRegistration("deployments", deployments.router),
    RouterRegistration("templates", templates.router),
    RouterRegistration("webhooks", webhooks.router),
    RouterRegistration("auth", auth.router),
    RouterRegistration("clawhub", clawhub.router),
    RouterRegistration("api_keys", api_keys.router),
    RouterRegistration("leads.contacts", leads.contacts_router, prefix="/v1/leads"),
    RouterRegistration("leads", leads.router),
    RouterRegistration("events", events.router),
    RouterRegistration("ingest", ingest.router),
    RouterRegistration("runs", runs.router),
    RouterRegistration("documents", documents.router),
    RouterRegistration("reasoning", reasoning.router),
    RouterRegistration("observability", observability.router),
    RouterRegistration("security", security.router),
    RouterRegistration("rag", rag.router),
    RouterRegistration("usage", usage.router),
    RouterRegistration("analytics", analytics.router),
    RouterRegistration("monitoring", monitoring.router),
    RouterRegistration("onboarding", onboarding.router),
    RouterRegistration("payments", payments.router),
    RouterRegistration("pico", pico.router),
    RouterRegistration("runtime", runtime.router),
    RouterRegistration("scheduler", scheduler.router),
    RouterRegistration("sessions", sessions.router),
    RouterRegistration("swarms", swarms.router),
    RouterRegistration("telemetry", telemetry.router),
    RouterRegistration("budgets", budgets.router),
    RouterRegistration("governance", governance.router),
    RouterRegistration("governance_credentials", governance_credentials.router),
    RouterRegistration("governance_supervision", governance_supervision.router),
    RouterRegistration("policies", policies.router),
    RouterRegistration("approvals", approvals.router),
)
PUBLIC_ROUTER_ALLOWLIST: tuple[str, ...] = tuple(
    registration.name for registration in PUBLIC_ROUTE_REGISTRATIONS
)
UNMOUNTED_ROUTER_NAMES: tuple[str, ...] = ("newsletter",)

# Routes that require authentication - these will be protected with get_current_user
# Add routes here that should always require authentication regardless of individual route dependencies
PRIVATE_ROUTE_REGISTRATIONS: tuple[RouterRegistration, ...] = (
    RouterRegistration("audit", audit.router),
)


def _initialize_app_state(
    app: FastAPI,
    *,
    background_monitor_enabled: bool,
    document_worker_enabled: bool,
    reasoning_worker_enabled: bool,
) -> None:
    app.state.start_time = time.time()
    app.state.database_ready = False
    app.state.database_ready_event = asyncio.Event()
    app.state.database_error = None
    app.state.database_error_detail = None
    app.state.schema_repairs_applied = []
    app.state.background_monitor_enabled = background_monitor_enabled
    app.state.background_monitor_state = MonitorRuntimeState()
    app.state.document_worker_enabled = document_worker_enabled
    app.state.document_worker_state = DocumentWorkerRuntimeState()
    app.state.document_worker_task = None
    app.state.reasoning_worker_enabled = reasoning_worker_enabled
    app.state.reasoning_worker_state = ReasoningWorkerRuntimeState()
    app.state.reasoning_worker_task = None
    app.state.public_router_allowlist = PUBLIC_ROUTER_ALLOWLIST


def _extract_hostname(value: str | None) -> str | None:
    if not value:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if not parsed.hostname:
        return None

    return parsed.hostname.lower()


def _build_allowed_hosts() -> list[str]:
    allowed_hosts = {
        host.strip().lower()
        for host in settings.allowed_hosts
        if isinstance(host, str) and host.strip()
    }

    for env_name in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_PRIVATE_DOMAIN", "API_BASE_URL"):
        host = _extract_hostname(os.environ.get(env_name))
        if host:
            allowed_hosts.add(host)

    return sorted(allowed_hosts)


async def _initialize_database(app: FastAPI) -> None:
    repaired_objects = await init_db()
    app.state.database_ready = True
    app.state.database_ready_event.set()
    app.state.database_error = None
    app.state.database_error_detail = None
    app.state.schema_repairs_applied = repaired_objects
    set_runtime_schema_repair_metrics(repaired_objects)
    logger.info("Database connectivity verified")


async def _initialize_database_with_retries(app: FastAPI) -> None:
    retry_delay = settings.database_init_retry_interval_seconds

    while True:
        try:
            await _initialize_database(app)
            return
        except Exception as exc:
            app.state.database_ready = False
            app.state.database_error = "Database unavailable"
            app.state.database_error_detail = str(exc)
            logger.exception(
                "Database initialization failed; retrying in %s seconds",
                retry_delay,
            )
            await asyncio.sleep(retry_delay)


async def _start_monitor_when_database_ready(app: FastAPI) -> None:
    while not getattr(app.state, "database_ready", False):
        await asyncio.sleep(1)

    logger.info("Database ready; starting background monitor")
    await start_background_monitor(app.state.background_monitor_state)


async def _start_document_worker_when_database_ready(app: FastAPI) -> None:
    await app.state.database_ready_event.wait()

    logger.info("Database ready; starting document queue worker")
    await run_document_worker(
        poll_seconds=settings.document_worker_poll_seconds,
        runtime_state=app.state.document_worker_state,
    )


async def _start_reasoning_worker_when_database_ready(app: FastAPI) -> None:
    await app.state.database_ready_event.wait()

    logger.info("Database ready; starting reasoning queue worker")
    await run_reasoning_worker(
        poll_seconds=settings.reasoning_worker_poll_seconds,
        runtime_state=app.state.reasoning_worker_state,
    )


async def _cancel_background_task(
    task: asyncio.Task[None] | None,
    *,
    name: str,
) -> None:
    if task is None:
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("%s failed while shutting down", name)


def _validate_environment() -> None:
    logger.info("Environment variable validation completed")

    if settings.is_production:
        logger.info("Running in PRODUCTION mode")
    else:
        logger.info("Running in %s mode", settings.environment)


def _build_lifespan(
    *,
    background_monitor_enabled: bool,
    database_required_on_startup: bool,
    document_worker_enabled: bool,
    reasoning_worker_enabled: bool,
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting up API...")

        try:
            _validate_environment()
        except ValueError as exc:
            logger.error("Environment validation failed: %s", exc)
            raise RuntimeError(f"Environment validation failed: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected error during environment validation: %s", exc)
            raise RuntimeError(f"Environment validation failed: {exc}") from exc

        _initialize_app_state(
            app,
            background_monitor_enabled=background_monitor_enabled,
            document_worker_enabled=document_worker_enabled,
            reasoning_worker_enabled=reasoning_worker_enabled,
        )
        database_init_task: asyncio.Task[None] | None = None
        monitor_task: asyncio.Task[None] | None = None
        document_worker_task: asyncio.Task[None] | None = None
        reasoning_worker_task: asyncio.Task[None] | None = None
        governance_webhook_task: asyncio.Task[None] | None = None

        await start_rate_limiting(app)
        try:
            if database_required_on_startup:
                await _initialize_database(app)
            else:
                logger.info("Database initialization running in background")
                database_init_task = asyncio.create_task(_initialize_database_with_retries(app))
        except BaseException:
            await close_rate_limiting(app)
            raise

        if document_worker_enabled:
            document_worker_task = asyncio.create_task(
                _start_document_worker_when_database_ready(app)
            )
            app.state.document_worker_task = document_worker_task
        else:
            logger.info("Document queue worker disabled for this process")

        if reasoning_worker_enabled:
            reasoning_worker_task = asyncio.create_task(
                _start_reasoning_worker_when_database_ready(app)
            )
            app.state.reasoning_worker_task = reasoning_worker_task
        else:
            logger.info("Reasoning queue worker disabled for this process")

        if background_monitor_enabled:
            if database_required_on_startup:
                monitor_task = asyncio.create_task(
                    start_background_monitor(app.state.background_monitor_state)
                )
            else:
                monitor_task = asyncio.create_task(_start_monitor_when_database_ready(app))
        else:
            logger.info("Background monitor disabled for this process")

        if database_required_on_startup:
            try:
                from src.api.database import async_session_maker

                governance_webhook_task = asyncio.create_task(
                    start_governance_webhooks(async_session_maker)
                )
                logger.info("Governance webhook dispatcher started")
            except Exception as e:
                logger.warning(f"Failed to start governance webhook dispatcher: {e}")

        # Initialize buffered audit log for high-throughput audit event buffering
        try:
            await get_buffered_audit_log()
            logger.info("Buffered audit log initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize buffered audit log: {e}")

        try:
            yield
        finally:
            await _cancel_background_task(
                document_worker_task,
                name="Document queue worker",
            )
            await _cancel_background_task(
                reasoning_worker_task,
                name="Reasoning queue worker",
            )

            if monitor_task is not None:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

            if database_init_task is not None:
                database_init_task.cancel()
                try:
                    await database_init_task
                except asyncio.CancelledError:
                    pass

            if governance_webhook_task is not None:
                governance_webhook_task.cancel()
                try:
                    await governance_webhook_task
                except asyncio.CancelledError:
                    pass
                await stop_governance_webhooks()

            # Close buffered audit log (flushes remaining events)
            try:
                await close_buffered_audit_log()
                logger.info("Buffered audit log closed")
            except Exception as e:
                logger.warning(f"Error closing buffered audit log: {e}")

            await close_rate_limiting(app)
            await dispose_engine()

            # Shutdown OpenTelemetry to flush pending spans before process exit
            try:
                from src.api.telemetry.telemetry import shutdown_telemetry

                shutdown_telemetry()
                logger.info("OpenTelemetry shutdown complete")
            except Exception as e:
                logger.warning(f"Error shutting down telemetry: {e}")

    return lifespan


def _register_application_routes(app: FastAPI) -> None:
    app.include_router(metrics_router, tags=["monitoring"])

    for registration in PUBLIC_ROUTE_REGISTRATIONS:
        include_kwargs: dict[str, object] = {}
        if registration.prefix:
            include_kwargs["prefix"] = registration.prefix
        if registration.tags:
            include_kwargs["tags"] = list(registration.tags)
        app.include_router(registration.router, **include_kwargs)

    # Private routers enforce authentication and authorization on each endpoint.
    # Do not add a second principal here: route dependencies must use the same
    # database-backed dashboard user as the rest of the control plane.
    for registration in PRIVATE_ROUTE_REGISTRATIONS:
        include_kwargs: dict[str, object] = {}
        if registration.prefix:
            include_kwargs["prefix"] = registration.prefix
        if registration.tags:
            include_kwargs["tags"] = list(registration.tags)
        app.include_router(registration.router, **include_kwargs)


def _serialize_background_monitor_component(app: FastAPI) -> dict[str, object]:
    monitor_state: MonitorRuntimeState = app.state.background_monitor_state

    if not app.state.background_monitor_enabled:
        component_status = "disabled"
    elif monitor_state.consecutive_failures >= 2:
        component_status = "degraded"
    elif monitor_state.last_success_at is not None:
        component_status = "healthy"
    elif monitor_state.started_at is not None:
        component_status = "starting"
    else:
        component_status = "waiting"

    return {
        "status": component_status,
        "consecutive_failures": monitor_state.consecutive_failures,
    }


def _serialize_queue_worker_component(app: FastAPI, worker_name: str) -> dict[str, object]:
    enabled = getattr(app.state, f"{worker_name}_worker_enabled")
    worker_state = getattr(app.state, f"{worker_name}_worker_state")
    worker_task = getattr(app.state, f"{worker_name}_worker_task")

    if not enabled:
        component_status = "disabled"
    elif worker_state.stopped_at is not None or (worker_task is not None and worker_task.done()):
        component_status = "stopped"
    elif worker_state.started_at is None:
        component_status = "waiting"
    elif worker_state.consecutive_failures:
        component_status = "degraded"
    elif worker_state.last_success_at is not None:
        component_status = "healthy"
    else:
        component_status = "running"

    return {
        "status": component_status,
        "consecutive_failures": worker_state.consecutive_failures,
        "total_failures": worker_state.total_failures,
    }


def _queue_workers_ready(worker_components: dict[str, dict[str, object]]) -> bool:
    ready_statuses = {"disabled", "running", "healthy"}
    return all(component["status"] in ready_statuses for component in worker_components.values())


def _register_system_routes(app: FastAPI) -> None:
    @app.get("/health", response_model=HealthResponse)
    async def health_check(request: Request):
        database_ready = request.app.state.database_ready
        database_error = request.app.state.database_error
        uptime = (
            time.time() - request.app.state.start_time
            if hasattr(request.app.state, "start_time")
            else 0
        )
        database_status = (
            "ready" if database_ready else "unavailable" if database_error else "initializing"
        )
        background_monitor = _serialize_background_monitor_component(request.app)
        worker_components = {
            "document_worker": _serialize_queue_worker_component(request.app, "document"),
            "reasoning_worker": _serialize_queue_worker_component(request.app, "reasoning"),
        }
        workers_ready = _queue_workers_ready(worker_components)
        overall_status = (
            "healthy"
            if database_ready and background_monitor["status"] != "degraded" and workers_ready
            else "degraded"
        )

        return HealthResponse(
            status=overall_status,
            timestamp=datetime.now(timezone.utc),
            database=database_status,
            error=database_error,
            uptime_seconds=uptime,
            components={
                "database": {
                    "status": "healthy" if database_ready else "degraded",
                    "error": database_error,
                },
                "background_monitor": background_monitor,
                **worker_components,
            },
        )

    @app.get("/ready")
    async def readiness_check(request: Request, response: Response):
        database_ready = request.app.state.database_ready
        database_error = request.app.state.database_error
        database_status = (
            "ready" if database_ready else "unavailable" if database_error else "initializing"
        )
        worker_components = {
            "document_worker": _serialize_queue_worker_component(request.app, "document"),
            "reasoning_worker": _serialize_queue_worker_component(request.app, "reasoning"),
        }
        workers_ready = _queue_workers_ready(worker_components)

        if not database_ready or not workers_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "ready" if database_ready and workers_ready else "not_ready",
            "timestamp": datetime.now(timezone.utc),
            "database": database_status,
            "error": database_error,
            "workers": worker_components,
        }

    @app.get("/release", include_in_schema=False)
    async def release_identity():
        try:
            return _load_release_identity()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Release identity is unavailable",
            ) from exc

    @app.get("/")
    async def root():
        return {"message": "mutx.dev API", "version": "1.0.0"}


def create_app(
    *,
    enable_lifespan: bool = True,
    background_monitor_enabled: bool | None = None,
    database_required_on_startup: bool | None = None,
    document_worker_enabled: bool | None = None,
    reasoning_worker_enabled: bool | None = None,
) -> FastAPI:
    resolved_background_monitor_enabled = (
        settings.background_monitor_enabled
        if background_monitor_enabled is None
        else background_monitor_enabled
    )
    resolved_database_required_on_startup = (
        settings.database_required_on_startup
        if database_required_on_startup is None
        else database_required_on_startup
    )
    resolved_document_worker_enabled = (
        settings.documents_enabled if document_worker_enabled is None else document_worker_enabled
    )
    resolved_reasoning_worker_enabled = (
        settings.reasoning_enabled if reasoning_worker_enabled is None else reasoning_worker_enabled
    )

    lifespan = None
    if enable_lifespan:
        lifespan = _build_lifespan(
            background_monitor_enabled=resolved_background_monitor_enabled,
            database_required_on_startup=resolved_database_required_on_startup,
            document_worker_enabled=resolved_document_worker_enabled,
            reasoning_worker_enabled=resolved_reasoning_worker_enabled,
        )

    expose_api_docs = not settings.is_production or settings.expose_api_docs_in_production

    app = FastAPI(
        title="mutx.dev API",
        description="API for the mutx platform",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if expose_api_docs else None,
        redoc_url="/redoc" if expose_api_docs else None,
        openapi_url="/openapi.json" if expose_api_docs else None,
    )
    _initialize_app_state(
        app,
        background_monitor_enabled=resolved_background_monitor_enabled,
        document_worker_enabled=resolved_document_worker_enabled,
        reasoning_worker_enabled=resolved_reasoning_worker_enabled,
    )

    # Initialize OpenTelemetry tracing at startup (guards against ImportError)
    try:
        from src.api.telemetry.telemetry import setup_telemetry

        setup_telemetry("mutx-api")

        # Auto-instrument FastAPI app to create spans for each request
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass  # opentelemetry packages not installed — tracing disabled

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_build_allowed_hosts(),
        www_redirect=False,
    )

    add_security_middleware(app, settings.cors_origins)
    add_rate_limiting(app)
    add_authentication_middleware(app)
    add_tracing_middleware(app)

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    app.middleware("http")(track_request)

    _register_application_routes(app)
    _register_system_routes(app)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
