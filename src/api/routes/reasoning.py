from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import User
from src.api.models.schemas import (
    ReasoningArtifactRegistrationCreate,
    ReasoningArtifactResponse,
    ReasoningJobCreate,
    ReasoningJobDispatchRequest,
    ReasoningJobEventCreate,
    ReasoningJobHistoryResponse,
    ReasoningJobLocalLaunchRequest,
    ReasoningJobLocalLaunchResponse,
    ReasoningJobResponse,
    ReasoningTemplateResponse,
)
from src.api.services.reasoning_jobs import (
    append_reasoning_job_event,
    build_local_launch_response,
    create_reasoning_job,
    dispatch_reasoning_job,
    get_artifact_download_path,
    get_reasoning_artifact_or_404,
    get_reasoning_job_or_404,
    list_reasoning_jobs,
    register_reasoning_artifact,
    serialize_reasoning_job,
    store_reasoning_upload,
)
from src.api.services.reasoning_templates import list_reasoning_templates

router = APIRouter(prefix="/reasoning", tags=["reasoning"])


@router.get("/templates", response_model=list[ReasoningTemplateResponse])
async def get_reasoning_templates(
    _current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    return list_reasoning_templates()


@router.post("/jobs", response_model=ReasoningJobResponse, status_code=status.HTTP_201_CREATED)
async def create_reasoning_job_endpoint(
    request: ReasoningJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await create_reasoning_job(db, current_user=current_user, request=request)
    return serialize_reasoning_job(job)


@router.get("/jobs", response_model=ReasoningJobHistoryResponse)
async def list_reasoning_jobs_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    template_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    items, total = await list_reasoning_jobs(
        db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
        template_id=template_id,
    )
    return ReasoningJobHistoryResponse(
        items=[serialize_reasoning_job(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(items),
        status=status_filter,
        template_id=template_id,
    )


@router.get("/jobs/{job_id}", response_model=ReasoningJobResponse)
async def get_reasoning_job_endpoint(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    job = await get_reasoning_job_or_404(db, job_id=job_id, current_user=current_user)
    return serialize_reasoning_job(job)


@router.post(
    "/jobs/{job_id}/artifacts",
    response_model=ReasoningArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_reasoning_artifact_endpoint(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_reasoning_job_or_404(db, job_id=job_id, current_user=current_user)
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(
                status_code=400, detail="multipart upload must include a file field"
            )

        role = str(form.get("role") or "context")
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

        result = await store_reasoning_upload(
            db,
            job=job,
            upload=upload,
            role=role,
            kind=kind,
            metadata=metadata,
        )
        return ReasoningArtifactResponse.model_validate(
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

    payload = ReasoningArtifactRegistrationCreate.model_validate(await request.json())
    artifact = await register_reasoning_artifact(db, job=job, request=payload)
    return ReasoningArtifactResponse.model_validate(
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


@router.post("/jobs/{job_id}/dispatch", response_model=ReasoningJobResponse)
async def dispatch_reasoning_job_endpoint(
    job_id: uuid.UUID,
    request: ReasoningJobDispatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_reasoning_job_or_404(db, job_id=job_id, current_user=current_user)
    updated = await dispatch_reasoning_job(db, job=job, request=request)
    return serialize_reasoning_job(updated)


@router.post("/jobs/{job_id}/launch-local", response_model=ReasoningJobLocalLaunchResponse)
async def launch_reasoning_job_local_endpoint(
    job_id: uuid.UUID,
    request: ReasoningJobLocalLaunchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_reasoning_job_or_404(db, job_id=job_id, current_user=current_user)
    return await build_local_launch_response(db, job=job, output_dir=request.output_dir)


@router.post("/jobs/{job_id}/events", response_model=ReasoningJobResponse)
async def append_reasoning_job_event_endpoint(
    job_id: uuid.UUID,
    event: ReasoningJobEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    job = await get_reasoning_job_or_404(db, job_id=job_id, current_user=current_user)
    updated = await append_reasoning_job_event(db, job=job, event=event)
    return serialize_reasoning_job(updated)


@router.get("/jobs/{job_id}/artifacts/{artifact_id}")
async def download_reasoning_artifact_endpoint(
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    artifact = await get_reasoning_artifact_or_404(
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
