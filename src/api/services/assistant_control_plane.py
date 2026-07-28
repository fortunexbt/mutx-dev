from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.api.models import Agent, AgentType
from src.api.services.orchestra_research_catalog import (
    managed_skill_roots,
    orchestra_bundles,
    orchestra_skills,
    orchestra_source,
    orchestra_swarm_blueprints,
    orchestra_templates,
)
from src.api.services.gateway_runtime import (
    get_detected_gateway_port,
    get_detected_gateway_token,
    get_detected_openclaw_config_path,
    get_detected_openclaw_state_dir,
)

DEFAULT_TEMPLATE_ID = "personal_assistant"
DEFAULT_ASSISTANT_MODEL = "openai/gpt-5"
SKILL_RECONCILIATION_METADATA_KEY = "skill_reconciliation"
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SkillCatalogItem:
    id: str
    name: str
    description: str
    author: str
    category: str
    source: str
    is_official: bool = False
    tags: tuple[str, ...] = ()
    path: str | None = None
    canonical_name: str | None = None
    upstream_path: str | None = None
    upstream_repo: str | None = None
    upstream_commit: str | None = None
    license: str | None = None
    available: bool = True


OFFICIAL_SKILL_CATALOG: tuple[SkillCatalogItem, ...] = (
    SkillCatalogItem(
        id="web_search",
        name="Web Search",
        description="Search the live web and synthesize results into assistant replies.",
        author="mutx",
        category="Research",
        source="catalog",
        is_official=True,
        tags=("web", "search", "research"),
    ),
    SkillCatalogItem(
        id="browser_control",
        name="Browser Control",
        description="Drive a managed browser session for operator workflows and web tasks.",
        author="mutx",
        category="Tools",
        source="catalog",
        is_official=True,
        tags=("browser", "automation"),
    ),
    SkillCatalogItem(
        id="workspace_memory",
        name="Workspace Memory",
        description="Persist working notes and memory into the assistant workspace.",
        author="mutx",
        category="Productivity",
        source="catalog",
        is_official=True,
        tags=("memory", "workspace"),
    ),
    SkillCatalogItem(
        id="inbox_triage",
        name="Inbox Triage",
        description="Summarize, categorize, and draft responses for inbox workflows.",
        author="mutx",
        category="Communication",
        source="catalog",
        is_official=False,
        tags=("email", "triage"),
    ),
    SkillCatalogItem(
        id="cron_manager",
        name="Wakeups And Cron",
        description="Manage timed reminders, recurring check-ins, and wakeup actions.",
        author="mutx",
        category="Automation",
        source="catalog",
        is_official=True,
        tags=("cron", "wakeups", "automation"),
    ),
)

DEFAULT_CHANNELS: tuple[dict[str, str], ...] = (
    {"id": "webchat", "label": "WebChat"},
    {"id": "telegram", "label": "Telegram"},
    {"id": "discord", "label": "Discord"},
    {"id": "slack", "label": "Slack"},
    {"id": "whatsapp", "label": "WhatsApp"},
)


def slugify_assistant_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "personal-assistant"


def deserialize_config(raw_config: Any) -> dict[str, Any]:
    if isinstance(raw_config, dict):
        return dict(raw_config)
    if isinstance(raw_config, str):
        try:
            parsed = json.loads(raw_config)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}


def serialize_config(config: dict[str, Any]) -> str:
    return json.dumps(config, sort_keys=True)


def default_channel_map() -> dict[str, dict[str, Any]]:
    return {
        item["id"]: {
            "label": item["label"],
            "enabled": False,
            "mode": "pairing",
            "allow_from": [],
        }
        for item in DEFAULT_CHANNELS
    }


