"""Request and response schemas for the telemetry backend registry."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TelemetryProtocol = Literal["grpc", "http"]
TelemetryProbeStatus = Literal[
    "unconfigured",
    "reachable",
    "unreachable",
    "blocked",
]


class TelemetryConfigRequest(BaseModel):
    """A tenant-owned OTLP connectivity target."""

    model_config = ConfigDict(extra="forbid")

    otlp_endpoint: str = Field(min_length=1, max_length=2048)
    protocol: TelemetryProtocol = "grpc"

    @field_validator("otlp_endpoint")
    @classmethod
    def strip_endpoint(cls, value: str) -> str:
        endpoint = value.strip()
        if not endpoint:
            raise ValueError("OTLP endpoint cannot be blank")
        return endpoint


class TelemetryStoredConfig(BaseModel):
    endpoint: str
    protocol: TelemetryProtocol
    updated_at: datetime


class TelemetryConfigStatusResponse(BaseModel):
    otel_enabled: bool
    exporter_type: str
    endpoint: str | None
    protocol: TelemetryProtocol | None
    configured: bool
    runtime_applied: bool


class TelemetryHealthResponse(BaseModel):
    configured: bool
    endpoint_reachable: bool
    using_grpc: bool
    endpoint: str | None
    status: TelemetryProbeStatus
    checked_at: datetime | None = None
    failure_reason: str | None = None


class TelemetryConfigureResponse(BaseModel):
    status: Literal["configured"]
    runtime_applied: bool
    config: TelemetryStoredConfig
    health: TelemetryHealthResponse
