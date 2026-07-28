"""Schemas dedicated to scheduler task actions."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ALLOWED_WEBHOOK_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_PROTECTED_WEBHOOK_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "proxy-authorization",
        "te",
        "transfer-encoding",
        "upgrade",
    }
)

SchedulerTaskType = Literal["log", "webhook", "agent_heartbeat"]
SchedulerTaskStatus = Literal["scheduled", "running", "succeeded", "failed"]


class SchedulerTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    enabled: bool = True
    schedule: str | None = Field(
        None,
        max_length=255,
        description="Cron expression, e.g. '*/5 * * * *'",
    )
    interval_seconds: int | None = Field(
        None,
        ge=1,
        le=604800,
        description="Interval in seconds (alternative to cron)",
    )
    task_type: SchedulerTaskType = Field(
        default="log",
        description="Task type: log, webhook, agent_heartbeat",
    )
    payload: dict[str, Any] = Field(default_factory=dict)


class SchedulerTaskUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    enabled: bool | None = None
    schedule: str | None = Field(None, max_length=255)
    interval_seconds: int | None = Field(None, ge=1, le=604800)
    task_type: SchedulerTaskType | None = None
    payload: dict[str, Any] | None = None


class SchedulerTaskResponse(BaseModel):
    id: str
    name: str
    description: str | None
    enabled: bool
    schedule: str | None
    interval_seconds: int | None
    task_type: str
    payload: dict[str, Any]
    last_run: int | None
    next_run: int | None
    run_count: int
    success_count: int = 0
    failure_count: int = 0
    status: SchedulerTaskStatus = "scheduled"
    last_started_at: int | None = None
    last_finished_at: int | None = None
    last_succeeded_at: int | None = None
    last_failed_at: int | None = None
    last_error: str | None = None
    active_execution_id: str | None = None
    created_at: int
    updated_at: int


class SchedulerListResponse(BaseModel):
    tasks: list[SchedulerTaskResponse]
    total: int


class TriggerTaskRequest(BaseModel):
    task_id: str


class TriggerTaskResponse(BaseModel):
    task_id: str
    triggered_at: int
    execution_id: str
    status: SchedulerTaskStatus = "succeeded"
    completed_at: int | None = None


class SchedulerWebhookPayload(BaseModel):
    """Validated payload for a scheduler webhook action."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=1, max_length=2048)
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = Field(default_factory=dict)
    max_retries: int = Field(
        default=0,
        ge=0,
        le=3,
        description="Retry count for transient delivery failures; each retry re-resolves DNS.",
    )

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        method = value.upper()
        if method not in _ALLOWED_WEBHOOK_METHODS:
            allowed = ", ".join(sorted(_ALLOWED_WEBHOOK_METHODS))
            raise ValueError(f"method must be one of: {allowed}")
        return method

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        malformed = sorted(
            name
            for name, header_value in value.items()
            if not _HEADER_NAME.fullmatch(name)
            or any(
                ord(character) < 0x20 and character != "\t" or ord(character) == 0x7F
                for character in header_value
            )
        )
        if malformed:
            raise ValueError(f"malformed webhook header is not allowed: {malformed[0]}")
        protected = sorted(name for name in value if name.lower() in _PROTECTED_WEBHOOK_HEADERS)
        if protected:
            raise ValueError(f"protected webhook header is not allowed: {protected[0]}")
        return value
