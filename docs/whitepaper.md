---
description: Technical architecture and design reference for the MUTX control plane.
icon: file-lines
---

# MUTX Technical Architecture Reference

## 1. Abstract

MUTX is a control plane for AI agents. It provides governance (policy evaluation, human approval workflows, cryptographic receipt chains), identity (JWT + API key + SPIFFE), observability (OpenTelemetry traces, Prometheus metrics, structured audit logs), and infrastructure management (deployment lifecycle, self-healing, credential brokering). The system is a FastAPI application backed by PostgreSQL (async via asyncpg), with a Python SDK and a Textual TUI.

This document describes the internal architecture. It is not a getting-started guide. It assumes you are a senior engineer who needs to understand how the system works in order to extend, debug, or operate it.

## 2. The Problem

Operating autonomous agents in production fails in predictable ways:

| Failure Mode | What Happens | MUTX Mitigation |
|---|---|---|
| Unbounded tool execution | Agent calls destructive tools (shell, file delete, network) without constraint | Supported supervised paths can evaluate a NormalizedAction before execution; complete current AARM R1 coverage is not yet demonstrated |
| Context-blind gating | Individual actions look safe but the sequence is dangerous (e.g., read-credit-cards → send-email) | ContextAccumulator stores session actions and data access (partial current R2/R3); IntentSignal is a heuristic, not current R7 semantic distance |
| No human override | High-risk actions execute automatically with no approval path | ApprovalService provides a human decision lifecycle (partial current R4; STEP_UP and DEFER are not yet distinct) |
| No audit trail | After an incident, there is no record of what the agent did, why, or who approved it | ReceiptGenerator automatically Ed25519-signs ActionReceipts for offline tamper verification (partial current R5; the full evidence schema/path proof is not yet demonstrated) |
| Credential sprawl | API keys and secrets embedded in agent configs or environment variables permanently | CredentialBroker retrieves on-demand with TTL, injects as ephemeral env vars |
| Agent zombie processes | Agent crashes but its status remains "running" indefinitely | MonitorRuntimeState tracks heartbeats; SelfHealer recovers via RESTART/ROLLBACK |
| Identity ambiguity | Cannot distinguish agent actions from developer actions or from different agents | JWT/API key auth plus agent, session, and user identifiers (partial current R6; service identity and privilege scope remain gaps) |

## 3. Design Principles

1. **Pre-execution gating target.** Supported supervised paths should pass through ActionMediator → PolicyEngine before execution. Complete path coverage and fail-closed behavior must be proven before making a universal claim.
2. **Context-aware decisions.** Policy evaluation considers accumulated session state, not just the current action in isolation.
3. **Cryptographic receipts.** Every evaluated action produces a tamper-evident receipt with chain integrity.
4. **Defense in depth.** Auth middleware, ownership enforcement, rate limiting, and input validation are independent layers.
5. **Framework agnostic.** The governance pipeline normalizes tool calls from any framework (LangGraph, CrewAI, AutoGen, etc.) into NormalizedAction before evaluation.

### Non-Goals

- MUTX does not train, fine-tune, or host language models.
- MUTX does not replace your infrastructure orchestrator. It integrates with Kubernetes/Helm for deployment but does not manage clusters.
- MUTX does not provide a browser-based agent runtime. It governs agents you run yourself or via Faramesh supervision.

## 4. System Architecture

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Operator Surfaces                         │
│  CLI (Click)  │  TUI (Textual)  │  Next.js Dashboard  │  SDK    │
├─────────────────────────────────────────────────────────────────┤
│                         Control Plane API                        │
│  FastAPI + Uvicorn  │  32 Route Modules  │  Middleware Stack     │
├─────────────────────────────────────────────────────────────────┤
│                      Governance Engine                           │
│  ActionMediator → ContextAccumulator → PolicyEngine              │
│  → ApprovalService │ ReceiptGenerator │ TelemetryExporter        │
├─────────────────────────────────────────────────────────────────┤
│                        Services                                  │
│  FarameshSupervisor │ CredentialBroker │ SPIFFEIdentityProvider  │
│  SelfHealer │ AuditLog │ PolicyStore │ Monitoring │ Webhooks    │
├─────────────────────────────────────────────────────────────────┤
│                         Data Layer                               │
│  PostgreSQL 16 (asyncpg) │ Redis 7 │ Alembic Migrations         │
├─────────────────────────────────────────────────────────────────┤
│                     Infrastructure                               │
│  Docker Compose │ Helm Chart │ Nginx │ Prometheus │ Grafana      │
│  OTel Collector │ Jaeger │ Ansible Playbooks                     │
└─────────────────────────────────────────────────────────────────┘
```

### Codebase Layout

```
src/api/                         # FastAPI control plane
  main.py                        # Application factory, lifespan, route registration
  config.py                      # Pydantic Settings (404 lines)
  database.py                    # Async engine, SSL negotiation, schema repair (387 lines)
  models/
    models.py                    # 24 SQLAlchemy ORM models (633 lines)
    schemas.py                   # Pydantic request/response schemas (865 lines)
    migrations/versions/         # 17 Alembic migration files
  auth/
    jwt.py                       # JWT + refresh token rotation (319 lines)
    ownership.py                 # Resource ownership enforcement (65 lines)
  middleware/
    auth.py                      # Dual auth resolution (346 lines)
    tracing.py                   # OTel context propagation (57 lines)
    rate_limit.py                # Rate limiting
    security.py                  # Security headers
  routes/                        # 32 route modules
  services/
    self_healer.py               # Autonomous recovery (718 lines)
    credential_broker.py         # 6-backend credential broker (863 lines)
    faramesh_supervisor.py       # Process supervision (637 lines)
    spiffe_identity.py           # SPIFFE/SPIRE identity (256 lines)
    audit_log.py                 # aiosqlite audit store (464 lines)
    policy_store.py              # In-memory policy CRUD + SSE (149 lines)
    monitoring.py                # Health monitoring + webhooks (309 lines)
    monitor.py                   # Background monitor daemon (201 lines)
    operator_state.py            # Onboarding state machine (297 lines)
  metrics.py                     # Prometheus metrics (141 lines)
  logging_config.py              # JSON structured logging (149 lines)
  exception_handlers.py          # Structured error responses (138 lines)

src/security/                    # Governance engine (framework-agnostic)
  mediator.py                    # Action mediation (317 lines)
  context.py                     # Context accumulation (388 lines)
  policy.py                      # Policy engine (465 lines)
  approvals.py                   # Approval service (395 lines)
  receipts.py                    # Cryptographic receipts (407 lines)
  compliance.py                  # Local AARM-alignment gap checker
  telemetry.py                   # Security telemetry exporter

sdk/mutx/                        # Python SDK
  agent_runtime.py               # Agent client (937 lines)
  guardrails.py                  # Client-side guardrails (371 lines)
  policy.py                      # Policy hot-reload client (207 lines)
  telemetry.py                   # SDK telemetry

cli/                             # CLI and TUI
  commands/                      # 23 Click command groups
  tui/                           # Textual cockpit

infrastructure/                  # Deployment and configuration
  docker/                        # Docker Compose + Dockerfiles
  helm/mutx/                     # Helm chart with templates
  kubernetes/                    # Raw K8s manifests
  ansible/                       # Configuration management playbooks
  monitoring/                    # Prometheus + Alertmanager configs
```

### Operator Surfaces

| Surface | Entry Point | Protocol | Use Case |
|---|---|---|---|
| REST API | `src/api/main.py:app` | HTTP/JSON | Primary integration surface |
| CLI | `cli/main.py` | Shell | Developer workflows |
| TUI | `cli/commands/tui.py` | Terminal | Operational cockpit |
| SDK | `sdk/mutx/agent_runtime.py` | Python library | Agent-side integration |
| Prometheus | `/metrics` endpoint | HTTP/text | Metrics scraping |
| SSE | `/v1/policies/stream` | Server-Sent Events | Policy hot-reload |
| Webhooks | User-registered URLs | HTTP POST | Event notifications |

## 5. Control Plane API

### Application Lifecycle

Source: `src/api/main.py`

The application lifecycle is managed by an async context manager built in `_build_lifespan()`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_environment()
    _initialize_app_state(app, ...)

    if database_required_on_startup:
        await _initialize_database(app)
    else:
        database_init_task = asyncio.create_task(
            _initialize_database_with_retries(app)
        )

    if background_monitor_enabled:
        monitor_task = asyncio.create_task(
            start_background_monitor(app.state.background_monitor_state)
        )

    # Governance webhook dispatcher
    governance_webhook_task = asyncio.create_task(
        start_governance_webhooks(async_session_maker)
    )

    # Buffered audit log
    await get_buffered_audit_log()

    try:
        yield
    finally:
        # Cancel all background tasks
        await close_buffered_audit_log()
        await dispose_engine()
```

Key behaviors:
- When `DATABASE_REQUIRED_ON_STARTUP=true`, database init blocks startup. When false, it retries in a background task.
- The background monitor waits for database readiness before starting.
- On shutdown, all tasks are cancelled, buffered audit events are flushed, and the database engine is disposed.

### Route Mounting

Source: `src/api/main.py:323-346`

Routes are organized into public and private registrations. Private routes receive `get_current_user` as a dependency:

```python
def _register_application_routes(app: FastAPI) -> None:
    app.include_router(metrics_router, tags=["monitoring"])

    for registration in PUBLIC_ROUTE_REGISTRATIONS:
        app.include_router(registration.router, ...)

    for registration in PRIVATE_ROUTE_REGISTRATIONS:
        app.include_router(
            registration.router,
            dependencies=[Depends(get_current_user)],
            ...
        )
```

32 routers are registered, each with `APIRouter(prefix=...)`:

