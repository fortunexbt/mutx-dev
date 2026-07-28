from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


@dataclass(slots=True)
class CLIStatus:
    api_url: str
    config_path: Path
    api_url_source: str
    authenticated: bool
    has_access_token: bool
    has_refresh_token: bool

    @property
    def has_api_key(self) -> bool:
        return self.has_access_token


@dataclass(slots=True)
class UserProfile:
    email: str
    name: str
    plan: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "UserProfile":
        return cls(
            email=str(payload.get("email", "")),
            name=str(payload.get("name", "")),
            plan=str(payload.get("plan", "")),
        )


@dataclass(slots=True)
class DeploymentEventRecord:
    id: str
    deployment_id: str
    event_type: str
    status: str
    node_id: str | None
    error_message: str | None
    created_at: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeploymentEventRecord":
        return cls(
            id=str(payload.get("id", "")),
            deployment_id=str(payload.get("deployment_id", "")),
            event_type=str(payload.get("event_type", "unknown")),
            status=str(payload.get("status", "unknown")),
            node_id=_as_optional_str(payload.get("node_id")),
            error_message=_as_optional_str(payload.get("error_message")),
            created_at=_as_optional_str(payload.get("created_at")),
        )


@dataclass(slots=True)
class LogEntry:
    id: str
    agent_id: str
    level: str
    message: str
    extra_data: str | None
    timestamp: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LogEntry":
        return cls(
            id=str(payload.get("id", "")),
            agent_id=str(payload.get("agent_id", "")),
            level=str(payload.get("level", "unknown")),
            message=str(payload.get("message", "")),
            extra_data=_as_optional_str(payload.get("extra_data")),
            timestamp=_as_optional_str(payload.get("timestamp")),
        )


@dataclass(slots=True)
class MetricPoint:
    id: str
    agent_id: str
    cpu_usage: float | None
    memory_usage: float | None
    timestamp: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MetricPoint":
        cpu_usage = payload.get("cpu_usage")
        memory_usage = payload.get("memory_usage")
        return cls(
            id=str(payload.get("id", "")),
            agent_id=str(payload.get("agent_id", "")),
            cpu_usage=float(cpu_usage) if isinstance(cpu_usage, (int, float)) else None,
            memory_usage=float(memory_usage) if isinstance(memory_usage, (int, float)) else None,
            timestamp=_as_optional_str(payload.get("timestamp")),
        )


@dataclass(slots=True)
class DeploymentRecord:
    id: str
    agent_id: str
    status: str
    version: str | None
    replicas: int
    node_id: str | None
    started_at: str | None
    ended_at: str | None
    error_message: str | None
    events: list[DeploymentEventRecord] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeploymentRecord":
        raw_events = payload.get("events") or []
        return cls(
            id=str(payload.get("id", "")),
            agent_id=str(payload.get("agent_id", "")),
            status=str(payload.get("status", "unknown")),
            version=_as_optional_str(payload.get("version")),
            replicas=int(payload.get("replicas", 1)),
            node_id=_as_optional_str(payload.get("node_id")),
            started_at=_as_optional_str(payload.get("started_at")),
            ended_at=_as_optional_str(payload.get("ended_at")),
            error_message=_as_optional_str(payload.get("error_message")),
            events=[
                DeploymentEventRecord.from_payload(item)
                for item in raw_events
                if isinstance(item, dict)
            ],
        )


@dataclass(slots=True)
class DeploymentEventHistory:
    deployment_id: str
    deployment_status: str
    items: list[DeploymentEventRecord]
    total: int
    skip: int
    limit: int
    event_type: str | None
    status_filter: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeploymentEventHistory":
        raw_items = payload.get("items") or []
        return cls(
            deployment_id=str(payload.get("deployment_id", "")),
            deployment_status=str(payload.get("deployment_status", "unknown")),
            items=[
                DeploymentEventRecord.from_payload(item)
                for item in raw_items
                if isinstance(item, dict)
            ],
            total=int(payload.get("total", 0)),
            skip=int(payload.get("skip", 0)),
            limit=int(payload.get("limit", 0)),
            event_type=_as_optional_str(payload.get("event_type")),
            status_filter=_as_optional_str(payload.get("status")),
        )


