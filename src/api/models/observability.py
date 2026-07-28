"""
MUTX Observability Schema - Agent Run Observability for AI Agents.

Based on the agent-run open standard for agent observability.
https://github.com/builderz-labs/agent-run

This module provides MUTX-native schemas for tracking agent executions,
inspired by agent-run but rebranded as MutxRun, MutxStep, etc.

MIT License - Copyright (c) 2026 Builderz Labs
https://github.com/builderz-labs/agent-run/blob/9c7c3fa68413de878fae2d605c90fb334a0201f6/LICENSE

Schema adaptation only. The current upstream package is quarantined pending
maintainer security review and is not required by this module.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.models.numeric import (
    DegradedNumericResponseModel,
    FiniteJsonDict,
    NonNegativeFiniteFloat,
    PercentageFloat,
    UnitIntervalFloat,
    reject_non_finite_floats,
)


class MutxStepType(str, Enum):
    """Types of steps within an agent run."""

    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    MESSAGE = "message"
    ERROR = "error"
    HANDOFF = "handoff"


class MutxRunTrigger(str, Enum):
    """What initiated a run."""

    MANUAL = "manual"
    CRON = "cron"
    WEBHOOK = "webhook"
    AGENT = "agent"
    PIPELINE = "pipeline"
    QUEUE = "queue"


class MutxRunStatus(str, Enum):
    """Current status of a run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    AWAITING_OWNER = "awaiting_owner"


class MutxOutcome(str, Enum):
    """Result quality of a run - distinct from status."""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    ABANDONED = "abandoned"


class MutxCost(BaseModel):
    """
    Token usage and cost attribution for a run.

    Ported from agent-run/cost.json schema.
    """

    model_config = ConfigDict(from_attributes=True)

    input_tokens: int = Field(..., ge=0, description="Total input/prompt tokens consumed")
    output_tokens: int = Field(..., ge=0, description="Total output/completion tokens consumed")
    cache_read_tokens: Optional[int] = Field(
        default=None, ge=0, description="Tokens served from prompt cache (reduced cost)"
    )
    cache_write_tokens: Optional[int] = Field(
        default=None, ge=0, description="Tokens written to prompt cache"
    )
    total_tokens: Optional[int] = Field(
        default=None, ge=0, description="Sum of all token fields. Convenience field."
    )
    cost_usd: Optional[NonNegativeFiniteFloat] = Field(
        default=None, description="Estimated cost in USD. Null if pricing is unknown."
    )
    model: Optional[str] = Field(
        default=None,
        description="Model used for cost calculation (may differ from run-level model)",
    )


class MutxProvenance(BaseModel):
    """
    Cryptographic provenance record - proves how an output was produced.

    Ported from agent-run/provenance.json schema.

    Every run gets a run_hash - a SHA-256 of the canonical inputs
    (agent_id, model, tools_available, config_hash, trigger).
    Runs triggered by other runs form a hash chain via lineage.
    """

    model_config = ConfigDict(from_attributes=True)

    run_hash: str = Field(
        ...,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 hash of canonical run inputs",
    )
    parent_run_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        description="Hash of the parent run that triggered this one, forming a hash chain",
    )
    lineage: list[str] = Field(
        default_factory=list,
        description="Ordered chain of ancestor run hashes (root first). Enables full audit trail traversal.",
    )
    model_version: Optional[str] = Field(
        default=None,
        description="Exact model version string used (e.g., 'claude-sonnet-4-5-20250514')",
    )
    config_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 hash of the agent's configuration at time of run",
    )
    runtime: Optional[str] = Field(
        default=None,
        description="Runtime that produced this run (e.g., 'mutx@1.0.0', 'openclaw@0.4.0')",
    )
    signed_by: Optional[str] = Field(
        default=None,
        description="Public key or key ID that signed this provenance record",
    )
    signature: Optional[str] = Field(
        default=None,
        description="Ed25519 signature over the canonical provenance JSON",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When this provenance record was generated",
    )