| Prefix | Route Module | Key Operations |
|---|---|---|
| `/agents` | `routes/agents.py` | CRUD, config management, metrics, logs |
| `/deployments` | `routes/deployments.py` | CRUD, versioning, events |
| `/auth` | `routes/auth.py` | Login, register, refresh, password reset, email verification |
| `/api-keys` | `routes/api_keys.py` | API key lifecycle |
| `/observability` | `routes/observability.py` | MutxRun, steps, costs, eval, provenance |
| `/security` | `routes/security.py` | Security evaluation API |
| `/policies` | `routes/policies.py` | Policy CRUD + SSE stream |
| `/approvals` | `routes/approvals.py` | Approval workflow API |
| `/audit` | `routes/audit.py` | Audit query API |
| `/runtime/governance/supervised` | `routes/governance_supervision.py` | Supervised launch |
| `/governance/credentials` | `routes/governance_credentials.py` | Credential broker API |
| `/webhooks` | `routes/webhooks.py` | Webhook registration |
| `/monitoring` | `routes/monitoring.py` | Health and metrics |
| `/usage` | `routes/usage.py` | Usage tracking |
| `/budgets` | `routes/budgets.py` | Budget management |
| `/scheduler` | `routes/scheduler.py` | Scheduled tasks |
| `/runs` | `routes/runs.py` | Agent run tracking |
| `/sessions` | `routes/sessions.py` | Session management |
| `/analytics` | `routes/analytics.py` | Analytics events |
| `/telemetry` | `routes/telemetry.py` | Telemetry config + health |
| `/pico` | `routes/pico.py` | Progress read/write for Pico |
| `/rag` | `routes/rag.py` | RAG operations |
| `/templates` | `routes/templates.py` | Agent templates |
| `/swarms` | `routes/swarms.py` | Swarm coordination |
| `/runtime` | `routes/runtime.py` | Runtime operations |
| `/assistant` | `routes/assistant.py` | Assistant integration |
| `/ingest` | `routes/ingest.py` | Data ingestion |
| `/clawhub` | `routes/clawhub.py` | ClawHub integration |
| `/newsletter` | `routes/newsletter.py` | Newsletter signup (UNMOUNTED — code exists but not served; `/v1/leads` is the active replacement) |
| `/onboarding` | `routes/onboarding.py` | User onboarding |
| `/leads` | `routes/leads.py` | Lead/contact management |
| `/agents` (agent-runtime) | `routes/agent_runtime.py` | Agent-side heartbeat, commands |
| `/contacts` | `routes/leads.py` (secondary router) | Contact management |

### Request Lifecycle

Source: `src/api/main.py:432-509`

Middleware is registered in reverse execution order (Starlette convention). The actual execution order for each request is:

```
TrustedHost → CORS → Security Headers → Rate Limit → Auth → Tracing → track_request → Route Handler
```

#### TracingMiddleware

Source: `src/api/middleware/tracing.py`

```python
class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        carrier = {}
        propagator = TraceContextTextMapPropagator()

        traceparent = request.headers.get("TRACEPARENT")
        tracestate = request.headers.get("TRACESTATE")

        if traceparent:
            carrier["traceparent"] = traceparent
        if tracestate:
            carrier["tracestate"] = tracestate

        propagator.extract(carrier)

        # Parse trace_id and span_id from TRACEPARENT
        # Format: 00-<trace_id>-<span_id>-<trace_flags>
        if traceparent:
            parts = traceparent.split("-")
            if len(parts) >= 3:
                trace_id = parts[1]
                span_id = parts[2]

        request.state.trace_id = trace_id
        request.state.span_id = span_id
        request.state.traceparent = traceparent
        request.state.tracestate = tracestate

        return await call_next(request)
```

The `TraceContextTextMapPropagator` from the OpenTelemetry SDK handles W3C trace context extraction. Parsed values are stored on `request.state` for downstream access by loggers, audit events, and error handlers.

#### AuthenticationMiddleware

Source: `src/api/middleware/auth.py` (346 lines)

The auth middleware resolves identity early in the request lifecycle so downstream middleware and route handlers can access it without performing their own auth resolution. It populates `request.state` with auth context.

**Dual resolution strategy:**

```python
class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        request.state.auth_user_id = None
        request.state.auth_method = None
        request.state.auth_api_key_id = None

        bearer_token = _extract_bearer_token(
            request.headers.get("Authorization")
        )
        x_api_key = request.headers.get("X-API-Key")

        if bearer_token:
            # Attempt JWT first
            user_id = verify_access_token(bearer_token)
            if user_id:
                request.state.auth_user_id = user_id
                request.state.auth_method = "jwt"
            else:
                # Fallback to API key in bearer position
                await _populate_api_key_context(request, bearer_token)
        elif x_api_key:
            await _populate_api_key_context(request, x_api_key)

        return await call_next(request)
```

Resolution order:
1. If `Authorization: Bearer <token>` is present, attempt JWT verification via `verify_access_token()`.
2. If JWT fails, attempt API key resolution via `_populate_api_key_context()`, which calls `UserService.authenticate_api_key(token)`.
3. If `X-API-Key` header is present, resolve as API key.
4. If none match, the request proceeds unauthenticated. Route-level dependencies (`get_current_user`) enforce auth where required.

**Email verification enforcement:**

```python
def _enforce_email_verification_if_required(user: User) -> None:
    settings = get_settings()
    if settings.require_email_verification and not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification is required",
        )
```

**Internal user restriction:**

```python
def assert_internal_user(user: User) -> None:
    if not user.is_email_verified:
        raise HTTPException(status_code=403, detail="Forbidden")

    allowed_domains = {
        domain.strip().lower()
        for domain in settings.internal_user_email_domains
        if domain and domain.strip()
    }

    user_domain = user.email.rsplit("@", 1)[-1].lower()
    if user_domain not in allowed_domains:
        raise HTTPException(status_code=403, detail="Forbidden")
```

Used by `get_current_internal_user()` to gate Faramesh supervision and other internal endpoints.

#### Rate Limiting

Configured via `src/api/config.py`:

```python
rate_limit_requests: int = 100        # requests per window
rate_limit_window_seconds: int = 60   # window duration
auth_rate_limit_requests: int = 10    # auth-sensitive limit
auth_rate_limit_window_seconds: int = 60
```

Applied via `add_rate_limiting(app)` in `create_app()`.

#### Security Headers Middleware

Source: `src/api/middleware/security.py`

Applied via `add_security_middleware(app, settings.cors_origins)`. Adds standard security headers (X-Content-Type-Options, X-Frame-Options, etc.) to all responses.

### Exception Handling

Source: `src/api/exception_handlers.py` (138 lines)

Three handlers are registered:

```python
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
```

All three produce structured JSON responses with request_id correlation:

```python
# RequestValidationError handler
response = ValidationErrorResponse(
    status="error",
    error_code="VALIDATION_ERROR",
    message="Request validation failed",
    details=details,
    request_id=request_id,
    timestamp=datetime.now(timezone.utc).isoformat(),
)
```

```python
# Generic 500 handler - does NOT leak exception details
response = InternalErrorResponse(
    status="error",
    error_code="INTERNAL_ERROR",
    message="An internal error occurred",
    request_id=request_id,
    timestamp=datetime.now(timezone.utc).isoformat(),
)
```

The `request_id` is extracted from `request.state.request_id` or generated as a new UUID. This correlates with structured log entries and trace spans.

### Prometheus Metrics

Source: `src/api/metrics.py` (141 lines)

Exposed at `GET /metrics` via the `prometheus_client` `generate_latest()` function.

**Counters:**

```python
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

mutx_agent_tasks_total = Counter(
    "mutx_agent_tasks_total",
    "Total agent tasks processed",
    ["status"],  # success, failed, timeout
)

mutx_api_calls_total = Counter(
    "mutx_api_calls_total",
    "Total API calls",
    ["endpoint"],
)

mutx_errors_total = Counter(
    "mutx_errors_total",
    "Total errors by type",
    ["type", "endpoint"],
)
```

**Histograms:**

```python
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

http_request_size_bytes = Histogram(
    "http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "path"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000],
)

http_response_size_bytes = Histogram(
    "http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "path"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000],
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

mutx_agent_task_duration_seconds = Histogram(
    "mutx_agent_task_duration_seconds",
    "Agent task duration in seconds",
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0],
)
```

**Gauges:**

```python
http_connections_active = Gauge("http_connections_active", "Number of active HTTP connections")
db_pool_size = Gauge("db_pool_size", "Database connection pool size")
db_pool_acquired = Gauge("db_pool_acquired", "Number of acquired database connections")
db_pool_overflow = Gauge("db_pool_overflow", "Number of overflow connections")
mutx_agents_total = Gauge("mutx_agents_total", "Total number of agents")
mutx_agents_active = Gauge("mutx_agents_active", "Number of active agents")
mutx_deployments_total = Gauge("mutx_deployments_total", "Total number of deployments")
mutx_deployments_running = Gauge("mutx_deployments_running", "Number of running deployments")
mutx_deployments_by_status = Gauge("mutx_deployments_by_status", "Deployments by status", ["status"])
mutx_queue_size = Gauge("mutx_queue_size", "Current size of agent task queue")
mutx_runtime_schema_repairs_applied = Gauge(...)
mutx_runtime_schema_repairs_total = Gauge(...)
mutx_background_monitor_consecutive_failures = Gauge(...)
```

The `track_request` middleware function wraps every HTTP request:

```python
async def track_request(request: Request, call_next):
    start_time = time.time()
    http_connections_active.inc()
    try:
        response = await call_next(request)
    except Exception as e:
        mutx_errors_total.labels(type=type(e).__name__, endpoint=request.url.path).inc()
        raise
    finally:
        http_connections_active.dec()

    duration = time.time() - start_time
    http_requests_total.labels(
        method=request.method, path=path, status=response.status_code
    ).inc()
    http_request_duration_seconds.labels(
        method=request.method, path=path
    ).observe(duration)
```

### JSON Structured Logging

Source: `src/api/logging_config.py` (149 lines)

```python
class StructuredJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)

        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["function"] = record.funcName
        log_record["line"] = record.lineno
        log_record["module"] = record.module
        log_record["process_id"] = record.process
        log_record["thread_id"] = record.thread
        log_record["message"] = record.getMessage()

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
```

A `RequestIdFilter` ensures every log record has a `request_id` field (generated as `uuid4()[:8]` if not already set).

