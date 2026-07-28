from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import AgentType, User, UserSetting
from src.api.models.schemas import AssistantTemplateResponse
from src.api.services.assistant_control_plane import (
    assistant_template_catalog,
    build_personal_assistant_config,
    slugify_assistant_id,
)

CATALOG_STATE_SETTING_KEY = "templates.catalog.state.v1"
CUSTOM_TEMPLATES_SETTING_KEY = "templates.custom.catalog.v1"
DEPLOY_IDEMPOTENCY_KEY_PREFIX = "templates.deploy.idempotency."
TEMPLATE_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,119}$"


class TemplateCatalogStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned_template_ids: list[str] = Field(default_factory=list, max_length=100)
    recent_template_ids: list[str] = Field(default_factory=list, max_length=24)
    deployment_count_by_template: dict[str, int] = Field(default_factory=dict)

    @field_validator("pinned_template_ids", "recent_template_ids")
    @classmethod
    def normalize_template_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            template_id = item.strip()
            if not template_id or len(template_id) > 120:
                raise ValueError("Template ids must contain between 1 and 120 characters")
            if template_id not in normalized:
                normalized.append(template_id)
        return normalized

    @field_validator("deployment_count_by_template")
    @classmethod
    def validate_deployment_counts(cls, value: dict[str, int]) -> dict[str, int]:
        if len(value) > 250:
            raise ValueError("Deployment counts cannot contain more than 250 templates")
        for template_id, count in value.items():
            if not template_id.strip() or len(template_id) > 120:
                raise ValueError("Deployment count keys must be valid template ids")
            if count < 0:
                raise ValueError("Deployment counts cannot be negative")
        return value


class TemplateCatalogStateResponse(TemplateCatalogStateUpdate):
    updated_at: datetime | None = None


class CustomTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120, pattern=TEMPLATE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="User-owned custom starter template.", max_length=500)
    description: str = Field(default="User-owned custom template.", max_length=4000)
    starter_prompt: str = Field(default="Deploy this custom template.", max_length=4000)
    system_prompt: str = Field(min_length=1, max_length=16000)
    category: str = Field(default="custom", max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=50)
    version: str = Field(default="1", min_length=1, max_length=50)
    source_path: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "name", "system_prompt", "version")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be blank")
        return stripped

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            tag = item.strip()
            if len(tag) > 80:
                raise ValueError("Template tags cannot exceed 80 characters")
            if tag and tag not in normalized:
                normalized.append(tag)
        return normalized


class CustomTemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=4000)
    starter_prompt: str | None = Field(default=None, max_length=4000)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=16000)
    category: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = Field(default=None, max_length=50)
    version: str | None = Field(default=None, min_length=1, max_length=50)
    source_path: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] | None = None

    @field_validator("name", "system_prompt", "version")
    @classmethod
    def strip_optional_required_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be blank")
        return stripped

    @field_validator("tags")
    @classmethod
    def normalize_optional_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return CustomTemplateCreate.normalize_tags(value)


class TemplateCloneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120, pattern=TEMPLATE_ID_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str = Field(default="custom", max_length=120)
    version: str = Field(default="1", min_length=1, max_length=50)

    @field_validator("id", "name", "version")
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be blank")
        return stripped


def _setting_value_as_dict(setting: UserSetting | None) -> dict[str, Any]:
    return dict(setting.value) if setting is not None and isinstance(setting.value, dict) else {}


async def _get_setting(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    key: str,
) -> UserSetting | None:
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
    )
    return result.scalar_one_or_none()