@dataclass(slots=True)
class DeploymentVersionRecord:
    id: str
    deployment_id: str
    version: int
    config_snapshot: dict[str, Any] | str | None
    status: str
    created_at: str | None
    rolled_back_at: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeploymentVersionRecord":
        raw_config_snapshot = payload.get("config_snapshot")
        config_snapshot: dict[str, Any] | str | None
        if isinstance(raw_config_snapshot, dict):
            config_snapshot = raw_config_snapshot
        elif raw_config_snapshot is None:
            config_snapshot = None
        else:
            config_snapshot = str(raw_config_snapshot)

        return cls(
            id=str(payload.get("id", "")),
            deployment_id=str(payload.get("deployment_id", "")),
            version=int(payload.get("version", 0)),
            config_snapshot=config_snapshot,
            status=str(payload.get("status", "unknown")),
            created_at=_as_optional_str(payload.get("created_at")),
            rolled_back_at=_as_optional_str(payload.get("rolled_back_at")),
        )


@dataclass(slots=True)
class DeploymentVersionHistory:
    deployment_id: str
    items: list[DeploymentVersionRecord]
    total: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeploymentVersionHistory":
        raw_items = payload.get("items") or []
        return cls(
            deployment_id=str(payload.get("deployment_id", "")),
            items=[
                DeploymentVersionRecord.from_payload(item)
                for item in raw_items
                if isinstance(item, dict)
            ],
            total=int(payload.get("total", 0)),
        )


@dataclass(slots=True)
class AgentRecord:
    id: str
    name: str
    description: str | None
    type: str
    status: str
    config: dict[str, Any] | str | None
    config_version: int
    created_at: str | None
    updated_at: str | None
    user_id: str | None
    deployments: list[DeploymentRecord] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AgentRecord":
        raw_deployments = payload.get("deployments") or []
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            description=_as_optional_str(payload.get("description")),
            type=str(payload.get("type", "")),
            status=str(payload.get("status", "unknown")),
            config=payload.get("config"),
            config_version=int(payload.get("config_version", 1)),
            created_at=_as_optional_str(payload.get("created_at")),
            updated_at=_as_optional_str(payload.get("updated_at")),
            user_id=_as_optional_str(payload.get("user_id")),
            deployments=[
                DeploymentRecord.from_payload(item)
                for item in raw_deployments
                if isinstance(item, dict)
            ],
        )


@dataclass(slots=True)
class AgentDeploymentResult:
    deployment_id: str | None
    status: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AgentDeploymentResult":
        return cls(
            deployment_id=_as_optional_str(payload.get("deployment_id")),
            status=_as_optional_str(payload.get("status")),
        )


@dataclass(slots=True)
class TemplateRecord:
    id: str
    name: str
    summary: str
    description: str
    agent_type: str
    starter_prompt: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TemplateRecord":
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            summary=str(payload.get("summary", "")),
            description=str(payload.get("description", "")),
            agent_type=str(payload.get("agent_type", "")),
            starter_prompt=str(payload.get("starter_prompt", "")),
        )


@dataclass(slots=True)
class AssistantSkillRecord:
    id: str
    name: str
    description: str
    author: str
    category: str
    source: str
    installed: bool
    configured: bool
    runtime_ready: bool
    status: str
    reconciliation_required: bool
    status_detail: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AssistantSkillRecord":
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            author=str(payload.get("author", "")),
            category=str(payload.get("category", "")),
            source=str(payload.get("source", "")),
            installed=bool(payload.get("installed", False)),
            configured=bool(payload.get("configured", False)),
            runtime_ready=bool(payload.get("runtime_ready", payload.get("installed", False))),
            status=str(payload.get("status", "available")),
            reconciliation_required=bool(payload.get("reconciliation_required", False)),
            status_detail=str(payload.get("status_detail", "")),
        )


@dataclass(slots=True)
class AssistantChannelRecord:
    id: str
    label: str
    enabled: bool
    mode: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AssistantChannelRecord":
        return cls(
            id=str(payload.get("id", "")),
            label=str(payload.get("label", "")),
            enabled=bool(payload.get("enabled", False)),
            mode=str(payload.get("mode", "")),
        )


@dataclass(slots=True)
class AssistantHealthRecord:
    status: str
    cli_available: bool
    gateway_configured: bool
    gateway_reachable: bool
    installed: bool = False
    onboarded: bool = False
    gateway_port: int | None = None
    gateway_url: str | None = None
    credential_detected: bool = False
    config_path: str | None = None
    state_dir: str | None = None
    doctor_summary: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AssistantHealthRecord":
        return cls(
            status=str(payload.get("status", "unknown")),
            cli_available=bool(payload.get("cli_available", False)),
            gateway_configured=bool(payload.get("gateway_configured", False)),
            gateway_reachable=bool(payload.get("gateway_reachable", False)),
            installed=bool(payload.get("installed", payload.get("cli_available", False))),
            onboarded=bool(payload.get("onboarded", payload.get("gateway_configured", False))),
            gateway_port=int(payload["gateway_port"]) if payload.get("gateway_port") else None,
            gateway_url=_as_optional_str(payload.get("gateway_url")),
            credential_detected=bool(payload.get("credential_detected", False)),
            config_path=_as_optional_str(payload.get("config_path")),
            state_dir=_as_optional_str(payload.get("state_dir")),
            doctor_summary=str(payload.get("doctor_summary", "")),
        )


