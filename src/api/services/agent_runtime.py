import os
import asyncio
from contextvars import ContextVar, copy_context
import logging
import uuid
from typing import Optional, List, Dict, Any, AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from src.api.services.governance_runtime import GovernanceRuntime, get_governance_runtime

from ..integrations.langchain_agent import (
    LangChainAgent,
    AgentConfig,
    AgentRegistry,
    AgentState,
    LLMProvider,
    ToolDefinition,
)
from ..integrations.vector_store import (
    VectorStoreConfig,
    VectorStoreRegistry,
    EmbeddingProvider,
)

logger = logging.getLogger(__name__)


class RuntimeStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class RuntimeConfig:
    max_concurrent_agents: int = 10
    default_timeout: int = 300
    enable_streaming: bool = True
    max_retries: int = 3
    retry_delay: float = 1.0
    vector_store_enabled: bool = True
    database_url: Optional[str] = None


@dataclass
class ExecutionContext:
    execution_id: str
    agent_id: str
    input_text: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "running"
    output: Optional[str] = None
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RuntimeState:
    runtime_id: str
    status: RuntimeStatus
    active_agents: int = 0
    total_executions: int = 0
    failed_executions: int = 0
    started_at: Optional[datetime] = None
    last_error: Optional[str] = None


class ToolExecutionHandler:
    def __init__(self, governance: GovernanceRuntime):
        self._handlers: Dict[str, Callable] = {}
        self._governance = governance

    def register_handler(self, tool_name: str, handler: Callable):
        if tool_name in self._governance.SAFE_BUILTIN_TOOLS:
            raise ValueError(f"Tool name is reserved for a runtime built-in: {tool_name}")
        self._register_handler(tool_name, handler)

    def _register_builtin_handler(self, tool_name: str, handler: Callable) -> None:
        if tool_name not in self._governance.SAFE_BUILTIN_TOOLS:
            raise ValueError(f"Tool name is not a runtime built-in: {tool_name}")
        self._register_handler(tool_name, handler)

    def _register_handler(self, tool_name: str, handler: Callable) -> None:
        self._handlers[tool_name] = handler
        logger.info(f"Registered handler for tool: {tool_name}")

    def get_handler(self, tool_name: str) -> Optional[Callable]:
        return self._handlers.get(tool_name)

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        *,
        agent_id: str = "runtime-agent",
        session_id: str | None = None,
        run_id: str | None = None,
        user_id: str = "",
        actor_type: str = "agent",
        actor_id: str | None = None,
        actor_display: str | None = None,
        handler_override: Callable | None = None,
    ) -> Any:
        resolved_run_id = run_id or str(uuid.uuid4())
        resolved_session_id = session_id or resolved_run_id
        evaluation = self._governance.authorize(
            tool_name=tool_name,
            tool_args=parameters,
            agent_id=agent_id,
            session_id=resolved_session_id,
            run_id=resolved_run_id,
            user_id=user_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display=actor_display,
        )

        if evaluation.decision.is_denied:
            receipt, audit_event = await self._governance.record_outcome(
                evaluation,
                outcome="blocked",
                outcome_detail=evaluation.decision.reason,
            )
            return {
                "error": "Tool execution denied by policy",
                "decision": evaluation.decision.decision.value,
                "reason": evaluation.decision.reason,
                "receipt_id": receipt.receipt_id,
                "integrity_hash": audit_event.integrity_hash,
            }

        if evaluation.decision.is_deferred:
            receipt, audit_event = await self._governance.record_outcome(
                evaluation,
                outcome="blocked_no_resume_binding",
                outcome_detail=(
                    "DEFER remained fail-closed because no durable canonical approval "
                    "resume binding is configured"
                ),
            )
            return {
                "error": (
                    "Tool execution is blocked: DEFER has no durable canonical "
                    "approval resume binding"
                ),
                "decision": evaluation.decision.decision.value,
                "reason": evaluation.decision.reason,
                "resumable": False,
                "receipt_id": receipt.receipt_id,
                "integrity_hash": audit_event.integrity_hash,
            }

        handler = handler_override or self.get_handler(tool_name)
        if not handler:
            logger.warning(f"No handler registered for tool: {tool_name}")
            error = f"Tool {tool_name} not found"
            receipt, audit_event = await self._governance.record_outcome(
                evaluation,
                outcome="error",
                outcome_detail=error,
                error=error,
            )
            return {
                "error": error,
                "receipt_id": receipt.receipt_id,
                "integrity_hash": audit_event.integrity_hash,
            }

        try:
            authorization_receipt, _ = await self._governance.record_authorization(evaluation)
        except Exception:
            logger.exception(
                "Tool execution blocked because authorization evidence could not be persisted: %s",
                tool_name,
            )
            return {
                "error": "Tool execution blocked because authorization evidence could not be persisted",
                "decision": evaluation.decision.decision.value,
                "reason": evaluation.decision.reason,
            }

        modification_envelope = evaluation.decision.modifications or {}
        effective_parameters = modification_envelope.get("modified_args", parameters)
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(effective_parameters)
            else:
                result = handler(effective_parameters)
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {str(e)}")
            try:
                await self._governance.record_execution_result(
                    evaluation,
                    authorization_receipt=authorization_receipt,
                    outcome="error",
                    error=str(e),
                )
            except Exception:
                logger.exception("Failed to persist tool execution failure evidence: %s", tool_name)
            return {"error": str(e)}

        try:
            await self._governance.record_execution_result(
                evaluation,
                authorization_receipt=authorization_receipt,
                outcome="executed",
                output_preview=str(result)[:500],
            )
        except Exception:
            logger.exception(
                "Tool executed but outcome evidence could not be persisted: %s", tool_name
            )
            return {
                "error": "Tool executed but outcome evidence could not be persisted",
                "result": result,
                "receipt_id": authorization_receipt.receipt_id,
            }
        return result