class MutxStep(BaseModel):
    """
    A single step within an agent run - a reasoning block, tool call, or error.

    Ported from agent-run/step.json schema.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique step identifier within the run")
    type: MutxStepType = Field(..., description="What kind of step this is")
    tool_name: Optional[str] = Field(
        default=None, description="Name of the tool called (for tool_call/tool_result steps)"
    )
    mcp_server: Optional[str] = Field(
        default=None, description="MCP server that provided the tool, if applicable"
    )
    input_preview: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Truncated preview of the step input (for observability without leaking full prompts)",
    )
    output_preview: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Truncated preview of the step output",
    )
    success: Optional[bool] = Field(
        default=None, description="Whether this step succeeded (for tool calls)"
    )
    error: Optional[str] = Field(default=None, description="Error message if the step failed")
    started_at: datetime = Field(..., description="ISO 8601 timestamp")
    ended_at: Optional[datetime] = Field(default=None, description="ISO 8601 timestamp")
    duration_ms: Optional[int] = Field(
        default=None, ge=0, description="Wall-clock duration of this step"
    )
    tokens_used: Optional[int] = Field(
        default=None, ge=0, description="Total tokens consumed by this step (input + output)"
    )
    step_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Extension point for step-specific data"
    )


class MutxEvalMetrics(BaseModel):
    """
    Quantitative metrics for evaluation.

    Ported from agent-run/eval.json metrics schema.
    """

    model_config = ConfigDict(from_attributes=True)

    cost_usd: Optional[NonNegativeFiniteFloat] = None
    duration_s: Optional[NonNegativeFiniteFloat] = None
    tool_calls: Optional[int] = Field(default=None, ge=0)
    retries: Optional[int] = Field(default=None, ge=0)
    convergence_score: Optional[UnitIntervalFloat] = Field(
        default=None,
        description="How directly the agent reached the solution (1.0 = optimal path, 0.0 = lost)",
    )
    total_steps: Optional[int] = Field(default=None, ge=0)
    optimal_steps: Optional[int] = Field(default=None, ge=0)


class MutxEval(BaseModel):
    """
    Evaluation result for a scored agent run.

    Ported from agent-run/eval.json schema.

    Runs can be scored after completion. MutxEval tracks:
    - pass/fail against acceptance criteria
    - score (0-100) for nuanced grading
    - metrics: cost, duration, tool calls, retries, convergence
    - regression detection via regression_from linking
    """

    model_config = ConfigDict(from_attributes=True)

    task_type: Optional[str] = Field(
        default=None,
        description="Category of task being evaluated (e.g., 'pr-review', 'bug-fix', 'test-gen')",
    )
    eval_layer: Optional[str] = Field(
        default=None,
        description="Which evaluation layer scored this (e.g., 'convergence', 'quality', 'regression')",
    )
    eval_pass: bool = Field(
        ..., alias="pass", description="Whether the run met its acceptance criteria"
    )
    score: PercentageFloat = Field(
        ...,
        description="Numeric score (0-100). Interpretation depends on task_type.",
    )
    expected_outcome: Optional[str] = Field(
        default=None, description="What the eval expected the agent to produce"
    )
    actual_outcome: Optional[str] = Field(
        default=None, description="What the agent actually produced"
    )
    metrics: Optional[MutxEvalMetrics] = Field(
        default=None, description="Quantitative metrics for this evaluation"
    )
    regression_from: Optional[str] = Field(
        default=None, description="Run ID this was compared against for regression detection"
    )
    detail: Optional[str] = Field(
        default=None, description="Human-readable evaluation notes or failure explanation"
    )
    benchmark_id: Optional[str] = Field(
        default=None,
        description="Identifier of the benchmark pack used (e.g., 'mutx/bench/bug-fix@1.0')",
    )


class MutxRun(BaseModel):
    """
    A single execution of an AI agent - the atomic unit of agent observability.

    Ported from agent-run/agent-run.json schema.

    MutxRun defines a standard object that any agent runtime can emit
    and any dashboard can consume. It answers: what ran, how it ran,
    what it cost, and whether it worked.

    Only id, agent_id, status, started_at, steps, cost, and provenance are required.
    Everything else is optional for incrementally adoptable observability.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description="Unique run identifier (UUID v7 recommended for sortability)",
    )
    agent_id: str = Field(..., description="Identifier for the agent that executed this run")
    agent_name: Optional[str] = Field(default=None, description="Human-readable agent name")
    model: Optional[str] = Field(
        default=None,
        description="Model identifier used for this run (e.g., 'claude-sonnet-4-5-20250514')",
    )
    provider: Optional[str] = Field(
        default=None, description="LLM provider (e.g., 'anthropic', 'openai', 'google')"
    )
    runtime: Optional[str] = Field(
        default=None,
        description="Agent runtime that produced this run (e.g., 'claude-code', 'codex', 'openclaw', 'mutx')",
    )
    runtime_version: Optional[str] = Field(default=None, description="Version of the agent runtime")
    trigger: Optional[MutxRunTrigger] = Field(default=None, description="What initiated this run")
    parent_run_id: Optional[str] = Field(
        default=None,
        description="If this run was triggered by another agent run, the parent's ID",
    )
    task_id: Optional[str] = Field(
        default=None, description="Task this run is associated with, if any"
    )
    status: MutxRunStatus = Field(..., description="Current status of the run")
    outcome: Optional[MutxOutcome] = Field(
        default=None,
        description="Result quality of the run (distinct from status - a run can complete but fail its objective)",
    )
    started_at: datetime = Field(..., description="ISO 8601 timestamp when the run started")
    ended_at: Optional[datetime] = Field(
        default=None, description="ISO 8601 timestamp when the run ended"
    )
    duration_ms: Optional[int] = Field(
        default=None, ge=0, description="Total wall-clock duration in milliseconds"
    )
    steps: list[MutxStep] = Field(
        default_factory=list,
        description="Ordered sequence of steps the agent took during this run",
    )
    tools_available: list[str] = Field(
        default_factory=list,
        description="List of tool names available to the agent during this run",
    )
    cost: MutxCost = Field(..., description="Token usage and cost for this run")
    provenance: MutxProvenance = Field(
        ..., description="Cryptographic provenance record for this run"
    )
    eval: Optional[MutxEval] = Field(
        default=None, description="Evaluation result, if this run was scored"
    )
    error: Optional[str] = Field(default=None, description="Error message if the run failed")
    git_branch: Optional[str] = Field(
        default=None, description="Git branch the agent was working on"
    )
    git_commit: Optional[str] = Field(
        default=None, description="Git commit SHA at the start of the run"
    )
    workspace_id: Optional[str] = Field(
        default=None, description="Workspace or tenant scope for multi-tenant deployments"
    )
    tags: list[str] = Field(default_factory=list, description="Free-form tags for categorization")
    run_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Extension point for runtime-specific data"
    )


