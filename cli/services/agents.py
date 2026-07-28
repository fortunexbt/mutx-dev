from __future__ import annotations

import json
from typing import Any, Callable

from cli.openclaw_runtime import reconcile_openclaw_agent_config
from cli.services.base import APIService, ValidationError
from cli.services.models import AgentDeploymentResult, AgentRecord, LogEntry


class AgentsService(APIService):
    def list_agents(self, *, limit: int = 50, skip: int = 0) -> list[AgentRecord]:
        response = self._request("get", "/v1/agents", params={"limit": limit, "skip": skip})
        self._expect_status(response, {200})
        payload = self._decode_json(response, expected_type=(dict, list))
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        return [AgentRecord.from_payload(item) for item in items]

    def get_agent(self, agent_id: str) -> AgentRecord:
        response = self._request("get", f"/v1/agents/{agent_id}")
        self._expect_status(response, {200}, not_found_message="Agent not found")
        return AgentRecord.from_payload(self._decode_json(response, expected_type=dict))

    def create_agent(
        self,
        *,
        name: str,
        description: str = "",
        agent_type: str = "openai",
        config: dict[str, Any] | str | None = None,
    ) -> AgentRecord:
        config_payload = config or {}
        if isinstance(config_payload, str):
            try:
                config_payload = json.loads(config_payload)
            except json.JSONDecodeError as exc:
                raise ValidationError("Invalid JSON in config") from exc

        if not isinstance(config_payload, dict):
            raise ValidationError("Invalid JSON in config")

        response = self._request(
            "post",
            "/v1/agents",
            json={
                "name": name,
                "description": description,
                "type": agent_type,
                "config": config_payload,
            },
        )
        self._expect_status(response, {201}, invalid_message="Invalid agent configuration")
        return AgentRecord.from_payload(self._decode_json(response, expected_type=dict))

    def update_config(self, agent_id: str, config: dict[str, Any]) -> AgentRecord:
        response = self._request(
            "patch",
            f"/v1/agents/{agent_id}/config",
            json={"config": config},
        )
        self._expect_status(response, {200}, not_found_message="Agent not found")
        detail = self.get_agent(agent_id)
        return detail

    def ensure_openclaw_binding(
        self,
        agent: AgentRecord,
        *,
        install_if_missing: bool,
        install_method: str,
        no_input: bool,
        prompt_install: Callable[[], bool] | None = None,
        install_command_runner: Callable[[str], None] | None = None,
        onboard_command_runner: Callable[[list[str]], None] | None = None,
    ) -> AgentRecord:
        if agent.type != "openclaw":
            return agent

        updated_config, _binding, _health = reconcile_openclaw_agent_config(
            agent_name=agent.name,
            config=agent.config,
            install_if_missing=install_if_missing,
            install_method=install_method,
            no_input=no_input,
            prompt_install=prompt_install,
            install_command_runner=install_command_runner,
            onboard_command_runner=onboard_command_runner,
        )
        if agent.config == updated_config:
            return agent
        return self.update_config(agent.id, updated_config)

    def deploy_agent(self, agent_id: str) -> AgentDeploymentResult:
        response = self._request("post", f"/v1/agents/{agent_id}/deploy")
        self._expect_status(response, {200}, not_found_message="Agent not found")
        return AgentDeploymentResult.from_payload(self._decode_json(response, expected_type=dict))

    def get_logs(
        self,
        agent_id: str,
        *,
        limit: int = 100,
        level: str | None = None,
    ) -> list[LogEntry]:
        params: dict[str, Any] = {"limit": limit}
        if level:
            params["level"] = level

        response = self._request("get", f"/v1/agents/{agent_id}/logs", params=params)
        self._expect_status(response, {200}, not_found_message="Agent not found")
        payload = self._decode_json(response, expected_type=dict)
        return [
            LogEntry.from_payload(item)
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]

    def stop_agent(self, agent_id: str) -> str | None:
        response = self._request("post", f"/v1/agents/{agent_id}/stop")
        self._expect_status(response, {200}, not_found_message="Agent not found")
        payload = self._decode_json(response, expected_type=dict)
        return payload.get("status")

    def delete_agent(self, agent_id: str) -> None:
        response = self._request("delete", f"/v1/agents/{agent_id}")
        self._expect_status(response, {204}, not_found_message="Agent not found")