class AgentRuntime:
    def __init__(
        self,
        config: RuntimeConfig,
        governance: GovernanceRuntime | None = None,
    ):
        self.config = config
        self.runtime_id = str(uuid.uuid4())
        self.state = RuntimeState(
            runtime_id=self.runtime_id,
            status=RuntimeStatus.STOPPED,
        )
        self.governance = governance or get_governance_runtime()
        self.tool_handler = ToolExecutionHandler(self.governance)
        self._execution_callbacks: Dict[str, Callable] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._execution_scope: ContextVar[tuple[str, str] | None] = ContextVar(
            f"mutx_runtime_execution_{self.runtime_id}", default=None
        )
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def _bind_event_loop(self) -> asyncio.AbstractEventLoop:
        """Bind governed operations to one owning loop for shared async state."""
        event_loop = asyncio.get_running_loop()
        if self._event_loop is not None and self._event_loop is not event_loop:
            if self._event_loop.is_running():
                raise RuntimeError("AgentRuntime is already bound to another event loop")
        self._event_loop = event_loop
        return event_loop

    async def start(self):
        self._bind_event_loop()
        if self.state.status == RuntimeStatus.RUNNING:
            logger.warning(f"Runtime {self.runtime_id} already running")
            return

        self.state.status = RuntimeStatus.STARTING
        self.state.started_at = datetime.now(timezone.utc)

        if self.config.vector_store_enabled and self.config.database_url:
            self._initialize_vector_store()

        self._register_default_tool_handlers()
        self.state.status = RuntimeStatus.RUNNING
        logger.info(f"Runtime {self.runtime_id} started")

    async def stop(self):
        self.state.status = RuntimeStatus.STOPPING

        for task_id, task in self._running_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info(f"Task {task_id} cancelled")

        self._running_tasks.clear()
        self.state.status = RuntimeStatus.STOPPED
        logger.info(f"Runtime {self.runtime_id} stopped")

    def _initialize_vector_store(self):
        try:
            vector_config = VectorStoreConfig(
                database_url=self.config.database_url
                or os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/mutx"),
                embedding_provider=EmbeddingProvider.OPENAI,
                embedding_model="text-embedding-ada-002",
                collection_name="default",
            )
            VectorStoreRegistry.create_store("default", vector_config)
            logger.info("Default vector store initialized")
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {str(e)}")

    def _register_default_tool_handlers(self):
        self.tool_handler._register_builtin_handler(
            "search_documents", self._handle_search_documents
        )
        self.tool_handler._register_builtin_handler("get_time", self._handle_get_time)
        self.tool_handler._register_builtin_handler("calculator", self._handle_calculator)

    async def _handle_search_documents(self, params: Dict[str, Any]) -> str:
        store_name = params.get("store_name", "default")
        query = params.get("query", "")
        k = params.get("k", 4)

        store = VectorStoreRegistry.get_store(store_name)
        if not store:
            return f"Vector store '{store_name}' not found"

        docs = store.similarity_search(query, k=k)
        if not docs:
            return "No relevant documents found"

        results = []
        for i, doc in enumerate(docs, 1):
            results.append(f"{i}. {doc.page_content[:200]}...")
        return "\n".join(results)

    async def _handle_get_time(self, params: Dict[str, Any]) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _handle_calculator(self, params: Dict[str, Any]) -> str:
        _expression = params.get("expression", "0")
        # Safety cleanup: removed dangerous eval()
        # In a real system, use a safe math parser like simpleeval or numexpr
        return "Calculator tool disabled for safety in this version. Use repo-native Python tools."

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
            tool_executor=self._execute_langchain_tool,
            **kwargs,
        )
        agent = AgentRegistry.create_agent(config)
        self.state.active_agents += 1
        logger.info(f"Created agent {agent.agent_id} in runtime {self.runtime_id}")
        return agent

    def _execute_langchain_tool(
        self,
        agent_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        handler: Callable,
    ) -> Any:
        """Bridge synchronous LangChain tools through async governance enforcement."""
        scope = self._execution_scope.get()
        run_id, session_id = scope or (str(uuid.uuid4()), str(uuid.uuid4()))

        async def execute() -> Any:
            return await self.tool_handler.execute_tool(
                tool_name,
                parameters,
                agent_id=agent_id,
                session_id=session_id,
                run_id=run_id,
                handler_override=handler,
            )

        owner_loop = self._event_loop
        if owner_loop is None or not owner_loop.is_running():
            return asyncio.run(execute())

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is owner_loop:
            raise RuntimeError(
                "Synchronous governed tool calls cannot block the runtime event loop"
            )

        worker_context = copy_context()
        future = worker_context.run(asyncio.run_coroutine_threadsafe, execute(), owner_loop)
        return future.result()

    async def execute_agent(
        self,
        agent_id: str,
        input_text: str,
        timeout: Optional[int] = None,
    ) -> ExecutionContext:
        self._bind_event_loop()
        execution_id = str(uuid.uuid4())
        context = ExecutionContext(
            execution_id=execution_id,
            agent_id=agent_id,
            input_text=input_text,
        )

        agent = AgentRegistry.get_agent(agent_id)
        if not agent:
            context.status = "error"
            context.error = f"Agent {agent_id} not found"
            context.completed_at = datetime.now(timezone.utc)
            self.state.failed_executions += 1
            return context

        timeout = timeout or self.config.default_timeout
        scope_token = self._execution_scope.set((execution_id, execution_id))

        try:
            result = await asyncio.wait_for(
                agent.arun(input_text),
                timeout=timeout,
            )

            context.output = result.get("output")
            context.status = "completed" if result.get("success") else "error"
            context.error = result.get("error")
            context.completed_at = datetime.now(timezone.utc)
            self.state.total_executions += 1

            if not result.get("success"):
                self.state.failed_executions += 1

        except asyncio.TimeoutError:
            context.status = "timeout"
            context.error = f"Execution timed out after {timeout} seconds"
            context.completed_at = datetime.now(timezone.utc)
            self.state.failed_executions += 1
            logger.error(f"Execution {execution_id} timed out")

        except Exception as e:
            context.status = "error"
            context.error = str(e)
            context.completed_at = datetime.now(timezone.utc)
            self.state.failed_executions += 1
            logger.error(f"Execution {execution_id} error: {str(e)}")
        finally:
            self._execution_scope.reset(scope_token)

        if self._execution_callbacks.get(execution_id):
            callback = self._execution_callbacks.pop(execution_id)
            callback(context)

        return context

    async def execute_agent_stream(
        self,
        agent_id: str,
        input_text: str,
    ) -> AsyncIterator[str]:
        self._bind_event_loop()
        agent = AgentRegistry.get_agent(agent_id)
        if not agent:
            yield f"Error: Agent {agent_id} not found"
            return

        execution_id = str(uuid.uuid4())
        scope_token = self._execution_scope.set((execution_id, execution_id))
        try:
            stream = iter(agent.stream_run(input_text))

            def next_chunk() -> tuple[bool, Any]:
                try:
                    return True, next(stream)
                except StopIteration:
                    return False, None

            while True:
                has_chunk, chunk = await asyncio.to_thread(next_chunk)
                if not has_chunk:
                    break
                if isinstance(chunk, str):
                    yield chunk
                else:
                    yield str(chunk)
        except Exception as e:
            logger.error(f"Stream execution error: {str(e)}")
            yield f"Error: {str(e)}"
        finally:
            self._execution_scope.reset(scope_token)

    def execute_agent_sync(self, agent_id: str, input_text: str) -> Dict[str, Any]:
        agent = AgentRegistry.get_agent(agent_id)
        if not agent:
            return {"success": False, "error": f"Agent {agent_id} not found"}

        execution_id = str(uuid.uuid4())
        scope_token = self._execution_scope.set((execution_id, execution_id))
        try:
            return agent.run(input_text)
        finally:
            self._execution_scope.reset(scope_token)

    def get_agent(self, agent_id: str) -> Optional[LangChainAgent]:
        return AgentRegistry.get_agent(agent_id)

    def delete_agent(self, agent_id: str) -> bool:
        success = AgentRegistry.delete_agent(agent_id)
        if success:
            self.state.active_agents = max(0, self.state.active_agents - 1)
        return success

    def list_agents(self) -> List[AgentState]:
        return AgentRegistry.list_agents()

    def get_state(self) -> RuntimeState:
        return self.state

    def get_stats(self) -> Dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "status": self.state.status.value,
            "active_agents": self.state.active_agents,
            "total_executions": self.state.total_executions,
            "failed_executions": self.state.failed_executions,
            "success_rate": (
                (self.state.total_executions - self.state.failed_executions)
                / self.state.total_executions
                if self.state.total_executions > 0
                else 0.0
            ),
            "started_at": self.state.started_at.isoformat() if self.state.started_at else None,
            "last_error": self.state.last_error,
        }

    def on_execution_complete(self, execution_id: str, callback: Callable):
        self._execution_callbacks[execution_id] = callback