The formatter has a graceful fallback when `pythonjsonlogger` is not installed:

```python
try:
    from pythonjsonlogger import jsonlogger
except ModuleNotFoundError:
    class _FallbackJsonFormatter(logging.Formatter):
        # Minimal JSON formatter that preserves the same add_fields interface
```

Configuration via `setup_json_logging()`:

```python
def setup_json_logging(log_level="INFO", json_format=True, log_file=None):
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if json_format:
        formatter = StructuredJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s",
            rename_fields={"levelname": "level", "name": "logger"},
        )
```

## 6. Data Layer

### ORM Schema

Source: `src/api/models/models.py` (633 lines)

All 24 models inherit from `Base` (SQLAlchemy `DeclarativeBase` defined in `src/api/database.py`). They use the `Mapped[]` / `mapped_column()` pattern from SQLAlchemy 2.0.

**Enums:**

```python
class Plan(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class AgentType(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LANGCHAIN = "langchain"
    CUSTOM = "custom"
    OPENCLAW = "openclaw"

class AgentStatus(str, enum.Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    DELETING = "deleting"

class AlertType(str, enum.Enum):
    CPU_HIGH = "cpu_high"
    MEMORY_HIGH = "memory_high"
    AGENT_DOWN = "agent_down"
    DEPLOYMENT_FAILED = "deployment_failed"
    QUOTA_EXCEEDED = "quota_exceeded"
```

**Polymorphic ARRAY type:**

```python
def ARRAY(type_):
    """Works with both PostgreSQL ARRAY and SQLite (as JSON string)."""
    class ArrayType(TypeDecorator):
        impl = TEXT
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == "postgresql":
                return dialect.type_descriptor(PG_ARRAY(type_))
            else:
                return dialect.type_descriptor(TEXT())

        def process_bind_param(self, value, dialect):
            if value is None: return None
            if dialect.name == "postgresql": return value
            return json.dumps(value)

        def process_result_value(self, value, dialect):
            if value is None: return None
            if dialect.name == "postgresql": return value
            return json.loads(value)

    return ArrayType()
```

Used for columns like `Webhook.events: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)`.

**JSONText type:**

```python
def JSONText():
    """Store JSON-compatible Python values in a text column."""
    class JSONTextType(TypeDecorator):
        impl = TEXT
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None: return None
            if isinstance(value, str): return value
            return json.dumps(value)

        def process_result_value(self, value, dialect):
            if value is None or isinstance(value, (dict, list)): return value
            try: return json.loads(value)
            except (TypeError, json.JSONDecodeError): return None

    return JSONTextType()
```

**Complete model catalog:**

| Model | Table | Primary Key | Key Columns | Relationships |
|---|---|---|---|---|
| User | users | UUID id | email (unique), name, password_hash, plan, api_key, is_active, is_email_verified, email_verification_token, email_verification_expires_at, email_verified_at, password_reset_token, password_reset_expires_at | agents, api_keys, refresh_token_sessions, settings, webhooks, runs |
| UserSetting | user_settings | UUID id | user_id (FK), key, value (JSONText) | user |
| Agent | agents | UUID id | user_id (FK), name, description, type (AgentType), config (Text), status, api_key, last_heartbeat | user, deployments, metrics, alerts, logs, agent_metrics, runs, versions |
| AgentVersion | agent_versions | UUID id | agent_id (FK), version (int), config_snapshot (Text), status, rolled_back_at | agent |
| Deployment | deployments | UUID id | agent_id (FK), status, region, version, replicas, node_id, started_at, ended_at, error_message | agent, events, versions |
| DeploymentEvent | deployment_events | UUID id | deployment_id (FK), event_type, status, node_id, error_message | deployment |
| DeploymentVersion | deployment_versions | UUID id | deployment_id (FK), version (int), config_snapshot (Text), status, rolled_back_at | deployment |
| APIKey | api_keys | UUID id | user_id (FK), key_hash, name, last_used, expires_at, is_active | user |
| RefreshTokenSession | refresh_token_sessions | UUID id | user_id (FK), token_jti (unique), family_id, expires_at, last_used_at, revoked_at, replaced_by_token_jti | user |
| Webhook | webhooks | UUID id | user_id (FK), url, events (ARRAY), secret, is_active | user |
| Metrics | metrics | UUID id | agent_id (FK), cpu, memory, requests, latency | agent |
| Alert | alerts | UUID id | agent_id (FK), type (AlertType), message, resolved, resolved_at | agent |
| AgentLog | agent_logs | UUID id | agent_id (FK), level, message, extra_data, meta_data (JSONText) | agent |
| Command | commands | UUID id | agent_id (FK), action, parameters (JSONText), status, result (JSONText), error_message, completed_at | agent |
| AgentMetric | agent_metrics | UUID id | agent_id (FK), cpu_usage, memory_usage | agent |
| AgentRun | agent_runs | UUID id | agent_id (FK), user_id (FK), status, input_text, output_text, error_message, run_metadata, started_at, completed_at | agent, user, traces |
| AgentRunTrace | agent_run_traces | UUID id | run_id (FK), event_type, message, payload, sequence (int) | run |
| WebhookDeliveryLog | webhook_delivery_logs | UUID id | webhook_id (FK), event, payload, status_code, response_body, success, error_message, attempts, delivered_at | webhook |
| WaitlistSignup | waitlist_signups | UUID id | email (unique), source | — |
| Lead | leads | UUID id | email, name, company, message, source | — |
| UsageEvent | usage_events | UUID id | event_type, user_id (FK), resource_type, resource_id, credits_used, event_metadata | user |
| AnalyticsEvent | analytics_events | UUID id | event_name, user_id (FK), event_type, properties (Text) | user |
| AgentResourceUsage | agent_resource_usage | UUID id | agent_id (FK), prompt_tokens, completion_tokens, total_tokens, api_calls, cost_usd, model, period_start, period_end | agent |

### Alembic Migrations

Source: `src/api/models/migrations/versions/`

17 migration files covering the full schema evolution:

```
e8f636a73690_initial_migration_create_all_tables.py
auth_fields_001.py
alter_plan_column.py
1b6f9c3d4e2a_add_email_verification_expiry.py
3a8f2b1c4d6e_add_meta_data_to_agent_logs.py
6c5b4a3921de_repair_openclaw_agenttype_and_alert_timestamps.py
7f3e2c1b4a6d_add_user_settings_table.py
8f2d6e4b9c1a_add_deployment_events_table.py
9a1b2c3d4e5f6_add_agent_versions_table.py
a1b2c3d4e5f6_add_analytics_events_table.py
c8a63f2d1f25_add_agent_runs_and_traces.py
f7e2a1c8d9b4_add_usage_events_table.py
d91f0a7b6c5e_converge_runtime_schema_repairs.py
f3b8c1d2e4f5_merge_live_mode_heads.py
8b3a6f1d2c4e_repair_live_auth_schema_drift.py
0f4d7b2c9a11_live_mode_schema_hardening.py
5c2f4a7d9e10_merge_orphan_schema_heads.py
```

The Docker Compose setup runs `alembic upgrade head` in a dedicated `migrate` service before starting the API.

### Database Engine Construction

Source: `src/api/database.py` (387 lines)

**SSL mode negotiation:**

```python
def _normalize_ssl_setting(value: str) -> str | bool:
    lowered_value = value.strip().lower()
    if lowered_value in {"1", "true", "yes", "on"}:
        return "require"
    if lowered_value in {"0", "false", "no", "off", "disable"}:
        return False
    if lowered_value in {"allow", "prefer", "require", "verify-ca", "verify-full"}:
        return lowered_value
    raise ValueError("Unsupported PostgreSQL SSL mode.")
```

SSL mode is resolved from three sources in priority order:
1. `override_ssl_mode` parameter (runtime override)
2. `settings.database_ssl_mode` (from `DATABASE_SSL_MODE` env var)
3. `sslmode` query parameter in the `DATABASE_URL`

**Engine creation:**

```python
def _create_engine(engine_config: EngineConfig) -> AsyncEngine:
    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
        "connect_args": engine_config.connect_args,
    }
    if engine_config.url.startswith("postgresql+"):
        engine_kwargs["poolclass"] = NullPool  # asyncpg manages its own pool

    return create_async_engine(engine_config.url, **engine_kwargs)
```

PostgreSQL uses `NullPool` because asyncpg manages connection pooling internally.

**Runtime schema repair:**

```python
async def init_db() -> list[str]:
    try:
        await _run_startup_probe()
        await _repair_runtime_schema()
    except Exception as exc:
        if not _should_retry_without_ssl(exc):
            raise
        logger.warning("Database rejected SSL upgrade; retrying with SSL disabled")
        await _reconfigure_engine(override_ssl_mode="disable")
        await _run_startup_probe()
        await _repair_runtime_schema()
    return get_last_runtime_schema_repairs()
```

`_repair_runtime_schema()` detects and auto-creates missing tables, columns, and indexes:

```python
def _repair_known_schema_drift(sync_connection: Connection) -> list[str]:
    repaired_objects = []

    # Add OPENCLAW to agenttype enum if missing
    if _is_postgresql(sync_connection) and not _has_postgresql_enum_value(
        sync_connection, "agenttype", "OPENCLAW"
    ):
        sync_connection.execute(
            text("ALTER TYPE agenttype ADD VALUE IF NOT EXISTS 'OPENCLAW'")
        )
        repaired_objects.append("agenttype.OPENCLAW")

    # Add last_heartbeat column if missing
    if _has_table(sync_connection, "agents") and not _has_column(
        sync_connection, "agents", "last_heartbeat"
    ):
        sync_connection.execute(
            text("ALTER TABLE agents ADD COLUMN last_heartbeat ...")
        )

    # Create entire tables if missing (agent_logs, refresh_token_sessions, usage_events)
    # Fix timezone-awareness on alert.resolved_at
    # Add missing indexes on refresh_token_sessions, usage_events
```

### Connection Lifecycle

The `init_db()` and `dispose_engine()` functions are called from the lifespan context manager in `main.py`. The `get_db()` dependency creates a session per request:

```python
async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
```

## 7. Authentication

