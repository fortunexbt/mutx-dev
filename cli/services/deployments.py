from __future__ import annotations

from typing import Any

from cli.services.base import APIService
from cli.services.models import (
    DeploymentEventHistory,
    DeploymentRecord,
    DeploymentVersionHistory,
    LogEntry,
    MetricPoint,
)


class DeploymentsService(APIService):
    def list_deployments(
        self,
        *,
        limit: int = 50,
        skip: int = 0,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> list[DeploymentRecord]:
        params: dict[str, Any] = {"limit": limit, "skip": skip}
        if agent_id:
            params["agent_id"] = agent_id
        if status:
            params["status"] = status

        response = self._request("get", "/v1/deployments", params=params)
        self._expect_status(response, {200})
        payload = self._decode_json(response, expected_type=(dict, list))
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        return [DeploymentRecord.from_payload(item) for item in items if isinstance(item, dict)]

    def get_deployment(self, deployment_id: str) -> DeploymentRecord:
        response = self._request("get", f"/v1/deployments/{deployment_id}")
        self._expect_status(response, {200}, not_found_message="Deployment not found")
        return DeploymentRecord.from_payload(self._decode_json(response, expected_type=dict))

    def create_deployment(self, *, agent_id: str, replicas: int = 1) -> DeploymentRecord:
        response = self._request(
            "post",
            "/v1/deployments",
            json={"agent_id": agent_id, "replicas": replicas},
        )
        self._expect_status(
            response,
            {201},
            not_found_message="Agent not found",
            invalid_message="Cannot create deployment",
        )
        return DeploymentRecord.from_payload(self._decode_json(response, expected_type=dict))

    def get_events(
        self,
        deployment_id: str,
        *,
        limit: int = 100,
        skip: int = 0,
        event_type: str | None = None,
        status: str | None = None,
    ) -> DeploymentEventHistory:
        params: dict[str, Any] = {"limit": limit, "skip": skip}
        if event_type:
            params["event_type"] = event_type
        if status:
            params["status"] = status

        response = self._request("get", f"/v1/deployments/{deployment_id}/events", params=params)
        self._expect_status(response, {200}, not_found_message="Deployment not found")
        return DeploymentEventHistory.from_payload(self._decode_json(response, expected_type=dict))

    def restart_deployment(self, deployment_id: str) -> DeploymentRecord:
        response = self._request("post", f"/v1/deployments/{deployment_id}/restart")
        self._expect_status(
            response,
            {200},
            not_found_message="Deployment not found",
            invalid_message="Cannot restart deployment",
        )
        return DeploymentRecord.from_payload(self._decode_json(response, expected_type=dict))

    def get_versions(self, deployment_id: str) -> DeploymentVersionHistory:
        response = self._request("get", f"/v1/deployments/{deployment_id}/versions")
        self._expect_status(response, {200}, not_found_message="Deployment not found")
        return DeploymentVersionHistory.from_payload(
            self._decode_json(response, expected_type=dict)
        )

    def rollback_deployment(self, deployment_id: str, *, version: int) -> DeploymentRecord:
        response = self._request(
            "post",
            f"/v1/deployments/{deployment_id}/rollback",
            json={"version": version},
        )
        self._expect_status(
            response,
            {200},
            not_found_message="Deployment not found",
            invalid_message="Cannot rollback deployment",
        )
        return DeploymentRecord.from_payload(self._decode_json(response, expected_type=dict))

    def get_logs(
        self,
        deployment_id: str,
        *,
        limit: int = 100,
        skip: int = 0,
        level: str | None = None,
    ) -> list[LogEntry]:
        params: dict[str, Any] = {"limit": limit, "skip": skip}
        if level:
            params["level"] = level

        response = self._request("get", f"/v1/deployments/{deployment_id}/logs", params=params)
        self._expect_status(response, {200}, not_found_message="Deployment not found")
        payload = self._decode_json(response, expected_type=(dict, list))
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        return [LogEntry.from_payload(item) for item in items if isinstance(item, dict)]

    def get_metrics(
        self,
        deployment_id: str,
        *,
        limit: int = 100,
        skip: int = 0,
    ) -> list[MetricPoint]:
        response = self._request(
            "get",
            f"/v1/deployments/{deployment_id}/metrics",
            params={"limit": limit, "skip": skip},
        )
        self._expect_status(response, {200}, not_found_message="Deployment not found")
        payload = self._decode_json(response, expected_type=(dict, list))
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        return [MetricPoint.from_payload(item) for item in items if isinstance(item, dict)]

    def scale_deployment(self, deployment_id: str, *, replicas: int) -> DeploymentRecord:
        response = self._request(
            "post",
            f"/v1/deployments/{deployment_id}/scale",
            json={"replicas": replicas},
        )
        self._expect_status(
            response,
            {200},
            not_found_message="Deployment not found",
            invalid_message="Cannot scale deployment",
        )
        return DeploymentRecord.from_payload(self._decode_json(response, expected_type=dict))

    def delete_deployment(self, deployment_id: str) -> None:
        response = self._request("delete", f"/v1/deployments/{deployment_id}")
        self._expect_status(response, {204}, not_found_message="Deployment not found")