class RuntimeManager:
    _runtimes: Dict[str, AgentRuntime] = {}
    _default_runtime: Optional[AgentRuntime] = None

    @classmethod
    def create_runtime(cls, config: Optional[RuntimeConfig] = None) -> AgentRuntime:
        runtime = AgentRuntime(config or RuntimeConfig())
        cls._runtimes[runtime.runtime_id] = runtime
        logger.info(f"Created runtime {runtime.runtime_id}")
        return runtime

    @classmethod
    async def start_runtime(cls, runtime_id: str) -> bool:
        runtime = cls._runtimes.get(runtime_id)
        if not runtime:
            return False
        await runtime.start()
        return True

    @classmethod
    async def stop_runtime(cls, runtime_id: str) -> bool:
        runtime = cls._runtimes.get(runtime_id)
        if not runtime:
            return False
        await runtime.stop()
        return True

    @classmethod
    def get_runtime(cls, runtime_id: str) -> Optional[AgentRuntime]:
        return cls._runtimes.get(runtime_id)

    @classmethod
    def get_or_create_default(cls, config: Optional[RuntimeConfig] = None) -> AgentRuntime:
        if cls._default_runtime is None:
            cls._default_runtime = cls.create_runtime(config)
        return cls._default_runtime

    @classmethod
    def delete_runtime(cls, runtime_id: str) -> bool:
        runtime = cls._runtimes.get(runtime_id)
        if runtime is None:
            return False

        if cls._default_runtime is runtime:
            cls._default_runtime = None

        del cls._runtimes[runtime_id]
        return True

    @classmethod
    def list_runtimes(cls) -> List[RuntimeState]:
        return [runtime.get_state() for runtime in cls._runtimes.values()]


@asynccontextmanager
async def runtime_context(config: Optional[RuntimeConfig] = None):
    runtime = RuntimeManager.get_or_create_default(config)
    await runtime.start()
    try:
        yield runtime
    finally:
        await runtime.stop()