### JWT Implementation

Source: `src/api/auth/jwt.py` (319 lines)

**Token structure:**

Access tokens:

```python
{
    "sub": "<user_uuid>",
    "type": "access",
    "exp": <expiry_timestamp>,
    "iat": <issued_at_timestamp>,
}
```

Refresh tokens:

```python
{
    "sub": "<user_uuid>",
    "type": "refresh",
    "exp": <expiry_timestamp>,
    "iat": <original_issued_at>,   # preserved across rotations
    "nonce": "<random_hex>",
    "family_id": "<family_uuid>",  # groups tokens from same login session
    "jti": "<token_uuid>",         # unique per token
}
```

**Sliding window expiry:**

```python
def create_refresh_token(user_id, original_iat=None, *, family_id=None, token_jti=None):
    now = datetime.now(timezone.utc)
    if original_iat is not None:
        # Sliding: cap at max sliding days from original issue time
        max_expire = original_iat + timedelta(days=REFRESH_TOKEN_MAX_SLIDING_DAYS)
        expire = min(now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), max_expire)
        iat = original_iat  # Keep original for future sliding
    else:
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        iat = now
```

Defaults: `ACCESS_TOKEN_EXPIRE_MINUTES=30`, `REFRESH_TOKEN_EXPIRE_DAYS=7`, `REFRESH_TOKEN_MAX_SLIDING_DAYS=30`.

**Refresh token rotation with family revocation:**

When a refresh token is used:
1. Look up the `RefreshTokenSession` by `token_jti`.
2. If the session's `revoked_at` is not null, the token was already used — revoke the entire family (token reuse detection):
   ```python
   if current_session.revoked_at is not None:
       await revoke_refresh_token_family(session, current_session.family_id, user_id=user_id)
       return None  # Forces re-login
   ```
3. Create a new token pair with the same `family_id`.
4. Mark the old session as revoked with `replaced_by_token_jti` pointing to the replacement.

### Local Bootstrap Auth

Source: `src/api/routes/auth.py`

For Docker-local setups, the system uses a special `local-operator@mutx.local` email that bypasses normal registration flows. This email is part of the `internal_user_email_domains` allowlist.

### Password Handling

Passwords are hashed with bcrypt via `passlib`. The `UserService` handles password hashing at creation time:

```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

Password strength validation is configurable via `Settings`.

### API Key Lifecycle

Source: `src/api/routes/api_keys.py`, `src/api/services/user_service.py`

1. **Creation:** User calls `POST /v1/api-keys` with a name. The system generates a key with `mutx_live_` prefix, hashes it with SHA-256 for storage, and returns the plaintext key exactly once.

2. **Storage:** Only the `key_hash` is stored in the `api_keys` table:
   ```python
   key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
   ```

3. **Verification:** When a request carries a bearer token that fails JWT verification, the system hashes the provided token and compares against stored hashes.

4. **Rotation:** Keys can be deactivated (`is_active=False`) but not rotated in-place. Users create a new key and deactivate the old one.

### Ownership Enforcement

Source: `src/api/auth/ownership.py` (65 lines)

```python
async def get_owned_agent(
    agent_id: uuid.UUID, db: AsyncSession, current_user: User,
    *, include_deployments=False, include_deployment_events=False,
) -> Agent:
    query = select(Agent).where(Agent.id == agent_id)
    if include_deployments:
        deployment_loader = selectinload(Agent.deployments)
        if include_deployment_events:
            deployment_loader = deployment_loader.selectinload(Deployment.events)
        query = query.options(deployment_loader)

    agent = (await db.execute(query)).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return agent
```

Uses `selectinload` for eager loading of deployments and their events, avoiding N+1 queries. The `get_owned_deployment()` function delegates to `get_owned_agent()` to verify the user owns the parent agent.

## 8. Governance Engine

The governance engine is the deepest subsystem in MUTX. It is designed toward
the current AARM runtime-security requirements and provides capability modules
from tool invocation normalization through receipt generation. It is not a
complete AARM Core implementation and is not an AARM conformance claim.

The pipeline flows:

```
Tool Invocation
    │
    ▼
ActionMediator          ← Normalizes to NormalizedAction
    │
    ▼
ContextAccumulator      ← Loads session state, detects intent drift
    │
    ▼
PolicyEngine            ← Evaluates against rules + context
    │
    ├──→ ApprovalService      (if DEFER)
    ├──→ ReceiptGenerator     (always)
    └──→ TelemetryExporter    (always)
```

### ActionMediator

Source: `src/security/mediator.py` (317 lines)

The entry point for all tool call interception. It normalizes heterogeneous framework tool calls into a canonical format.

**ActionCategory classification:**

```python
class ActionCategory(str, Enum):
    FORBIDDEN = "forbidden"                  # Always blocked regardless of context
    CONTEXT_DEPENDENT_DENY = "context_dependent_deny"  # Blocked unless context clears it
    CONTEXT_DEPENDENT_ALLOW = "context_dependent_allow" # Allowed unless context flags it
    PERMIT = "permit"                        # Always allowed
```

**NormalizedAction:**

```python
@dataclass
class NormalizedAction:
    id: str                          # UUID
    tool_name: str                   # e.g. "shell", "send_email", "http_request"
    tool_args: dict[str, Any]        # Arguments passed to the tool
    agent_id: str
    session_id: str
    user_id: str
    timestamp: datetime
    trigger: str                     # "manual", "cron", "agent"
    runtime: str                     # "mutx"
    raw_action: Any                  # Original framework action for debugging
    input_preview: Optional[str]
    output_preview: Optional[str]
    parent_action_id: Optional[str]  # For sub-actions

    @property
    def action_hash(self) -> str:
        """SHA-256 hash for deduplication and chain integrity."""
        canonical = f"{self.tool_name}:{self.agent_id}:{self.session_id}:{self.timestamp.isoformat()}"
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

**ToolSchema and ParameterConstraint:**

```python
@dataclass
class ParameterConstraint:
    name: str
    type: str                        # "string", "number", "boolean", "array", "object"
    required: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    allowed_values: Optional[list[str]] = None

@dataclass
class ToolSchema:
    tool_name: str
    description: str = ""
    parameters: list[ParameterConstraint]
    category: str = "general"
    risk_level: str = "low"
    requires_approval: bool = False
    approval_timeout_seconds: int = 300
```

The ActionMediator maintains a registry of tool schemas:

```python
class ActionMediator:
    def __init__(self):
        self._tool_schemas: dict[str, ToolSchema] = {}
        self._interceptors: list[callable] = []

    def register_tool(self, schema: ToolSchema) -> None:
        self._tool_schemas[schema.tool_name] = schema

    def intercept(self, tool_name, tool_args, agent_id, session_id, ...) -> NormalizedAction:
        action = NormalizedAction(tool_name=tool_name, tool_args=tool_args, ...)
        # Run registered interceptors
        for interceptor in self._interceptors:
            interceptor(action)
        return action

    def categorize(self, action: NormalizedAction) -> ActionCategory:
        """Static categorization based on tool schema, without session context."""
        schema = self._tool_schemas.get(action.tool_name)
        if schema is None:
            return ActionCategory.CONTEXT_DEPENDENT_ALLOW
        if schema.risk_level == "critical":
            return ActionCategory.FORBIDDEN
        if schema.requires_approval:
            return ActionCategory.CONTEXT_DEPENDENT_DENY
        ...
```

### ContextAccumulator

Source: `src/security/context.py` (388 lines)

Accumulates session state throughout an agent's execution to enable context-aware policy evaluation.

**IntentSignal:**

```python
class IntentSignal(str, Enum):
    ALIGNED = "aligned"
    DRIFT_SUSPECTED = "drift_suspected"
    DRIFT_CONFIRMED = "drift_confirmed"
    UNKNOWN = "unknown"
```

**ActionRecord:**

```python
@dataclass
class ActionRecord:
    id: str
    tool_name: str
    tool_args: dict[str, Any]
    action_hash: str
    timestamp: datetime
    effect: str                     # "PERMIT", "DENY", "MODIFY", "DEFER"
    decision_reason: str
    output_preview: Optional[str]
    error: Optional[str]
```

**DataAccess:**

```python
@dataclass
class DataAccess:
    resource_type: str
    resource_id: str
    access_time: datetime
    access_type: str                # "read", "write", "delete"
    sensitive: bool = False
```

**SessionContext:**

```python
@dataclass
class SessionContext:
    session_id: str
    agent_id: str
    user_id: str
    workspace_id: str
    original_request: str           # The user's initial prompt
    stated_intent: str              # Extracted goal
    intent_signals: list[IntentSignal]
    actions: list[ActionRecord]
    data_accessed: list[DataAccess]
    tool_call_count: int
    error_count: int
    denied_count: int
    last_action_timestamp: Optional[datetime]
    last_action_tool: Optional[str]
    metadata: dict[str, Any]

    @property
    def action_hashes(self) -> list[str]:
        return [a.action_hash for a in self.actions]

    @property
    def recent_tool_sequence(self) -> list[str]:
        return [a.tool_name for a in self.actions[-10:]]

    @property
    def session_duration_seconds(self) -> float:
        return (self.updated_at - self.created_at).total_seconds()
```

**ContextAccumulator operations:**

```python
class ContextAccumulator:
    def __init__(self):
        self._sessions: dict[str, SessionContext] = {}
        self._max_history: int = 1000

    def create_session(self, session_id, agent_id, ..., original_request, stated_intent):
        context = SessionContext(session_id=session_id, ...)
        self._sessions[session_id] = context
        return context

    def record_action(self, session_id, action, effect, ...):
        context = self._sessions[session_id]
        record = ActionRecord(id=action.id, tool_name=action.tool_name, ...)
        context.actions.append(record)
        context.tool_call_count += 1

    def record_data_access(self, session_id, resource_type, resource_id, ...):
        context.data_accessed.append(DataAccess(...))

    def evaluate_intent(self, context) -> IntentSignal:
        """Evaluate whether the session's recent actions align with stated intent."""
        # Examines tool sequence, data access patterns, and denied count
```

### PolicyEngine