@dataclass(slots=True)
class AssistantOverviewRecord:
    agent_id: str
    name: str
    status: str
    onboarding_status: str
    assistant_id: str
    workspace: str
    session_count: int
    gateway: AssistantHealthRecord
    deployments: list[DeploymentRecord]
    installed_skills: list[AssistantSkillRecord]
    channels: list[AssistantChannelRecord]
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AssistantOverviewRecord":
        return cls(
            agent_id=str(payload.get("agent_id", "")),
            name=str(payload.get("name", "")),
            status=str(payload.get("status", "unknown")),
            onboarding_status=str(payload.get("onboarding_status", "unknown")),
            assistant_id=str(payload.get("assistant_id", "")),
            workspace=str(payload.get("workspace", "")),
            session_count=int(payload.get("session_count", 0)),
            gateway=AssistantHealthRecord.from_payload(payload.get("gateway") or {}),
            deployments=[
                DeploymentRecord.from_payload(item)
                for item in (payload.get("deployments") or [])
                if isinstance(item, dict)
            ],
            installed_skills=[
                AssistantSkillRecord.from_payload(item)
                for item in (payload.get("installed_skills") or [])
                if isinstance(item, dict)
            ],
            channels=[
                AssistantChannelRecord.from_payload(item)
                for item in (payload.get("channels") or [])
                if isinstance(item, dict)
            ],
            config=payload.get("config") if isinstance(payload.get("config"), dict) else {},
        )


@dataclass(slots=True)
class RuntimeProviderRecord:
    provider: str
    label: str
    status: str
    last_seen_at: str | None
    stale: bool
    install_method: str | None
    gateway_url: str | None
    binding_count: int
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RuntimeProviderRecord":
        return cls(
            provider=str(payload.get("provider", "")),
            label=str(payload.get("label", "")),
            status=str(payload.get("status", "unknown")),
            last_seen_at=_as_optional_str(payload.get("last_seen_at")),
            stale=bool(payload.get("stale", False)),
            install_method=_as_optional_str(payload.get("install_method")),
            gateway_url=_as_optional_str(payload.get("gateway_url")),
            binding_count=int(payload.get("binding_count", 0)),
            payload=payload,
        )


@dataclass(slots=True)
class OnboardingStateRecord:
    provider: str
    status: str
    current_step: str
    completed_steps: list[str]
    failed_step: str | None
    last_error: str | None
    checklist_dismissed: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    providers: list[dict[str, Any]] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OnboardingStateRecord":
        return cls(
            provider=str(payload.get("provider", "openclaw")),
            status=str(payload.get("status", "unknown")),
            current_step=str(payload.get("current_step", "")),
            completed_steps=[str(item) for item in (payload.get("completed_steps") or [])],
            failed_step=_as_optional_str(payload.get("failed_step")),
            last_error=_as_optional_str(payload.get("last_error")),
            checklist_dismissed=bool(payload.get("checklist_dismissed", False)),
            steps=[dict(item) for item in (payload.get("steps") or []) if isinstance(item, dict)],
            providers=[
                dict(item) for item in (payload.get("providers") or []) if isinstance(item, dict)
            ],
            payload=payload,
        )


@dataclass(slots=True)
class DocumentTemplateFieldRecord:
    name: str
    type: str
    required: bool
    accepts_multiple: bool
    description: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DocumentTemplateFieldRecord":
        return cls(
            name=str(payload.get("name", "")),
            type=str(payload.get("type", "")),
            required=bool(payload.get("required", True)),
            accepts_multiple=bool(payload.get("accepts_multiple", False)),
            description=str(payload.get("description", "")),
        )


@dataclass(slots=True)
class DocumentTemplateOutputRecord:
    role: str
    kind: str
    description: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DocumentTemplateOutputRecord":
        return cls(
            role=str(payload.get("role", "")),
            kind=str(payload.get("kind", "")),
            description=str(payload.get("description", "")),
        )