class MutxRunCreate(BaseModel):
    """Schema for creating a new MutxRun via API."""

    id: Optional[str] = Field(
        default=None,
        description="Unique run identifier (UUID v7 recommended). Auto-generated if not provided.",
    )
    agent_id: str = Field(..., description="Identifier for the agent")
    agent_name: Optional[str] = Field(default=None, description="Human-readable agent name")
    model: Optional[str] = Field(default=None, description="Model identifier")
    provider: Optional[str] = Field(default=None, description="LLM provider")
    runtime: Optional[str] = Field(default=None, description="Agent runtime")
    runtime_version: Optional[str] = Field(default=None, description="Runtime version")
    trigger: Optional[MutxRunTrigger] = Field(default=None, description="What initiated this run")
    parent_run_id: Optional[str] = Field(
        default=None, description="Parent run ID if triggered by another run"
    )
    task_id: Optional[str] = Field(default=None, description="Associated task ID")
    status: MutxRunStatus = Field(default=MutxRunStatus.PENDING, description="Initial status")
    outcome: Optional[MutxOutcome] = Field(default=None, description="Expected outcome")
    started_at: Optional[datetime] = Field(
        default=None,
        description="Start timestamp. Defaults to now if not provided.",
    )
    ended_at: Optional[datetime] = Field(default=None, description="End timestamp")
    duration_ms: Optional[int] = Field(default=None, ge=0, description="Duration in milliseconds")
    steps: list[MutxStep] = Field(default_factory=list, description="Initial steps")
    tools_available: list[str] = Field(default_factory=list, description="Available tools")
    cost: Optional[MutxCost] = Field(
        default=None,
        description="Cost info. Will be set to zero-cost if not provided.",
    )
    provenance: Optional[MutxProvenance] = Field(
        default=None,
        description="Provenance. Will be generated if not provided.",
    )
    eval: Optional[MutxEval] = Field(default=None, description="Evaluation result")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    git_branch: Optional[str] = Field(default=None, description="Git branch")
    git_commit: Optional[str] = Field(default=None, description="Git commit SHA")
    workspace_id: Optional[str] = Field(default=None, description="Workspace/tenant scope")
    tags: list[str] = Field(default_factory=list, description="Tags")
    run_metadata: FiniteJsonDict = Field(default_factory=dict, description="Additional metadata")

    @model_validator(mode="after")
    def _validate_nested_step_metadata(self) -> "MutxRunCreate":
        for index, step in enumerate(self.steps):
            reject_non_finite_floats(
                step.step_metadata,
                path=f"$.steps[{index}].step_metadata",
            )
        return self


class MutxStepCreate(BaseModel):
    """Schema for adding a step to an existing run."""

    id: Optional[str] = Field(
        default=None,
        description="Step ID. Auto-generated if not provided.",
    )
    type: MutxStepType = Field(..., description="Type of step")
    tool_name: Optional[str] = Field(default=None, description="Tool name if applicable")
    mcp_server: Optional[str] = Field(default=None, description="MCP server if applicable")
    input_preview: Optional[str] = Field(default=None, max_length=500, description="Input preview")
    output_preview: Optional[str] = Field(
        default=None, max_length=500, description="Output preview"
    )
    success: Optional[bool] = Field(default=None, description="Success status")
    error: Optional[str] = Field(default=None, description="Error message")
    started_at: Optional[datetime] = Field(
        default=None,
        description="Step start time. Defaults to now if not provided.",
    )
    ended_at: Optional[datetime] = Field(default=None, description="Step end time")
    duration_ms: Optional[int] = Field(default=None, ge=0, description="Duration in ms")
    tokens_used: Optional[int] = Field(default=None, ge=0, description="Tokens consumed")
    step_metadata: FiniteJsonDict = Field(default_factory=dict, description="Additional metadata")