Source: `src/security/policy.py` (465 lines)

Evaluates NormalizedAction against policy rules AND session context.

**PolicyDecision:**

```python
class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"     # Strip/redact parameters before execution
    DEFER = "defer"       # Require human approval
```

**PolicyRule:**

```python
@dataclass
class PolicyRule:
    id: str
    name: str
    enabled: bool = True
    priority: int = 100             # Lower = evaluated first

    tool_pattern: str = "*"         # Glob matching against tool_name
    agent_pattern: str = "*"        # Glob matching against agent_id
    session_pattern: str = "*"      # Glob matching against session_id

    action: PolicyDecision = PolicyDecision.DENY
    reason: str = ""
    require_context_alignment: bool = False

    rate_limit_per_minute: Optional[int] = None
    rate_limit_per_session: Optional[int] = None

    def matches(self, action: NormalizedAction, context=None) -> bool:
        if not self.enabled: return False
        if not self._matches_pattern(self.tool_pattern, action.tool_name): return False
        if not self._matches_pattern(self.agent_pattern, action.agent_id): return False
        if not self._matches_pattern(self.session_pattern, action.session_id): return False
        if context and self.require_context_alignment:
            latest_signal = context.intent_signals[-1]
            if latest_signal in (DRIFT_CONFIRMED, DRIFT_SUSPECTED):
                return True
        return True
```

Pattern matching supports glob-style wildcards: `*` (any), `prefix*`, `*suffix`, `*contains*`.

**PolicySet:**

```python
@dataclass
class PolicySet:
    id: str
    name: str
    rules: list[PolicyRule]
    default_decision: PolicyDecision = PolicyDecision.DENY

    def add_rule(self, rule: PolicyRule):
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)  # Priority order
```

**PolicyDecisionResult:**

```python
@dataclass
class PolicyDecisionResult:
    decision: PolicyDecision
    rule_id: Optional[str]
    rule_name: Optional[str]
    reason: str
    modifications: Optional[dict[str, Any]] = None   # For MODIFY decisions
    timestamp: datetime
    session_id: Optional[str]
    action_id: Optional[str]

    @property
    def is_allowed(self) -> bool: return self.decision == PolicyDecision.ALLOW
    @property
    def is_denied(self) -> bool: return self.decision == PolicyDecision.DENY
    @property
    def is_deferred(self) -> bool: return self.decision == PolicyDecision.DEFER
    @property
    def is_modified(self) -> bool: return self.decision == PolicyDecision.MODIFY
```

**Evaluation:**

```python
class PolicyEngine:
    def evaluate(
        self, action: NormalizedAction,
        context: Optional[SessionContext] = None,
    ) -> PolicyDecisionResult:
        for policy_set in self._policies.values():
            if not policy_set.enabled:
                continue
            for rule in policy_set.rules:
                if rule.matches(action, context):
                    rule.record_hit()
                    if rule.action == PolicyDecision.ALLOW:
                        return PolicyDecisionResult(
                            decision=PolicyDecision.ALLOW,
                            rule_id=rule.id, reason=rule.reason,
                        )
                    elif rule.action == PolicyDecision.DENY:
                        return PolicyDecisionResult(
                            decision=PolicyDecision.DENY,
                            rule_id=rule.id, reason=rule.reason,
                        )
                    elif rule.action == PolicyDecision.MODIFY:
                        return PolicyDecisionResult(
                            decision=PolicyDecision.MODIFY,
                            modifications=self._compute_modifications(action, rule),
                        )
                    elif rule.action == PolicyDecision.DEFER:
                        return PolicyDecisionResult(
                            decision=PolicyDecision.DEFER,
                            rule_id=rule.id, reason=rule.reason,
                        )

        # No rule matched — apply default decision
        return PolicyDecisionResult(decision=self._default_decision, reason="No matching rule")
```

### ApprovalService

Source: `src/security/approvals.py` (395 lines)

**ApprovalRequest lifecycle:**

```python
class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
```

```python
@dataclass
class ApprovalRequest:
    id: str                              # UUID
    token: str                           # secrets.token_urlsafe(16) — one-time approval URL
    action: Optional[NormalizedAction]
    context: Optional[SessionContext]
    status: ApprovalStatus = PENDING
    created_at: datetime
    expires_at: datetime                 # Default: now + 5 minutes
    decided_at: Optional[datetime]
    decided_by: Optional[str]
    tool_name: str
    tool_args: dict[str, Any]
    agent_id: str
    session_id: str
    user_id: str
    reason: str
    reviewers: list[str]
    reviewer_comments: list[str]
    escalation_enabled: bool = True
    escalation_timeout_minutes: int = 10
    escalated_to: Optional[str]
    metadata: dict[str, Any]

    @property
    def remaining_seconds(self) -> int:
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))
```

**State transitions:**

```
PENDING ──── approve(reviewer, comment) ────→ APPROVED
       ──── deny(reviewer, reason) ─────────→ DENIED
       ──── cancel() ──────────────────────→ CANCELLED
       ──── (timeout) check_expired() ─────→ EXPIRED
```

```python
def approve(self, reviewer: str, comment: str = "") -> bool:
    if not self.is_pending: return False
    self.status = ApprovalStatus.APPROVED
    self.decided_at = datetime.now(timezone.utc)
    self.decided_by = reviewer
    if comment:
        self.reviewer_comments.append(f"[APPROVED by {reviewer}]: {comment}")
    return True
```

**ApprovalService operations:**

```python
class ApprovalService:
    def request_approval(
        self, action, context=None, reason="",
        reviewers=None, timeout_minutes=None, metadata=None,
    ) -> ApprovalRequest:
        """Create approval request. Default timeout: 5 minutes."""

    def approve(self, token, reviewer, comment="") -> Optional[ApprovalRequest]:
        """Approve by token. Returns None if token invalid or not pending."""

    def deny(self, token, reviewer, reason="") -> Optional[ApprovalRequest]:
        """Deny by token."""

    def check_expired(self) -> list[ApprovalRequest]:
        """Check all pending requests and mark expired ones."""

    def get_pending_for_reviewer(self, reviewer_id) -> list[ApprovalRequest]:
        """Get pending requests for a specific reviewer."""
```

### ReceiptGenerator

Source: `src/security/receipts.py` (407 lines)

**ActionReceipt:**

```python
@dataclass
class ActionReceipt:
    receipt_version: str              # Canonical receipt schema version
    receipt_id: str                    # UUID
    action_id: str
    action_hash: str                   # SHA-256 of the action
    session_id: str
    tool_name: str
    tool_args: dict[str, Any]
    agent_id: str
    user_id: str
    policy_decision: str               # "allow", "deny", "modify", "defer"
    policy_rule_id: Optional[str]
    policy_rule_name: Optional[str]
    decision_reason: str
    outcome: str                       # "executed", "blocked", "error"
    outcome_detail: str
    timestamp: datetime
    duration_ms: Optional[int]
    session_snapshot: Optional[dict]   # Snapshot of SessionContext at decision time
    prior_action_hashes: list[str]     # Chain integrity: hashes of previous receipts
    signature: Optional[str]           # Mandatory on generated receipts
    signed_by: Optional[str]           # Embedded Ed25519 public key
    signature_algorithm: Optional[str] # "Ed25519"
    signing_key_id: Optional[str]      # Stable operator key identifier
    metadata: dict[str, Any]

    def compute_hash(self) -> str:
        """SHA-256 of the JSON-serialized receipt."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()
```

**ReceiptChain:**

```python
@dataclass
class ReceiptChain:
    chain_id: str
    session_id: str
    root_action_hash: Optional[str]
    receipts: list[ActionReceipt]

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify prior_action_hashes linkage between consecutive receipts."""
        errors = []
        for i, receipt in enumerate(self.receipts):
            if i > 0:
                prev_receipt = self.receipts[i - 1]
                if receipt.prior_action_hashes:
                    if prev_receipt.action_hash not in receipt.prior_action_hashes:
                        errors.append(f"Receipt {i}: prior action hash mismatch")
        return len(errors) == 0, errors
```

**ReceiptGenerator:**

```python
class ReceiptGenerator:
    def generate(
        self, action, context, decision, outcome,
        outcome_detail="", duration_ms=None, metadata=None,
    ) -> ActionReceipt:
        """Create and sign a receipt binding action, context, decision, and outcome."""
        receipt = ActionReceipt(
            action_id=action.id,
            action_hash=action.action_hash,
            prior_action_hashes=context.action_hashes if context else [],
            session_snapshot=context.to_dict() if context else None,
            ...
        )
        self.sign(receipt)
        # Add the signed receipt to the chain
        chain = self._chains.get(action.session_id)
        if chain is None:
            chain = ReceiptChain(session_id=action.session_id)
            self._chains[action.session_id] = chain
        chain.add_receipt(receipt)
        return receipt
```

### AARMComplianceChecker

Source: `src/security/compliance.py`

The historical class and `/v1/security/compliance` route are retained for API
compatibility. They now return a local capability-gap assessment against the
current AARM model; they do not certify conformance.

| Requirement | Level | Current requirement | MUTX status |
|---|---|---|---|
| R1 | MUST | Pre-execution interception, blocking/deferral, and fail-closed behavior | Partial; not demonstrated |
| R2 | MUST | Accumulated actions, data classifications, and original request | Partial; not demonstrated |
| R3 | MUST | Static and contextual policy evaluation with mandatory deferral conditions | Partial; not demonstrated |
| R4 | MUST | Distinct ALLOW, DENY, MODIFY, STEP_UP, and DEFER decisions | Partial; STEP_UP is missing as a distinct decision |
| R5 | MUST | Complete signed, offline-verifiable receipts for every decision | Partial; mandatory Ed25519 signing is implemented, full schema/path proof remains |
| R6 | MUST | Multi-level trusted identity binding and preservation | Partial; not demonstrated |
| R7 | SHOULD | Calibrated cumulative semantic-distance tracking | Gap; current heuristic is not sufficient |
| R8 | SHOULD | Structured near-real-time telemetry and historical export | Partial; not demonstrated |
| R9 | SHOULD | Just-in-time operation-scoped credentials | Gap; not demonstrated |

