"""Templates API SDK - /templates endpoints."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from mutx._http import api_path


class AssistantTemplate:
    """Represents an assistant template."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.description: str = data.get("description", "")
        self.category: str = data.get("category", "")
        self.icon: Optional[str] = data.get("icon")
        self.default_model: Optional[str] = data.get("default_model")
        self.skills: list[str] = data.get("skills", [])
        self.config: dict[str, Any] = data.get("config", {})
        self._data = data

    def __repr__(self) -> str:
        return f"AssistantTemplate(id={self.id}, name={self.name})"


class TemplateDeployResponse:
    """Response from deploying a template."""

    def __init__(self, data: dict[str, Any]):
        self.template_id: str = data["template_id"]
        self.agent: dict = data["agent"]
        self.deployment: dict = data["deployment"]
        self._data = data


class Templates:
    """SDK resource for /templates endpoints."""

    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self._client = client

    def _require_sync_client(self) -> None:
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This resource requires a sync httpx.Client. For async clients, use the `a*` methods."
            )

    def _require_async_client(self) -> None:
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This async resource helper requires an async httpx.AsyncClient and an `a*` method call."
            )

    def list(self) -> list[AssistantTemplate]:
        """List all available assistant templates."""
        self._require_sync_client()
        response = self._client.get("templates")
        response.raise_for_status()
        return [AssistantTemplate(d) for d in response.json()]

    async def alist(self) -> list[AssistantTemplate]:
        """List all available assistant templates (async)."""
        self._require_async_client()
        response = await self._client.get("templates")
        response.raise_for_status()
        return [AssistantTemplate(d) for d in response.json()]

    def deploy(
        self,
        template_id: str,
        name: str,
        description: Optional[str] = None,
        model: Optional[str] = None,
        workspace: Optional[str] = None,
        assistant_id: Optional[str] = None,
        skills: Optional[list[str]] = None,
        channels: Optional[dict[str, Any]] = None,
        replicas: int = 1,
        runtime_metadata: Optional[dict[str, Any]] = None,
    ) -> TemplateDeployResponse:
        """Deploy a template to create a new agent and deployment.

        Args:
            template_id: Template ID to deploy
            name: Name for the new agent
            description: Optional description
            model: Optional model override
            workspace: Optional workspace path
            assistant_id: Optional assistant ID
            skills: Optional list of skill IDs to install
            channels: Optional channel configurations
            replicas: Number of replicas (default 1)
            runtime_metadata: Optional runtime metadata
        """
        self._require_sync_client()
        payload: dict[str, Any] = {"name": name, "replicas": replicas}
        if description:
            payload["description"] = description
        if model:
            payload["model"] = model
        if workspace:
            payload["workspace"] = workspace
        if assistant_id:
            payload["assistant_id"] = assistant_id
        if skills:
            payload["skills"] = skills
        if channels:
            payload["channels"] = channels
        if runtime_metadata:
            payload["runtime_metadata"] = runtime_metadata

        response = self._client.post(
            api_path("templates/{template_id}/deploy", template_id=template_id), json=payload
        )
        response.raise_for_status()
        return TemplateDeployResponse(response.json())

    async def adeploy(
        self,
        template_id: str,
        name: str,
        description: Optional[str] = None,
        model: Optional[str] = None,
        workspace: Optional[str] = None,
        assistant_id: Optional[str] = None,
        skills: Optional[list[str]] = None,
        channels: Optional[dict[str, Any]] = None,
        replicas: int = 1,
        runtime_metadata: Optional[dict[str, Any]] = None,
    ) -> TemplateDeployResponse:
        """Deploy a template (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {"name": name, "replicas": replicas}
        if description:
            payload["description"] = description
        if model:
            payload["model"] = model
        if workspace:
            payload["workspace"] = workspace
        if assistant_id:
            payload["assistant_id"] = assistant_id
        if skills:
            payload["skills"] = skills
        if channels:
            payload["channels"] = channels
        if runtime_metadata:
            payload["runtime_metadata"] = runtime_metadata

        response = await self._client.post(
            api_path("templates/{template_id}/deploy", template_id=template_id), json=payload
        )
        response.raise_for_status()
        return TemplateDeployResponse(response.json())