class MutxCostResponse(DegradedNumericResponseModel):
    """Legacy-safe cost telemetry returned without inventing a numeric value."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None


class MutxEvalMetricsResponse(DegradedNumericResponseModel):
    cost_usd: Optional[float] = None
    duration_s: Optional[float] = None
    tool_calls: Optional[int] = None
    retries: Optional[int] = None
    convergence_score: Optional[float] = None
    total_steps: Optional[int] = None
    optimal_steps: Optional[int] = None


class MutxEvalResponse(DegradedNumericResponseModel):
    task_type: Optional[str] = None
    eval_layer: Optional[str] = None
    eval_pass: bool = Field(..., alias="pass")
    score: Optional[float]
    expected_outcome: Optional[str] = None
    actual_outcome: Optional[str] = None
    metrics: Optional[MutxEvalMetricsResponse] = None
    regression_from: Optional[str] = None
    detail: Optional[str] = None
    benchmark_id: Optional[str] = None


class MutxRunResponse(DegradedNumericResponseModel):
    """Schema for MutxRun API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    agent_name: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    runtime: Optional[str] = None
    runtime_version: Optional[str] = None
    trigger: Optional[MutxRunTrigger] = None
    parent_run_id: Optional[str] = None
    task_id: Optional[str] = None
    status: MutxRunStatus
    outcome: Optional[MutxOutcome] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    step_count: int = 0
    tools_available: list[str] = []
    cost: Optional[MutxCostResponse] = None
    provenance: Optional[MutxProvenance] = None
    eval: Optional[MutxEvalResponse] = None
    error: Optional[str] = None
    git_branch: Optional[str] = None
    git_commit: Optional[str] = None
    workspace_id: Optional[str] = None
    tags: list[str] = []
    run_metadata: dict[str, Any] = {}
    created_at: datetime


class MutxRunHistoryResponse(BaseModel):
    """Paginated list of runs."""

    items: list[MutxRunResponse]
    total: int
    skip: int
    limit: int
    has_more: bool
    agent_id: Optional[str] = None
    status: Optional[str] = None


class MutxRunDetailResponse(MutxRunResponse):
    """MutxRun with full step details."""

    steps: list[MutxStep] = []


class MutxStepBatchResponse(BaseModel):
    """Response after adding steps to a run."""

    total: int = Field(..., description="Total number of steps in the run after this batch")
    added: int = Field(..., description="Number of steps added in this request")


class MutxEvalCreate(BaseModel):
    """Schema for submitting an evaluation result."""

    task_type: Optional[str] = None
    eval_layer: Optional[str] = None
    eval_pass: bool = Field(..., alias="pass", description="Pass/fail result")
    score: PercentageFloat = Field(..., description="Score 0-100")
    expected_outcome: Optional[str] = None
    actual_outcome: Optional[str] = None
    metrics: Optional[MutxEvalMetrics] = None
    regression_from: Optional[str] = None
    detail: Optional[str] = None
    benchmark_id: Optional[str] = None


def generate_run_id() -> str:
    """Generate a UUID v7 for run IDs."""
    import time
    from uuid import uuid4

    # UUID v7 combines timestamp with random bits
    timestamp_bytes = int(time.time() * 1000).to_bytes(6, "big")
    random_bytes = uuid4().bytes[:10]
    # Set version (7) and variant bits
    combined = bytearray(timestamp_bytes + random_bytes)
    combined[0] = (combined[0] & 0x0F) | 0x70  # Version 7
    combined[8] = (combined[8] & 0x3F) | 0x80  # Variant 10
    return uuid.UUID(bytes=bytes(combined)).hex


def compute_run_hash(
    agent_id: str,
    model: Optional[str],
    tools_available: list[str],
    config_hash: Optional[str],
    trigger: Optional[str],
) -> str:
    """
    Compute SHA-256 run hash from canonical inputs.

    This enables anyone with the same inputs to reproduce and verify the hash.
    """
    import hashlib

    canonical = "|".join(
        sorted(
            [
                str(agent_id),
                str(model or ""),
                ",".join(sorted(tools_available)),
                str(config_hash or ""),
                str(trigger or ""),
            ]
        )
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