See [`docs/legal/aarm-alignment.md`](legal/aarm-alignment.md) for exact evidence,
upstream verification links, technical gaps, and organizational conditions.

```python
@dataclass
class ConformanceResult:
    requirement_id: str               # "R1" through "R9"
    level: ConformanceLevel           # MUST or SHOULD
    description: str
    satisfied: bool
    details: str
    timestamp: datetime

@dataclass
class AARMComplianceReport:
    version: str = "2026-03-26"
    overall_satisfied: bool = True    # False if any MUST requirement fails
    results: list[ConformanceResult]

    def add_result(self, result):
        self.results.append(result)
        if not result.satisfied and result.level == ConformanceLevel.MUST:
            self.overall_satisfied = False
```

## 9. Faramesh Supervisor

Source: `src/api/services/faramesh_supervisor.py` (637 lines)

### Process Lifecycle State Machine

```python
class SupervisionState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    RESTARTING = "restarting"
```

State transitions:

```
STOPPED ──start()──→ STARTING ──process spawned──→ RUNNING
RUNNING ──stop()──→ STOPPING ──process exits──→ STOPPED
RUNNING ──process crashes──→ FAILED ──auto_restart──→ RESTARTING ──→ STARTING
RESTARTING ──max_restarts exceeded──→ FAILED (terminal)
```

### SupervisedAgent

```python
@dataclass
class SupervisedAgent:
    agent_id: str
    command: list[str]
    env: dict[str, str]
    launch_profile: Optional[str]
    state: SupervisionState = STOPPED
    process: Optional[subprocess.Popen]
    pid: Optional[int]
    restart_count: int = 0
    last_exit_code: Optional[int]
    last_start_at: Optional[datetime]
    last_stop_at: Optional[datetime]
    faramesh_policy: Optional[str]
```

### Framework Auto-Patches

Faramesh supports 13 frameworks with runtime auto-patching of tool calls:

LangGraph, CrewAI, AutoGen, Pydantic AI, LlamaIndex, Hayject, AgentKit, AgentOps, Braintrust, Helicone, Weave, AG2, Mem0

When `faramesh run -- <command>` is used, it intercepts tool calls from these frameworks and routes them through the MUTX governance pipeline.

### Unix Domain Socket Communication

```python
FAREMESH_SOCKET_PATH = _default_faramesh_socket_path()
```

Faramesh communicates with supervised processes via Unix domain socket for low-latency governance checks. `_default_faramesh_socket_path()` honors `FAREMESH_SOCKET_PATH`, then `$XDG_RUNTIME_DIR/faramesh.sock`, then `~/.mutx/run/faramesh.sock`.

### SupervisionConfig

```python
@dataclass
class SupervisionConfig:
    faramesh_bin: Optional[str]
    policy_path: Optional[str]
    allowed_commands: tuple[str, ...]       # Executable basenames allowed
    allowed_env_keys: tuple[str, ...]       # Env var names allowed
    allow_direct_commands: bool = False      # Must use profiles if False
    profiles: dict[str, object]
    allowed_policy_dir: Optional[str]        # Bounds user-selectable FPL files
    socket_path: str = FAREMESH_SOCKET_PATH
    auto_restart: bool = True
    max_restarts: int = 3
    restart_delay: float = 5.0
    health_check_interval: float = 30.0
    shutdown_timeout: float = 10.0
```

### Input Validation

```python
@staticmethod
def _normalize_command(command: list[str]) -> list[str]:
    if not command:
        raise SupervisionValidationError("command must contain at least one executable")
    for part in command:
        if not isinstance(part, str):
            raise SupervisionValidationError("command entries must be strings")
        if not part.strip():
            raise SupervisionValidationError("command entries must not be empty")
```

### API Routes

Source: `src/api/routes/governance_supervision.py`

```
POST /v1/runtime/governance/supervised/start   — Launch supervised agent
POST /v1/runtime/governance/supervised/stop     — Stop supervised agent
GET  /v1/runtime/governance/supervised/status   — Get supervision status
GET  /v1/runtime/governance/supervised/profiles — List available launch profiles
```

All routes require `get_current_internal_user` — restricted to verified users on `settings.internal_user_email_domains` (default: `["mutx.dev"]`).

## 10. Credential Broker

Source: `src/api/services/credential_broker.py` (863 lines)

### Backend Implementations

6 credential backend providers, all implementing the `CredentialProvider` ABC:

```python
class CredentialProvider(ABC):
    def __init__(self, config: BackendConfig):
        self.config = config
        self._cache: dict[str, tuple[Credential, datetime]] = {}

    @abstractmethod
    async def get_secret(self, path: str) -> Optional[Credential]: ...
    @abstractmethod
    async def list_secrets(self) -> list[str]: ...
    @abstractmethod
    async def health_check(self) -> bool: ...

    def _is_cache_valid(self, path: str) -> bool:
        _, cached_at = self._cache[path]
        return datetime.now(timezone.utc) - cached_at < self.config.ttl
```

| Backend | Class | Auth Method | API |
|---|---|---|---|
| HashiCorp Vault | `VaultProvider` | X-Vault-Token header | HTTP GET `/v1/{mount}/{path}` |
| AWS Secrets Manager | `AWSSecretsProvider` | SigV4 | boto3/HTTP |
| GCP Secret Manager | `GCPSecretProvider` | Service account | HTTP GET via google-cloud-secret-manager |
| Azure Key Vault | `AzureKVProvider` | Azure AD token | HTTP GET via azure-keyvault |
| 1Password | `OnePasswordProvider` | Service account token | HTTP GET via 1Password Connect |
| Infisical | `InfisicalProvider` | Machine identity | HTTP GET via Infisical API |

### Credential Dataclass

```python
@dataclass
class Credential:
    name: str
    backend: str
    path: str
    value: str                       # Ephemeral — only in memory
    expires_at: Optional[datetime]
    metadata: dict = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None: return False
        return datetime.now(timezone.utc) >= self.expires_at
```

### BackendConfig

```python
@dataclass
class BackendConfig:
    name: str
    backend: CredentialBackend
    path: str
    ttl: timedelta = timedelta(minutes=15)   # Cache TTL
    config: dict = field(default_factory=dict)
    is_active: bool = True
```

### On-Demand Injection Flow

1. Agent requests a credential via the API.
2. `CredentialBroker` resolves the backend, calls `get_secret(path)`.
3. `get_secret()` checks cache first (TTL-based).
4. If cache miss, calls the backend API.
5. The secret value is decrypted via `decrypt_secret_value()` from `src/api/security`.
6. The credential is injected as an ephemeral environment variable for the tool call.
7. After the tool call completes, the env var is cleared.

### Health Checking

Each backend implements `health_check()` which returns a boolean. The broker tracks `is_active` and health status per backend.

### API Surface

Source: `src/api/routes/governance_credentials.py`

```
GET  /v1/governance/credentials/backends       — List registered backends
POST /v1/governance/credentials/retrieve        — Retrieve a credential
POST /v1/governance/credentials/register        — Register a backend
GET  /v1/governance/credentials/health          — Backend health status
```

## 11. SPIFFE Identity

Source: `src/api/services/spiffe_identity.py` (256 lines)

### Identity Sources

```python
class IdentitySource(str, Enum):
    SPIRE = "spire"           # Production: SPIRE agent via Workload API
    KUBERNETES = "kubernetes"  # K8s service account tokens
    ENVIRONMENT = "environment"  # Dev: environment variables
    STATIC = "static"          # Testing: static configuration
```

### AgentIdentity

```python
@dataclass
class AgentIdentity:
    spiffe_id: str              # e.g. spiffe://mutx.dev/agent/{agent_id}
    trust_domain: str           # e.g. "mutx.dev"
    agent_id: str
    certificate: str            # X.509 SVID certificate
    private_key: str            # X.509 SVID private key
    expires_at: Optional[datetime]
    source: IdentitySource = IdentitySource.SPIRE
```

### SPIRE Integration

```python
@dataclass
class SPIREConfig:
    server_address: str = "localhost:8081"
    socket_path: str = field(default_factory=_default_spire_socket_path)
    trust_bundle_path: Optional[str]
    agent_config_path: Optional[str]
    workload_api_path: str = field(default_factory=_default_spire_socket_path)
    spire_bin: Optional[str]
```

`SPIFFEIdentityProvider.fetch_svid()` fetches X.509 SVIDs from the SPIRE agent via its Workload API. When SPIRE is not available, it falls back to Kubernetes service account tokens, environment variables, or static configuration.

### mTLS

Agent identities (X.509 SVIDs) are used to establish mutual TLS connections between agents and governance services. The SPIFFE trust bundle is used for certificate verification.

## 12. Self-Healing

Source: `src/api/services/self_healer.py` (718 lines), `src/api/services/monitor.py` (201 lines), `src/api/services/monitoring.py` (309 lines)

### RecoveryAction

```python
class RecoveryAction(str, Enum):
    RESTART = "restart"
    ROLLBACK = "rollback"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    RECREATE = "recreate"
    NONE = "none"
```

### RecoveryConfig

```python
@dataclass
class RecoveryConfig:
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    health_check_interval_seconds: int = 10
    health_check_timeout_seconds: float = 5.0
    max_consecutive_failures: int = 3
    rollback_on_failure: bool = True
    enable_auto_restart: bool = True
    enable_auto_rollback: bool = True
    min_recovery_interval_seconds: float = 60.0
```

### RecoveryStatus

```python
class RecoveryStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
```

### RecoveryRecord

```python
@dataclass
class RecoveryRecord:
    record_id: str
    agent_id: str
    action: RecoveryAction
    status: RecoveryStatus
    started_at: datetime
    completed_at: Optional[datetime]
    previous_version: Optional[str]
    new_version: Optional[str]
    error_message: Optional[str]
    recovery_time_seconds: float = 0.0
    metadata: Dict[str, Any]
```

### VersionManager

