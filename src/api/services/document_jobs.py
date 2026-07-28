from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
import socket
from pathlib import Path
from typing import Any
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.datastructures import UploadFile

from src.api.metrics import (
    mutx_document_artifact_ops_total,
    mutx_document_execution_duration_seconds,
    mutx_document_jobs_total,
    mutx_document_queue_depth,
)
from src.api.models import AgentRun, AgentRunTrace, DocumentArtifact, DocumentJob, User
from src.api.models.schemas import (
    DocumentArtifactRegistrationCreate,
    DocumentArtifactResponse,
    DocumentJobCreate,
    DocumentJobDispatchRequest,
    DocumentJobEventCreate,
    DocumentJobLocalLaunchResponse,
    DocumentJobResponse,
)
from src.api.services.analytics import AnalyticsEventType, log_analytics_event
from src.api.services.document_engine import (
    DOCUMENT_TRACE_EVENT_TYPES,
    DocumentEngineError,
    EngineExecutionResult,
    build_document_manifest,
    execute_document_manifest,
    get_document_engine_readiness,
)
from src.api.services.document_storage import (
    MANAGED_STORAGE_BACKENDS,
    StoredArtifactResult,
    assert_upload_size_within_limit,
    get_artifacts_root,
    register_artifact_reference,
    resolve_artifact_path,
    store_prepared_artifact,
    store_uploaded_artifact,
    sync_managed_output_artifact,
)
from src.api.services.document_templates import get_document_template
from src.api.services.usage import track_usage_best_effort

logger = logging.getLogger(__name__)

DOCUMENT_PENDING_STATUSES = {"queued", "dispatching"}
DOCUMENT_ACTIVE_STATUSES = {"running"}
DOCUMENT_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
DOCUMENT_IDEMPOTENT_DISPATCH_STATUSES = {"queued", "running", "completed"}


@dataclass(frozen=True)
class ClaimedDocumentJob:
    job: DocumentJob
    claim_token: str
    worker_name: str


@dataclass(frozen=True)
class PreparedDocumentUpload:
    role: str
    kind: str
    filename: str
    content_type: str | None
    content: bytes
    sha256: str