@dataclass(slots=True)
class DocumentTemplateRecord:
    id: str
    name: str
    summary: str
    description: str
    supports_managed: bool
    supports_local: bool
    inputs: list[DocumentTemplateFieldRecord] = field(default_factory=list)
    outputs: list[DocumentTemplateOutputRecord] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DocumentTemplateRecord":
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            summary=str(payload.get("summary", "")),
            description=str(payload.get("description", "")),
            supports_managed=bool(payload.get("supports_managed", True)),
            supports_local=bool(payload.get("supports_local", True)),
            inputs=[
                DocumentTemplateFieldRecord.from_payload(item)
                for item in (payload.get("inputs") or [])
                if isinstance(item, dict)
            ],
            outputs=[
                DocumentTemplateOutputRecord.from_payload(item)
                for item in (payload.get("outputs") or [])
                if isinstance(item, dict)
            ],
        )


@dataclass(slots=True)
class DocumentArtifactRecord:
    id: str
    job_id: str
    role: str
    kind: str
    storage_backend: str
    storage_uri: str | None
    local_path: str | None
    filename: str
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DocumentArtifactRecord":
        raw_metadata = payload.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        return cls(
            id=str(payload.get("id", "")),
            job_id=str(payload.get("job_id", "")),
            role=str(payload.get("role", "")),
            kind=str(payload.get("kind", "")),
            storage_backend=str(payload.get("storage_backend", "")),
            storage_uri=_as_optional_str(payload.get("storage_uri")),
            local_path=_as_optional_str(payload.get("local_path")),
            filename=str(payload.get("filename", "")),
            content_type=_as_optional_str(payload.get("content_type")),
            size_bytes=(
                int(payload["size_bytes"]) if payload.get("size_bytes") is not None else None
            ),
            sha256=_as_optional_str(payload.get("sha256")),
            metadata=metadata,
            created_at=_as_optional_str(payload.get("created_at")),
            updated_at=_as_optional_str(payload.get("updated_at")),
        )


@dataclass(slots=True)
class DocumentJobRecord:
    id: str
    run_id: str
    template_id: str
    execution_mode: str
    status: str
    parameters: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    claimed_by: str | None = None
    claimed_at: str | None = None
    last_heartbeat_at: str | None = None
    attempts: int = 0
    dispatched_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    artifacts: list[DocumentArtifactRecord] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DocumentJobRecord":
        return cls(
            id=str(payload.get("id", "")),
            run_id=str(payload.get("run_id", "")),
            template_id=str(payload.get("template_id", "")),
            execution_mode=str(payload.get("execution_mode", "")),
            status=str(payload.get("status", "unknown")),
            parameters=(
                payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
            ),
            result_summary=(
                payload.get("result_summary")
                if isinstance(payload.get("result_summary"), dict)
                else {}
            ),
            error_message=_as_optional_str(payload.get("error_message")),
            claimed_by=_as_optional_str(payload.get("claimed_by")),
            claimed_at=_as_optional_str(payload.get("claimed_at")),
            last_heartbeat_at=_as_optional_str(payload.get("last_heartbeat_at")),
            attempts=int(payload.get("attempts", 0)),
            dispatched_at=_as_optional_str(payload.get("dispatched_at")),
            completed_at=_as_optional_str(payload.get("completed_at")),
            created_at=_as_optional_str(payload.get("created_at")),
            updated_at=_as_optional_str(payload.get("updated_at")),
            artifacts=[
                DocumentArtifactRecord.from_payload(item)
                for item in (payload.get("artifacts") or [])
                if isinstance(item, dict)
            ],
        )


@dataclass(slots=True)
class DocumentJobHistoryRecord:
    items: list[DocumentJobRecord]
    total: int
    skip: int
    limit: int
    status: str | None
    template_id: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DocumentJobHistoryRecord":
        return cls(
            items=[
                DocumentJobRecord.from_payload(item)
                for item in (payload.get("items") or [])
                if isinstance(item, dict)
            ],
            total=int(payload.get("total", 0)),
            skip=int(payload.get("skip", 0)),
            limit=int(payload.get("limit", 0)),
            status=_as_optional_str(payload.get("status")),
            template_id=_as_optional_str(payload.get("template_id")),
        )


@dataclass(slots=True)
class DocumentLocalLaunchRecord:
    job_id: str
    template_id: str
    execution_mode: str
    manifest: dict[str, Any] = field(default_factory=dict)
    artifacts: list[DocumentArtifactRecord] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DocumentLocalLaunchRecord":
        return cls(
            job_id=str(payload.get("job_id", "")),
            template_id=str(payload.get("template_id", "")),
            execution_mode=str(payload.get("execution_mode", "")),
            manifest=payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {},
            artifacts=[
                DocumentArtifactRecord.from_payload(item)
                for item in (payload.get("artifacts") or [])
                if isinstance(item, dict)
            ],
        )