```python
class VersionManager:
    def __init__(self, max_versions: int = 10):
        self._agent_versions: Dict[str, deque] = {}  # Bounded version history
        self._current_versions: Dict[str, str]
        self._stable_versions: Dict[str, str]          # Last known-good version

    def mark_stable_version(self, agent_id, version=None):
        """Mark current version as stable after health check passes."""
```

### Background Monitor

Source: `src/api/services/monitor.py`

```python
@dataclass
class MonitorRuntimeState:
    started_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
    consecutive_failures: int = 0

    def mark_success(self):
        self.last_success_at = datetime.now(timezone.utc)
        self.last_error = None
        self.consecutive_failures = 0

    def mark_error(self, error):
        self.last_error_at = datetime.now(timezone.utc)
        self.last_error = str(error)
        self.consecutive_failures += 1
```

### Health Monitoring Thresholds

Source: `src/api/services/monitoring.py`

```python
HEARTBEAT_THRESHOLD_SECONDS = 60   # Agent is stale after 60s without heartbeat
STALE_THRESHOLD_SECONDS = 120      # Agent is considered failed after 120s
HEAL_THRESHOLD_SECONDS = 30        # Wait 30s before attempting recovery
```

### Webhook Emission

```python
async def _emit_agent_status_webhook(session, *, user_id, agent_id, old_status, new_status, agent_name):
    await trigger_agent_status_event(session, user_id, agent_id, old_status, new_status, agent_name)

async def _emit_deployment_webhook(session, *, user_id, deployment_id, agent_id, event_type, status):
    await trigger_deployment_event(session, user_id, deployment_id, agent_id, event_type=event_type, status=status)
```

Webhooks are emitted on status transitions. Failures are logged but do not block the monitoring loop:

```python
try:
    await trigger_agent_status_event(...)
except Exception:
    logger.exception("Monitor webhook emission failed for agent.status")
```

### Deployment Event Recording

```python
def _record_deployment_event(session, deployment, *, event_type, status, error_message=None):
    session.add(DeploymentEvent(
        deployment_id=deployment.id,
        event_type=event_type,
        status=status,
        node_id=deployment.node_id,
        error_message=error_message,
    ))
```

This is an append-only event log. Events are never modified or deleted.

### Recovery Flow

The monitor checks agent health on a configurable interval:

1. Query all agents with status `RUNNING`.
2. For each agent, check if `last_heartbeat` exceeds `STALE_THRESHOLD_SECONDS`.
3. If stale, attempt recovery via `SelfHealingService`:
   - Skip if agent was explicitly stopped (`status == STOPPED`).
   - Set status back to `RUNNING` and log a recovery event.
   - Register health check callbacks.
   - If consecutive failures exceed `max_consecutive_failures`, attempt `ROLLBACK` to previous stable version.

## 13. Observability

### OpenTelemetry Integration

Source: `src/api/main.py:469-480`

```python
try:
    from src.api.telemetry.telemetry import setup_telemetry
    setup_telemetry("mutx-api")

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    pass  # OTel packages not installed — tracing disabled
```

Span naming convention: `mutx.<operation>` (e.g., `mutx.agent.create`, `mutx.policy.evaluate`).

Standard attributes: `agent.id`, `session.id`, `trace.id`.

### Audit Log Service

Source: `src/api/services/audit_log.py` (464 lines)

**Storage:** aiosqlite-backed append-only store.

```python
DATABASE_PATH = "audit.db"
AUDIT_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
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
```

**Indexes:**

```python
AUDIT_TABLE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_audit_agent_id ON audit_events(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_session_id ON audit_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_trace_id ON audit_events(trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type)",
]
```

**Event types:**

```python
class AuditEventType(str, Enum):
    AGENT_START = "AGENT_START"
    LLM_CALL = "LLM_CALL"
    TOOL_CALL = "TOOL_CALL"
    POLICY_CHECK = "POLICY_CHECK"
    GUARDRAIL_TRIGGER = "GUARDRAIL_TRIGGER"
    AGENT_END = "AGENT_END"
```

**OTel trace context extraction:**

```python
def _get_otel_trace_context() -> tuple[str | None, str | None]:
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span is None: return None, None
        ctx = span.get_span_context()
        if ctx is None or not ctx.is_valid: return None, None
        trace_id = format(ctx.trace_id, "032x")
        span_id = format(ctx.span_id, "016x")
        return trace_id, span_id
    except Exception:
        return None, None
```

This is called when logging audit events to correlate them with distributed traces.

### Observability API

Source: `src/api/routes/observability.py` (580 lines)

Based on a local adaptation of the agent-run observability schemas. The current
upstream package is quarantined pending maintainer security review and is not a
runtime dependency.

**Models:**

```
MutxRun          — Top-level run container (status, input/output, error)
MutxStep         — Individual step within a run (tool calls, LLM calls)
MutxCost         — Token usage and cost tracking per step
MutxProvenance   — Provenance chain for a run (data lineage)
MutxEvalResult   — Evaluation result for a run (quality metrics)
```

**Routes:**

```
POST /v1/observability/runs              — Create/report a MutxRun
GET  /v1/observability/runs              — List runs with filters
GET  /v1/observability/runs/{id}         — Get run detail with steps
POST /v1/observability/runs/{id}/steps   — Add steps to a run
GET  /v1/observability/runs/{id}/eval    — Get eval for a run
POST /v1/observability/runs/{id}/eval    — Submit eval result
GET  /v1/observability/runs/{id}/provenance — Get provenance for a run
```

**Run status lifecycle:**

```
running → completed | failed | cancelled
```

**Cost tracking per step:**

```python
MutxCost:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int
    cost_usd: float
    model: str
```

### Prometheus Metrics

Full metrics catalog at `/metrics`:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | method, path, status | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, path | Request latency |
| `http_request_size_bytes` | Histogram | method, path | Request body size |
| `http_response_size_bytes` | Histogram | method, path | Response body size |
| `http_connections_active` | Gauge | — | Active HTTP connections |
| `db_pool_size` | Gauge | — | Connection pool size |
| `db_pool_acquired` | Gauge | — | Acquired connections |
| `db_pool_overflow` | Gauge | — | Overflow connections |
| `db_query_duration_seconds` | Histogram | — | Query latency |
| `mutx_agents_total` | Gauge | — | Total agents |
| `mutx_agents_active` | Gauge | — | Active agents |
| `mutx_agent_tasks_total` | Counter | status | Task counts |
| `mutx_agent_task_duration_seconds` | Histogram | — | Task duration |
| `mutx_deployments_total` | Gauge | — | Total deployments |
| `mutx_deployments_running` | Gauge | — | Running deployments |
| `mutx_deployments_by_status` | Gauge | status | Deployments per status |
| `mutx_queue_size` | Gauge | — | Task queue size |
| `mutx_api_calls_total` | Counter | endpoint | API call counts |
| `mutx_errors_total` | Counter | type, endpoint | Error counts |
| `mutx_runtime_schema_repairs_applied` | Gauge | — | Schema repairs flag |
| `mutx_runtime_schema_repairs_total` | Gauge | — | Schema repairs count |
| `mutx_background_monitor_consecutive_failures` | Gauge | — | Monitor failure count |

## 14. Policy Store

Source: `src/api/services/policy_store.py` (149 lines)

### In-Memory Repository

```python
class Rule(BaseModel):
    type: Literal["block", "allow", "warn"]
    pattern: str
    action: str
    scope: Literal["input", "output", "tool"]

class Policy(BaseModel):
    id: str
    name: str
    rules: list[Rule]
    enabled: bool
    version: int
    created_at: datetime | None
    updated_at: datetime | None
```

```python
class PolicyStore:
    def __init__(self):
        self._policies: dict[str, Policy] = {}
        self._lock = asyncio.Lock()
        self._reload_clients: set[object] = set()
```

All CRUD operations are protected by `asyncio.Lock()` for thread safety:

```python
async def upsert_policy(self, policy: Policy) -> Policy:
    async with self._lock:
        now = datetime.now(timezone.utc)
        existing = self._policies.get(policy.name)
        if existing:
            stored = Policy(
                id=existing.id,
                version=existing.version + 1,  # Auto-increment version
                created_at=existing.created_at,
                updated_at=now,
                ...
            )
        else:
            stored = Policy(version=1, created_at=now, updated_at=now, ...)
        self._policies[policy.name] = stored
    await self._notify_reload(policy.name)
    return stored
```

### SSE-Based Hot-Reload

```python
async def _notify_reload(self, policy_name: str) -> None:
    """Push notification to registered SSE clients."""
    for client in self._reload_clients:
        try:
            await client.send({"event": "policy_updated", "data": policy_name})
        except Exception:
            self._reload_clients.discard(client)

def register_reload_client(self, client) -> None:
    self._reload_clients.add(client)

def unregister_reload_client(self, client) -> None:
    self._reload_clients.discard(client)
```

### API

Source: `src/api/routes/policies.py`

```
GET    /v1/policies          — List all policies
POST   /v1/policies          — Create a policy
GET    /v1/policies/{name}   — Get a specific policy
PUT    /v1/policies/{name}   — Update a policy
DELETE /v1/policies/{name}   — Delete a policy
GET    /v1/policies/stream   — SSE endpoint for hot-reload notifications
```

## 15. SDK Architecture

### MutxClient

The top-level SDK client is httpx-based, exposing 26 resource modules that map to the API route families.

### MutxAgentClient

Source: `sdk/mutx/agent_runtime.py` (937 lines)

```python
class MutxAgentClient:
    def __init__(
        self,
        mutx_url="https://api.mutx.dev",
        api_key=None,
        agent_id=None,
        timeout=30.0,
        guardrail_middleware=None,
        policy_client=None,
    ):
        self._http = httpx.Client(
            base_url=self.mutx_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=timeout,
        )
        self._guardrail = guardrail_middleware
        self._policy = policy_client
```

**Operations:**

| Method | Description |
|---|---|
| `register()` | Register agent with MUTX, receive agent_id and api_key |
| `start_heartbeat(interval=30)` | Background thread sending periodic heartbeats |
| `report_metrics(metrics)` | Send CPU, memory, uptime, request counts |
| `poll_commands()` | Long-poll for pending commands from MUTX |
| `stop()` | Graceful shutdown: stop heartbeat, cancel tasks |

