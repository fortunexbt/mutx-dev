from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field
import uuid

from src.api.models.models import AgentStatus, AgentType
from src.api.models.numeric import (
    DegradedNumericResponseModel,
    FiniteFloat,
    FiniteJsonDict,
    NonNegativeFiniteFloat,
    PercentageFloat,
)


class AgentConfigBase(BaseModel):
    """Base schema for specialized agent configurations"""

    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    system_prompt: Optional[str] = Field(default=None, max_length=16000)
    version: int = Field(default=1, ge=1)


class OpenAIAgentConfig(AgentConfigBase):
    model: str = Field(default="gpt-4o", min_length=1, max_length=255)
    temperature: FiniteFloat = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)


class AnthropicAgentConfig(AgentConfigBase):
    model: str = Field(default="claude-3-5-sonnet-20240620", min_length=1, max_length=255)
    temperature: FiniteFloat = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, gt=0)


class LangChainAgentConfig(AgentConfigBase):
    chain_id: str
    parameters: FiniteJsonDict = Field(default_factory=dict)


class CustomAgentConfig(AgentConfigBase):
    image: str
    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class OpenClawChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=120)
    enabled: bool = False
    mode: str = Field(default="pairing", min_length=1, max_length=64)
    allow_from: list[str] = Field(default_factory=list)


class OpenClawWakeupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    schedule: Optional[str] = Field(default=None, max_length=255)
    timezone: Optional[str] = Field(default=None, max_length=120)
    label: Optional[str] = Field(default=None, max_length=120)


class OpenClawGatewayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: int = Field(default=18789, ge=1, le=65535)
    auth_mode: str = Field(default="token", min_length=1, max_length=64)
    dashboard_allowed_origins: list[str] = Field(default_factory=list)


class OpenClawAgentConfig(AgentConfigBase):
    runtime: str = Field(default="personal_assistant", min_length=1, max_length=120)
    template: str = Field(default="personal_assistant", min_length=1, max_length=120)
    assistant_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    workspace: str = Field(default="default", min_length=1, max_length=255)
    model: str = Field(default="openai/gpt-5", min_length=1, max_length=255)
    safety_mode: str = Field(default="pairing", min_length=1, max_length=64)
    channels: dict[str, OpenClawChannelConfig] = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list)
    wakeups: list[OpenClawWakeupConfig] = Field(default_factory=list)
    metadata: FiniteJsonDict = Field(default_factory=dict)
    gateway: OpenClawGatewayConfig = Field(default_factory=OpenClawGatewayConfig)


AgentConfigSchema = (
    OpenAIAgentConfig
    | AnthropicAgentConfig
    | LangChainAgentConfig
    | CustomAgentConfig
    | OpenClawAgentConfig
)


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    type: AgentType = Field(default=AgentType.OPENAI)
    config: Optional[FiniteJsonDict | str] = None
    # user_id is set from current_user in the route, not from request body


class AgentConfigUpdateRequest(BaseModel):
    config: FiniteJsonDict | str = Field(
        ...,
        description="Updated agent configuration payload. Can be a JSON object or JSON string.",
    )


class DeploymentCreate(BaseModel):
    """Request model for creating a deployment"""

    agent_id: uuid.UUID
    replicas: int = Field(default=1, ge=1, le=10, description="Number of replicas (1-10)")