class DocumentSubmissionError(RuntimeError):
    def __init__(self, *, job_id: uuid.UUID, phase: str, message: str):
        super().__init__(message)
        self.job_id = job_id
        self.phase = phase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _decode_run_metadata(value: str | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _encode_run_metadata(value: dict[str, Any]) -> str:
    return json.dumps(value)


def ensure_documents_enabled() -> None:
    readiness = get_document_engine_readiness()
    if not readiness.enabled:
        raise HTTPException(status_code=404, detail="Document workflows are disabled")


def _subject_metadata(job_id: uuid.UUID, template_id: str, execution_mode: str) -> dict[str, Any]:
    template = get_document_template(template_id)
    subject_label = template.name if template is not None else template_id
    return {
        "subject_type": "document_job",
        "subject_id": str(job_id),
        "subject_label": subject_label,
        "template_id": template_id,
        "execution_mode": execution_mode,
    }


def _serialize_artifact(artifact: DocumentArtifact) -> DocumentArtifactResponse:
    return DocumentArtifactResponse(
        id=artifact.id,
        job_id=artifact.job_id,
        role=artifact.role,
        kind=artifact.kind,
        storage_backend=artifact.storage_backend,
        storage_uri=artifact.storage_uri,
        local_path=artifact.local_path,
        filename=artifact.filename,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        metadata=artifact.extra_metadata or {},
        created_at=_as_utc(artifact.created_at),
        updated_at=_as_utc(artifact.updated_at),
    )


def serialize_document_job(job: DocumentJob) -> DocumentJobResponse:
    loaded_artifacts = job.__dict__.get("artifacts") or []
    return DocumentJobResponse(
        id=job.id,
        run_id=job.run_id,
        template_id=job.template_id,
        execution_mode=job.execution_mode,
        status=job.status,
        parameters=job.parameters or {},
        result_summary=job.result_summary or {},
        error_message=job.error_message,
        claimed_by=job.claimed_by,
        claimed_at=_as_utc(job.claimed_at),
        last_heartbeat_at=_as_utc(job.last_heartbeat_at),
        attempts=job.attempts,
        dispatched_at=_as_utc(job.dispatched_at),
        completed_at=_as_utc(job.completed_at),
        created_at=_as_utc(job.created_at),
        updated_at=_as_utc(job.updated_at),
        artifacts=[_serialize_artifact(item) for item in loaded_artifacts],
    )


def _record_trace(
    db: AsyncSession,
    *,
    run: AgentRun,
    event_type: str,
    message: str | None,
    payload: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> AgentRunTrace:
    if event_type not in DOCUMENT_TRACE_EVENT_TYPES and event_type not in {
        "step",
        "tool_call",
        "prompt",
        "done",
    }:
        logger.debug("Recording non-standard trace event type %s for run %s", event_type, run.id)

    loaded_traces = run.__dict__.get("traces")
    if loaded_traces is None:
        sequence = 0
    else:
        sequence = len(loaded_traces)
    trace = AgentRunTrace(
        run=run,
        event_type=event_type,
        message=message,
        payload=json.dumps(payload or {}),
        sequence=sequence,
        timestamp=timestamp or _utcnow(),
    )
    db.add(trace)
    return trace


def _update_run_metadata(run: AgentRun, job: DocumentJob) -> None:
    metadata = _decode_run_metadata(run.run_metadata)
    metadata.update(_subject_metadata(job.id, job.template_id, job.execution_mode))
    run.run_metadata = _encode_run_metadata(metadata)


async def _rollback_preserving_user(db: AsyncSession, current_user: User) -> None:
    """Rollback workflow mutations without leaving the request principal expired."""
    await db.rollback()
    await db.refresh(current_user)


async def _get_document_job_query(
    db: AsyncSession, *, job_id: uuid.UUID, user_id: uuid.UUID
) -> DocumentJob | None:
    result = await db.execute(
        select(DocumentJob)
        .options(
            selectinload(DocumentJob.artifacts),
            selectinload(DocumentJob.run).selectinload(AgentRun.traces),
        )
        .execution_options(populate_existing=True)
        .where(DocumentJob.id == job_id, DocumentJob.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_document_job_or_404(
    db: AsyncSession, *, job_id: uuid.UUID, current_user: User
) -> DocumentJob:
    job = await _get_document_job_query(db, job_id=job_id, user_id=current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Document job not found")
    return job


async def get_document_artifact_or_404(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
    current_user: User,
) -> DocumentArtifact:
    job = await get_document_job_or_404(db, job_id=job_id, current_user=current_user)
    for artifact in job.artifacts:
        if artifact.id == artifact_id:
            return artifact
    raise HTTPException(status_code=404, detail="Document artifact not found")


def _validate_execution_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in {"managed", "local"}:
        raise HTTPException(status_code=400, detail="execution_mode must be managed or local")
    return mode


def _get_template_or_404(template_id: str):
    template = get_document_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Document template not found")
    return template


def validate_template_inputs(
    *,
    template_id: str,
    parameters: dict[str, Any],
    artifact_roles: list[str],
    reject_unknown_artifact_roles: bool = False,
) -> None:
    template = _get_template_or_404(template_id)
    artifact_fields = {field.name: field for field in template.inputs if field.type == "artifact"}
    role_counts = {role: artifact_roles.count(role) for role in set(artifact_roles)}

    if reject_unknown_artifact_roles:
        unknown_roles = sorted(set(artifact_roles) - set(artifact_fields))
        if unknown_roles:
            raise HTTPException(
                status_code=400,
                detail=f"Unexpected artifact roles for template {template_id}: {', '.join(unknown_roles)}",
            )

    missing: list[str] = []
    for field in template.inputs:
        if not field.required:
            continue
        if field.type == "artifact":
            if role_counts.get(field.name, 0) == 0:
                missing.append(field.name)
            continue
        if not str(parameters.get(field.name) or "").strip():
            missing.append(field.name)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required inputs for template {template_id}: {', '.join(sorted(missing))}",
        )

    duplicate_single_inputs = sorted(
        name
        for name, field in artifact_fields.items()
        if not field.accepts_multiple and role_counts.get(name, 0) > 1
    )
    if duplicate_single_inputs:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Template {template_id} accepts one file for: {', '.join(duplicate_single_inputs)}"
            ),
        )


def validate_job_inputs(job: DocumentJob, artifacts: list[DocumentArtifact]) -> None:
    validate_template_inputs(
        template_id=job.template_id,
        parameters=job.parameters or {},
        artifact_roles=[artifact.role for artifact in artifacts],
    )


async def prepare_document_submission(
    *,
    template_id: str,
    parameters: dict[str, Any],
    uploads: list[tuple[str, UploadFile]],
) -> tuple[list[PreparedDocumentUpload], str]:
    """Read and validate every managed input before a canonical job is created."""
    template = _get_template_or_404(template_id)
    if not template.supports_managed:
        raise HTTPException(status_code=400, detail="Template does not support managed execution")

    prepared: list[PreparedDocumentUpload] = []
    for role, upload in uploads:
        normalized_role = role.strip()
        if upload.size is not None:
            assert_upload_size_within_limit(upload.size)
        content = await upload.read()
        assert_upload_size_within_limit(len(content))
        if not content:
            raise HTTPException(
                status_code=400,
                detail=f"Managed document input {normalized_role or 'file'} must not be empty",
            )
        prepared.append(
            PreparedDocumentUpload(
                role=normalized_role,
                kind="file",
                filename=Path(upload.filename or f"{normalized_role}.bin").name,
                content_type=upload.content_type,
                content=content,
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )

    validate_template_inputs(
        template_id=template_id,
        parameters=parameters,
        artifact_roles=[item.role for item in prepared],
        reject_unknown_artifact_roles=True,
    )

    fingerprint_payload = {
        "template_id": template_id,
        "execution_mode": "managed",
        "parameters": parameters,
        "files": sorted(
            (
                {
                    "role": item.role,
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "size_bytes": len(item.content),
                    "sha256": item.sha256,
                }
                for item in prepared
            ),
            key=lambda item: (item["role"], item["filename"], item["sha256"]),
        ),
    }
    encoded = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return prepared, hashlib.sha256(encoded).hexdigest()


def validate_artifact_registration_request(request: DocumentArtifactRegistrationCreate) -> None:
    if request.storage_backend != "local_reference":
        raise HTTPException(
            status_code=400,
            detail=(
                "Client artifact registration only supports local_reference storage_backend. "
                "Use multipart upload for managed files."
            ),
        )

    if not str(request.local_path or "").strip():
        raise HTTPException(
            status_code=400,
            detail="local_reference artifact registration requires local_path.",
        )

    if request.storage_uri:
        raise HTTPException(
            status_code=400,
            detail="local_reference artifact registration cannot set storage_uri.",
        )


def validate_dispatch_mode_artifacts(*, mode: str, artifacts: list[DocumentArtifact]) -> None:
    if mode != "managed":
        return

    invalid = [
        artifact.filename
        for artifact in artifacts
        if artifact.storage_backend not in MANAGED_STORAGE_BACKENDS
    ]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=(
                "Managed execution requires artifacts in managed storage. "
                "Re-upload files with multipart or launch locally."
            ),
        )


async def create_document_job(
    db: AsyncSession,
    *,
    current_user: User,
    request: DocumentJobCreate,
    job_id: uuid.UUID | None = None,
    initial_status: str = "created",
    extra_run_metadata: dict[str, Any] | None = None,
) -> DocumentJob:
    ensure_documents_enabled()
    template = get_document_template(request.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Document template not found")

    execution_mode = _validate_execution_mode(request.execution_mode)
    resolved_job_id = job_id or uuid.uuid4()
    run_metadata = _subject_metadata(
        resolved_job_id,
        request.template_id,
        execution_mode,
    )
    run_metadata.update(extra_run_metadata or {})
    run = AgentRun(
        agent_id=None,
        user_id=current_user.id,
        status=initial_status,
        input_text=None,
        output_text=None,
        error_message=None,
        run_metadata=_encode_run_metadata(run_metadata),
        started_at=_utcnow(),
        completed_at=None,
    )
    db.add(run)
    await db.flush()

    job = DocumentJob(
        id=resolved_job_id,
        user_id=current_user.id,
        run_id=run.id,
        template_id=request.template_id,
        execution_mode=execution_mode,
        status=initial_status,
        parameters=request.parameters or {},
        result_summary={},
    )
    db.add(job)
    await db.flush()
    _record_trace(
        db,
        run=run,
        event_type="job_created",
        message=f"Created document job for template {request.template_id}",
        payload={
            "job_id": str(job.id),
            "template_id": request.template_id,
            "execution_mode": execution_mode,
        },
    )
    await db.commit()

    mutx_document_jobs_total.labels(template_id=request.template_id, status="created").inc()
    await log_analytics_event(
        db,
        event_name="Document job created",
        event_type=AnalyticsEventType.AGENT_RUN_STARTED,
        user_id=current_user.id,
        properties={
            "job_id": str(job.id),
            "run_id": str(run.id),
            "template_id": request.template_id,
        },
    )
    await track_usage_best_effort(
        db=db,
        user_id=current_user.id,
        event_type="document_job_created",
        resource_type="document_job",
        resource_id=str(job.id),
        metadata={"template_id": request.template_id, "execution_mode": execution_mode},
    )
    refreshed = await _get_document_job_query(db, job_id=job.id, user_id=current_user.id)
    assert refreshed is not None
    return refreshed


async def list_document_jobs(
    db: AsyncSession,
    *,
    current_user: User,
    skip: int,
    limit: int,
    status_filter: str | None,
    template_id: str | None,
) -> tuple[list[DocumentJob], int]:
    ensure_documents_enabled()

    filters = [DocumentJob.user_id == current_user.id]
    if status_filter:
        filters.append(DocumentJob.status == status_filter)
    if template_id:
        filters.append(DocumentJob.template_id == template_id)

    total_stmt = select(func.count()).select_from(DocumentJob).where(*filters)
    total = (await db.execute(total_stmt)).scalar_one()

    query = (
        select(DocumentJob)
        .options(selectinload(DocumentJob.artifacts), selectinload(DocumentJob.run))
        .where(*filters)
        .order_by(DocumentJob.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = (await db.execute(query)).scalars().all()
    return items, total


async def register_document_artifact(
    db: AsyncSession,
    *,
    job: DocumentJob,
    request: DocumentArtifactRegistrationCreate,
) -> DocumentArtifact:
    ensure_job_accepts_artifacts(job)
    validate_artifact_registration_request(request)
    artifact = await register_artifact_reference(
        db,
        job=job,
        role=request.role,
        kind=request.kind,
        filename=request.filename,
        storage_backend=request.storage_backend,
        local_path=request.local_path,
        storage_uri=request.storage_uri,
        content_type=request.content_type,
        size_bytes=request.size_bytes,
        sha256=request.sha256,
        metadata=request.metadata,
    )
    _record_trace(
        db,
        run=job.run,
        event_type="artifact_registered",
        message=f"Registered {request.role} artifact {request.filename}",
        payload={
            "artifact_id": str(artifact.id),
            "role": artifact.role,
            "storage_backend": artifact.storage_backend,
        },
    )
    mutx_document_artifact_ops_total.labels(
        operation="register", storage_backend=artifact.storage_backend
    ).inc()
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts"])
    return artifact


async def store_document_upload(
    db: AsyncSession,
    *,
    job: DocumentJob,
    upload,
    role: str,
    kind: str,
    metadata: dict[str, Any] | None = None,
) -> StoredArtifactResult:
    ensure_job_accepts_artifacts(job)
    result = await store_uploaded_artifact(
        db,
        job=job,
        upload=upload,
        role=role,
        kind=kind,
        metadata=metadata,
    )
    _record_trace(
        db,
        run=job.run,
        event_type="artifact_uploaded",
        message=f"Uploaded {role} artifact {result.artifact.filename}",
        payload={
            "artifact_id": str(result.artifact.id),
            "role": result.artifact.role,
            "storage_backend": result.artifact.storage_backend,
            "size_bytes": result.artifact.size_bytes,
        },
    )
    mutx_document_artifact_ops_total.labels(operation="upload", storage_backend="managed").inc()
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts"])
    return result


def ensure_job_accepts_artifacts(job: DocumentJob) -> None:
    if job.status in {"queued", "completed", "cancelled"} or (
        job.status == "running" and job.execution_mode == "managed"
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Document job in {job.status} state does not accept artifact changes",
        )


async def store_prepared_document_upload(
    db: AsyncSession,
    *,
    job: DocumentJob,
    upload: PreparedDocumentUpload,
) -> StoredArtifactResult:
    ensure_job_accepts_artifacts(job)
    result = await store_prepared_artifact(
        db,
        job=job,
        content=upload.content,
        role=upload.role,
        kind=upload.kind,
        filename=upload.filename,
        content_type=upload.content_type,
    )
    _record_trace(
        db,
        run=job.run,
        event_type="artifact_uploaded",
        message=f"Uploaded {upload.role} artifact {result.artifact.filename}",
        payload={
            "artifact_id": str(result.artifact.id),
            "role": result.artifact.role,
            "storage_backend": result.artifact.storage_backend,
            "size_bytes": result.artifact.size_bytes,
        },
    )
    mutx_document_artifact_ops_total.labels(operation="upload", storage_backend="managed").inc()
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts"])
    return result


async def dispatch_document_job(
    db: AsyncSession,
    *,
    job: DocumentJob,
    request: DocumentJobDispatchRequest,
) -> DocumentJob:
    ensure_documents_enabled()
    mode = _validate_execution_mode(request.mode or job.execution_mode)
    if job.status in DOCUMENT_IDEMPOTENT_DISPATCH_STATUSES:
        if job.execution_mode != mode:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Document job was already dispatched in {job.execution_mode} mode; "
                    f"cannot redispatch in {mode} mode"
                ),
            )
        return job
    if job.status != "created":
        raise HTTPException(
            status_code=409,
            detail=f"Document job in {job.status} state cannot be dispatched",
        )
    if mode != job.execution_mode:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Document job was created for {job.execution_mode} execution and cannot be "
                f"dispatched in {mode} mode"
            ),
        )

    validate_dispatch_mode_artifacts(mode=mode, artifacts=job.artifacts)
    validate_job_inputs(job, job.artifacts)
    dispatched_at = _utcnow()
    result = await db.execute(
        update(DocumentJob)
        .where(DocumentJob.id == job.id, DocumentJob.status == "created")
        .values(
            execution_mode=mode,
            status="queued",
            dispatched_at=dispatched_at,
            error_message=None,
            completed_at=None,
        )
    )
    if result.rowcount != 1:
        await db.commit()
        refreshed = await _get_document_job_query(db, job_id=job.id, user_id=job.user_id)
        if refreshed is not None and refreshed.status in DOCUMENT_IDEMPOTENT_DISPATCH_STATUSES:
            if refreshed.execution_mode == mode:
                return refreshed
        raise HTTPException(status_code=409, detail="Document job dispatch is already in progress")

    job.execution_mode = mode
    job.status = "queued"
    job.dispatched_at = dispatched_at
    job.error_message = None
    job.completed_at = None
    _update_run_metadata(job.run, job)
    job.run.status = "queued"
    job.run.error_message = None
    job.run.completed_at = None
    _record_trace(
        db,
        run=job.run,
        event_type="job_dispatched",
        message="Document job accepted for managed execution",
        payload={"job_id": str(job.id), "execution_mode": job.execution_mode},
    )
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts", "run"])
    mutx_document_jobs_total.labels(template_id=job.template_id, status="queued").inc()
    return job


def document_submission_job_id(*, user_id: uuid.UUID, idempotency_key: str) -> uuid.UUID:
    return uuid.uuid5(user_id, f"mutx.document.submission:{idempotency_key}")


def _submission_metadata(job: DocumentJob) -> dict[str, Any]:
    metadata = _decode_run_metadata(job.run.run_metadata)
    submission = metadata.get("document_submission")
    return submission if isinstance(submission, dict) else {}


def _remove_managed_artifact_file(*, job: DocumentJob, artifact: DocumentArtifact) -> None:
    if artifact.storage_backend not in MANAGED_STORAGE_BACKENDS or not artifact.local_path:
        return

    path = Path(artifact.local_path).resolve()
    expected_directory = (get_artifacts_root() / str(job.id)).resolve()
    if path.parent != expected_directory:
        raise RuntimeError(f"Refusing to clean artifact outside job directory: {artifact.filename}")
    path.unlink(missing_ok=True)


async def _purge_document_artifacts(db: AsyncSession, *, job: DocumentJob) -> list[str]:
    errors: list[str] = []
    removed: list[DocumentArtifact] = []
    for artifact in list(job.artifacts):
        try:
            _remove_managed_artifact_file(job=job, artifact=artifact)
            removed.append(artifact)
        except OSError as exc:
            errors.append(f"{artifact.filename}: {exc}")
        except RuntimeError as exc:
            errors.append(str(exc))

    for artifact in removed:
        await db.delete(artifact)
    return errors


async def _mark_document_submission_failed(
    db: AsyncSession,
    *,
    job: DocumentJob,
    phase: str,
    error: Exception | str,
) -> DocumentJob:
    now = _utcnow()
    message = f"Managed document submission failed during {phase}: {error}"
    job.status = "failed"
    job.error_message = message
    job.completed_at = now
    job.run.status = "failed"
    job.run.error_message = message
    job.run.completed_at = now
    _record_trace(
        db,
        run=job.run,
        event_type="submission_failed",
        message=message,
        payload={"phase": phase, "error": str(error), "recoverable": True},
    )
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts", "run"])
    mutx_document_jobs_total.labels(template_id=job.template_id, status="failed").inc()
    return job


async def cleanup_document_job(
    db: AsyncSession,
    *,
    job: DocumentJob,
) -> DocumentJob:
    ensure_documents_enabled()
    if job.status == "cancelled":
        return job
    if job.status not in {"created", "uploading", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Document job in {job.status} state cannot be cleaned up",
        )

    errors = await _purge_document_artifacts(db, job=job)
    if errors:
        failed = await _mark_document_submission_failed(
            db,
            job=job,
            phase="cleanup",
            error="; ".join(errors),
        )
        raise HTTPException(
            status_code=500,
            detail=(
                f"Cleanup failed for document job {failed.id}; canonical state remains failed: "
                f"{'; '.join(errors)}"
            ),
        )

    now = _utcnow()
    job.status = "cancelled"
    job.error_message = "Cancelled and cleaned up by operator"
    job.completed_at = now
    job.run.status = "cancelled"
    job.run.error_message = job.error_message
    job.run.completed_at = now
    _record_trace(
        db,
        run=job.run,
        event_type="job_cancelled",
        message=job.error_message,
        payload={"cleanup_completed": True},
    )
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts", "run"])
    return job


async def _reset_document_submission_for_retry(
    db: AsyncSession,
    *,
    job: DocumentJob,
) -> DocumentJob:
    previous_status = job.status
    claim = await db.execute(
        update(DocumentJob)
        .where(DocumentJob.id == job.id, DocumentJob.status == previous_status)
        .values(status="uploading")
    )
    if claim.rowcount != 1:
        await db.commit()
        raise HTTPException(
            status_code=409, detail="Document submission retry is already in progress"
        )
    job.run.status = "uploading"
    job.run.error_message = None
    job.run.completed_at = None
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts", "run"])

    errors = await _purge_document_artifacts(db, job=job)
    if errors:
        failed = await _mark_document_submission_failed(
            db,
            job=job,
            phase="retry cleanup",
            error="; ".join(errors),
        )
        raise DocumentSubmissionError(
            job_id=failed.id,
            phase="retry cleanup",
            message=failed.error_message or "Retry cleanup failed",
        )

    job.error_message = None
    job.completed_at = None
    job.dispatched_at = None
    job.claimed_by = None
    job.claim_token = None
    job.claimed_at = None
    job.last_heartbeat_at = None
    job.run.status = "uploading"
    job.run.error_message = None
    job.run.completed_at = None
    _record_trace(
        db,
        run=job.run,
        event_type="submission_retry",
        message="Retrying managed document submission",
        payload={"artifacts_cleaned": True},
    )
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts", "run"])
    return job


async def submit_managed_document_job(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
    parameters: dict[str, Any],
    idempotency_key: str,
    fingerprint: str,
    uploads: list[PreparedDocumentUpload],
) -> DocumentJob:
    current_user_id = current_user.id
    job_id = document_submission_job_id(
        user_id=current_user_id,
        idempotency_key=idempotency_key,
    )
    job = await _get_document_job_query(db, job_id=job_id, user_id=current_user_id)
    owns_submission = False

    if job is None:
        try:
            job = await create_document_job(
                db,
                current_user=current_user,
                request=DocumentJobCreate(
                    template_id=template_id,
                    execution_mode="managed",
                    parameters=parameters,
                ),
                job_id=job_id,
                initial_status="uploading",
                extra_run_metadata={
                    "document_submission": {
                        "idempotency_key": idempotency_key,
                        "fingerprint": fingerprint,
                    }
                },
            )
            owns_submission = True
        except IntegrityError:
            await _rollback_preserving_user(db, current_user)
            job = await _get_document_job_query(db, job_id=job_id, user_id=current_user_id)
            if job is None:
                raise
        except Exception as exc:
            await _rollback_preserving_user(db, current_user)
            job = await _get_document_job_query(db, job_id=job_id, user_id=current_user_id)
            if job is None:
                raise
            failed = await _mark_document_submission_failed(
                db,
                job=job,
                phase="creation",
                error=exc,
            )
            raise DocumentSubmissionError(
                job_id=failed.id,
                phase="creation",
                message=failed.error_message or str(exc),
            ) from exc

    submission_metadata = _submission_metadata(job)
    if submission_metadata.get("fingerprint") != fingerprint:
        raise HTTPException(
            status_code=409,
            detail="Idempotency key was already used for a different document submission",
        )

    if job.status in DOCUMENT_IDEMPOTENT_DISPATCH_STATUSES:
        return job
    if job.status in {"failed", "cancelled"}:
        job = await _reset_document_submission_for_retry(db, job=job)
        owns_submission = True
    elif job.status != "uploading":
        raise HTTPException(
            status_code=409,
            detail=f"Document submission is already in {job.status} state",
        )
    elif not owns_submission:
        raise HTTPException(status_code=409, detail="Document submission is already in progress")

    try:
        canonical_job_id = job.id
        for upload in uploads:
            await store_prepared_document_upload(db, job=job, upload=upload)
    except Exception as exc:
        await _rollback_preserving_user(db, current_user)
        refreshed = await _get_document_job_query(
            db,
            job_id=canonical_job_id,
            user_id=current_user_id,
        )
        if refreshed is None:
            raise
        failed = await _mark_document_submission_failed(
            db,
            job=refreshed,
            phase="upload",
            error=exc,
        )
        raise DocumentSubmissionError(
            job_id=failed.id,
            phase="upload",
            message=failed.error_message or str(exc),
        ) from exc

    job.status = "created"
    job.run.status = "created"
    _record_trace(
        db,
        run=job.run,
        event_type="submission_staged",
        message="All managed document inputs were uploaded",
        payload={"artifact_count": len(job.artifacts)},
    )
    await db.commit()

    canonical_job_id = job.id
    try:
        return await dispatch_document_job(
            db,
            job=job,
            request=DocumentJobDispatchRequest(mode="managed"),
        )
    except Exception as exc:
        await _rollback_preserving_user(db, current_user)
        refreshed = await _get_document_job_query(
            db,
            job_id=canonical_job_id,
            user_id=current_user_id,
        )
        if refreshed is not None and refreshed.status in DOCUMENT_IDEMPOTENT_DISPATCH_STATUSES:
            return refreshed
        if refreshed is None:
            raise
        failed = await _mark_document_submission_failed(
            db,
            job=refreshed,
            phase="dispatch",
            error=exc,
        )
        raise DocumentSubmissionError(
            job_id=failed.id,
            phase="dispatch",
            message=failed.error_message or str(exc),
        ) from exc


async def build_local_launch_response(
    db: AsyncSession,
    *,
    job: DocumentJob,
    output_dir: str | None,
) -> DocumentJobLocalLaunchResponse:
    ensure_documents_enabled()
    if job.status != "created" or job.execution_mode != "local":
        raise HTTPException(
            status_code=409,
            detail="Only created local document jobs can be launched locally",
        )
    _update_run_metadata(job.run, job)
    validate_job_inputs(job, job.artifacts)
    manifest = build_document_manifest(job, job.artifacts, output_dir=output_dir)
    await db.commit()
    return DocumentJobLocalLaunchResponse(
        job_id=job.id,
        template_id=job.template_id,
        execution_mode=job.execution_mode,
        manifest=manifest,
        artifacts=[_serialize_artifact(item) for item in job.artifacts],
    )


async def append_document_job_event(
    db: AsyncSession,
    *,
    job: DocumentJob,
    event: DocumentJobEventCreate,
) -> DocumentJob:
    if (
        job.status in DOCUMENT_TERMINAL_STATUSES
        and event.status is not None
        and event.status != job.status
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Document job in terminal {job.status} state cannot transition to {event.status}",
        )
    timestamp = event.timestamp or _utcnow()
    _record_trace(
        db,
        run=job.run,
        event_type=event.event_type,
        message=event.message,
        payload=event.payload,
        timestamp=timestamp,
    )
    job.last_heartbeat_at = timestamp

    if event.status:
        job.status = event.status
        job.run.status = event.status

    if event.output_text is not None:
        job.run.output_text = event.output_text

    if event.error_message is not None:
        job.error_message = event.error_message
        job.run.error_message = event.error_message

    if event.result_summary is not None:
        job.result_summary = event.result_summary

    if event.status in DOCUMENT_TERMINAL_STATUSES:
        job.completed_at = timestamp
        job.run.completed_at = timestamp

    if event.event_type == "job_failed":
        mutx_document_jobs_total.labels(template_id=job.template_id, status="failed").inc()
    elif event.event_type == "job_completed":
        mutx_document_jobs_total.labels(template_id=job.template_id, status="completed").inc()

    await db.commit()
    return job


async def claim_next_document_job(
    db: AsyncSession,
    *,
    worker_name: str | None = None,
    stale_after_seconds: int = 300,
) -> ClaimedDocumentJob | None:
    ensure_documents_enabled()
    worker_identity = worker_name or f"{socket.gethostname()}:{os.getpid()}"
    now = _utcnow()
    stale_cutoff = now - timedelta(seconds=stale_after_seconds)

    result = await db.execute(
        select(DocumentJob)
        .options(
            selectinload(DocumentJob.artifacts),
            selectinload(DocumentJob.run).selectinload(AgentRun.traces),
        )
        .where(
            DocumentJob.status.in_(["queued", "running"]),
        )
        .order_by(DocumentJob.dispatched_at.asc().nullsfirst(), DocumentJob.created_at.asc())
    )
    candidates = result.scalars().all()
    for job in candidates:
        if (
            job.status == "running"
            and job.last_heartbeat_at
            and job.last_heartbeat_at > stale_cutoff
        ):
            continue

        claim_token = uuid.uuid4().hex
        job.status = "running"
        job.claimed_by = worker_identity
        job.claim_token = claim_token
        job.claimed_at = now
        job.last_heartbeat_at = now
        job.attempts = (job.attempts or 0) + 1
        job.run.status = "running"
        _record_trace(
            db,
            run=job.run,
            event_type="dispatch_started",
            message=f"Claimed by worker {worker_identity}",
            payload={"worker": worker_identity, "attempt": job.attempts},
        )
        await db.commit()
        return ClaimedDocumentJob(job=job, claim_token=claim_token, worker_name=worker_identity)
    return None


async def heartbeat_document_job(
    db: AsyncSession,
    *,
    job: DocumentJob,
    claim_token: str,
) -> None:
    if job.claim_token != claim_token:
        raise DocumentEngineError("Claim token mismatch")
    job.last_heartbeat_at = _utcnow()
    await db.commit()


async def _persist_execution_artifacts(
    db: AsyncSession,
    *,
    job: DocumentJob,
    execution_result: EngineExecutionResult,
) -> None:
    for item in execution_result.artifacts:
        stored = await sync_managed_output_artifact(
            db,
            job=job,
            source_path=item.path,
            role=item.role,
            kind=item.kind,
            content_type=item.content_type,
            metadata=item.metadata,
            filename=item.filename,
        )
        _record_trace(
            db,
            run=job.run,
            event_type="artifact_synced",
            message=f"Synced output artifact {stored.artifact.filename}",
            payload={
                "artifact_id": str(stored.artifact.id),
                "role": stored.artifact.role,
                "kind": stored.artifact.kind,
            },
        )
        mutx_document_artifact_ops_total.labels(operation="sync", storage_backend="managed").inc()


async def finalize_document_job_execution(
    db: AsyncSession,
    *,
    job: DocumentJob,
    execution_result: EngineExecutionResult,
    started_at: datetime,
) -> DocumentJob:
    await _persist_execution_artifacts(db, job=job, execution_result=execution_result)
    now = _utcnow()
    job.status = execution_result.status
    job.result_summary = execution_result.summary
    job.error_message = None
    job.completed_at = now
    job.last_heartbeat_at = now
    job.run.status = execution_result.status
    job.run.output_text = execution_result.output_text
    job.run.error_message = None
    job.run.completed_at = now

    for event in execution_result.events:
        _record_trace(
            db,
            run=job.run,
            event_type=event.event_type,
            message=event.message,
            payload=event.payload,
        )

    _record_trace(
        db,
        run=job.run,
        event_type="job_completed",
        message="Document job completed successfully",
        payload={"driver": execution_result.driver},
    )
    mutx_document_execution_duration_seconds.labels(
        template_id=job.template_id,
        status=execution_result.status,
    ).observe(max((_utcnow() - started_at).total_seconds(), 0))
    mutx_document_jobs_total.labels(template_id=job.template_id, status="completed").inc()
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts", "run"])
    return job


async def fail_document_job_execution(
    db: AsyncSession,
    *,
    job: DocumentJob,
    error: Exception,
    started_at: datetime,
) -> DocumentJob:
    now = _utcnow()
    job.status = "failed"
    job.error_message = str(error)
    job.completed_at = now
    job.last_heartbeat_at = now
    job.run.status = "failed"
    job.run.error_message = str(error)
    job.run.completed_at = now
    _record_trace(
        db,
        run=job.run,
        event_type="job_failed",
        message="Document job failed",
        payload={"error": str(error)},
    )
    mutx_document_execution_duration_seconds.labels(
        template_id=job.template_id,
        status="failed",
    ).observe(max((_utcnow() - started_at).total_seconds(), 0))
    mutx_document_jobs_total.labels(template_id=job.template_id, status="failed").inc()
    await db.commit()
    await db.refresh(job, attribute_names=["artifacts", "run"])
    return job


async def execute_document_job(
    db: AsyncSession,
    *,
    claimed_job: ClaimedDocumentJob,
) -> DocumentJob:
    job = claimed_job.job
    started_at = _utcnow()
    try:
        validate_job_inputs(job, job.artifacts)
        manifest = build_document_manifest(job, job.artifacts)
        execution_result = execute_document_manifest(manifest)
        return await finalize_document_job_execution(
            db,
            job=job,
            execution_result=execution_result,
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Document job %s failed: %s", job.id, exc)
        return await fail_document_job_execution(db, job=job, error=exc, started_at=started_at)


async def update_document_queue_depth(db: AsyncSession) -> None:
    total = (
        await db.execute(
            select(func.count())
            .select_from(DocumentJob)
            .where(DocumentJob.status.in_(DOCUMENT_PENDING_STATUSES | DOCUMENT_ACTIVE_STATUSES))
        )
    ).scalar_one()
    mutx_document_queue_depth.set(total)


def get_artifact_download_path(artifact: DocumentArtifact) -> Path:
    return resolve_artifact_path(artifact)
