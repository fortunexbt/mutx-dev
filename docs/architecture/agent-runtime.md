---
description: Runtime behavior, monitoring, recovery flows, and execution model.
icon: microchip
---

# Agent Runtime

This document describes how agents run in mutx.dev, including their lifecycle, monitoring, and self-healing capabilities.

## What is active today

* `POST /v1/agents/heartbeat` is the live runtime path for connected agents. It updates `agents.status` and `last_heartbeat` in the control plane.
* Each runtime heartbeat now emits an `agent.heartbeat` outgoing webhook event for subscribers.
* When a heartbeat changes the persisted agent status, MUTX also emits an `agent.status` outgoing webhook event.
* The background monitor in `src/api/services/monitoring.py` owns stale-agent detection, failure marking, alert resolution, and the active recovery loop.
* The background monitor now wires tracked agents into `SelfHealingService` in `src/api/services/self_healer.py` (heartbeat-based health checks + recovery handlers) so those paths are now connected to real runtime paths.
* Advanced self-healing actions such as rollback version trees, recreate, or scale-up/down are still aspirational until they are backed by real execution infrastructure.

***

## Overview

The Agent Runtime (`src/api/services/agent_runtime.py`) is the core execution engine that manages agent lifecycles, tool routing, and resource allocation.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Agent Runtime Architecture                            │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                         RuntimeManager                                    │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │                     AgentRuntime                                    │  │  │
│  │  │                                                                     │  │  │
│  │  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐  │  │ │
│  │  │  │  RuntimeConfig │  │  RuntimeState │  │   ToolExecutionHandler │  │  │ │
│  │  │  │  - timeout    │  │  - status     │  │   - register_handler   │  │  │ │
│  │  │  │  - max_agents │  │  - metrics    │  │   - execute_tool       │  │  │ │
│  │  │  │  - retries    │  │  - active    │  │                        │  │  │ │
│  │  │  └────────────────┘  └────────────────┘  └────────────────────────┘  │  │ │
│  │  │                                                                     │  │  │
│  │  │  ┌─────────────────────────────────────────────────────────────────┐ │  │ │
│  │  │  │                    Agent Registry                               │ │  │ │
│  │  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │ │  │ │
│  │  │  │  │ Agent 1 │ │ Agent 2 │ │ Agent 3 │ │ Agent N │              │ │  │ │
│  │  │  │  │(LangChain│ │(OpenClaw│ │  (n8n)  │ │         │              │ │  │ │
│  │  │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘              │ │  │ │
│  │  │  └─────────────────────────────────────────────────────────────────┘ │  │ │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

***

## Agent Lifecycle

### Lifecycle States

```
        ┌─────────┐
        │ CREATED │
        └────┬────┘
             │ initialize()
             ▼
      ┌──────────────┐
      │ INITIALIZING │──── Exception ───▶ ┌─────────┐
      └──────┬───────┘                    │  ERROR  │
             │                            └────┬────┘
             │ success                           │
             ▼                                   │ reset()
      ┌──────────────┐                           │
      │    READY     │◀──────────────────────────┘
      └──────┬───────┘
             │ execute()
             ▼
      ┌──────────────┐
      │   RUNNING    │──── Complete ───▶ ┌─────────┐
      └──────┬───────┘                   │  READY  │
             │                            └────────┘
             │ Error/Timeout
             ▼
       ┌───────────┐
       │  ERROR    │
       └───────────┘
```

### Creating an Agent

```python
# From agent_runtime.py:189
def create_agent(
    self,
    name: str,
    provider: str,
    model: str,
    system_prompt: Optional[str] = None,
    tools: Optional[List[ToolDefinition]] = None,
    vector_store_name: Optional[str] = None,
    **kwargs,
) -> LangChainAgent:
    provider_enum = LLMProvider(provider.lower())
    config = AgentConfig(
        name=name,
        provider=provider_enum,
        model=model,
        system_prompt=system_prompt,
        tools=tools or [],
        vector_store_name=vector_store_name,
        **kwargs,
    )
    agent = AgentRegistry.create_agent(config)
    self.state.active_agents += 1
    return agent
```

### Execution Modes

| Mode          | Method                   | Use Case                      |
| ------------- | ------------------------ | ----------------------------- |
| **Async**     | `execute_agent()`        | Non-blocking, high throughput |
| **Sync**      | `execute_agent_sync()`   | Simple scripts, CLI tools     |
| **Streaming** | `execute_agent_stream()` | Real-time output, chat UIs    |

***

## Agent Types

### 1. LangChain Agent

From `src/api/integrations/langchain_agent.py`:

```python
class LangChainAgent:
    def __init__(self, config: AgentConfig):
        self.llm = LLMWrapper.create(config)
        self.memory_manager = ConversationMemoryManager(config.memory_type)
        self.tools = self._initialize_tools()
        self.agent_executor = None
```

**Features:**

* Multiple LLM providers (OpenAI, Anthropic, Ollama)
* Tool-augmented execution
* Conversation memory
* Streaming support

### 2. OpenClaw Agent

Multi-agent orchestration framework for complex workflows.

### 3. n8n Agent

Workflow automation with visual builder integration.

***

## Tool Execution

Every LangChain tool registered through `AgentRuntime` is mediated before its
handler can run. The runtime normalizes the call with `ActionMediator`, evaluates
the active `PolicyEngine` policy, and then applies the decision:

* `ALLOW` and `MODIFY` execute the original handler (with modified arguments when supplied).
* `DENY` blocks the handler and emits an action receipt.
* `DEFER` blocks the handler. Because arbitrary handler continuations are not
  durably serializable yet, the runtime returns `resumable: false` and does not
  create a ghost approval.

The default runtime policy allows the low-risk built-ins (`get_time`,
`calculator`, and `search_documents`) and denies custom tools until a policy is
configured. Security REST routes expose the separate canonical durable approval
workflow. A caller that needs resumability must bind that workflow to its own
durable, idempotent job continuation.

Each decision also appends a RunEvent v1-compatible audit record with the run,
actor, policy decision, approval, cost/redaction metadata, and a SHA-256 link to
the prior event in that run. Administrators can retrieve and verify a chain with
`GET /v1/audit/export?run_id=<run-id>` (or export all run chains in a session via
`session_id`).

### Tool Handler Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Tool Execution Flow                                      │
│                                                                                  │
│  ┌──────────┐     ┌─────────────────┐     ┌────────────────────────────────┐  │
│  │  Agent   │────▶│ ToolExecution   │────▶│  Tool Registry                 │  │
│  │ Request  │     │    Handler       │     │                                │  │
│  └──────────┘     └────────┬────────┘     │  ┌──────────────────────────┐ │  │
│                            │               │  │ search_documents (RAG)    │ │  │
│                            │               │  │ get_time                  │ │  │
│                            ▼               │  │ calculator                │ │  │
│                     ┌─────────────────┐   │  │ [custom tools...]         │ │  │
│                     │  Validate Input  │   │  └──────────────────────────┘ │  │
│                     └────────┬────────┘   └────────────────────────────────┘  │
│                              │                                                 │
│                              ▼                                                 │
│                     ┌─────────────────┐     ┌────────────────────────────────┐  │
│                     │  Execute Tool   │────▶│  Return/Stream Result         │  │
│                     │  (Async/Sync)   │     │                                │  │
│                     └─────────────────┘     └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Built-in Tools

| Tool               | Description                      | Example                        |
| ------------------ | -------------------------------- | ------------------------------ |
| `search_documents` | Semantic search via vector store | `query="deployment guide"`     |
| `get_time`         | Current timestamp                | `get_time()`                   |
| `calculator`       | Safe math evaluation             | `calculator(expression="2+2")` |

### Custom Tool Registration

```python
from src.api.services.agent_runtime import AgentRuntime

runtime = AgentRuntime(config)
runtime.tool_handler.register_handler(
    "my_tool",
    async def my_tool_handler(params):
        # Custom logic
        return {"result": "..."}
)
```

***

## Monitoring

The `MonitoringService` in `src/api/services/monitoring.py` provides comprehensive observability.

### Metrics Collection

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      Monitoring Service Architecture                            │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                        MonitoringService                                  │  │
│  │                                                                           │  │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │  │
│  │  │ MetricsCollector │  │  HealthChecker   │  │    AlertManager     │  │  │
│  │  │                  │  │                  │  │                      │  │  │
│  │  │ - request_count  │  │ - health_checks  │  │ - create_alert      │  │  │
│  │  │ - error_count    │  │ - retry logic    │  │ - severity levels   │  │  │
│  │  │ - latency (p95)  │  │ - status types   │  │ - callbacks         │  │  │
│  │  │ - success_rate   │  │                  │  │                      │  │  │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────────┘  │  │
│  │                                                                           │  │
│  │  ┌──────────────────┐  ┌──────────────────────────────────────────────┐  │  │
│  │  │  UptimeTracker   │  │              SystemMetrics                    │  │  │
│  │  │                  │  │                                               │  │  │
│  │  │ - start/stop     │  │  - cpu_usage  - memory_usage                 │  │  │
│  │  │ - uptime_pct     │  │  - disk_usage  - network_io                   │  │  │
│  │  │ - downtime       │  │                                               │  │  │
│  │  └──────────────────┘  └──────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Health Status Levels

| Status        | Condition                   | Action           |
| ------------- | --------------------------- | ---------------- |
| **HEALTHY**   | All checks pass             | Normal operation |
| **DEGRADED**  | Performance below threshold | Log warning      |
| **UNHEALTHY** | Health check failed         | Trigger recovery |
| **UNKNOWN**   | No health data              | Skip monitoring  |

### Alert Severity

| Level        | Threshold        | Example               |
| ------------ | ---------------- | --------------------- |
| **INFO**     | -                | Agent registered      |
| **WARNING**  | Error rate > 10% | High latency detected |
| **ERROR**    | Error rate > 25% | Agent unhealthy       |
| **CRITICAL** | Error rate > 50% | System failure        |

### Metrics Collected

| Metric              | Type    | Description              |
| ------------------- | ------- | ------------------------ |
| `request_count`     | Counter | Total requests processed |
| `error_count`       | Counter | Failed requests          |
| `avg_latency_ms`    | Gauge   | Average response time    |
| `p95_latency_ms`    | Gauge   | 95th percentile latency  |
| `p99_latency_ms`    | Gauge   | 99th percentile latency  |
| `cpu_usage`         | Gauge   | System CPU percentage    |
| `memory_usage`      | Gauge   | System memory percentage |
| `uptime_percentage` | Gauge   | Agent uptime ratio       |

***

## Self-Healing

The `SelfHealingService` in `src/api/services/self_healer.py` provides automatic recovery.

### Self-Healing Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       Self-Healing Service Architecture                         │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                       SelfHealingService                                  │  │
│  │                                                                           │  │
│  │  ┌────────────────────┐  ┌────────────────────────────────────────────┐ │  │
│  │  │  HealthCheckScheduler │  │           RecoveryExecutor              │ │  │
│  │  │                    │  │                                             │ │  │
│  │  │ - check_interval   │  │ - RecoveryAction.ROLLBACK                  │ │  │
│  │  │ - timeout          │  │ - RecoveryAction.RESTART                   │ │  │
│  │  │ - max_retries      │  │ - RecoveryAction.RECREATE                  │ │  │
│  │  │ - agent_health     │  │ - RecoveryAction.SCALE_UP                 │ │  │
│  │  └────────────────────┘  └────────────────────────────────────────────┘ │  │
│  │                                                                           │  │
│  │  ┌────────────────────┐  ┌────────────────────────────────────────────┐ │  │
│  │  │   VersionManager   │  │        RecoveryTimeTracker                │ │  │
│  │  │                    │  │                                             │ │  │
│  │  │ - record_version   │  │ - record_recovery_time                     │ │  │
│  │  │ - mark_stable      │  │ - get_average_recovery_time                │ │  │
│  │  │ - get_history      │  │ - recovery_stats                           │ │  │
│  │  └────────────────────┘  └────────────────────────────────────────────┘ │  │
│  │                                                                           │  │
│  │  ┌───────────────────────────────────────────────────────────────────────┐ │  │
│  │  │                    Recovery History (deque maxlen=1000)             │ │  │
│  │  └───────────────────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Recovery Actions

| Action          | Trigger                | Description                |
| --------------- | ---------------------- | -------------------------- |
| **RESTART**     | 3 consecutive failures | Restart agent process      |
| **ROLLBACK**    | After failed restart   | Revert to stable version   |
| **RECREATE**    | Persistent failure     | Destroy and recreate agent |
| **SCALE\_UP**   | High load              | Add more agent instances   |
| **SCALE\_DOWN** | Low load               | Reduce resource usage      |

### Health Check Configuration

```python
@dataclass
class RecoveryConfig:
    max_retries: int = 3                    # Max recovery attempts
    retry_delay_seconds: float = 5.0        # Delay between retries
    health_check_interval_seconds: int = 10 # Check frequency
    health_check_timeout_seconds: float = 5.0 # Timeout per check
    max_consecutive_failures: int = 3       # Failures before recovery
    rollback_on_failure: bool = True        # Auto-rollback enabled
    enable_auto_restart: bool = True        # Auto-restart enabled
    min_recovery_interval_seconds: float = 60.0 # Min time between recoveries
```

### Recovery Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Health     │────▶│   Check      │────▶│   Consecutive│────▶│   Trigger    │
│   Check      │     │   Result     │     │   Failures   │     │   Recovery  │
│   (30s)      │     │   (FAIL)     │     │   >= 3       │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                     │
     ┌─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Execute   │────▶│   Success?   │─No─▶│   Rollback   │────▶│   Mark       │
│   Recovery  │     │              │     │   to Stable  │     │   Stable     │
│   (RESTART)  │     └──────────────┘     └──────────────┘     │   Version    │
     │                                                          └──────────────┘
     │ Yes
     ▼
┌──────────────┐
│   Record    │
│   Recovery  │
│   Time      │
└──────────────┘
```

### Recovery Time Tracking

The service tracks recovery metrics:

```python
{
    "agent_id": "agent-001",
    "total_recoveries": 5,
    "average_recovery_time_seconds": 2.3,
    "min_recovery_time_seconds": 1.1,
    "max_recovery_time_seconds": 4.8,
    "last_recovery_time_seconds": 2.1
}
```

**Target**: Recovery time < 5 seconds

***

## Configuration

### Runtime Configuration

```python
@dataclass
class RuntimeConfig:
    max_concurrent_agents: int = 10        # Max agents per runtime
    default_timeout: int = 300             # Execution timeout (seconds)
    enable_streaming: bool = True          # Enable streaming responses
    max_retries: int = 3                   # Retry attempts on failure
    retry_delay: float = 1.0               # Delay between retries
    vector_store_enabled: bool = True      # Enable RAG
    database_url: Optional[str] = None     # Database connection
```

### Example Usage

```python
from src.api.services.agent_runtime import (
    AgentRuntime,
    RuntimeConfig,
    RuntimeManager
)

# Create runtime
config = RuntimeConfig(
    max_concurrent_agents=5,
    default_timeout=600,
)
runtime = RuntimeManager.create_runtime(config)

# Start runtime
await runtime.start()

# Create and execute agent
agent = runtime.create_agent(
    name="my-agent",
    provider="openai",
    model="gpt-4",
    system_prompt="You are a helpful assistant."
)

result = await runtime.execute_agent(
    agent_id=agent.agent_id,
    input_text="Hello, world!"
)

# Get stats
stats = runtime.get_stats()
# {
#   "runtime_id": "...",
#   "status": "running",
#   "active_agents": 1,
#   "total_executions": 1,
#   "failed_executions": 0,
#   "success_rate": 1.0
# }

# Stop runtime
await runtime.stop()
```

***

## Next Steps

* [Security](security.md)