### GuardrailMiddleware

Source: `sdk/mutx/guardrails.py` (371 lines)

```python
@dataclass
class GuardrailResult:
    passed: bool
    triggered_rule: str | None
    action: Literal["block", "allow", "warn"]
    message: str
```

**PIIBlocklistGuardrail:**

```python
class PIIBlocklistGuardrail:
    SSN_PATTERN = r"\b\d{3}-\d{2}-\d{4}\b"
    CREDIT_CARD_PATTERN = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
    EMAIL_PATTERN = r"\b[\w.-]+@[\w.-]+\.\w+\b"
```

**ToxicityGuardrail:** HTTP-based toxicity detection service.

**RegexGuardrail:** Custom pattern matching with user-defined regex patterns.

**GuardrailMiddleware:** Composites multiple guardrails:

```python
class GuardrailMiddleware:
    def __init__(self):
        self._input_guardrails: list[InputGuardrail] = []
        self._output_guardrails: list[OutputGuardrail] = []

    def add_input_guardrail(self, guardrail): ...
    def add_output_guardrail(self, guardrail): ...

    def check_input(self, text, context) -> GuardrailResult:
        for guardrail in self._input_guardrails:
            result = guardrail.check(text, context)
            if not result.passed:
                return result
        return GuardrailResult(passed=True, action="allow", message="OK")
```

### MutxPolicyClient

Source: `sdk/mutx/policy.py` (207 lines)

```python
DEFAULT_GUARDRAIL_PROFILES = {
    "strict": ["pii_block", "toxicity_check"],
    "standard": ["pii_block"],
    "permissive": [],
}

class MutxPolicyClient:
    def __init__(self, api_url, policy_name, api_key):
        self._http = httpx.Client(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=30.0,
        )

    def start_watching(self, poll_interval=30):
        """Start polling for policy changes."""

    def stop_watching(self):
        """Stop the watch loop."""

    def get_current_rules(self) -> list[Rule]:
        """Get current policy rules."""
```

### Telemetry Module

Source: `sdk/mutx/telemetry.py`

```python
def init_telemetry(service_name: str):
    """Initialize OTel tracing and metrics for the SDK."""

@contextmanager
def span(name: str, attributes=None):
    """Create a span context manager."""

def trace_context() -> dict:
    """Extract current trace context for propagation."""
```

## 16. CLI and TUI

### CLI

Source: `cli/commands/` (23 Click command groups)

23 command groups map 1:1 to API route families:

```
mutx agents      → /v1/agents
mutx deployments → /v1/deployments
mutx auth        → /v1/auth
mutx api-keys    → /v1/api-keys
mutx config      → settings
mutx security    → /v1/security
mutx governance  → /v1/runtime/governance/*
mutx observability → /v1/observability
mutx policies    → /v1/policies
mutx approvals   → /v1/approvals
mutx audit       → /v1/audit
mutx webhooks    → /v1/webhooks
mutx runtime     → /v1/runtime
mutx usage       → /v1/usage
mutx budgets     → /v1/budgets
mutx scheduler   → /v1/scheduler
mutx agent       → single agent operations
mutx deploy      → deployment shortcuts
mutx assistant   → /v1/assistant
mutx clawhub     → /v1/clawhub
mutx onboard     → /v1/onboarding
mutx setup       → initial configuration
mutx update      → self-update
mutx doctor      → diagnostic checks
```

### TUI

Source: `cli/commands/tui.py`, `cli/tui/`

A Textual-based cockpit interface with components:

- `app.py` — Textual Application subclass
- `cockpit.py` — Main cockpit layout
- `screens.py` — Screen definitions (agents, deployments, metrics, logs)
- `renderers.py` — Custom renderers for agent status, deployment events
- `models.py` — TUI-specific data models

Launched via `mutx tui`.

## 17. Infrastructure

### Docker Compose

Source: `infrastructure/docker/docker-compose.yml` (220 lines)

9 services:

| Service | Image | Purpose | Health Check |
|---|---|---|---|
| postgres | postgres:16-alpine | Primary database | `pg_isready -U mutx` |
| redis | redis:7-alpine | Cache and queue | `redis-cli ping` |
| migrate | Custom | Alembic migration runner | One-shot, `service_completed_successfully` |
| api | Custom (Dockerfile.api) | FastAPI backend | `curl -f http://localhost:8000/ready` |
| frontend | Custom (Dockerfile.frontend) | Next.js dashboard | `curl -f http://localhost:3000` |
| prometheus | prom/prometheus:v2.54.1 | Metrics collection | — |
| grafana | grafana/grafana:11.2.2 | Dashboards | — |
| otel-collector | otel/opentelemetry-collector:0.102.1 | Trace/metric forwarding | — |
| jaeger | jaegertracing/all-in-one:1.57 | Trace visualization | — |

Two networks: `mutx-network` (application) and `otel-network` (observability).

The API service depends on the `migrate` service completing successfully and both `postgres` and `redis` being healthy.

### Kubernetes/Helm

Source: `infrastructure/helm/mutx/`

Helm chart with 12 templates:

```
templates/
  _helpers.tpl
  deployment.yaml
  service.yaml
  ingress.yaml
  configmap.yaml
  hpa.yaml
  tests/test-connection.yaml
```

**values.yaml defaults:**

```yaml
replicaCount: 2
service:
  type: ClusterIP
  port: 8000
ingress:
  className: nginx
  tls:
    enabled: true
autoscaling:
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 75
resources:
  limits: { cpu: 1000m, memory: 1Gi }
  requests: { cpu: 100m, memory: 256Mi }
```

**Environment overlays:**

- `values.yaml` — Base defaults
- `values.dev.yaml` — Development overrides
- `values.staging.yaml` — Staging overrides
- `values.prod.yaml` — Production overrides

### Ansible

Source: `infrastructure/ansible/`

13 playbooks for configuration management. Example playbooks:

- `playbooks/deploy-agent.yml` — Deploy agent to target hosts
- `playbooks/provision.yml` — Provision infrastructure

Requirements defined in `requirements.yml`.

### Monitoring Stack

Source: `infrastructure/monitoring/prometheus/`

- `prometheus.yml` — Scrape configuration
- `alerts.yml` — Alert rules
- `alertmanager.yml` — Alert routing and notification

## 18. What Ships Today

- FastAPI control plane with 32 route modules (141 paths, 181 operations)
- JWT + API key dual authentication with refresh token rotation
- Governance engine: ActionMediator, ContextAccumulator, PolicyEngine, ApprovalService, ReceiptGenerator, AARMComplianceChecker
- Faramesh supervisor with 13 framework auto-patches
- Credential broker with 6 backends (Vault, AWS, GCP, Azure, 1Password, Infisical)
- SPIFFE/SPIRE identity integration
- Self-healing with restart, rollback, scale recovery actions
- Observability: OpenTelemetry traces, Prometheus metrics, aiosqlite audit log
- Policy store with SSE hot-reload
- Python SDK with guardrails, policy client, and telemetry
- CLI with 23 command groups
- Textual TUI cockpit
- Docker Compose development stack (9 services)
- Helm chart with dev/staging/prod overlays
- 17 Alembic migrations
- Runtime schema repair for zero-downtime deployments
- Structured JSON logging with request_id/trace_id correlation
- Prometheus metrics with request/agent/deployment/database gauges and histograms

## 19. Build Roadmap

1. OIDC/JWKS integration for enterprise SSO (Okta, Auth0, Azure AD, Keycloak)
2. WebSocket command streaming (replace polling in SDK)
3. Distributed policy evaluation (multi-node PolicyEngine)
4. Encrypted audit log storage (at-rest encryption for audit.db)
5. Agent sandboxing (container-level isolation per agent)
6. Multi-tenant workspace isolation
7. RBAC with fine-grained permissions (beyond owner/admin)
8. GraphQL API surface alongside REST
9. Agent-to-agent communication governance
10. Cost attribution and billing integration

## 20. Documentation Truth Rule

When this document conflicts with the source code, the source code is correct. When the source code conflicts with the OpenAPI spec, the source code is correct. When the OpenAPI spec conflicts with prose documentation (including this document), the OpenAPI spec is correct.

Hierarchy: **source code > OpenAPI spec (`/openapi.json`) > prose docs**

## 21. Built On

| Component | Technology | License |
|---|---|---|
| Web framework | FastAPI (Starlette) | MIT |
| ORM | SQLAlchemy 2.0 | MIT |
| Async PostgreSQL driver | asyncpg | Apache 2.0 |
| Migration | Alembic | MIT |
| JWT | python-jose | MIT |
| Password hashing | passlib / bcrypt | BSD / Apache 2.0 |
| HTTP client | httpx | BSD |
| CLI | Click | BSD |
| TUI | Textual | MIT |
| Metrics | prometheus_client | Apache 2.0 |
| Tracing | OpenTelemetry SDK | Apache 2.0 |
| Audit storage | aiosqlite | MIT |
| Agent-run schema source | builderz-labs/agent-run | MIT (current package quarantined; local adaptation only) |
| AARM documentation | aarm-dev/docs | MIT, Copyright (c) 2023 Mintlify |
| Faramesh Core and FPL | faramesh/faramesh-core, faramesh/fpl-lang | Core main/FPL main: Apache-2.0; pinned Core `v0.2.0` and historical `v1.2.9`: MPL-2.0 |
| Database | PostgreSQL 16 | PostgreSQL License |
| Cache | Redis 7 | BSD 3-Clause |
| Frontend | Next.js | MIT |
| Container orchestration | Docker, Kubernetes | Apache 2.0 |
| Configuration management | Ansible | GPL 3.0 |
| Identity | SPIFFE/SPIRE | Apache 2.0 |

## 22. License

MUTX core is source-available under BUSL-1.1 and the Python SDK is Apache-2.0.
Runtime-security components are informed by the MIT-licensed AARM documentation
but are not presented as AARM-conformant. The observability schema is a local
adaptation of MIT-licensed agent-run schemas; MUTX does not execute the
quarantined current upstream package. See `CREDITS.md` for exact refs and notices.
