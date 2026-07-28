from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PicoTutorConfidence = Literal["high", "medium", "low"]
PicoTutorIntent = Literal[
    "choose",
    "install",
    "repair",
    "migrate",
    "compare",
    "tailscale",
    "optimize",
    "integrate",
]
PicoTutorSkillLevel = Literal["beginner", "intermediate", "advanced"]
PicoTutorSourceKind = Literal["lesson", "knowledge_pack", "official"]
PicoTutorOpenAIConnectionStatusValue = Literal["connected", "platform", "disconnected", "error"]
PicoTutorOpenAIConnectionSource = Literal["user", "platform", "none"]
PicoTutorPlan = Literal["free", "starter", "pro", "enterprise"]
PicoTutorProviderProofKind = Literal["validated_user_key", "configured_platform_key"]


class PicoTutorSetupContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    onboarding: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    currentSurface: str | None = None


class PicoTutorRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(..., min_length=1, max_length=6000)
    lessonSlug: str | None = Field(default=None, max_length=255)
    progress: dict[str, Any] | None = None
    setupContext: PicoTutorSetupContext | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        if "question" not in normalized and "message" in normalized:
            normalized["question"] = normalized["message"]
        if "lessonSlug" not in normalized and "lesson" in normalized:
            normalized["lessonSlug"] = normalized["lesson"]
        return normalized


class PicoTutorOpenAIConnectionRequest(BaseModel):
    apiKey: str = Field(..., min_length=10, max_length=512)

    @field_validator("apiKey", mode="before")
    @classmethod
    def normalize_api_key(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("apiKey", mode="after")
    @classmethod
    def reject_api_key_whitespace(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("OpenAI key must not contain whitespace")
        return value


class PicoTutorLessonLink(BaseModel):
    id: str
    title: str
    href: str


class PicoTutorDocLink(BaseModel):
    label: str
    href: str
    sourcePath: str


class PicoTutorCommand(BaseModel):
    label: str
    code: str
    language: str = "bash"
    note: str | None = None


class PicoTutorSource(BaseModel):
    kind: PicoTutorSourceKind
    title: str
    sourcePath: str
    href: str | None = None
    excerpt: str | None = None


class PicoTutorStructuredReply(BaseModel):
    situation: str
    diagnosis: str
    steps: list[str] = Field(default_factory=list)
    commands: list[PicoTutorCommand] = Field(default_factory=list)
    verify: list[str] = Field(default_factory=list)
    ifThisFails: list[str] = Field(default_factory=list)
    officialLinks: list[PicoTutorDocLink] = Field(default_factory=list)
    sources: list[PicoTutorSource] = Field(default_factory=list)
    nextQuestion: str | None = None


class PicoTutorGuidance(BaseModel):
    title: str
    summary: str
    answer: str
    confidence: PicoTutorConfidence
    nextActions: list[str] = Field(default_factory=list)
    lessons: list[PicoTutorLessonLink] = Field(default_factory=list)
    docs: list[PicoTutorDocLink] = Field(default_factory=list)
    recommendedLessonIds: list[str] = Field(default_factory=list)
    escalate: bool = False
    escalationReason: str | None = None
    structured: PicoTutorStructuredReply
    intent: PicoTutorIntent
    skillLevel: PicoTutorSkillLevel
    usedOfficialFallback: bool = False
    reply: str | None = None
    nextLesson: str | None = None

    @model_validator(mode="after")
    def _sync_legacy_response_fields(self) -> "PicoTutorGuidance":
        if self.reply is None:
            self.reply = self.answer
        if self.nextLesson is None and self.recommendedLessonIds:
            self.nextLesson = self.recommendedLessonIds[0]
        return self


class PicoTutorEntitlement(BaseModel):
    authenticated: bool = True
    plan: PicoTutorPlan
    tutorAccess: bool
    minimumPlan: PicoTutorPlan = "starter"
    byokAccess: bool
    byokMinimumPlan: PicoTutorPlan = "pro"


class PicoTutorGenerationProof(BaseModel):
    provider: Literal["openai"] = "openai"
    source: Literal["user", "platform"]
    model: str
    responseId: str
    completedAt: str


class PicoTutorResponse(PicoTutorGuidance):
    entitlement: PicoTutorEntitlement
    generation: PicoTutorGenerationProof


class PicoTutorProviderProof(BaseModel):
    kind: PicoTutorProviderProofKind
    checkedAt: str
    validatedAt: str | None = None


class PicoTutorOpenAIConnectionStatus(BaseModel):
    provider: str = "openai"
    status: PicoTutorOpenAIConnectionStatusValue
    source: PicoTutorOpenAIConnectionSource
    connected: bool
    model: str
    maskedKey: str | None = None
    connectedAt: str | None = None
    validatedAt: str | None = None
    message: str
    providerAvailable: bool
    canConnect: bool
    entitlement: PicoTutorEntitlement
    proof: PicoTutorProviderProof | None = None
    apiKeySet: bool | None = None

    @model_validator(mode="after")
    def _sync_legacy_status_fields(self) -> "PicoTutorOpenAIConnectionStatus":
        if self.apiKeySet is None:
            self.apiKeySet = self.source == "user" and self.connected

        if self.status == "connected":
            if not (
                self.connected
                and self.source == "user"
                and self.providerAvailable
                and self.validatedAt
                and self.proof
                and self.proof.kind == "validated_user_key"
                and self.proof.validatedAt == self.validatedAt
            ):
                raise ValueError("Connected Tutor status requires validated user-key proof")
        elif self.connected:
            raise ValueError("Only validated user-key status may be connected")

        if self.status == "platform" and not (
            self.source == "platform"
            and not self.providerAvailable
            and self.proof
            and self.proof.kind == "configured_platform_key"
        ):
            raise ValueError("Platform Tutor status must distinguish configured credentials")

        if self.status in {"disconnected", "error"} and self.providerAvailable:
            raise ValueError("Unavailable Tutor status cannot claim provider availability")

        if self.canConnect != self.entitlement.byokAccess:
            raise ValueError("Tutor BYOK capability must match the authoritative entitlement")
        return self
