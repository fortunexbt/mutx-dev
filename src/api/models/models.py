from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.api.models.subscription import Payment, Subscription
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY as PG_ARRAY
import enum

from src.api.database import Base


def ARRAY(type_):
    """
    Polymorphic ARRAY type that works with both PostgreSQL and SQLite (as JSON string).
    """
    from sqlalchemy.types import TypeDecorator, TEXT
    import json

    class ArrayType(TypeDecorator):
        impl = TEXT
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == "postgresql":
                return dialect.type_descriptor(PG_ARRAY(type_))
            else:
                return dialect.type_descriptor(TEXT())

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if dialect.name == "postgresql":
                return value
            return json.dumps(value, allow_nan=False)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if dialect.name == "postgresql":
                return value
            return json.loads(value)

    return ArrayType()


def JSONText():
    """
    Store JSON-compatible Python values in a text column.
    """
    from sqlalchemy.types import TypeDecorator, TEXT
    import json

    class JSONTextType(TypeDecorator):
        impl = TEXT
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return json.dumps(value, allow_nan=False)

        def process_result_value(self, value, dialect):
            if value is None or isinstance(value, (dict, list)):
                return value
            try:
                return json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return None

    return JSONTextType()


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


class AlertType(str, enum.Enum):
    CPU_HIGH = "cpu_high"
    MEMORY_HIGH = "memory_high"
    AGENT_DOWN = "agent_down"
    DEPLOYMENT_FAILED = "deployment_failed"
    QUOTA_EXCEEDED = "quota_exceeded"


class AgentStatus(str, enum.Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    DELETING = "deleting"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    plan: Mapped[str] = mapped_column(String(20), default="FREE")
    # Database roles are the authorization authority. Signup and SSO flows use
    # this least-privilege default and never promote users from token claims.
    roles: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=lambda: ["VIEWER"],
        server_default='["VIEWER"]',
    )
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Email verification fields
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verification_token: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    email_verification_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    # Password reset fields
    password_reset_token: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    password_reset_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    agents: Mapped[list["Agent"]] = relationship(
        "Agent", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_token_sessions: Mapped[list["RefreshTokenSession"]] = relationship(
        "RefreshTokenSession", back_populates="user", cascade="all, delete-orphan"
    )
    external_auth_identities: Mapped[list["ExternalAuthIdentity"]] = relationship(
        "ExternalAuthIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    settings: Mapped[list["UserSetting"]] = relationship(
        "UserSetting", back_populates="user", cascade="all, delete-orphan"
    )
    webhooks: Mapped[list["Webhook"]] = relationship(
        "Webhook", back_populates="user", cascade="all, delete-orphan"
    )
    runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun", back_populates="user", cascade="all, delete-orphan"
    )
    document_jobs: Mapped[list["DocumentJob"]] = relationship(
        "DocumentJob", back_populates="user", cascade="all, delete-orphan"
    )
    reasoning_jobs: Mapped[list["ReasoningJob"]] = relationship(
        "ReasoningJob", back_populates="user", cascade="all, delete-orphan"
    )
    swarms: Mapped[list["Swarm"]] = relationship(
        "Swarm", back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )


class ExternalAuthIdentity(Base):
    __tablename__ = "external_auth_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_external_auth_identities_provider_user",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    profile: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONText(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User", back_populates="external_auth_identities")


class OAuthAuthorizationState(Base):
    """One-time server-side binding for OAuth and SSO authorization callbacks."""

    __tablename__ = "oauth_authorization_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    flow: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_settings_user_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONText(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User", back_populates="settings")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[AgentType] = mapped_column(SQLEnum(AgentType), default=AgentType.OPENAI)
    config: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="creating")
    api_key: Mapped[str] = mapped_column(
        String(128), nullable=True, index=True
    )  # Agent API key for self-auth
    api_key_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User", back_populates="agents")
    deployments: Mapped[list["Deployment"]] = relationship(
        "Deployment", back_populates="agent", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["Metrics"]] = relationship(
        "Metrics", back_populates="agent", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="agent", cascade="all, delete-orphan"
    )
    logs: Mapped[list["AgentLog"]] = relationship(
        "AgentLog", back_populates="agent", cascade="all, delete-orphan"
    )
    agent_metrics: Mapped[list["AgentMetric"]] = relationship(
        "AgentMetric", back_populates="agent", cascade="all, delete-orphan"
    )
    runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun", back_populates="agent", cascade="all, delete-orphan"
    )
    versions: Mapped[list["AgentVersion"]] = relationship(
        "AgentVersion", back_populates="agent", cascade="all, delete-orphan"
    )


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="current")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    rolled_back_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    agent: Mapped["Agent"] = relationship("Agent", back_populates="versions")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="pending")
    region: Mapped[str] = mapped_column(String(50), nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    replicas: Mapped[int] = mapped_column(Integer, default=1)
    node_id: Mapped[str] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    agent: Mapped["Agent"] = relationship("Agent", back_populates="deployments")
    events: Mapped[list["DeploymentEvent"]] = relationship(
        "DeploymentEvent", back_populates="deployment", cascade="all, delete-orphan"
    )
    versions: Mapped[list["DeploymentVersion"]] = relationship(
        "DeploymentVersion", back_populates="deployment", cascade="all, delete-orphan"
    )


class DeploymentEvent(Base):
    __tablename__ = "deployment_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deployments.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    node_id: Mapped[str] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    deployment: Mapped["Deployment"] = relationship("Deployment", back_populates="events")


class DeploymentVersion(Base):
    __tablename__ = "deployment_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deployments.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="current")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    rolled_back_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    deployment: Mapped["Deployment"] = relationship("Deployment", back_populates="versions")


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship("User", back_populates="api_keys")


class RefreshTokenSession(Base):
    __tablename__ = "refresh_token_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    token_jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    token_nonce: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_token_jti: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rotation_grace_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="refresh_token_sessions")


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    events: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    secret: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="webhooks")