class DeploymentEventResponse(BaseModel):
    """Response model for deployment events"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deployment_id: uuid.UUID
    event_type: str
    status: str
    node_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime


class DeploymentEventHistoryResponse(BaseModel):
    """Paginated deployment lifecycle event history."""

    deployment_id: uuid.UUID
    deployment_status: str
    items: list[DeploymentEventResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool
    event_type: Optional[str] = None
    status: Optional[str] = None


DeploymentAction = Literal["start", "stop", "restart", "scale", "terminate"]


def deployment_allowed_actions(status: str) -> list[DeploymentAction]:
    if status in {"running", "ready"}:
        return ["stop", "restart", "scale", "terminate"]
    if status in {"pending", "deploying"}:
        return ["stop", "terminate"]
    if status == "stopped":
        return ["start", "terminate"]
    if status == "failed":
        return ["restart", "terminate"]
    return []


class DeploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    status: str
    version: Optional[str] = None
    replicas: int
    node_id: Optional[str]
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime]
    error_message: Optional[str]
    events: list[DeploymentEventResponse] = Field(default_factory=list)

    @computed_field(description="Lifecycle actions currently accepted for this deployment state.")
    @property
    def allowed_actions(self) -> list[DeploymentAction]:
        return deployment_allowed_actions(self.status)


class DeploymentListResponse(BaseModel):
    items: list[DeploymentResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool


class DeploymentScale(BaseModel):
    replicas: int = Field(
        ...,
        ge=0,
        le=10,
        description=(
            "Desired replicas (1-10). Zero stops an active deployment while preserving its "
            "last non-zero desired replica count."
        ),
    )


class DeploymentLogsResponse(BaseModel):
    """Response model for deployment logs"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    level: str
    message: str
    extra_data: Optional[str]
    timestamp: datetime


class DeploymentMetricsResponse(DegradedNumericResponseModel):
    """Response model for deployment metrics"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    cpu_usage: Optional[float]
    memory_usage: Optional[float]
    timestamp: datetime


class DeploymentVersionResponse(BaseModel):
    """Response model for deployment version"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deployment_id: uuid.UUID
    version: int
    config_snapshot: str
    status: str
    created_at: datetime
    rolled_back_at: Optional[datetime] = None


class DeploymentLogsHistoryResponse(BaseModel):
    """Paginated response for deployment logs"""

    deployment_id: uuid.UUID
    items: list[DeploymentLogsResponse]
    total: int
    skip: int
    limit: int
    has_more: bool
    level: Optional[str] = None