def build_personal_assistant_config(
    *,
    name: str = "Personal Assistant",
    description: str | None = None,
    model: str | None = None,
    workspace: str | None = None,
    assistant_id: str | None = None,
    skills: list[str] | None = None,
    channels: dict[str, dict[str, Any]] | None = None,
    runtime_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_assistant_id = assistant_id or slugify_assistant_id(name)
    normalized_channels = default_channel_map()
    for channel_id, payload in (channels or {}).items():
        existing = normalized_channels.get(
            channel_id,
            {
                "label": channel_id.replace("_", " ").title(),
                "enabled": False,
                "mode": "pairing",
                "allow_from": [],
            },
        )
        if isinstance(payload, dict):
            existing.update(payload)
        normalized_channels[channel_id] = existing

    return {
        "name": name,
        "system_prompt": (
            "You are the MUTX Personal Assistant. Operate as a proactive, safe, channel-aware "
            "assistant for a single operator. Prefer concise, operationally useful responses."
        ),
        "version": 1,
        "runtime": DEFAULT_TEMPLATE_ID,
        "template": DEFAULT_TEMPLATE_ID,
        "assistant_id": resolved_assistant_id,
        "workspace": workspace or resolved_assistant_id,
        "model": model or DEFAULT_ASSISTANT_MODEL,
        "safety_mode": "pairing",
        "skills": list(dict.fromkeys(skills or ["web_search", "workspace_memory"])),
        "channels": normalized_channels,
        "wakeups": [],
        "metadata": {
            "starter": True,
            "description": description,
            "starter_template": DEFAULT_TEMPLATE_ID,
            "runtime": dict(runtime_metadata or {}),
        },
        "gateway": {
            "port": 18789,
            "auth_mode": "token",
            "dashboard_allowed_origins": [],
        },
    }


def _clone_config(config: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(config))


def _merge_channel_map(
    base_channels: dict[str, dict[str, Any]] | None,
    override_channels: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    normalized = default_channel_map()
    for source in (base_channels or {}, override_channels or {}):
        for channel_id, payload in source.items():
            existing = normalized.get(
                channel_id,
                {
                    "label": channel_id.replace("_", " ").title(),
                    "enabled": False,
                    "mode": "pairing",
                    "allow_from": [],
                },
            )
            if isinstance(payload, dict):
                existing.update(payload)
            normalized[channel_id] = existing
    return normalized


def _base_personal_template() -> dict[str, Any]:
    default_config = build_personal_assistant_config()
    return {
        "id": DEFAULT_TEMPLATE_ID,
        "name": "Personal Assistant",
        "summary": "Deploy an OpenClaw-backed assistant as the first MUTX agent.",
        "description": (
            "A branded starter template for a single-operator assistant with safe channel "
            "defaults, workspace memory, and a control-plane-friendly runtime surface."
        ),
        "agent_type": AgentType.OPENCLAW,
        "starter_prompt": "Authenticate, deploy the assistant, then connect channels and skills.",
        "default_config": default_config,
        "category": "mutx",
        "tags": ["starter", "assistant", "mutx"],
        "is_official": True,
        "source_path": None,
        "version": "1.0.0",
        "validation_status": "native",
        "validation_message": "First-party MUTX starter template.",
        "bundle_ids": [],
    }


def _normalized_orchestra_templates() -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for template in orchestra_templates():
        entry = _clone_config(template)
        entry.setdefault("agent_type", AgentType.OPENCLAW)
        entry.setdefault(
            "starter_prompt",
            "Deploy this research operator, then connect the recommended bundle and swarm blueprint.",
        )
        entry.setdefault("category", "orchestra-research")
        entry.setdefault("tags", [])
        entry.setdefault("bundle_ids", [])
        normalized.append(entry)
    return normalized


def assistant_template_catalog() -> list[dict[str, Any]]:
    templates = [_base_personal_template()]
    templates.extend(_normalized_orchestra_templates())
    return templates


def get_template_definition(template_id: str) -> dict[str, Any] | None:
    if template_id == DEFAULT_TEMPLATE_ID:
        return _base_personal_template()
    return next(
        (
            _clone_config(template)
            for template in _normalized_orchestra_templates()
            if str(template.get("id") or "") == template_id
        ),
        None,
    )


def build_template_config(
    *,
    template_id: str,
    name: str,
    description: str | None = None,
    model: str | None = None,
    workspace: str | None = None,
    assistant_id: str | None = None,
    skills: list[str] | None = None,
    channels: dict[str, dict[str, Any]] | None = None,
    runtime_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if template_id == DEFAULT_TEMPLATE_ID:
        return build_personal_assistant_config(
            name=name,
            description=description,
            model=model,
            workspace=workspace,
            assistant_id=assistant_id,
            skills=skills,
            channels=channels,
            runtime_metadata=runtime_metadata,
        )

    template = get_template_definition(template_id)
    if template is None:
        raise KeyError(template_id)

    base_config = template.get("default_config")
    if not isinstance(base_config, dict):
        raise KeyError(template_id)

    config = _clone_config(base_config)
    resolved_name = name or str(config.get("name") or template.get("name") or "Assistant")
    resolved_assistant_id = assistant_id or str(
        config.get("assistant_id") or slugify_assistant_id(resolved_name)
    )
    resolved_workspace = workspace or str(config.get("workspace") or resolved_assistant_id)
    resolved_skills = [str(item) for item in (skills or config.get("skills") or []) if str(item)]

    metadata = config.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    runtime = metadata.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime.update(runtime_metadata or {})
    metadata["runtime"] = runtime
    metadata["starter"] = True
    metadata["description"] = description
    metadata["starter_template"] = template_id

    gateway = config.get("gateway")
    if not isinstance(gateway, dict):
        gateway = {
            "port": 18789,
            "auth_mode": "token",
            "dashboard_allowed_origins": [],
        }

    return {
        "name": resolved_name,
        "system_prompt": str(config.get("system_prompt") or ""),
        "version": int(config.get("version") or 1),
        "runtime": str(config.get("runtime") or DEFAULT_TEMPLATE_ID),
        "template": template_id,
        "assistant_id": resolved_assistant_id,
        "workspace": resolved_workspace,
        "model": str(model or config.get("model") or DEFAULT_ASSISTANT_MODEL),
        "safety_mode": str(config.get("safety_mode") or "pairing"),
        "skills": list(dict.fromkeys(resolved_skills)),
        "channels": _merge_channel_map(
            config.get("channels") if isinstance(config.get("channels"), dict) else None,
            channels,
        ),
        "wakeups": config.get("wakeups") if isinstance(config.get("wakeups"), list) else [],
        "metadata": metadata,
        "gateway": gateway,
    }


def is_assistant_agent(agent: Agent) -> bool:
    return agent.type == AgentType.OPENCLAW


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _extract_skill_metadata(skill_file: Path) -> SkillCatalogItem | None:
    text = _read_text(skill_file).strip()
    if not text:
        return None

    first_heading = next(
        (
            line.strip().lstrip("#").strip()
            for line in text.splitlines()
            if line.strip().startswith("#")
        ),
        None,
    )
    description = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            continue
        description = stripped
        break

    slug = skill_file.parent.name
    author = skill_file.parent.parent.name if skill_file.parent.parent else "workspace"
    return SkillCatalogItem(
        id=slug,
        name=first_heading or slug.replace("-", " ").title(),
        description=description or "Workspace skill discovered from local OpenClaw state.",
        author=author,
        category="Workspace",
        source="workspace",
        tags=("workspace",),
        path=str(skill_file.parent),
    )


def _candidate_skill_roots() -> list[Path]:
    state_dir = get_detected_openclaw_state_dir()
    roots = [
        *managed_skill_roots(),
        Path.home() / ".hermes" / "skills",
        Path.home() / ".openclaw" / "skills",
    ]
    if state_dir is not None:
        roots.extend(
            [
                state_dir / "skills",
                state_dir / "workspace" / "skills",
                state_dir / "workspaces",
            ]
        )

    env_root = os.environ.get("OPENCLAW_SKILLS_DIR")
    if env_root:
        roots.insert(0, Path(env_root).expanduser())

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = str(root.expanduser())
        if resolved not in seen:
            deduped.append(root.expanduser())
            seen.add(resolved)
    return deduped


def discover_workspace_skills() -> list[SkillCatalogItem]:
    discovered: dict[str, SkillCatalogItem] = {}
    for root in _candidate_skill_roots():
        if not root.exists():
            continue
        for skill_file in root.rglob("SKILL.md"):
            item = _extract_skill_metadata(skill_file)
            if item is not None:
                discovered.setdefault(item.id, item)
    return sorted(discovered.values(), key=lambda item: item.name.lower())


def _merge_catalog_item(
    existing: SkillCatalogItem, discovered: SkillCatalogItem
) -> SkillCatalogItem:
    return SkillCatalogItem(
        id=existing.id,
        name=existing.name,
        description=existing.description,
        author=existing.author,
        category=existing.category,
        source=existing.source,
        is_official=existing.is_official,
        tags=existing.tags or discovered.tags,
        path=discovered.path or existing.path,
        canonical_name=existing.canonical_name,
        upstream_path=existing.upstream_path,
        upstream_repo=existing.upstream_repo,
        upstream_commit=existing.upstream_commit,
        license=existing.license,
        available=True,
    )


def _orchestra_skill_catalog_items(
    workspace_skill_map: dict[str, SkillCatalogItem],
) -> list[SkillCatalogItem]:
    source = orchestra_source()
    repo_url = str(
        source.get("repo_url") or "https://github.com/Orchestra-Research/AI-Research-SKILLs"
    )
    commit = str(source.get("commit") or "") or None
    license_name = str(source.get("license") or "MIT")

    items: list[SkillCatalogItem] = []
    for raw in orchestra_skills():
        skill_id = str(raw.get("id") or "").strip()
        if not skill_id:
            continue
        discovered = workspace_skill_map.get(skill_id)
        items.append(
            SkillCatalogItem(
                id=skill_id,
                name=str(raw.get("name") or skill_id.replace("-", " ").title()),
                description=str(raw.get("description") or ""),
                author=str(raw.get("author") or "Orchestra Research"),
                category=str(
                    raw.get("category_name") or raw.get("category_id") or "Orchestra Research"
                ),
                source="orchestra-research",
                is_official=False,
                tags=tuple(str(tag) for tag in (raw.get("tags") or []) if tag),
                path=discovered.path if discovered else None,
                canonical_name=str(raw.get("canonical_name") or "") or None,
                upstream_path=str(raw.get("upstream_path") or "") or None,
                upstream_repo=repo_url,
                upstream_commit=commit,
                license=license_name,
                available=discovered is not None,
            )
        )
    return items


def list_skill_catalog() -> list[SkillCatalogItem]:
    workspace_items = discover_workspace_skills()
    workspace_skill_map: dict[str, SkillCatalogItem] = {item.id: item for item in workspace_items}
    catalog: dict[str, SkillCatalogItem] = {item.id: item for item in OFFICIAL_SKILL_CATALOG}

    for item in _orchestra_skill_catalog_items(workspace_skill_map):
        catalog[item.id] = item

    for item in workspace_items:
        existing = catalog.get(item.id)
        catalog[item.id] = _merge_catalog_item(existing, item) if existing else item

    return sorted(catalog.values(), key=lambda item: (not item.available, item.name.lower()))


def find_skill_catalog_item(skill_id: str) -> SkillCatalogItem | None:
    normalized = str(skill_id).strip()
    if not normalized:
        return None
    return next((item for item in list_skill_catalog() if item.id == normalized), None)


def list_skill_bundles() -> list[dict[str, Any]]:
    catalog = {item.id: item for item in list_skill_catalog()}
    bundles: list[dict[str, Any]] = []
    for raw in orchestra_bundles():
        skill_ids = [str(item) for item in (raw.get("skill_ids") or []) if str(item)]
        available = [
            skill_id
            for skill_id in skill_ids
            if catalog.get(skill_id) and catalog[skill_id].available
        ]
        unavailable = [skill_id for skill_id in skill_ids if skill_id not in available]
        bundles.append(
            {
                "id": str(raw.get("id") or ""),
                "name": str(raw.get("name") or ""),
                "summary": str(raw.get("summary") or ""),
                "description": str(raw.get("description") or ""),
                "skill_ids": skill_ids,
                "skill_count": len(skill_ids),
                "available_skill_count": len(available),
                "unavailable_skill_ids": unavailable,
                "recommended_template_id": raw.get("recommended_template_id"),
                "recommended_swarm_blueprint_id": raw.get("recommended_swarm_blueprint_id"),
                "tags": [str(tag) for tag in (raw.get("tags") or []) if tag],
                "source": "orchestra-research",
            }
        )
    return bundles


def get_skill_bundle(bundle_id: str) -> dict[str, Any] | None:
    normalized = str(bundle_id).strip()
    if not normalized:
        return None
    return next((item for item in list_skill_bundles() if item["id"] == normalized), None)


def _skill_reconciliation_entries(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = config.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    raw_entries = metadata.get(SKILL_RECONCILIATION_METADATA_KEY)
    if not isinstance(raw_entries, dict):
        return {}
    return {
        str(skill_id): dict(payload)
        for skill_id, payload in raw_entries.items()
        if isinstance(skill_id, str) and isinstance(payload, dict)
    }


def _set_skill_reconciliation_entries(
    config: dict[str, Any], entries: dict[str, dict[str, Any]]
) -> None:
    metadata = config.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata[SKILL_RECONCILIATION_METADATA_KEY] = entries
    config["metadata"] = metadata


def _mark_skill_configured(
    entries: dict[str, dict[str, Any]], *, skill_id: str, requested_at: str
) -> None:
    existing = entries.get(skill_id, {})
    if str(existing.get("status") or "").lower() in {"reconciled", "runtime_ready"}:
        return
    entries[skill_id] = {
        "status": "configured",
        "requested_at": str(existing.get("requested_at") or requested_at),
        "configured_at": requested_at,
    }


def install_skill_bundle(agent: Agent, *, bundle_id: str) -> dict[str, Any]:
    bundle = get_skill_bundle(bundle_id)
    if bundle is None:
        raise KeyError(bundle_id)

    config = deserialize_config(agent.config)
    skills = list_configured_skill_ids(agent)
    reconciliation_entries = _skill_reconciliation_entries(config)
    configured_now: list[str] = []
    requested_at = datetime.now(timezone.utc).isoformat()
    for skill_id in bundle["skill_ids"]:
        item = find_skill_catalog_item(skill_id)
        if item is None or not item.available:
            continue
        if skill_id not in skills:
            skills.append(skill_id)
            configured_now.append(skill_id)
        _mark_skill_configured(
            reconciliation_entries,
            skill_id=skill_id,
            requested_at=requested_at,
        )

    config["skills"] = skills
    _set_skill_reconciliation_entries(config, reconciliation_entries)
    agent.config = serialize_config(config)
    return {
        "bundle_id": bundle["id"],
        "configured_skill_ids": [
            skill_id for skill_id in bundle["skill_ids"] if skill_id in skills
        ],
        "newly_configured_skill_ids": configured_now,
        "unavailable_skill_ids": list(bundle["unavailable_skill_ids"]),
        "skills": skills,
    }


def list_swarm_blueprints() -> list[dict[str, Any]]:
    return [item for item in orchestra_swarm_blueprints() if isinstance(item, dict)]


def list_configured_skill_ids(agent: Agent) -> list[str]:
    config = deserialize_config(agent.config)
    raw_skills = config.get("skills") or []
    return [str(skill_id) for skill_id in raw_skills if isinstance(skill_id, str)]


def list_installed_skill_ids(agent: Agent) -> list[str]:
    """Compatibility alias for callers that previously treated configuration as installation."""
    return list_configured_skill_ids(agent)


def skill_catalog_payload(item: SkillCatalogItem) -> dict[str, Any]:
    status = "available" if item.available else "unavailable"
    status_detail = (
        "Available to configure; runtime activation has not been requested."
        if item.available
        else "The catalog entry exists, but its skill files are unavailable to this control plane."
    )
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "author": item.author,
        "category": item.category,
        "source": item.source,
        "is_official": item.is_official,
        "installed": False,
        "configured": False,
        "runtime_ready": False,
        "status": status,
        "reconciliation_required": False,
        "status_detail": status_detail,
        "reconciliation_error": None,
        "tags": list(item.tags),
        "path": item.path,
        "canonical_name": item.canonical_name,
        "upstream_path": item.upstream_path,
        "upstream_repo": item.upstream_repo,
        "upstream_commit": item.upstream_commit,
        "license": item.license,
        "available": item.available,
    }


def _assistant_skill_lifecycle(
    *,
    item: SkillCatalogItem,
    configured: bool,
    reconciliation: dict[str, Any] | None,
) -> dict[str, Any]:
    reconciliation = reconciliation or {}
    reconciliation_status = str(reconciliation.get("status") or "").lower()
    runtime_ready = configured and reconciliation_status in {"reconciled", "runtime_ready"}
    failed = configured and reconciliation_status == "failed"

    if runtime_ready:
        status = "runtime_ready"
        detail = str(
            reconciliation.get("detail")
            or "The assistant runtime has reported successful skill reconciliation."
        )
    elif failed:
        status = "failed"
        detail = str(
            reconciliation.get("error")
            or reconciliation.get("detail")
            or "Runtime reconciliation failed."
        )
    elif configured and not item.available:
        status = "unavailable"
        detail = (
            "Configured for this assistant, but the skill files required for reconciliation "
            "are unavailable to this control plane."
        )
    elif configured:
        status = "configured"
        detail = "Saved in the assistant configuration. Runtime reconciliation has not been proven."
    elif item.available:
        status = "available"
        detail = "Available to configure; runtime activation has not been requested."
    else:
        status = "unavailable"
        detail = "The catalog entry exists, but its skill files are unavailable."

    return {
        # Keep the legacy field truthful: it is only true after runtime evidence exists.
        "installed": runtime_ready,
        "configured": configured,
        "runtime_ready": runtime_ready,
        "status": status,
        "reconciliation_required": configured and not runtime_ready,
        "status_detail": detail,
        "reconciliation_error": detail if failed else None,
    }


def list_assistant_skills(agent: Agent) -> list[dict[str, Any]]:
    config = deserialize_config(agent.config)
    configured_skill_ids = set(list_configured_skill_ids(agent))
    reconciliation_entries = _skill_reconciliation_entries(config)
    entries = []
    for item in list_skill_catalog():
        payload = skill_catalog_payload(item)
        payload.update(
            _assistant_skill_lifecycle(
                item=item,
                configured=item.id in configured_skill_ids,
                reconciliation=reconciliation_entries.get(item.id),
            )
        )
        entries.append(payload)
    return sorted(
        entries,
        key=lambda entry: (
            not entry["configured"],
            not entry["runtime_ready"],
            not entry["available"],
            entry["name"].lower(),
        ),
    )


def update_assistant_skills(agent: Agent, *, skill_id: str, install: bool) -> dict[str, Any]:
    item = find_skill_catalog_item(skill_id)
    if install and item is None:
        raise KeyError(skill_id)
    if install and item is not None and not item.available:
        raise RuntimeError(
            f"Skill '{skill_id}' is catalogued but its files are unavailable to this control plane"
        )

    config = deserialize_config(agent.config)
    skills = list_configured_skill_ids(agent)
    reconciliation_entries = _skill_reconciliation_entries(config)
    if install and skill_id not in skills:
        skills.append(skill_id)
    if install:
        _mark_skill_configured(
            reconciliation_entries,
            skill_id=skill_id,
            requested_at=datetime.now(timezone.utc).isoformat(),
        )
    if not install:
        skills = [existing for existing in skills if existing != skill_id]
        reconciliation_entries.pop(skill_id, None)
    config["skills"] = skills
    _set_skill_reconciliation_entries(config, reconciliation_entries)
    agent.config = serialize_config(config)
    return config


def record_assistant_skill_reconciliation(
    agent: Agent,
    *,
    skill_id: str,
    status: str,
    detail: str | None = None,
) -> dict[str, Any]:
    """Record runtime reconciliation evidence; the owning session must commit the agent."""
    normalized_status = status.strip().lower()
    if normalized_status not in {"configured", "runtime_ready", "failed"}:
        raise ValueError(f"Unsupported skill reconciliation status: {status}")
    if skill_id not in set(list_configured_skill_ids(agent)):
        raise KeyError(skill_id)

    config = deserialize_config(agent.config)
    entries = _skill_reconciliation_entries(config)
    now = datetime.now(timezone.utc).isoformat()
    existing = entries.get(skill_id, {})
    entry = {
        "status": normalized_status,
        "requested_at": str(existing.get("requested_at") or now),
        "configured_at": str(existing.get("configured_at") or now),
    }
    if normalized_status == "runtime_ready":
        entry["reconciled_at"] = now
        if detail:
            entry["detail"] = detail
    elif normalized_status == "failed":
        entry["failed_at"] = now
        entry["error"] = detail or "Runtime reconciliation failed."
    entries[skill_id] = entry
    _set_skill_reconciliation_entries(config, entries)
    agent.config = serialize_config(config)
    return entry


def list_assistant_channels(agent: Agent) -> list[dict[str, Any]]:
    config = deserialize_config(agent.config)
    raw_channels = config.get("channels")
    normalized = default_channel_map()
    if isinstance(raw_channels, dict):
        for channel_id, payload in raw_channels.items():
            existing = normalized.get(
                channel_id,
                {
                    "label": channel_id.replace("_", " ").title(),
                    "enabled": False,
                    "mode": "pairing",
                    "allow_from": [],
                },
            )
            if isinstance(payload, dict):
                existing.update(payload)
            normalized[channel_id] = existing

    return [
        {
            "id": channel_id,
            "label": str(payload.get("label") or channel_id.replace("_", " ").title()),
            "enabled": bool(payload.get("enabled", False)),
            "mode": str(payload.get("mode") or "pairing"),
            "allow_from": [
                str(item) for item in (payload.get("allow_from") or []) if isinstance(item, str)
            ],
        }
        for channel_id, payload in sorted(normalized.items())
    ]


def list_assistant_wakeups(agent: Agent) -> list[dict[str, Any]]:
    config = deserialize_config(agent.config)
    wakeups = config.get("wakeups") or []
    items: list[dict[str, Any]] = []
    for wakeup in wakeups:
        if isinstance(wakeup, dict):
            items.append(
                {
                    "enabled": bool(wakeup.get("enabled", False)),
                    "schedule": wakeup.get("schedule"),
                    "timezone": wakeup.get("timezone"),
                    "label": wakeup.get("label"),
                }
            )
    return items


def _normalize_timestamp(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0
        if stripped.isdigit():
            return int(stripped)
        try:
            return int(datetime.fromisoformat(stripped.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return 0
    return 0


def _format_age(last_activity: int, start_time: int) -> str:
    baseline = last_activity or start_time or int(time.time())
    age_seconds = max(0, int(time.time()) - baseline)
    if age_seconds < 60:
        return f"{age_seconds}s"
    if age_seconds < 3600:
        return f"{age_seconds // 60}m"
    if age_seconds < 86400:
        return f"{age_seconds // 3600}h"
    return f"{age_seconds // 86400}d"


def _session_matches_assistant(raw: dict[str, Any], assistant_id: str | None) -> bool:
    if not assistant_id:
        return True

    needle = assistant_id.strip().lower()
    candidates = [
        raw.get("assistant_id"),
        raw.get("assistant"),
        raw.get("agent"),
        raw.get("workspace"),
        raw.get("name"),
        raw.get("key"),
        raw.get("session_key"),
        raw.get("id"),
    ]
    return any(needle in str(candidate).lower() for candidate in candidates if candidate)


def _normalize_flags(raw: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    raw_flags = raw.get("flags")
    if isinstance(raw_flags, list):
        flags.extend(str(flag) for flag in raw_flags if flag)

    for key in ("thinking", "verbose", "reasoning", "label"):
        value = raw.get(key)
        if value in (None, "", False):
            continue
        flags.append(key if value is True else f"{key}:{value}")

    return list(dict.fromkeys(flags))


def _normalize_gateway_session(raw: dict[str, Any]) -> dict[str, Any] | None:
    key = str(
        raw.get("key") or raw.get("session_key") or raw.get("session") or raw.get("id") or ""
    ).strip()
    if not key:
        return None

    start_time = _normalize_timestamp(
        raw.get("start_time") or raw.get("created_at") or raw.get("started_at")
    )
    last_activity = _normalize_timestamp(
        raw.get("last_activity") or raw.get("updated_at") or raw.get("timestamp")
    )
    total_tokens = raw.get("tokens") or raw.get("total_tokens")
    if total_tokens is None:
        input_tokens = int(raw.get("input_tokens") or 0)
        output_tokens = int(raw.get("output_tokens") or 0)
        total_tokens = input_tokens + output_tokens if input_tokens or output_tokens else ""

    status = str(raw.get("status") or "").lower()
    active = bool(raw.get("active", status in {"active", "running", "open", "available"}))
    agent = str(
        raw.get("agent")
        or raw.get("assistant")
        or raw.get("assistant_id")
        or raw.get("workspace")
        or "unknown"
    )

    normalized = {
        "id": str(raw.get("id") or key),
        "key": key,
        "agent": agent,
        "kind": str(raw.get("kind") or raw.get("type") or "session"),
        "age": _format_age(last_activity, start_time),
        "model": str(raw.get("model") or raw.get("provider_model") or "unknown"),
        "tokens": str(total_tokens),
        "channel": str(raw.get("channel") or raw.get("source") or "direct"),
        "flags": _normalize_flags(raw),
        "active": active,
        "start_time": start_time,
        "last_activity": last_activity or start_time,
        "source": str(raw.get("source") or "openclaw"),
    }
    if raw.get("agent_id") is not None:
        # Preserve immutable provider identity for the ownership layer. Mutable
        # assistant names and workspace labels must never become authority.
        normalized["agent_id"] = raw["agent_id"]
    return normalized


def _gateway_base_url() -> tuple[int | None, str | None]:
    port = get_detected_gateway_port()
    host = os.environ.get("OPENCLAW_GATEWAY_HOST", "127.0.0.1")
    if port is None:
        return None, None
    return port, f"http://{host}:{port}"


def _gateway_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = get_detected_gateway_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_gateway_json(paths: tuple[str, ...]) -> Any | None:
    _port, base_url = _gateway_base_url()
    if not base_url:
        return None

    headers = _gateway_headers()
    with httpx.Client(timeout=3.0, follow_redirects=False) as client:
        for path in paths:
            try:
                response = client.get(f"{base_url}{path}", headers=headers)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                payload = response.text
                if not payload:
                    return None
                return json.loads(payload)
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                logger.debug("Gateway request failed for %s: %s", path, exc)
                return None
    return None


def _load_sessions_from_json_store(
    state_dir: Path,
    assistant_id: str | None = None,
) -> list[dict[str, Any]]:
    agents_dir = state_dir / "agents"
    if not agents_dir.exists():
        return []

    discovered: list[dict[str, Any]] = []
    for agent_dir in agents_dir.iterdir():
        sessions_file = agent_dir / "sessions" / "sessions.json"
        if not sessions_file.is_file():
            continue

        agent_name = agent_dir.name
        if assistant_id and agent_name != assistant_id:
            continue

        try:
            payload = json.loads(sessions_file.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(payload, dict):
            continue

        for key, entry in payload.items():
            if not isinstance(entry, dict):
                continue

            updated_at = _normalize_timestamp(
                entry.get("updatedAt") or entry.get("updated_at") or entry.get("last_activity")
            )
            created_at = _normalize_timestamp(
                entry.get("startedAt")
                or entry.get("createdAt")
                or entry.get("created_at")
                or updated_at
            )
            channel = (
                (entry.get("deliveryContext") or {}).get("channel")
                or entry.get("lastChannel")
                or entry.get("channel")
                or "direct"
            )
            total_tokens = entry.get("totalTokens")
            if total_tokens is None:
                total_tokens = int(entry.get("inputTokens") or 0) + int(
                    entry.get("outputTokens") or 0
                )

            raw = {
                "id": entry.get("sessionId") or f"{agent_name}:{key}",
                "key": str(key),
                "assistant_id": agent_name,
                "agent": agent_name,
                "kind": entry.get("chatType") or entry.get("kind") or "session",
                "created_at": created_at,
                "updated_at": updated_at,
                "model": entry.get("model"),
                "channel": channel,
                "total_tokens": total_tokens,
                "active": bool(updated_at and (int(time.time()) - updated_at) < (90 * 60)),
                "source": "openclaw-local",
            }
            normalized = _normalize_gateway_session(raw)
            if normalized is not None:
                discovered.append(normalized)

    return discovered


def _load_sessions_from_state_dir(assistant_id: str | None = None) -> list[dict[str, Any]]:
    state_dir = get_detected_openclaw_state_dir()
    if state_dir is None or not state_dir.exists():
        return []

    discovered: list[dict[str, Any]] = _load_sessions_from_json_store(state_dir, assistant_id)

    candidates = [
        state_dir / "sessions",
        state_dir / "gateway" / "sessions",
        state_dir / "state" / "sessions",
    ]
    for root in candidates:
        if not root.exists():
            continue
        for path in root.rglob("*.json*"):
            try:
                stat = path.stat()
            except OSError:
                continue
            raw = {
                "id": path.stem,
                "key": path.stem,
                "assistant_id": assistant_id or root.name,
                "agent": assistant_id or root.name,
                "kind": path.suffix.lstrip(".") or "session",
                "created_at": int(stat.st_ctime),
                "updated_at": int(stat.st_mtime),
                "source": "openclaw-state",
            }
            if not _session_matches_assistant(raw, assistant_id):
                continue
            normalized = _normalize_gateway_session(raw)
            if normalized is not None:
                discovered.append(normalized)

    deduped: dict[str, dict[str, Any]] = {}
    for session in discovered:
        key = str(session.get("key") or session.get("id") or "")
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None or session.get("last_activity", 0) >= existing.get("last_activity", 0):
            deduped[key] = session

    return sorted(deduped.values(), key=lambda item: item.get("last_activity", 0), reverse=True)


def list_gateway_sessions(*, assistant_id: str | None = None) -> list[dict[str, Any]]:
    payload = _request_gateway_json(("/api/sessions", "/sessions"))
    raw_sessions: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        items = payload.get("sessions") or payload.get("items") or payload.get("data") or []
        if isinstance(items, list):
            raw_sessions = [item for item in items if isinstance(item, dict)]
    elif isinstance(payload, list):
        raw_sessions = [item for item in payload if isinstance(item, dict)]

    sessions = [
        normalized
        for normalized in (
            _normalize_gateway_session(item)
            for item in raw_sessions
            if _session_matches_assistant(item, assistant_id)
        )
        if normalized is not None
    ]

    if not sessions:
        sessions = _load_sessions_from_state_dir(assistant_id)

    sessions.sort(key=lambda item: item.get("last_activity", 0), reverse=True)
    return sessions


def collect_gateway_health(*, include_host_diagnostics: bool = False) -> dict[str, Any]:
    if not include_host_diagnostics:
        return {
            "status": "restricted",
            "cli_available": None,
            "gateway_configured": None,
            "gateway_reachable": None,
            "gateway_port": None,
            "gateway_url": None,
            "credential_detected": None,
            "config_path": None,
            "state_dir": None,
            "doctor_summary": "Gateway host diagnostics are restricted to administrators.",
        }

    config_path = get_detected_openclaw_config_path()
    detected_state_dir = get_detected_openclaw_state_dir()
    state_dir = detected_state_dir if detected_state_dir and detected_state_dir.exists() else None
    port, gateway_url = _gateway_base_url()
    credential_detected = bool(get_detected_gateway_token())
    gateway_reachable = _request_gateway_json(("/health", "/api/health")) is not None
    gateway_configured = any([config_path, credential_detected, port is not None])
    cli_available = config_path is not None or state_dir is not None

    if gateway_reachable:
        status = "healthy"
        doctor_summary = "OpenClaw gateway is reachable and returning health data."
    elif gateway_configured:
        status = "configured"
        doctor_summary = (
            "OpenClaw configuration was detected, but the local gateway is not reachable from this process. "
            "Start the operator runtime or check gateway auth and port settings."
        )
    else:
        status = "client_required"
        doctor_summary = (
            "Local OpenClaw runtime state is resolved from the operator host. "
            "Use the MUTX CLI or TUI on that machine to inspect live health and sessions."
        )

    return {
        "status": status,
        "cli_available": cli_available,
        "gateway_configured": gateway_configured,
        "gateway_reachable": gateway_reachable,
        "gateway_port": port,
        "gateway_url": gateway_url,
        "credential_detected": credential_detected,
        "config_path": str(config_path) if config_path else None,
        "state_dir": str(state_dir) if state_dir else None,
        "doctor_summary": doctor_summary,
    }


def collect_assistant_overview(
    agent: Agent,
    deployments: list[Any],
    *,
    include_host_diagnostics: bool = False,
) -> dict[str, Any]:
    config = deserialize_config(agent.config)
    assistant_id = str(config.get("assistant_id") or slugify_assistant_id(agent.name))
    onboarding_status = "needs_deployment" if not deployments else "deployed"

    return {
        "agent_id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "runtime": str(config.get("runtime") or DEFAULT_TEMPLATE_ID),
        "template_id": str(config.get("template") or DEFAULT_TEMPLATE_ID),
        "status": agent.status,
        "onboarding_status": onboarding_status,
        "assistant_id": assistant_id,
        "workspace": str(config.get("workspace") or assistant_id),
        "last_activity": None,
        "session_count": 0,
        "installed_skills": [item for item in list_assistant_skills(agent) if item["installed"]],
        "channels": list_assistant_channels(agent),
        "wakeups": list_assistant_wakeups(agent),
        "gateway": collect_gateway_health(
            include_host_diagnostics=include_host_diagnostics,
        ),
        "deployments": deployments,
        "config": config,
    }