class Metrics(Base):
    __tablename__ = "metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    cpu: Mapped[float] = mapped_column(Float, nullable=True)
    memory: Mapped[float] = mapped_column(Float, nullable=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    latency: Mapped[float] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="metrics")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    type: Mapped[AlertType] = mapped_column(SQLEnum(AlertType), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped["Agent"] = relationship("Agent", back_populates="alerts")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[str] = mapped_column(Text, nullable=True)
    meta_data: Mapped[Optional[dict]] = mapped_column(JSONText(), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="logs")


class Command(Base):
    __tablename__ = "commands"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONText(), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    result: Mapped[Optional[dict]] = mapped_column(JSONText(), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    agent: Mapped["Agent"] = relationship("Agent")


class AgentMetric(Base):
    __tablename__ = "agent_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    cpu_usage: Mapped[float] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[float] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="agent_metrics")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="completed", index=True)
    input_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    agent: Mapped[Optional["Agent"]] = relationship("Agent", back_populates="runs")
    user: Mapped["User"] = relationship("User", back_populates="runs")
    document_job: Mapped[Optional["DocumentJob"]] = relationship(
        "DocumentJob", back_populates="run", uselist=False
    )
    reasoning_job: Mapped[Optional["ReasoningJob"]] = relationship(
        "ReasoningJob", back_populates="run", uselist=False
    )
    traces: Mapped[list["AgentRunTrace"]] = relationship(
        "AgentRunTrace", back_populates="run", cascade="all, delete-orphan"
    )


class AgentRunTrace(Base):
    __tablename__ = "agent_run_traces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="traces")


class DocumentJob(Base):
    __tablename__ = "document_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False, unique=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", index=True)
    parameters: Mapped[dict | None] = mapped_column(JSONText(), nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONText(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    user: Mapped["User"] = relationship("User", back_populates="document_jobs")
    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="document_job")
    artifacts: Mapped[list["DocumentArtifact"]] = relationship(
        "DocumentArtifact", back_populates="job", cascade="all, delete-orphan"
    )


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_jobs.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    storage_backend: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONText(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    job: Mapped["DocumentJob"] = relationship("DocumentJob", back_populates="artifacts")


class ReasoningJob(Base):
    __tablename__ = "reasoning_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False, unique=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", index=True)
    parameters: Mapped[dict | None] = mapped_column(JSONText(), nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONText(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    user: Mapped["User"] = relationship("User", back_populates="reasoning_jobs")
    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="reasoning_job")
    artifacts: Mapped[list["ReasoningArtifact"]] = relationship(
        "ReasoningArtifact", back_populates="job", cascade="all, delete-orphan"
    )


class ReasoningArtifact(Base):
    __tablename__ = "reasoning_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reasoning_jobs.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    storage_backend: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONText(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    job: Mapped["ReasoningJob"] = relationship("ReasoningJob", back_populates="artifacts")


class WebhookDeliveryLog(Base):
    """Log of webhook delivery attempts"""

    __tablename__ = "webhook_delivery_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhooks.id"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parent_delivery_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    webhook: Mapped["Webhook"] = relationship("Webhook")


class WaitlistSignup(Base):
    __tablename__ = "waitlist_signups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    interest: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    locale: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    product_updates_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notification_scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


class UsageEvent(Base):
    """Track usage events for telemetry and quota enforcement"""

    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    credits_used: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    event_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    user: Mapped["User"] = relationship("User")


class AnalyticsEvent(Base):
    """Simple analytics events for usage telemetry (quick win for issue #264)"""

    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    # Event types: agent_run.started, agent_run.completed, agent_run.failed,
    # api_key.created, api_key.used, api_key.expired, user.login, user.logout
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    properties: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    user: Mapped[Optional["User"]] = relationship("User")


class AgentResourceUsage(Base):
    """Track resource usage for agents (tokens, API calls, cost)."""

    __tablename__ = "agent_resource_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    # Token usage
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    # API call tracking
    api_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Cost tracking (in USD)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    # Metadata
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extra_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    # Timestamps
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    agent: Mapped["Agent"] = relationship("Agent")


class Swarm(Base):
    """Multi-agent swarm — a collection of agent deployments that work together."""

    __tablename__ = "swarms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    min_replicas: Mapped[int] = mapped_column(Integer, default=1)
    max_replicas: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User", back_populates="swarms")