@dataclass(slots=True)
class ReasoningTemplateRecord:
    id: str
    name: str
    summary: str
    description: str
    supports_managed: bool
    supports_local: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReasoningTemplateRecord":
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            summary=str(payload.get("summary", "")),
            description=str(payload.get("description", "")),
            supports_managed=bool(payload.get("supports_managed", True)),
            supports_local=bool(payload.get("supports_local", True)),
        )


@dataclass(slots=True)
class ReasoningArtifactRecord:
    id: str
    job_id: str
    role: str
    kind: str
    storage_backend: str
    storage_uri: str | None
    local_path: str | None
    filename: str
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReasoningArtifactRecord":
        raw_metadata = payload.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        return cls(
            id=str(payload.get("id", "")),
            job_id=str(payload.get("job_id", "")),
            role=str(payload.get("role", "")),
            kind=str(payload.get("kind", "")),
            storage_backend=str(payload.get("storage_backend", "")),
            storage_uri=_as_optional_str(payload.get("storage_uri")),
            local_path=_as_optional_str(payload.get("local_path")),
            filename=str(payload.get("filename", "")),
            content_type=_as_optional_str(payload.get("content_type")),
            size_bytes=(
                int(payload["size_bytes"]) if payload.get("size_bytes") is not None else None
            ),
            sha256=_as_optional_str(payload.get("sha256")),
            metadata=metadata,
            created_at=_as_optional_str(payload.get("created_at")),
            updated_at=_as_optional_str(payload.get("updated_at")),
        )


@dataclass(slots=True)
class ReasoningJobRecord:
    id: str
    run_id: str
    template_id: str
    execution_mode: str
    status: str
    parameters: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    claimed_by: str | None = None
    claimed_at: str | None = None
    last_heartbeat_at: str | None = None
    attempts: int = 0
    dispatched_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    artifacts: list[ReasoningArtifactRecord] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReasoningJobRecord":
        return cls(
            id=str(payload.get("id", "")),
            run_id=str(payload.get("run_id", "")),
            template_id=str(payload.get("template_id", "")),
            execution_mode=str(payload.get("execution_mode", "")),
            status=str(payload.get("status", "unknown")),
            parameters=(
                payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
            ),
            result_summary=(
                payload.get("result_summary")
                if isinstance(payload.get("result_summary"), dict)
                else {}
            ),
            error_message=_as_optional_str(payload.get("error_message")),
            claimed_by=_as_optional_str(payload.get("claimed_by")),
            claimed_at=_as_optional_str(payload.get("claimed_at")),
            last_heartbeat_at=_as_optional_str(payload.get("last_heartbeat_at")),
            attempts=int(payload.get("attempts", 0)),
            dispatched_at=_as_optional_str(payload.get("dispatched_at")),
            completed_at=_as_optional_str(payload.get("completed_at")),
            created_at=_as_optional_str(payload.get("created_at")),
            updated_at=_as_optional_str(payload.get("updated_at")),
            artifacts=[
                ReasoningArtifactRecord.from_payload(item)
                for item in (payload.get("artifacts") or [])
                if isinstance(item, dict)
            ],
        )


@dataclass(slots=True)
class ReasoningJobHistoryRecord:
    items: list[ReasoningJobRecord]
    total: int
    skip: int
    limit: int
    status: str | None
    template_id: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReasoningJobHistoryRecord":
        return cls(
            items=[
                ReasoningJobRecord.from_payload(item)
                for item in (payload.get("items") or [])
                if isinstance(item, dict)
            ],
            total=int(payload.get("total", 0)),
            skip=int(payload.get("skip", 0)),
            limit=int(payload.get("limit", 0)),
            status=_as_optional_str(payload.get("status")),
            template_id=_as_optional_str(payload.get("template_id")),
        )


@dataclass(slots=True)
class ReasoningLocalLaunchRecord:
    job_id: str
    template_id: str
    execution_mode: str
    manifest: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ReasoningArtifactRecord] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReasoningLocalLaunchRecord":
        return cls(
            job_id=str(payload.get("job_id", "")),
            template_id=str(payload.get("template_id", "")),
            execution_mode=str(payload.get("execution_mode", "")),
            manifest=payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {},
            artifacts=[
                ReasoningArtifactRecord.from_payload(item)
                for item in (payload.get("artifacts") or [])
                if isinstance(item, dict)
            ],
        )
