from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Any

from cli.errors import CLIServiceError, ValidationError
from cli.services.base import APIService
from cli.services.models import (
    ReasoningArtifactRecord,
    ReasoningJobHistoryRecord,
    ReasoningJobRecord,
    ReasoningLocalLaunchRecord,
    ReasoningTemplateRecord,
)


def _guess_content_type(path: Path) -> str | None:
    content_type, _encoding = mimetypes.guess_type(path.name)
    return content_type


class ReasoningService(APIService):
    def list_templates(self) -> list[ReasoningTemplateRecord]:
        response = self._request("get", "/v1/reasoning/templates", require_auth=False)
        self._expect_status(response, {200})
        payload = self._decode_json(response, expected_type=list)
        return [ReasoningTemplateRecord.from_payload(item) for item in payload]

    def create_job(
        self,
        *,
        template_id: str,
        execution_mode: str,
        parameters: dict[str, Any] | None = None,
    ) -> ReasoningJobRecord:
        response = self._request(
            "post",
            "/v1/reasoning/jobs",
            json={
                "template_id": template_id,
                "execution_mode": execution_mode,
                "parameters": parameters or {},
            },
        )
        self._expect_status(response, {201}, invalid_message="Unable to create reasoning job")
        return ReasoningJobRecord.from_payload(self._decode_json(response, expected_type=dict))

    def list_jobs(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        status_filter: str | None = None,
        template_id: str | None = None,
    ) -> ReasoningJobHistoryRecord:
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if status_filter:
            params["status"] = status_filter
        if template_id:
            params["template_id"] = template_id
        response = self._request("get", "/v1/reasoning/jobs", params=params)
        self._expect_status(response, {200})
        return ReasoningJobHistoryRecord.from_payload(
            self._decode_json(response, expected_type=dict)
        )

    def get_job(self, job_id: str) -> ReasoningJobRecord:
        response = self._request("get", f"/v1/reasoning/jobs/{job_id}")
        self._expect_status(response, {200}, not_found_message="Reasoning job not found")
        return ReasoningJobRecord.from_payload(self._decode_json(response, expected_type=dict))

    def register_artifact_reference(
        self,
        *,
        job_id: str,
        role: str,
        kind: str,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> ReasoningArtifactRecord:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise ValidationError(f"Artifact path does not exist: {path}")

        payload = {
            "role": role,
            "kind": kind,
            "storage_backend": "local_reference",
            "filename": path.name,
            "local_path": str(path),
            "content_type": _guess_content_type(path),
            "size_bytes": path.stat().st_size,
            "metadata": metadata or {},
        }
        response = self._request("post", f"/v1/reasoning/jobs/{job_id}/artifacts", json=payload)
        self._expect_status(
            response, {201}, invalid_message="Unable to register reasoning artifact"
        )
        return ReasoningArtifactRecord.from_payload(self._decode_json(response, expected_type=dict))

    def upload_artifact(
        self,
        *,
        job_id: str,
        role: str,
        kind: str,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> ReasoningArtifactRecord:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise ValidationError(f"Artifact path does not exist: {path}")

        with path.open("rb") as handle:
            files = {
                "file": (path.name, handle, _guess_content_type(path) or "application/octet-stream")
            }
            data = {
                "role": role,
                "kind": kind,
                "metadata": json.dumps(metadata or {}),
            }
            response = self._request(
                "post",
                f"/v1/reasoning/jobs/{job_id}/artifacts",
                files=files,
                data=data,
            )
        self._expect_status(response, {201}, invalid_message="Unable to upload reasoning artifact")
        return ReasoningArtifactRecord.from_payload(self._decode_json(response, expected_type=dict))

    def dispatch_job(self, *, job_id: str, mode: str) -> ReasoningJobRecord:
        response = self._request(
            "post",
            f"/v1/reasoning/jobs/{job_id}/dispatch",
            json={"mode": mode},
        )
        self._expect_status(response, {200}, invalid_message="Unable to dispatch reasoning job")
        return ReasoningJobRecord.from_payload(self._decode_json(response, expected_type=dict))

    def launch_local(
        self, *, job_id: str, output_dir: str | None = None
    ) -> ReasoningLocalLaunchRecord:
        response = self._request(
            "post",
            f"/v1/reasoning/jobs/{job_id}/launch-local",
            json={"output_dir": output_dir},
        )
        self._expect_status(
            response, {200}, invalid_message="Unable to launch reasoning job locally"
        )
        return ReasoningLocalLaunchRecord.from_payload(
            self._decode_json(response, expected_type=dict)
        )

    def submit_event(
        self,
        *,
        job_id: str,
        event_type: str,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        status_value: str | None = None,
        output_text: str | None = None,
        error_message: str | None = None,
        result_summary: dict[str, Any] | None = None,
    ) -> ReasoningJobRecord:
        body = {
            "event_type": event_type,
            "message": message,
            "payload": payload or {},
            "status": status_value,
            "output_text": output_text,
            "error_message": error_message,
            "result_summary": result_summary,
        }
        response = self._request("post", f"/v1/reasoning/jobs/{job_id}/events", json=body)
        self._expect_status(response, {200}, invalid_message="Unable to submit reasoning job event")
        return ReasoningJobRecord.from_payload(self._decode_json(response, expected_type=dict))

    def download_artifact(
        self,
        *,
        job_id: str,
        artifact_id: str,
        destination: str | None = None,
    ) -> Path:
        response = self._request(
            "get",
            f"/v1/reasoning/jobs/{job_id}/artifacts/{artifact_id}",
            allow_refresh=True,
        )
        self._expect_status(response, {200}, not_found_message="Reasoning artifact not found")

        header = response.headers.get("content-disposition", "")
        filename = artifact_id
        if "filename=" in header:
            filename = header.split("filename=", 1)[1].strip().strip('"')

        path = Path(destination).expanduser().resolve() if destination else Path.cwd() / filename
        if path.exists() and path.is_dir():
            path = path / filename

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return path

    def run_local_job(
        self,
        *,
        job: ReasoningJobRecord,
        output_dir: str | None = None,
    ) -> ReasoningJobRecord:
        try:
            from src.api.services.reasoning_engine import execute_reasoning_manifest
        except Exception as exc:  # noqa: BLE001
            raise CLIServiceError(
                "Local reasoning execution requires the backend source tree to be available."
            ) from exc

        launch = self.launch_local(job_id=job.id, output_dir=output_dir)
        self.submit_event(
            job_id=job.id,
            event_type="reasoning.pass_started",
            message="Local reasoning execution started",
            payload={"execution_mode": "local"},
            status_value="running",
        )

        try:
            execution_result = asyncio.run(execute_reasoning_manifest(launch.manifest))
            for event in execution_result.events:
                self.submit_event(
                    job_id=job.id,
                    event_type=event.event_type,
                    message=event.message,
                    payload=event.payload,
                )
            for artifact in execution_result.artifacts:
                self.upload_artifact(
                    job_id=job.id,
                    role=artifact.role,
                    kind=artifact.kind,
                    file_path=str(artifact.path),
                    metadata=artifact.metadata,
                )
            return self.submit_event(
                job_id=job.id,
                event_type="reasoning.completed",
                message="Local reasoning execution completed",
                payload={"driver": execution_result.driver},
                status_value="completed",
                output_text=execution_result.output_text,
                result_summary=execution_result.summary,
            )
        except Exception as exc:  # noqa: BLE001
            return self.submit_event(
                job_id=job.id,
                event_type="reasoning.failed",
                message="Local reasoning execution failed",
                payload={"error": str(exc)},
                status_value="failed",
                error_message=str(exc),
            )