async def _upsert_setting(
    db: AsyncSession,
    *,
    user: User,
    key: str,
    value: dict[str, Any],
) -> UserSetting:
    setting = await _get_setting(db, user_id=user.id, key=key)
    if setting is None:
        setting = UserSetting(user_id=user.id, key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    await db.flush()
    return setting


def _normalize_custom_template(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    try:
        template = AssistantTemplateResponse.model_validate(value)
    except (TypeError, ValueError):
        return None
    normalized = template.model_dump(mode="json")
    normalized["category"] = "custom"
    normalized["is_official"] = False
    return normalized


async def get_custom_templates(db: AsyncSession, *, user: User) -> list[dict[str, Any]]:
    setting = await _get_setting(db, user_id=user.id, key=CUSTOM_TEMPLATES_SETTING_KEY)
    raw_templates = _setting_value_as_dict(setting).get("templates", [])
    if not isinstance(raw_templates, list):
        return []

    builtin_ids = {str(item["id"]) for item in assistant_template_catalog()}
    templates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_template in raw_templates:
        template = _normalize_custom_template(raw_template)
        if template is None:
            continue
        template_id = str(template["id"])
        if template_id in builtin_ids or template_id in seen_ids:
            continue
        templates.append(template)
        seen_ids.add(template_id)
    return templates


async def get_user_template_catalog(db: AsyncSession, *, user: User) -> list[dict[str, Any]]:
    return [*assistant_template_catalog(), *(await get_custom_templates(db, user=user))]


async def get_user_template(
    db: AsyncSession,
    *,
    user: User,
    template_id: str,
) -> dict[str, Any] | None:
    builtin = next(
        (item for item in assistant_template_catalog() if str(item.get("id")) == template_id),
        None,
    )
    if builtin is not None:
        return builtin
    return next(
        (item for item in await get_custom_templates(db, user=user) if item["id"] == template_id),
        None,
    )


def is_builtin_template_id(template_id: str) -> bool:
    return any(str(item.get("id")) == template_id for item in assistant_template_catalog())


def _custom_template_metadata(
    metadata: dict[str, Any] | None,
    *,
    source_template_id: str | None = None,
) -> dict[str, Any]:
    normalized = copy.deepcopy(metadata) if isinstance(metadata, dict) else {}
    normalized["kind"] = "custom_template"
    files = normalized.get("files")
    normalized["files"] = [str(item) for item in files] if isinstance(files, list) else []
    if source_template_id is not None:
        normalized["source_template_id"] = source_template_id
    else:
        normalized.setdefault("source_template_id", None)
    return normalized


def _prepare_custom_default_config(
    *,
    template_id: str,
    name: str,
    description: str,
    system_prompt: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    config = build_personal_assistant_config(name=name, description=description)
    config["system_prompt"] = system_prompt
    config["template"] = template_id
    config["assistant_id"] = slugify_assistant_id(name)
    config_metadata = config.setdefault("metadata", {})
    config_metadata["starter_template"] = template_id
    config_metadata["template"] = metadata
    return config


async def create_custom_template(
    db: AsyncSession,
    *,
    user: User,
    request: CustomTemplateCreate,
) -> dict[str, Any]:
    templates = await get_custom_templates(db, user=user)
    existing_ids = {str(item["id"]) for item in assistant_template_catalog()}
    existing_ids.update(str(item["id"]) for item in templates)
    if request.id in existing_ids:
        raise ValueError("A template with this id already exists")

    metadata = _custom_template_metadata(request.metadata)
    template = {
        "id": request.id,
        "name": request.name,
        "summary": request.summary,
        "description": request.description,
        "agent_type": AgentType.OPENCLAW.value,
        "starter_prompt": request.starter_prompt,
        "default_config": _prepare_custom_default_config(
            template_id=request.id,
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt,
            metadata=metadata,
        ),
        "category": "custom",
        "tags": request.tags,
        "is_official": False,
        "source_path": request.source_path,
        "version": request.version,
        "validation_status": "user-owned",
        "validation_message": "Editable custom template owned by the current user.",
        "bundle_ids": [],
    }
    normalized = _normalize_custom_template(template)
    if normalized is None:
        raise ValueError("Custom template configuration is invalid")
    templates.append(normalized)
    await _upsert_setting(
        db,
        user=user,
        key=CUSTOM_TEMPLATES_SETTING_KEY,
        value={"templates": templates},
    )
    await db.commit()
    return normalized


async def clone_user_template(
    db: AsyncSession,
    *,
    user: User,
    source: dict[str, Any],
    request: TemplateCloneCreate,
) -> dict[str, Any]:
    templates = await get_custom_templates(db, user=user)
    existing_ids = {str(item["id"]) for item in assistant_template_catalog()}
    existing_ids.update(str(item["id"]) for item in templates)
    if request.id in existing_ids:
        raise ValueError("A template with this id already exists")

    cloned = AssistantTemplateResponse.model_validate(source).model_dump(mode="json")
    source_template_id = str(cloned["id"])
    cloned["id"] = request.id
    cloned["name"] = request.name or f"{cloned['name']} Custom"
    cloned["category"] = "custom"
    cloned["version"] = request.version
    cloned["is_official"] = False
    cloned["validation_status"] = "user-owned"
    cloned["validation_message"] = "Editable clone owned by the current user."
    cloned["bundle_ids"] = []

    config = cloned.get("default_config")
    if not isinstance(config, dict):
        config = _prepare_custom_default_config(
            template_id=request.id,
            name=str(cloned["name"]),
            description=str(cloned["description"]),
            system_prompt="You are a custom MUTX assistant template.",
            metadata=_custom_template_metadata({}, source_template_id=source_template_id),
        )
    else:
        config = copy.deepcopy(config)
        config["name"] = cloned["name"]
        config["template"] = request.id
        config["assistant_id"] = slugify_assistant_id(str(cloned["name"]))
        config_metadata = config.get("metadata")
        if not isinstance(config_metadata, dict):
            config_metadata = {}
        template_metadata = config_metadata.get("template")
        config_metadata["template"] = _custom_template_metadata(
            template_metadata if isinstance(template_metadata, dict) else {},
            source_template_id=source_template_id,
        )
        config_metadata["starter_template"] = request.id
        config["metadata"] = config_metadata
    cloned["default_config"] = config

    normalized = _normalize_custom_template(cloned)
    if normalized is None:
        raise ValueError("Cloned template configuration is invalid")
    templates.append(normalized)
    await _upsert_setting(
        db,
        user=user,
        key=CUSTOM_TEMPLATES_SETTING_KEY,
        value={"templates": templates},
    )
    await db.commit()
    return normalized


async def update_custom_template(
    db: AsyncSession,
    *,
    user: User,
    template_id: str,
    request: CustomTemplateUpdate,
) -> dict[str, Any] | None:
    templates = await get_custom_templates(db, user=user)
    index = next((index for index, item in enumerate(templates) if item["id"] == template_id), None)
    if index is None:
        return None

    current = copy.deepcopy(templates[index])
    updates = request.model_dump(exclude_unset=True)
    for field in ("name", "summary", "description", "starter_prompt", "tags", "version"):
        value = updates.get(field)
        if value is not None:
            current[field] = value
    if "source_path" in updates:
        current["source_path"] = updates["source_path"]

    config = current.get("default_config")
    if not isinstance(config, dict):
        config = {}
    if updates.get("name") is not None:
        config["name"] = updates["name"]
    if updates.get("system_prompt") is not None:
        config["system_prompt"] = updates["system_prompt"]
    config["template"] = template_id
    config_metadata = config.get("metadata")
    if not isinstance(config_metadata, dict):
        config_metadata = {}
    if updates.get("metadata") is not None:
        config_metadata["template"] = _custom_template_metadata(updates["metadata"])
    config_metadata["starter_template"] = template_id
    config["metadata"] = config_metadata
    current["default_config"] = config
    current["category"] = "custom"
    current["is_official"] = False

    normalized = _normalize_custom_template(current)
    if normalized is None:
        raise ValueError("Custom template configuration is invalid")
    templates[index] = normalized
    await _upsert_setting(
        db,
        user=user,
        key=CUSTOM_TEMPLATES_SETTING_KEY,
        value={"templates": templates},
    )
    await db.commit()
    return normalized


async def delete_custom_template(
    db: AsyncSession,
    *,
    user: User,
    template_id: str,
) -> bool:
    templates = await get_custom_templates(db, user=user)
    remaining = [item for item in templates if item["id"] != template_id]
    if len(remaining) == len(templates):
        return False

    await _upsert_setting(
        db,
        user=user,
        key=CUSTOM_TEMPLATES_SETTING_KEY,
        value={"templates": remaining},
    )

    state_setting = await _get_setting(db, user_id=user.id, key=CATALOG_STATE_SETTING_KEY)
    if state_setting is not None:
        state = normalize_catalog_state(state_setting)
        state.pinned_template_ids = [
            item for item in state.pinned_template_ids if item != template_id
        ]
        state.recent_template_ids = [
            item for item in state.recent_template_ids if item != template_id
        ]
        state.deployment_count_by_template.pop(template_id, None)
        state_setting.value = state.model_dump(exclude={"updated_at"})

    await db.commit()
    return True


def normalize_catalog_state(setting: UserSetting | None) -> TemplateCatalogStateResponse:
    try:
        state = TemplateCatalogStateUpdate.model_validate(_setting_value_as_dict(setting))
    except ValueError:
        state = TemplateCatalogStateUpdate()
    return TemplateCatalogStateResponse(
        **state.model_dump(),
        updated_at=setting.updated_at if setting is not None else None,
    )


async def get_catalog_state(
    db: AsyncSession,
    *,
    user: User,
) -> TemplateCatalogStateResponse:
    setting = await _get_setting(db, user_id=user.id, key=CATALOG_STATE_SETTING_KEY)
    return normalize_catalog_state(setting)


async def update_catalog_state(
    db: AsyncSession,
    *,
    user: User,
    state: TemplateCatalogStateUpdate,
) -> TemplateCatalogStateResponse:
    setting = await _upsert_setting(
        db,
        user=user,
        key=CATALOG_STATE_SETTING_KEY,
        value=state.model_dump(),
    )
    await db.commit()
    await db.refresh(setting)
    return normalize_catalog_state(setting)


def build_custom_deployment_config(
    template: dict[str, Any],
    *,
    name: str,
    description: str | None,
    model: str | None,
    workspace: str | None,
    assistant_id: str | None,
    skills: list[str],
    skills_provided: bool,
    channels: dict[str, dict[str, Any]],
    runtime_metadata: dict[str, Any],
) -> dict[str, Any]:
    default_config = template.get("default_config")
    if not isinstance(default_config, dict):
        raise ValueError("Custom template configuration is invalid")
    config = copy.deepcopy(default_config)
    template_id = str(template["id"])
    config["name"] = name
    config["template"] = template_id
    config["assistant_id"] = assistant_id or slugify_assistant_id(name)
    config["workspace"] = workspace or str(config.get("workspace") or config["assistant_id"])
    if model:
        config["model"] = model
    if skills_provided:
        config["skills"] = list(dict.fromkeys(skills))

    configured_channels = config.get("channels")
    if not isinstance(configured_channels, dict):
        configured_channels = {}
    for channel_id, payload in channels.items():
        current = configured_channels.get(channel_id)
        if not isinstance(current, dict):
            current = {
                "label": channel_id.replace("_", " ").title(),
                "enabled": False,
                "mode": "pairing",
                "allow_from": [],
            }
        current.update(payload)
        configured_channels[channel_id] = current
    config["channels"] = configured_channels

    metadata = config.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    runtime = metadata.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime.update(runtime_metadata)
    metadata["runtime"] = runtime
    metadata["starter"] = True
    metadata["description"] = description
    metadata["starter_template"] = template_id
    config["metadata"] = metadata
    return config


def deployment_request_hash(template_id: str, payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        {"template_id": template_id, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def claim_deployment_idempotency(
    db: AsyncSession,
    *,
    user: User,
    idempotency_key: str,
    template_id: str,
    request_hash: str,
) -> dict[str, Any] | None:
    setting_key = f"{DEPLOY_IDEMPOTENCY_KEY_PREFIX}{idempotency_key}"

    async def inspect_existing() -> dict[str, Any] | None:
        existing = await _get_setting(db, user_id=user.id, key=setting_key)
        if existing is None:
            return None
        value = _setting_value_as_dict(existing)
        if value.get("request_hash") != request_hash or value.get("template_id") != template_id:
            raise ValueError("Idempotency key was already used for a different deployment")
        if value.get("status") == "completed":
            return value
        raise RuntimeError("A deployment with this idempotency key is already in progress")

    existing_value = await inspect_existing()
    if existing_value is not None:
        return existing_value

    db.add(
        UserSetting(
            user_id=user.id,
            key=setting_key,
            value={
                "status": "pending",
                "template_id": template_id,
                "request_hash": request_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return await inspect_existing()
    return None


async def complete_deployment_idempotency(
    db: AsyncSession,
    *,
    user: User,
    idempotency_key: str,
    request_hash: str,
    template_id: str,
    agent_id: str,
    deployment_id: str,
) -> None:
    setting_key = f"{DEPLOY_IDEMPOTENCY_KEY_PREFIX}{idempotency_key}"
    setting = await _get_setting(db, user_id=user.id, key=setting_key)
    if setting is None:
        return
    setting.value = {
        "status": "completed",
        "template_id": template_id,
        "request_hash": request_hash,
        "agent_id": agent_id,
        "deployment_id": deployment_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.commit()


async def release_deployment_idempotency(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    idempotency_key: str,
) -> None:
    setting_key = f"{DEPLOY_IDEMPOTENCY_KEY_PREFIX}{idempotency_key}"
    await db.execute(
        delete(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == setting_key,
        )
    )
    await db.commit()
