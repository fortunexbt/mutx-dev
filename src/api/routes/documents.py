from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import User
from src.api.models.schemas import (
    DocumentArtifactRegistrationCreate,
    DocumentArtifactResponse,
    DocumentJobCreate,
    DocumentJobDispatchRequest,
    DocumentJobEventCreate,
    DocumentJobHistoryResponse,
    DocumentJobLocalLaunchRequest,
    DocumentJobLocalLaunchResponse,
    DocumentJobResponse,
    DocumentTemplateResponse,
)
from src.api.services.document_jobs import (
    DocumentSubmissionError,
    append_document_job_event,
    build_local_launch_response,
    cleanup_document_job,
    create_document_job,
    dispatch_document_job,
    get_artifact_download_path,
    get_document_artifact_or_404,
    get_document_job_or_404,
    list_document_jobs,
    prepare_document_submission,
    register_document_artifact,
    serialize_document_job,
    store_document_upload,
    submit_managed_document_job,
)
from src.api.services.document_templates import list_document_templates

router = APIRouter(prefix="/documents", tags=["documents"])
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


@router.get("/templates", response_model=list[DocumentTemplateResponse])
async def get_document_templates(
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    del current_user
    return list_document_templates()


@router.post("/jobs", response_model=DocumentJobResponse, status_code=status.HTTP_201_CREATED)
async def create_document_job_endpoint(
    request: DocumentJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    if request.execution_mode.strip().lower() == "managed":
        raise HTTPException(
            status_code=409,
            detail=(
                "Managed document jobs must use /documents/jobs/submit so inputs are "
                "validated before canonical history is created"
            ),
        )
    job = await create_document_job(db, current_user=current_user, request=request)
    return serialize_document_job(job)


@router.post("/jobs/submit", response_model=DocumentJobResponse)
async def submit_managed_document_job_endpoint(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    if not idempotency_key or not IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key must be 8-128 URL-safe characters",
        )

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(
            status_code=400, detail="Managed submission requires multipart form data"
        )

    form = await request.form()
    template_id = str(form.get("template_id") or "").strip()
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")

    raw_parameters = form.get("parameters")
    parameters: dict[str, object] = {}
    if isinstance(raw_parameters, str) and raw_parameters.strip():
        try:
            parsed_parameters = json.loads(raw_parameters)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="parameters must be valid JSON") from exc
        if not isinstance(parsed_parameters, dict):
            raise HTTPException(status_code=400, detail="parameters must be a JSON object")
        parameters = parsed_parameters

    uploads = [
        (field_name, value)
        for field_name, value in form.multi_items()
        if isinstance(value, UploadFile)
    ]
    prepared, fingerprint = await prepare_document_submission(
        template_id=template_id,
        parameters=parameters,
        uploads=uploads,
    )

    try:
        job = await submit_managed_document_job(
            db,
            current_user=current_user,
            template_id=template_id,
            parameters=parameters,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            uploads=prepared,
        )
    except DocumentSubmissionError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"{exc}. Job {exc.job_id} remains in canonical failed state; "
                "retry with the same Idempotency-Key or clean it up."
            ),
        ) from exc
    return serialize_document_job(job)