class DeploymentMetricsHistoryResponse(BaseModel):
    """Paginated response for deployment metrics"""

    deployment_id: uuid.UUID
    items: list[DeploymentMetricsResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class DeploymentVersionHistoryResponse(BaseModel):
    """Response model for deployment version history"""

    deployment_id: uuid.UUID
    items: list[DeploymentVersionResponse]
    total: int
    has_more: bool


class DeploymentRollbackRequest(BaseModel):
    """Request model for rolling back a deployment"""

    version: int = Field(..., gt=0, description="Version number to rollback to")


class AgentVersionResponse(BaseModel):
    """Response model for agent version"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    version: int
    config_snapshot: str
    status: str
    created_at: datetime
    rolled_back_at: Optional[datetime] = None


class AgentVersionHistoryResponse(BaseModel):
    """Response model for agent version history"""

    agent_id: uuid.UUID
    items: list[AgentVersionResponse]
    total: int
    has_more: bool


class AgentRollbackRequest(BaseModel):
    """Request model for rolling back an agent"""

    version: int = Field(..., gt=0, description="Version number to rollback to")


class AgentResponse(DegradedNumericResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    type: AgentType
    status: str
    config: Optional[AgentConfigSchema | dict[str, Any]]
    config_version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime
    user_id: uuid.UUID


class AgentListResponse(BaseModel):
    """Paginated response for listing agents."""

    items: list[AgentResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class AgentDetailResponse(AgentResponse):
    deployments: list[DeploymentResponse] = Field(default_factory=list)


class AgentConfigResponse(DegradedNumericResponseModel):
    agent_id: uuid.UUID
    type: AgentType
    config: AgentConfigSchema | dict[str, Any]
    config_version: int = Field(..., ge=1)
    updated_at: datetime


class AgentLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    level: str
    message: str
    extra_data: Optional[str]
    timestamp: datetime


class AgentMetricResponse(DegradedNumericResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    cpu_usage: Optional[float]
    memory_usage: Optional[float]
    timestamp: datetime


class AgentLogHistoryResponse(BaseModel):
    """Paginated response for agent logs."""

    agent_id: uuid.UUID
    items: list["AgentLogResponse"]
    total: int
    has_more: bool


class AgentMetricHistoryResponse(BaseModel):
    """Paginated response for agent metrics."""

    agent_id: uuid.UUID
    items: list["AgentMetricResponse"]
    total: int
    has_more: bool


class AgentResourceUsageResponse(DegradedNumericResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    prompt_tokens: Optional[int] = 0
    completion_tokens: Optional[int] = 0
    total_tokens: Optional[int] = 0
    api_calls: int = 0
    cost_usd: Optional[float] = 0.0
    model: Optional[str] = None
    extra_metadata: Optional[dict[str, Any]] = None
    period_start: datetime
    period_end: Optional[datetime] = None
    created_at: datetime


class PaginatedAgentResourceUsageResponse(BaseModel):
    """Paginated response for agent resource usage records."""

    items: list[AgentResourceUsageResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class AgentResourceUsageCreate(BaseModel):
    """Request schema for creating agent resource usage record."""

    prompt_tokens: Optional[int] = Field(default=0, ge=0)
    completion_tokens: Optional[int] = Field(default=0, ge=0)
    total_tokens: Optional[int] = Field(default=0, ge=0)
    api_calls: int = Field(default=0, ge=0)
    cost_usd: Optional[NonNegativeFiniteFloat] = 0.0
    model: Optional[str] = Field(default=None, max_length=100)
    extra_metadata: Optional[FiniteJsonDict] = Field(default_factory=dict)
    period_start: datetime
    period_end: Optional[datetime] = None


class RunTraceCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    message: Optional[str] = Field(None, max_length=5000)
    payload: FiniteJsonDict = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class RunCreate(BaseModel):
    agent_id: uuid.UUID
    status: str = Field(default="completed", min_length=1, max_length=50)
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    error_message: Optional[str] = None
    metadata: FiniteJsonDict = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    traces: list[RunTraceCreate] = Field(default_factory=list)


class RunTraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    event_type: str
    message: Optional[str]
    payload: dict[str, Any]
    sequence: int
    timestamp: datetime


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID | None = None
    status: str
    input_text: Optional[str]
    output_text: Optional[str]
    error_message: Optional[str]
    metadata: dict
    started_at: datetime
    completed_at: Optional[datetime]
    created_at: datetime
    trace_count: int = 0
    subject_type: str | None = None
    subject_id: str | None = None
    subject_label: str | None = None
    template_id: str | None = None
    execution_mode: str | None = None


class RunDetailResponse(RunResponse):
    traces: list[RunTraceResponse] = Field(default_factory=list)


class RunHistoryResponse(BaseModel):
    items: list[RunResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool
    agent_id: Optional[uuid.UUID] = None
    status: Optional[str] = None


class RunTraceHistoryResponse(BaseModel):
    run_id: uuid.UUID
    items: list[RunTraceResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool
    event_type: Optional[str] = None


class DocumentTemplateFieldResponse(BaseModel):
    name: str
    type: str
    required: bool = True
    accepts_multiple: bool = False
    description: str


class DocumentTemplateOutputResponse(BaseModel):
    role: str
    kind: str
    description: str


class DocumentTemplateResponse(BaseModel):
    id: str
    name: str
    summary: str
    description: str
    supports_managed: bool = True
    supports_local: bool = True
    max_upload_bytes: int
    inputs: list[DocumentTemplateFieldResponse] = Field(default_factory=list)
    outputs: list[DocumentTemplateOutputResponse] = Field(default_factory=list)


class DocumentArtifactRegistrationCreate(BaseModel):
    role: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(..., min_length=1, max_length=120)
    storage_backend: str = Field(default="local_reference", min_length=1, max_length=64)
    filename: str = Field(..., min_length=1, max_length=255)
    local_path: str | None = None
    storage_uri: str | None = None
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    role: str
    kind: str
    storage_backend: str
    storage_uri: str | None = None
    local_path: str | None = None
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DocumentJobCreate(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=120)
    execution_mode: str = Field(default="managed", min_length=1, max_length=32)
    parameters: dict[str, Any] = Field(default_factory=dict)


class DocumentJobDispatchRequest(BaseModel):
    mode: str = Field(default="managed", min_length=1, max_length=32)


class DocumentJobLocalLaunchRequest(BaseModel):
    output_dir: str | None = None


class DocumentJobLocalLaunchResponse(BaseModel):
    job_id: uuid.UUID
    template_id: str
    execution_mode: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[DocumentArtifactResponse] = Field(default_factory=list)


class DocumentJobEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    message: str | None = Field(default=None, max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default=None, max_length=50)
    output_text: str | None = None
    error_message: str | None = None
    result_summary: dict[str, Any] | None = None
    timestamp: datetime | None = None


class DocumentJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    template_id: str
    execution_mode: str
    status: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    attempts: int = 0
    dispatched_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    artifacts: list[DocumentArtifactResponse] = Field(default_factory=list)


class DocumentJobHistoryResponse(BaseModel):
    items: list[DocumentJobResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool
    status: str | None = None
    template_id: str | None = None


class ReasoningTemplateFieldResponse(BaseModel):
    name: str
    type: str
    required: bool = True
    accepts_multiple: bool = False
    description: str


class ReasoningTemplateOutputResponse(BaseModel):
    role: str
    kind: str
    description: str


class ReasoningTemplateResponse(BaseModel):
    id: str
    name: str
    summary: str
    description: str
    supports_managed: bool = True
    supports_local: bool = True
    inputs: list[ReasoningTemplateFieldResponse] = Field(default_factory=list)
    outputs: list[ReasoningTemplateOutputResponse] = Field(default_factory=list)


class ReasoningArtifactRegistrationCreate(BaseModel):
    role: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(..., min_length=1, max_length=120)
    storage_backend: str = Field(default="local_reference", min_length=1, max_length=64)
    filename: str = Field(..., min_length=1, max_length=255)
    local_path: str | None = None
    storage_uri: str | None = None
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReasoningArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    role: str
    kind: str
    storage_backend: str
    storage_uri: str | None = None
    local_path: str | None = None
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ReasoningJobCreate(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=120)
    execution_mode: str = Field(default="managed", min_length=1, max_length=32)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ReasoningJobDispatchRequest(BaseModel):
    mode: str = Field(default="managed", min_length=1, max_length=32)


class ReasoningJobLocalLaunchRequest(BaseModel):
    output_dir: str | None = None


class ReasoningJobLocalLaunchResponse(BaseModel):
    job_id: uuid.UUID
    template_id: str
    execution_mode: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ReasoningArtifactResponse] = Field(default_factory=list)


class ReasoningJobEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    message: str | None = Field(default=None, max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default=None, max_length=50)
    output_text: str | None = None
    error_message: str | None = None
    result_summary: dict[str, Any] | None = None
    timestamp: datetime | None = None


class ReasoningJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    template_id: str
    execution_mode: str
    status: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    attempts: int = 0
    dispatched_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    artifacts: list[ReasoningArtifactResponse] = Field(default_factory=list)


class ReasoningJobHistoryResponse(BaseModel):
    items: list[ReasoningJobResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool
    status: str | None = None
    template_id: str | None = None


class AgentStatusUpdate(BaseModel):
    agent_id: uuid.UUID
    status: AgentStatus
    node_id: Optional[str] = None
    error_message: Optional[str] = None


class DeploymentEvent(BaseModel):
    deployment_id: uuid.UUID
    event: str
    status: Optional[str] = None
    node_id: Optional[str] = None
    error_message: Optional[str] = None


class MetricsReportRequest(BaseModel):
    """Request model for reporting agent metrics"""

    agent_id: uuid.UUID
    cpu_usage: PercentageFloat = Field(..., description="CPU usage percentage (0-100)")
    memory_usage: PercentageFloat = Field(..., description="Memory usage percentage (0-100)")


class IngestEvent(BaseModel):
    """Generic event ingestion payload from SDK adapters.

    Accepts any structured event from LangChain, CrewAI, AutoGen, or future
    adapters.  ``event_type`` is the only required field; all other fields
    are carried as a free-form ``payload`` dict.
    """

    event_type: str = Field(
        ..., min_length=1, description="Adapter event type (e.g. agent_action, crew_task_start)"
    )
    timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp from the adapter")
    agent_id: Optional[uuid.UUID] = Field(None, description="Agent UUID if available")
    payload: FiniteJsonDict = Field(default_factory=dict, description="Adapter-specific event data")


class HealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: str
    timestamp: datetime
    database: Optional[str] = None
    error: Optional[str] = None
    version: str = "1.0.0"
    uptime_seconds: Optional[float] = None
    components: dict[str, dict[str, Any]] = Field(default_factory=dict)
    schema_repairs_applied: list[str] = Field(default_factory=list)


class AssistantTemplateResponse(BaseModel):
    id: str
    name: str
    summary: str
    description: str
    agent_type: AgentType
    starter_prompt: str
    default_config: OpenClawAgentConfig | dict[str, Any]
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    is_official: bool = False
    source_path: Optional[str] = None
    version: Optional[str] = None
    validation_status: Optional[str] = None
    validation_message: Optional[str] = None
    bundle_ids: list[str] = Field(default_factory=list)


class ClawHubSkillBundleResponse(BaseModel):
    id: str
    name: str
    summary: str
    description: str
    skill_ids: list[str] = Field(default_factory=list)
    skill_count: int = 0
    available_skill_count: int = 0
    unavailable_skill_ids: list[str] = Field(default_factory=list)
    recommended_template_id: Optional[str] = None
    recommended_swarm_blueprint_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    source: str = "orchestra-research"


class SwarmBlueprintRoleResponse(BaseModel):
    id: str
    title: str
    bundle_id: str
    goal: str


class SwarmBlueprintResponse(BaseModel):
    id: str
    name: str
    summary: str
    description: str
    roles: list[SwarmBlueprintRoleResponse] = Field(default_factory=list)
    recommended_min_agents: int = 1
    recommended_max_agents: int = 1
    coordination_notes: str
    tags: list[str] = Field(default_factory=list)


class StarterDeploymentCreate(BaseModel):
    name: str = Field(default="Personal Assistant", min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    replicas: int = Field(default=1, ge=1, le=10)
    model: Optional[str] = Field(default=None, min_length=1, max_length=255)
    assistant_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    workspace: Optional[str] = Field(default=None, min_length=1, max_length=255)
    skills: list[str] = Field(default_factory=list)
    channels: dict[str, OpenClawChannelConfig] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class StarterDeploymentResponse(BaseModel):
    template_id: str
    agent: AgentResponse
    deployment: DeploymentResponse


class AssistantSkillResponse(BaseModel):
    id: str
    name: str
    description: str
    author: str
    category: str
    source: str
    is_official: bool = False
    # ``installed`` is retained for compatibility and now means runtime activation is proven.
    installed: bool = False
    configured: bool = False
    runtime_ready: bool = False
    status: Literal["available", "configured", "runtime_ready", "unavailable", "failed"] = (
        "available"
    )
    reconciliation_required: bool = False
    status_detail: str = "Available to configure; runtime activation has not been requested."
    reconciliation_error: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    path: Optional[str] = None
    canonical_name: Optional[str] = None
    upstream_path: Optional[str] = None
    upstream_repo: Optional[str] = None
    upstream_commit: Optional[str] = None
    license: Optional[str] = None
    available: bool = True


class AssistantChannelResponse(BaseModel):
    id: str
    label: str
    enabled: bool
    mode: str
    allow_from: list[str] = Field(default_factory=list)


class AssistantWakeupResponse(BaseModel):
    enabled: bool
    schedule: Optional[str] = None
    timezone: Optional[str] = None
    label: Optional[str] = None


class AssistantHealthResponse(BaseModel):
    status: str
    cli_available: Optional[bool] = None
    gateway_configured: Optional[bool] = None
    gateway_reachable: Optional[bool] = None
    gateway_port: Optional[int] = None
    gateway_url: Optional[str] = None
    credential_detected: Optional[bool] = None
    config_path: Optional[str] = None
    state_dir: Optional[str] = None
    doctor_summary: str


class AssistantSessionResponse(BaseModel):
    id: str
    key: str
    agent: str
    kind: str
    age: str
    model: str
    tokens: str
    channel: str
    flags: list[str] = Field(default_factory=list)
    active: bool
    start_time: int
    last_activity: int
    source: str


class AssistantOverviewResponse(BaseModel):
    agent_id: uuid.UUID
    name: str
    description: Optional[str] = None
    runtime: str
    template_id: str
    status: str
    onboarding_status: str
    assistant_id: str
    workspace: str
    last_activity: Optional[datetime] = None
    session_count: int = 0
    installed_skills: list[AssistantSkillResponse] = Field(default_factory=list)
    channels: list[AssistantChannelResponse] = Field(default_factory=list)
    wakeups: list[AssistantWakeupResponse] = Field(default_factory=list)
    gateway: AssistantHealthResponse
    deployments: list[DeploymentResponse] = Field(default_factory=list)
    config: OpenClawAgentConfig | dict[str, Any]


class AssistantOverviewEnvelope(BaseModel):
    has_assistant: bool
    recommended_template_id: str = "personal_assistant"
    assistant: Optional[AssistantOverviewResponse] = None


class ProviderOptionResponse(BaseModel):
    id: str
    label: str
    summary: str
    enabled: bool = False
    cue: str | None = None


class OnboardingStepResponse(BaseModel):
    id: str
    title: str
    completed: bool = False


class OnboardingStateResponse(BaseModel):
    provider: str = "openclaw"
    status: str
    action_type: str | None = None
    import_source: dict[str, Any] = Field(default_factory=dict)
    current_step: str
    completed_steps: list[str] = Field(default_factory=list)
    failed_step: str | None = None
    last_error: str | None = None
    checklist_dismissed: bool = False
    assistant_name: str | None = None
    assistant_id: str | None = None
    workspace: str | None = None
    gateway_url: str | None = None
    updated_at: datetime | None = None
    steps: list[OnboardingStepResponse] = Field(default_factory=list)
    providers: list[ProviderOptionResponse] = Field(default_factory=list)


class OnboardingUpdateRequest(BaseModel):
    action: str = Field(..., min_length=1, max_length=64)
    provider: str = Field(default="openclaw", min_length=1, max_length=64)
    step: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class RuntimeProviderSnapshotUpsert(BaseModel):
    provider: str = Field(default="openclaw", min_length=1, max_length=64)
    runtime_key: str = Field(default="openclaw", min_length=1, max_length=64)
    label: str = Field(default="OpenClaw", min_length=1, max_length=120)
    cue: str | None = Field(default=None, max_length=8)
    provider_root: str | None = None
    wizard_state_path: str | None = None
    binary_path: str | None = None
    binary_confirmed: bool = False
    home_path: str | None = None
    home_source: str | None = Field(default=None, max_length=64)
    config_path: str | None = None
    state_dir: str | None = None
    install_method: str | None = Field(default=None, max_length=32)
    installation_disposition: str | None = Field(default=None, max_length=64)
    tracking_mode: str | None = Field(default=None, max_length=64)
    imported_into_mutx: bool = False
    adopted_existing_runtime: bool = False
    keys_remain_local: bool = False
    credential_sync_policy: str | None = Field(default=None, max_length=64)
    privacy_summary: str | None = Field(default=None, max_length=1000)
    last_action_type: str | None = Field(default=None, max_length=64)
    import_source: dict[str, Any] = Field(default_factory=dict)
    version: str | None = Field(default=None, max_length=255)
    status: str = Field(default="unknown", max_length=64)
    gateway: dict[str, Any] = Field(default_factory=dict)
    gateway_url: str | None = None
    gateway_port: int | None = None
    last_seen_at: datetime | None = None
    last_synced_at: datetime | None = None
    binding_count: int = Field(default=0, ge=0)
    current_binding: dict[str, Any] | None = None
    bindings: list[dict[str, Any]] = Field(default_factory=list)
    observed_source: str = Field(default="local", max_length=64)


class RuntimeProviderSnapshotResponse(RuntimeProviderSnapshotUpsert):
    stale: bool = False
    stale_after_seconds: int = 900


# API Key Schemas
class APIKeyCreate(BaseModel):
    name: str
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class APIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    last_used: Optional[datetime]
    created_at: datetime
    expires_at: Optional[datetime]
    is_active: bool


class APIKeyCreateResponse(BaseModel):
    """Response containing the newly created API key - only shown once!"""

    id: uuid.UUID
    name: str
    key: str  # The plain API key - only returned on creation
    created_at: datetime
    expires_at: Optional[datetime]


# Webhook Schemas
class WebhookCreate(BaseModel):
    """Request model for creating a webhook"""

    url: str = Field(
        ..., max_length=512, min_length=1, description="The URL to receive webhook events"
    )
    name: Optional[str] = Field(
        None, max_length=120, description="Optional human-readable name for the webhook"
    )
    events: list[str] = Field(
        default_factory=lambda: ["*"],
        description="List of events to subscribe to (e.g., 'agent.status', 'deployment.*', '*' for all)",
    )
    secret: Optional[str] = Field(
        None, max_length=64, description="Optional secret for signature verification"
    )
    is_active: bool = Field(True, description="Whether the webhook should be active immediately")


class WebhookUpdate(BaseModel):
    url: Optional[str] = Field(None, max_length=512)
    name: Optional[str] = Field(None, max_length=120)
    events: Optional[list[str]] = None
    is_active: Optional[bool] = None
    reset_circuit: Optional[bool] = Field(
        None, description="Set to true to reset the circuit breaker and re-enable delivery"
    )


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: Optional[str] = None
    url: str
    events: list[str]
    secret: Optional[str] = Field(
        default=None,
        description="Always null. Webhook secrets are write-only and never returned after creation.",
    )
    has_secret: bool = False
    is_active: bool
    circuit_open: bool = False
    consecutive_failures: int = 0
    created_at: datetime
    # Aggregate delivery stats (populated when requested)
    total_deliveries: Optional[int] = None
    successful_deliveries: Optional[int] = None
    failed_deliveries: Optional[int] = None


class WebhookDelivery(BaseModel):
    """Schema for webhook delivery attempts"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    webhook_id: uuid.UUID
    event: str
    payload: str
    status_code: Optional[int]
    response_body: Optional[str] = None
    success: bool
    error_message: Optional[str]
    attempts: int
    duration_ms: Optional[int] = None
    parent_delivery_id: Optional[uuid.UUID] = None
    created_at: datetime
    delivered_at: Optional[datetime]


class WebhookRetryRequest(BaseModel):
    """Request body for manually retrying a delivery."""

    delivery_id: uuid.UUID = Field(..., description="ID of the original delivery to retry")


class WebhookListResponse(BaseModel):
    """Paginated response for listing webhooks."""

    items: list[WebhookResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool


class WebhookDeliveryListResponse(BaseModel):
    """Paginated response for listing webhook deliveries."""

    webhook_id: uuid.UUID
    items: list[WebhookDelivery] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool
    event: Optional[str] = None
    success: Optional[bool] = None


class WaitlistSignupCreate(BaseModel):
    email: EmailStr
    source: Optional[str] = None


class WaitlistSignupResponse(BaseModel):
    success: bool = True
    message: str
    duplicate: bool = False


class WaitlistCountResponse(BaseModel):
    count: int


# Lead Schemas
class LeadCreate(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    name: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    message: Optional[str] = Field(None, max_length=2000)
    source: Optional[str] = Field(None, max_length=120)
    tier: Optional[str] = Field(None, max_length=50)
    interest: Optional[str] = Field(None, max_length=80)
    locale: Optional[str] = Field(None, max_length=16, pattern=r"^[a-zA-Z]{2}(?:-[a-zA-Z]{2})?$")
    product_updates_consent: bool = False


class LeadUpdate(BaseModel):
    email: Optional[EmailStr] = Field(None, max_length=255)
    name: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    message: Optional[str] = Field(None, max_length=2000)
    source: Optional[str] = Field(None, max_length=120)
    tier: Optional[str] = Field(None, max_length=50)
    interest: Optional[str] = Field(None, max_length=80)
    locale: Optional[str] = Field(None, max_length=16, pattern=r"^[a-zA-Z]{2}(?:-[a-zA-Z]{2})?$")
    product_updates_consent: Optional[bool] = None


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: Optional[str]
    company: Optional[str]
    message: Optional[str]
    source: Optional[str]
    tier: Optional[str]
    interest: Optional[str]
    locale: Optional[str]
    product_updates_consent: bool
    notification_scheduled_at: Optional[datetime]
    created_at: datetime


class LeadCaptureResponse(LeadResponse):
    success: bool = True
    status: Literal["accepted"] = "accepted"
    persisted: bool = True
    replayed: bool = False
    notification_scheduled: bool
    follow_up: Literal["best-effort", "unavailable"]
    message_to_submitter: str


class LeadListResponse(BaseModel):
    """Paginated response for listing leads."""

    items: list[LeadResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool


class APIKeyHistoryResponse(BaseModel):
    """Paginated response for listing API keys."""

    items: list[APIKeyResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    has_more: bool


# Usage Event Schemas
class UsageEventCreate(BaseModel):
    """Request model for creating a usage event"""

    event_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of usage event (e.g., api_call, agent_run, deployment)",
    )
    resource_type: Optional[str] = Field(
        None,
        max_length=100,
        description="Type of resource that was used",
    )
    resource_id: Optional[str] = Field(None, max_length=255, description="Resource that was used")
    credits_used: NonNegativeFiniteFloat = Field(1.0, description="Credits consumed by this event")
    metadata: Optional[FiniteJsonDict] = Field(
        default_factory=dict, description="Additional event metadata"
    )


class UsageEventResponse(DegradedNumericResponseModel):
    """Response model for usage events"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    user_id: uuid.UUID
    resource_type: Optional[str]
    resource_id: Optional[str]
    credits_used: Optional[float]
    event_metadata: Optional[str] = None  # JSON string from DB
    created_at: datetime

    @computed_field
    @property
    def metadata(self) -> Optional[dict]:
        """Deserialize event_metadata JSON string to dict"""
        if self.event_metadata:
            try:
                import json

                return json.loads(self.event_metadata)
            except (json.JSONDecodeError, TypeError):
                return None
        return None


# Analytics & Monitoring Schemas
class AnalyticsSummaryResponse(BaseModel):
    total_agents: int
    active_agents: int
    total_deployments: int
    active_deployments: int
    total_runs: int
    successful_runs: int
    failed_runs: int
    total_api_calls: int
    avg_latency_ms: Optional[float]
    period_start: datetime
    period_end: datetime
    incomplete: bool = False


class AgentMetricsSummary(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    avg_cpu: Optional[float]
    avg_memory: Optional[float]
    total_requests: int
    avg_latency_ms: Optional[float]
    period_start: datetime
    period_end: datetime
    incomplete: bool = False


class AnalyticsTimeSeries(BaseModel):
    timestamp: datetime
    value: Optional[float]
    label: Optional[str] = None


class AnalyticsTimeSeriesResponse(BaseModel):
    metric: str
    interval: str
    data: list[AnalyticsTimeSeries]
    period_start: datetime
    period_end: datetime
    incomplete: bool = False


class CostSummaryResponse(BaseModel):
    total_credits_used: float
    credits_remaining: float
    credits_total: float
    usage_by_event_type: dict[str, float]
    usage_by_agent: dict[str, float]
    period_start: datetime
    period_end: datetime


class BudgetResponse(BaseModel):
    user_id: uuid.UUID
    plan: str
    credits_total: float
    credits_used: float
    credits_remaining: float
    reset_date: datetime
    usage_percentage: float
