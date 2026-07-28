from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx


class Skill:
    def __init__(self, data: dict[str, Any]):
        self.id = data["id"]
        self.name = data["name"]
        self.description = data["description"]
        self.author = data["author"]
        self.stars = data.get("stars", 0)
        self.category = data["category"]
        self.source = data.get("source", "catalog")
        self.is_official = data.get("is_official", False)
        self.tags = list(data.get("tags") or [])
        self.path = data.get("path")
        self.canonical_name = data.get("canonical_name")
        self.upstream_path = data.get("upstream_path")
        self.upstream_repo = data.get("upstream_repo")
        self.upstream_commit = data.get("upstream_commit")
        self.license = data.get("license")
        self.available = data.get("available", True)
        self._data = data

    def __repr__(self) -> str:
        return f"Skill(id={self.id}, name={self.name}, author={self.author})"


class SkillBundle:
    def __init__(self, data: dict[str, Any]):
        self.id = data["id"]
        self.name = data["name"]
        self.summary = data.get("summary", "")
        self.description = data.get("description", "")
        self.skill_ids = list(data.get("skill_ids") or [])
        self.skill_count = int(data.get("skill_count", len(self.skill_ids)))
        self.available_skill_count = int(data.get("available_skill_count", 0))
        self.unavailable_skill_ids = list(data.get("unavailable_skill_ids") or [])
        self.recommended_template_id = data.get("recommended_template_id")
        self.recommended_swarm_blueprint_id = data.get("recommended_swarm_blueprint_id")
        self.tags = list(data.get("tags") or [])
        self.source = data.get("source", "orchestra-research")
        self._data = data

    def __repr__(self) -> str:
        return f"SkillBundle(id={self.id}, skills={self.skill_count})"


class ClawHub:
    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self._client = client

    def list_skills(self) -> list[Skill]:
        """Returns the current MUTX skill catalog."""
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use alist_skills() for async clients")
        response = self._client.get("clawhub/skills")
        response.raise_for_status()
        return [Skill(data) for data in response.json()]

    async def alist_skills(self) -> list[Skill]:
        """Returns the current MUTX skill catalog (Async)."""
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use list_skills() for sync clients")
        response = await self._client.get("clawhub/skills")
        response.raise_for_status()
        return [Skill(data) for data in response.json()]

    def list_bundles(self) -> list[SkillBundle]:
        """Returns curated skill bundles."""
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use alist_bundles() for async clients")
        response = self._client.get("clawhub/bundles")
        response.raise_for_status()
        return [SkillBundle(data) for data in response.json()]

    async def alist_bundles(self) -> list[SkillBundle]:
        """Returns curated skill bundles (Async)."""
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use list_bundles() for sync clients")
        response = await self._client.get("clawhub/bundles")
        response.raise_for_status()
        return [SkillBundle(data) for data in response.json()]

    def install_skill(self, agent_id: UUID | str, skill_id: str) -> dict[str, Any]:
        """Installs a skill to an agent's configuration."""
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use ainstall_skill() for async clients")
        response = self._client.post(
            "clawhub/install",
            json={"agent_id": str(agent_id), "skill_id": skill_id},
        )
        response.raise_for_status()
        return response.json()

    async def ainstall_skill(self, agent_id: UUID | str, skill_id: str) -> dict[str, Any]:
        """Installs a skill to an agent's configuration (Async)."""
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use install_skill() for sync clients")
        response = await self._client.post(
            "clawhub/install",
            json={"agent_id": str(agent_id), "skill_id": skill_id},
        )
        response.raise_for_status()
        return response.json()

    def install_bundle(self, agent_id: UUID | str, bundle_id: str) -> dict[str, Any]:
        """Installs all currently available skills in a curated bundle."""
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use ainstall_bundle() for async clients")
        response = self._client.post(
            "clawhub/install-bundle",
            json={"agent_id": str(agent_id), "bundle_id": bundle_id},
        )
        response.raise_for_status()
        return response.json()

    async def ainstall_bundle(self, agent_id: UUID | str, bundle_id: str) -> dict[str, Any]:
        """Installs all currently available skills in a curated bundle (Async)."""
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use install_bundle() for sync clients")
        response = await self._client.post(
            "clawhub/install-bundle",
            json={"agent_id": str(agent_id), "bundle_id": bundle_id},
        )
        response.raise_for_status()
        return response.json()

    def uninstall_skill(self, agent_id: UUID | str, skill_id: str) -> dict[str, Any]:
        """Removes a skill from an agent's configuration."""
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use auninstall_skill() for async clients")
        response = self._client.post(
            "clawhub/uninstall",
            json={"agent_id": str(agent_id), "skill_id": skill_id},
        )
        response.raise_for_status()
        return response.json()

    async def auninstall_skill(self, agent_id: UUID | str, skill_id: str) -> dict[str, Any]:
        """Removes a skill from an agent's configuration (Async)."""
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError("Use uninstall_skill() for sync clients")
        response = await self._client.post(
            "clawhub/uninstall",
            json={"agent_id": str(agent_id), "skill_id": skill_id},
        )
        response.raise_for_status()
        return response.json()