@router.get("/jobs", response_model=DocumentJobHistoryResponse)
async def list_document_jobs_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    template_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    items, total = await list_document_jobs(
        db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
        template_id=template_id,
    )
    return DocumentJobHistoryResponse(
        items=[serialize_document_job(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(items),
        status=status_filter,
        template_id=template_id,
    )


@router.get("/jobs/{job_id}", response_model=DocumentJobResponse)
async def get_document_job_endpoint(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    job = await get_document_job_or_404(db, job_id=job_id, current_user=current_user)
    return serialize_document_job(job)


@router.post("/jobs/{job_id}/cleanup", response_model=DocumentJobResponse)
async def cleanup_document_job_endpoint(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_document_job_or_404(db, job_id=job_id, current_user=current_user)
    cleaned = await cleanup_document_job(db, job=job)
    return serialize_document_job(cleaned)


@router.post(
    "/jobs/{job_id}/artifacts",
    response_model=DocumentArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_document_artifact_endpoint(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_document_job_or_404(db, job_id=job_id, current_user=current_user)
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(
                status_code=400, detail="multipart upload must include a file field"
            )

        role = str(form.get("role") or "document")
        kind = str(form.get("kind") or "file")
        raw_metadata = form.get("metadata")
        metadata: dict[str, object] = {}
        if isinstance(raw_metadata, str) and raw_metadata.strip():
            try:
                parsed = json.loads(raw_metadata)
                if isinstance(parsed, dict):
                    metadata = parsed
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=400, detail=f"Invalid metadata JSON: {exc}"
                ) from exc

        result = await store_document_upload(
            db,
            job=job,
            upload=upload,
            role=role,
            kind=kind,
            metadata=metadata,
        )
        return DocumentArtifactResponse.model_validate(
            {
                "id": result.artifact.id,
                "job_id": result.artifact.job_id,
                "role": result.artifact.role,
                "kind": result.artifact.kind,
                "storage_backend": result.artifact.storage_backend,
                "storage_uri": result.artifact.storage_uri,
                "local_path": result.artifact.local_path,
                "filename": result.artifact.filename,
                "content_type": result.artifact.content_type,
                "size_bytes": result.artifact.size_bytes,
                "sha256": result.artifact.sha256,
                "metadata": result.artifact.extra_metadata or {},
                "created_at": result.artifact.created_at,
                "updated_at": result.artifact.updated_at,
            }
        )

    payload = DocumentArtifactRegistrationCreate.model_validate(await request.json())
    artifact = await register_document_artifact(db, job=job, request=payload)
    return DocumentArtifactResponse.model_validate(
        {
            "id": artifact.id,
            "job_id": artifact.job_id,
            "role": artifact.role,
            "kind": artifact.kind,
            "storage_backend": artifact.storage_backend,
            "storage_uri": artifact.storage_uri,
            "local_path": artifact.local_path,
            "filename": artifact.filename,
            "content_type": artifact.content_type,
            "size_bytes": artifact.size_bytes,
            "sha256": artifact.sha256,
            "metadata": artifact.extra_metadata or {},
            "created_at": artifact.created_at,
            "updated_at": artifact.updated_at,
        }
    )


@router.post("/jobs/{job_id}/dispatch", response_model=DocumentJobResponse)
async def dispatch_document_job_endpoint(
    job_id: uuid.UUID,
    request: DocumentJobDispatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_document_job_or_404(db, job_id=job_id, current_user=current_user)
    updated = await dispatch_document_job(db, job=job, request=request)
    return serialize_document_job(updated)


@router.post("/jobs/{job_id}/launch-local", response_model=DocumentJobLocalLaunchResponse)
async def launch_document_job_local_endpoint(
    job_id: uuid.UUID,
    request: DocumentJobLocalLaunchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_document_job_or_404(db, job_id=job_id, current_user=current_user)
    return await build_local_launch_response(db, job=job, output_dir=request.output_dir)


@router.post("/jobs/{job_id}/events", response_model=DocumentJobResponse)
async def append_document_job_event_endpoint(
    job_id: uuid.UUID,
    event: DocumentJobEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_document_job_or_404(db, job_id=job_id, current_user=current_user)
    updated = await append_document_job_event(db, job=job, event=event)
    return serialize_document_job(updated)


@router.get("/jobs/{job_id}/artifacts/{artifact_id}")
async def download_document_artifact_endpoint(
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    artifact = await get_document_artifact_or_404(
        db,
        job_id=job_id,
        artifact_id=artifact_id,
        current_user=current_user,
    )
    path = get_artifact_download_path(artifact)
    return FileResponse(
        path,
        filename=artifact.filename,
        media_type=artifact.content_type or "application/octet-stream",
    )
