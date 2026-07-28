from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from src.api.models.schemas import DocumentJobCreate
from src.api.services.document_jobs import (
    claim_next_document_job,
    create_document_job,
    execute_document_job,
)
from src.api.services.document_engine import (
    DocumentEnginePrerequisiteError,
    EngineEvent,
    EngineExecutionResult,
    EngineManagedOutput,
    EngineReadiness,
)


@pytest.fixture(autouse=True)
def enable_document_workflows(monkeypatch, tmp_path, test_user):
    from src.api.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "documents_enabled", True)
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path / "artifacts"))
    monkeypatch.setattr(settings, "document_max_upload_mb", 10)
    test_user.roles = ["DEVELOPER"]
    yield


def _ready_readiness(tmp_path: Path) -> EngineReadiness:
    return EngineReadiness(
        enabled=True,
        python_ok=True,
        predict_rlm_available=True,
        deno_available=True,
        credentials_ok=True,
        ready=True,
        driver="predict_rlm",
        artifacts_dir=str(tmp_path / "artifacts"),
        missing_requirements=(),
        configured_model_providers=("openai",),
    )


@pytest.fixture
def stub_predict_rlm_document_engine(monkeypatch, tmp_path):
    def readiness() -> EngineReadiness:
        return _ready_readiness(tmp_path)

    def execute(manifest: dict[str, object]) -> EngineExecutionResult:
        output_dir = tmp_path / "predict-rlm-outputs" / str(manifest["template_id"])
        output_dir.mkdir(parents=True, exist_ok=True)
        template_id = str(manifest["template_id"])

        summary = {"template_id": template_id, "driver": "predict_rlm"}
        events = [
            EngineEvent(
                event_type="rlm_iteration",
                message="Executed predict-rlm document workflow.",
                payload={"driver": "predict_rlm", "template_id": template_id},
            ),
            EngineEvent(
                event_type="tool_call",
                message="predict-rlm invoked its recursive execution environment.",
                payload={"lm": "openai/gpt-5.4", "sub_lm": "openai/gpt-5.1"},
            ),
        ]

        if template_id == "invoice_extraction":
            workbook_path = output_dir / "invoice-extraction.xlsx"
            workbook_path.write_bytes(b"predict-rlm workbook")
            summary_path = output_dir / "invoice-extraction-summary.json"
            summary_path.write_text('{"driver":"predict_rlm"}', encoding="utf-8")
            artifacts = [
                EngineManagedOutput(
                    path=workbook_path,
                    role="workbook",
                    kind="xlsx",
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                EngineManagedOutput(
                    path=summary_path,
                    role="summary",
                    kind="json",
                    content_type="application/json",
                ),
            ]
        elif template_id == "document_redaction":
            redacted_path = output_dir / "redacted-input.txt"
            redacted_path.write_text("redacted", encoding="utf-8")
            report_path = output_dir / "verification.md"
            report_path.write_text("# Verification", encoding="utf-8")
            summary_path = output_dir / "document-redaction-summary.json"
            summary_path.write_text('{"driver":"predict_rlm"}', encoding="utf-8")
            artifacts = [
                EngineManagedOutput(
                    path=redacted_path,
                    role="redacted_document",
                    kind="file",
                    content_type="text/plain",
                ),
                EngineManagedOutput(
                    path=report_path,
                    role="verification_report",
                    kind="markdown",
                    content_type="text/markdown",
                ),
                EngineManagedOutput(
                    path=summary_path,
                    role="summary",
                    kind="json",
                    content_type="application/json",
                ),
            ]
        else:
            report_path = output_dir / f"{template_id}-report.md"
            report_path.write_text("# Report", encoding="utf-8")
            summary_path = output_dir / f"{template_id}-summary.json"
            summary_path.write_text('{"driver":"predict_rlm"}', encoding="utf-8")
            artifacts = [
                EngineManagedOutput(
                    path=report_path,
                    role="report",
                    kind="markdown",
                    content_type="text/markdown",
                ),
                EngineManagedOutput(
                    path=summary_path,
                    role="summary",
                    kind="json",
                    content_type="application/json",
                ),
            ]

        return EngineExecutionResult(
            driver="predict_rlm",
            status="completed",
            output_text=f"{template_id} completed with predict-rlm.",
            summary=summary,
            artifacts=artifacts,
            events=events,
        )

    monkeypatch.setattr("src.api.services.document_engine.get_document_engine_readiness", readiness)
    monkeypatch.setattr("src.api.services.document_jobs.execute_document_manifest", execute)
    yield


def _not_ready_readiness(tmp_path: Path) -> EngineReadiness:
    return EngineReadiness(
        enabled=True,
        python_ok=True,
        predict_rlm_available=False,
        deno_available=False,
        credentials_ok=False,
        ready=False,
        driver="unavailable",
        artifacts_dir=str(tmp_path / "artifacts"),
        missing_requirements=("deno", "predict_rlm"),
        configured_model_providers=("openai",),
    )


def _managed_submission_files(template_id: str, content: bytes = b"document body"):
    if template_id == "contract_comparison":
        return [
            ("base_document", ("base.txt", content, "text/plain")),
            ("comparison_document", ("comparison.txt", content, "text/plain")),
        ]
    return [("documents", (f"{template_id}.txt", content, "text/plain"))]


def _managed_submission_parameters(template_id: str) -> dict[str, str]:
    if template_id == "document_redaction":
        return {"redaction_policy": "Remove account numbers"}
    return {"instructions": "Process every supplied document"}


async def _submit_managed(
    client,
    *,
    template_id: str,
    idempotency_key: str,
    files=None,
    parameters: dict[str, str] | None = None,
):
    return await client.post(
        "/v1/documents/jobs/submit",
        data={
            "template_id": template_id,
            "parameters": json.dumps(
                _managed_submission_parameters(template_id) if parameters is None else parameters
            ),
        },
        files=_managed_submission_files(template_id) if files is None else files,
        headers={"Idempotency-Key": idempotency_key},
    )


@pytest.mark.asyncio
async def test_document_template_catalog_returns_expected_templates(client):
    response = await client.get("/v1/documents/templates")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [
        "document_analysis",
        "contract_comparison",
        "invoice_extraction",
        "document_redaction",
    ]


def test_document_engine_readiness_reports_missing_model_credentials(monkeypatch, tmp_path):
    from src.api.services import document_engine

    monkeypatch.setattr(document_engine.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(document_engine.shutil, "which", lambda name: "/usr/bin/deno")
    monkeypatch.setenv("MUTX_DOCUMENTS_LM", "openai/gpt-5.4")
    monkeypatch.setenv("MUTX_DOCUMENTS_SUB_LM", "openai/gpt-5.1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    readiness = document_engine.get_document_engine_readiness()

    assert readiness.enabled is True
    assert readiness.predict_rlm_available is True
    assert readiness.deno_available is True
    assert readiness.credentials_ok is False
    assert readiness.configured_model_providers == ("openai",)
    assert "OPENAI_API_KEY" in readiness.missing_requirements


@pytest.mark.asyncio
async def test_managed_create_without_validated_inputs_is_rejected_without_history(client):
    create_response = await client.post(
        "/v1/documents/jobs",
        json={
            "template_id": "document_analysis",
            "execution_mode": "managed",
            "parameters": {},
        },
    )
    assert create_response.status_code == 409
    assert "/documents/jobs/submit" in create_response.json()["detail"]
    history = await client.get("/v1/documents/jobs")
    assert history.json()["total"] == 0


@pytest.mark.asyncio
async def test_document_artifact_upload_and_download_are_user_scoped(
    client,
    other_user_client,
):
    create_response = await client.post(
        "/v1/documents/jobs",
        json={
            "template_id": "document_analysis",
            "execution_mode": "local",
            "parameters": {},
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["id"]

    upload_response = await client.post(
        f"/v1/documents/jobs/{job_id}/artifacts",
        files={"file": ("brief.txt", io.BytesIO(b"incident summary"), "text/plain")},
        data={"role": "documents", "kind": "file"},
    )
    assert upload_response.status_code == 201
    artifact = upload_response.json()

    download_response = await client.get(f"/v1/documents/jobs/{job_id}/artifacts/{artifact['id']}")
    assert download_response.status_code == 200
    assert download_response.content == b"incident summary"

    forbidden_response = await other_user_client.get(
        f"/v1/documents/jobs/{job_id}/artifacts/{artifact['id']}"
    )
    assert forbidden_response.status_code == 404


@pytest.mark.asyncio
async def test_document_artifact_registration_rejects_client_managed_backends(client):
    create_response = await client.post(
        "/v1/documents/jobs",
        json={
            "template_id": "document_analysis",
            "execution_mode": "local",
            "parameters": {},
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["id"]

    register_response = await client.post(
        f"/v1/documents/jobs/{job_id}/artifacts",
        json={
            "role": "documents",
            "kind": "file",
            "storage_backend": "managed",
            "filename": "server-secret.txt",
            "local_path": "/tmp/server-secret.txt",
            "metadata": {},
        },
    )

    assert register_response.status_code == 400
    assert "local_reference" in register_response.json()["detail"]


@pytest.mark.asyncio
async def test_managed_dispatch_rejects_local_reference_artifacts(
    client,
    db_session,
    test_user,
):
    job = await create_document_job(
        db_session,
        current_user=test_user,
        request=DocumentJobCreate(
            template_id="document_redaction",
            execution_mode="managed",
            parameters={"redaction_policy": "Remove secrets"},
        ),
    )
    job_id = job.id

    register_response = await client.post(
        f"/v1/documents/jobs/{job_id}/artifacts",
        json={
            "role": "documents",
            "kind": "file",
            "storage_backend": "local_reference",
            "filename": "input.txt",
            "local_path": "/tmp/input.txt",
            "metadata": {},
        },
    )
    assert register_response.status_code == 201

    dispatch_response = await client.post(
        f"/v1/documents/jobs/{job_id}/dispatch",
        json={"mode": "managed"},
    )

    assert dispatch_response.status_code == 400
    assert "managed storage" in dispatch_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_managed_dispatch_allows_split_deployments(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.api.services.document_engine.get_document_engine_readiness",
        lambda: _not_ready_readiness(tmp_path),
    )

    dispatch_response = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="split-deployment",
        files=[("documents", ("brief.txt", b"system nominal", "text/plain"))],
        parameters={"instructions": "Summarize the uploaded file"},
    )
    assert dispatch_response.status_code == 200
    assert dispatch_response.json()["status"] == "queued"


def test_execute_document_manifest_requires_predict_rlm(monkeypatch, tmp_path):
    from src.api.services.document_engine import execute_document_manifest

    monkeypatch.setattr(
        "src.api.services.document_engine.get_document_engine_readiness",
        lambda: _not_ready_readiness(tmp_path),
    )

    with pytest.raises(DocumentEnginePrerequisiteError, match="predict-rlm document execution"):
        execute_document_manifest({"template_id": "document_analysis"})


@pytest.mark.asyncio
async def test_managed_document_lifecycle_executes_through_worker(
    client, db_session, stub_predict_rlm_document_engine
):
    dispatch_response = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="worker-lifecycle",
        files=[("documents", ("brief.txt", b"system nominal", "text/plain"))],
        parameters={"instructions": "Summarize the uploaded file"},
    )
    assert dispatch_response.status_code == 200
    assert dispatch_response.json()["status"] == "queued"
    job = dispatch_response.json()

    claimed = await claim_next_document_job(db_session, worker_name="test-worker")
    assert claimed is not None
    executed = await execute_document_job(db_session, claimed_job=claimed)

    assert executed.status == "completed"
    assert executed.run.status == "completed"
    assert any(artifact.role == "report" for artifact in executed.artifacts)
    assert any(artifact.role == "summary" for artifact in executed.artifacts)

    run_response = await client.get(f"/v1/runs/{job['run_id']}")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["agent_id"] is None
    assert run_payload["subject_type"] == "document_job"
    assert run_payload["subject_id"] == job["id"]
    assert run_payload["template_id"] == "document_analysis"
    assert run_payload["execution_mode"] == "managed"
    assert any(trace["event_type"] == "job_completed" for trace in run_payload["traces"])


@pytest.mark.asyncio
async def test_local_launch_allows_split_deployments(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.api.services.document_engine.get_document_engine_readiness",
        lambda: _not_ready_readiness(tmp_path),
    )

    create_response = await client.post(
        "/v1/documents/jobs",
        json={
            "template_id": "document_redaction",
            "execution_mode": "local",
            "parameters": {"redaction_policy": "Remove SSNs"},
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    register_response = await client.post(
        f"/v1/documents/jobs/{job['id']}/artifacts",
        json={
            "role": "documents",
            "kind": "file",
            "storage_backend": "local_reference",
            "filename": "input.txt",
            "local_path": "/tmp/input.txt",
            "metadata": {},
        },
    )
    assert register_response.status_code == 201

    launch_response = await client.post(
        f"/v1/documents/jobs/{job['id']}/launch-local",
        json={"output_dir": "/tmp/mutx-local-docs"},
    )
    assert launch_response.status_code == 200
    payload = launch_response.json()
    assert payload["manifest"]["engine"]["ready"] is False
    assert payload["manifest"]["engine"]["missing_requirements"]


@pytest.mark.asyncio
async def test_local_document_lifecycle_supports_events_and_uploaded_outputs(
    client, stub_predict_rlm_document_engine
):
    create_response = await client.post(
        "/v1/documents/jobs",
        json={
            "template_id": "document_redaction",
            "execution_mode": "local",
            "parameters": {"redaction_policy": "Remove SSNs"},
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    register_response = await client.post(
        f"/v1/documents/jobs/{job['id']}/artifacts",
        json={
            "role": "documents",
            "kind": "file",
            "storage_backend": "local_reference",
            "filename": "input.txt",
            "local_path": "/tmp/input.txt",
            "metadata": {},
        },
    )
    assert register_response.status_code == 201

    launch_response = await client.post(
        f"/v1/documents/jobs/{job['id']}/launch-local",
        json={"output_dir": "/tmp/mutx-local-docs"},
    )
    assert launch_response.status_code == 200
    assert launch_response.json()["manifest"]["template_id"] == "document_redaction"

    running_response = await client.post(
        f"/v1/documents/jobs/{job['id']}/events",
        json={
            "event_type": "dispatch_started",
            "message": "Local execution started",
            "status": "running",
        },
    )
    assert running_response.status_code == 200
    assert running_response.json()["status"] == "running"

    upload_response = await client.post(
        f"/v1/documents/jobs/{job['id']}/artifacts",
        files={
            "file": (
                "verification.md",
                io.BytesIO(b"# Verification\n\nNo residual identifiers found."),
                "text/markdown",
            )
        },
        data={"role": "verification_report", "kind": "markdown"},
    )
    assert upload_response.status_code == 201

    complete_response = await client.post(
        f"/v1/documents/jobs/{job['id']}/events",
        json={
            "event_type": "job_completed",
            "message": "Local execution finished",
            "status": "completed",
            "output_text": "Local redaction complete",
            "result_summary": {"redacted_outputs": 1},
        },
    )
    assert complete_response.status_code == 200
    payload = complete_response.json()
    assert payload["status"] == "completed"
    assert payload["result_summary"] == {"redacted_outputs": 1}
    assert any(artifact["role"] == "verification_report" for artifact in payload["artifacts"])


@pytest.mark.asyncio
async def test_document_jobs_appear_in_runs_listing(client):
    create_response = await _submit_managed(
        client,
        template_id="invoice_extraction",
        idempotency_key="runs-listing",
    )
    assert create_response.status_code == 200
    job = create_response.json()

    runs_response = await client.get("/v1/runs")
    assert runs_response.status_code == 200
    runs = runs_response.json()["items"]
    document_run = next(item for item in runs if item["id"] == job["run_id"])
    assert document_run["agent_id"] is None
    assert document_run["subject_label"] == "Invoice Extraction"
    assert document_run["template_id"] == "invoice_extraction"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "template_id,expected_roles",
    [
        ("document_analysis", {"documents"}),
        ("contract_comparison", {"base_document", "comparison_document"}),
        ("invoice_extraction", {"documents"}),
        ("document_redaction", {"documents"}),
    ],
)
async def test_managed_submission_prevalidates_and_queues_every_template(
    client,
    template_id,
    expected_roles,
):
    response = await _submit_managed(
        client,
        template_id=template_id,
        idempotency_key=f"valid-{template_id}",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["dispatched_at"] is not None
    assert {artifact["role"] for artifact in payload["artifacts"]} == expected_roles


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "template_id,files,parameters,missing_name",
    [
        (
            "document_analysis",
            [("documents", ("empty.txt", b"", "text/plain"))],
            {},
            "documents",
        ),
        (
            "contract_comparison",
            [("base_document", ("base.txt", b"base", "text/plain"))],
            {},
            "comparison_document",
        ),
        ("invoice_extraction", [("marker", (None, ""))], {}, "documents"),
        (
            "document_redaction",
            [("documents", ("input.txt", b"secret", "text/plain"))],
            {},
            "redaction_policy",
        ),
    ],
)
async def test_missing_template_inputs_never_create_jobs(
    client,
    template_id,
    files,
    parameters,
    missing_name,
):
    response = await _submit_managed(
        client,
        template_id=template_id,
        idempotency_key=f"missing-{template_id}",
        files=files,
        parameters=parameters,
    )

    assert response.status_code == 400
    assert missing_name in response.json()["detail"]
    history = await client.get("/v1/documents/jobs")
    assert history.json()["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "template_id",
    [
        "document_analysis",
        "contract_comparison",
        "invoice_extraction",
        "document_redaction",
    ],
)
async def test_oversized_template_inputs_never_create_jobs(client, monkeypatch, template_id):
    from src.api.config import get_settings

    monkeypatch.setattr(get_settings(), "document_max_upload_mb", 1)
    oversized = b"x" * (1024 * 1024 + 1)
    files = _managed_submission_files(template_id, oversized)

    response = await _submit_managed(
        client,
        template_id=template_id,
        idempotency_key=f"oversized-{template_id}",
        files=files,
    )

    assert response.status_code == 413
    history = await client.get("/v1/documents/jobs")
    assert history.json()["total"] == 0


@pytest.mark.asyncio
async def test_partial_upload_failure_is_canonical_and_same_key_retry_is_idempotent(
    client,
    monkeypatch,
):
    from src.api.services import document_jobs

    original_store = document_jobs.store_prepared_artifact
    upload_attempts = 0

    async def fail_second_upload(*args, **kwargs):
        nonlocal upload_attempts
        upload_attempts += 1
        if upload_attempts == 2:
            raise OSError("simulated second upload failure")
        return await original_store(*args, **kwargs)

    monkeypatch.setattr(document_jobs, "store_prepared_artifact", fail_second_upload)
    files = [
        ("documents", ("one.txt", b"one", "text/plain")),
        ("documents", ("two.txt", b"two", "text/plain")),
    ]
    first = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="retry-upload-failure",
        files=files,
    )

    assert first.status_code == 500
    history = (await client.get("/v1/documents/jobs")).json()
    assert history["total"] == 1
    failed = history["items"][0]
    assert failed["status"] == "failed"
    assert len(failed["artifacts"]) == 1
    assert "upload" in failed["error_message"]

    monkeypatch.setattr(document_jobs, "store_prepared_artifact", original_store)
    retry = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="retry-upload-failure",
        files=files,
    )
    duplicate = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="retry-upload-failure",
        files=files,
    )

    assert retry.status_code == 200
    assert retry.json()["status"] == "queued"
    assert retry.json()["id"] == failed["id"]
    assert len(retry.json()["artifacts"]) == 2
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == failed["id"]
    canonical_history = (await client.get("/v1/documents/jobs")).json()
    assert canonical_history["total"] == 1


@pytest.mark.asyncio
async def test_submission_idempotency_key_rejects_changed_payload(client):
    first = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="same-key-different-payload",
    )
    changed = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="same-key-different-payload",
        parameters={"instructions": "Different instructions"},
    )

    assert first.status_code == 200
    assert changed.status_code == 409
    assert "different document submission" in changed.json()["detail"]


@pytest.mark.asyncio
async def test_dispatch_failure_preserves_staged_artifacts_and_failed_history(client, monkeypatch):
    from src.api.services import document_jobs

    original_dispatch = document_jobs.dispatch_document_job

    async def fail_dispatch(*args, **kwargs):
        raise RuntimeError("simulated dispatch failure")

    monkeypatch.setattr(document_jobs, "dispatch_document_job", fail_dispatch)
    response = await _submit_managed(
        client,
        template_id="invoice_extraction",
        idempotency_key="dispatch-failure",
    )

    assert response.status_code == 500
    failed = (await client.get("/v1/documents/jobs")).json()["items"][0]
    assert failed["status"] == "failed"
    assert len(failed["artifacts"]) == 1
    assert "dispatch" in failed["error_message"]
    run = (await client.get(f"/v1/runs/{failed['run_id']}")).json()
    assert any(trace["event_type"] == "submission_staged" for trace in run["traces"])
    assert not any(trace["event_type"] == "job_dispatched" for trace in run["traces"])

    monkeypatch.setattr(document_jobs, "dispatch_document_job", original_dispatch)


@pytest.mark.asyncio
async def test_dispatch_is_idempotent_and_records_one_canonical_dispatch(client):
    create = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="dispatch-idempotency",
    )
    job = create.json()

    first = await client.post(
        f"/v1/documents/jobs/{job['id']}/dispatch",
        json={"mode": "managed"},
    )
    second = await client.post(
        f"/v1/documents/jobs/{job['id']}/dispatch",
        json={"mode": "managed"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["dispatched_at"] == first.json()["dispatched_at"]
    run = (await client.get(f"/v1/runs/{job['run_id']}")).json()
    assert sum(trace["event_type"] == "job_dispatched" for trace in run["traces"]) == 1


@pytest.mark.asyncio
async def test_cleanup_failure_remains_failed_and_retry_cancels_canonical_job(
    client,
    monkeypatch,
):
    from src.api.services import document_jobs

    create = await client.post(
        "/v1/documents/jobs",
        json={
            "template_id": "document_analysis",
            "execution_mode": "local",
            "parameters": {},
        },
    )
    job = create.json()
    upload = await client.post(
        f"/v1/documents/jobs/{job['id']}/artifacts",
        files={"file": ("input.txt", io.BytesIO(b"input"), "text/plain")},
        data={"role": "documents", "kind": "file"},
    )
    artifact_path = Path(upload.json()["local_path"])
    await client.post(
        f"/v1/documents/jobs/{job['id']}/events",
        json={
            "event_type": "job_failed",
            "status": "failed",
            "error_message": "simulated workflow failure",
        },
    )

    original_remove = document_jobs._remove_managed_artifact_file

    def fail_cleanup(**kwargs):
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(document_jobs, "_remove_managed_artifact_file", fail_cleanup)
    failed_cleanup = await client.post(f"/v1/documents/jobs/{job['id']}/cleanup")

    assert failed_cleanup.status_code == 500
    canonical_failed = (await client.get(f"/v1/documents/jobs/{job['id']}")).json()
    assert canonical_failed["status"] == "failed"
    assert "cleanup" in canonical_failed["error_message"]
    assert len(canonical_failed["artifacts"]) == 1

    monkeypatch.setattr(document_jobs, "_remove_managed_artifact_file", original_remove)
    cleaned = await client.post(f"/v1/documents/jobs/{job['id']}/cleanup")
    cleaned_again = await client.post(f"/v1/documents/jobs/{job['id']}/cleanup")

    assert cleaned.status_code == 200
    assert cleaned.json()["status"] == "cancelled"
    assert cleaned.json()["artifacts"] == []
    assert cleaned_again.status_code == 200
    assert cleaned_again.json()["status"] == "cancelled"
    assert not artifact_path.exists()


@pytest.mark.asyncio
async def test_document_submission_auth_not_found_and_conflict_statuses(
    client,
    client_no_auth,
    other_user_client,
):
    unauthenticated = await client_no_auth.get("/v1/documents/templates")
    missing_template = await _submit_managed(
        client,
        template_id="missing_template",
        idempotency_key="missing-template",
        files=[("documents", ("input.txt", b"input", "text/plain"))],
        parameters={},
    )
    submitted = await _submit_managed(
        client,
        template_id="document_analysis",
        idempotency_key="cleanup-conflict",
    )
    job_id = submitted.json()["id"]
    forbidden_by_ownership = await other_user_client.post(f"/v1/documents/jobs/{job_id}/cleanup")
    active_cleanup = await client.post(f"/v1/documents/jobs/{job_id}/cleanup")

    assert unauthenticated.status_code == 401
    assert missing_template.status_code == 404
    assert forbidden_by_ownership.status_code == 403
    assert active_cleanup.status_code == 409


@pytest.mark.asyncio
async def test_document_submission_preserves_explicit_forbidden_status(client):
    from src.api.auth.dependencies import get_current_user

    original_dependency = client.app.dependency_overrides[get_current_user]

    async def forbid_documents():
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Document workflow access denied")

    client.app.dependency_overrides[get_current_user] = forbid_documents
    try:
        response = await client.get("/v1/documents/templates")
    finally:
        client.app.dependency_overrides[get_current_user] = original_dependency

    assert response.status_code == 403
    assert response.json()["detail"] == "Document workflow access denied"
