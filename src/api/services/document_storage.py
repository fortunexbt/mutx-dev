from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import shutil
from typing import Any
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.models import DocumentArtifact, DocumentJob

logger = logging.getLogger(__name__)

MANAGED_STORAGE_BACKENDS = {"managed", "filesystem"}


@dataclass(frozen=True)
class StoredArtifactResult:
    artifact: DocumentArtifact
    path: Path | None = None


def get_artifacts_root() -> Path:
    root = Path(get_settings().artifacts_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_job_artifact_dir(job_id: uuid.UUID) -> Path:
    path = get_artifacts_root() / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def compute_sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_filename(value: str) -> str:
    name = Path(value or "artifact.bin").name
    return name or "artifact.bin"


def _managed_storage_uri(job_id: uuid.UUID, artifact_id: uuid.UUID, filename: str) -> str:
    return f"managed://documents/{job_id}/{artifact_id}/{_safe_filename(filename)}"


def get_document_max_upload_bytes() -> int:
    return get_settings().document_max_upload_mb * 1024 * 1024


def assert_upload_size_within_limit(size_bytes: int) -> None:
    max_size_bytes = get_document_max_upload_bytes()
    if size_bytes > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Artifact exceeds max upload size of {get_settings().document_max_upload_mb} MB",
        )


async def register_artifact_reference(
    db: AsyncSession,
    *,
    job: DocumentJob,
    role: str,
    kind: str,
    filename: str,
    storage_backend: str,
    local_path: str | None,
    storage_uri: str | None,
    content_type: str | None,
    size_bytes: int | None,
    sha256: str | None,
    metadata: dict[str, Any] | None,
) -> DocumentArtifact:
    artifact = DocumentArtifact(
        job_id=job.id,
        role=role,
        kind=kind,
        storage_backend=storage_backend,
        storage_uri=storage_uri,
        local_path=local_path,
        filename=_safe_filename(filename),
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        extra_metadata=metadata or {},
    )
    db.add(artifact)
    await db.flush()
    return artifact


async def store_uploaded_artifact(
    db: AsyncSession,
    *,
    job: DocumentJob,
    upload: UploadFile,
    role: str,
    kind: str,
    metadata: dict[str, Any] | None = None,
) -> StoredArtifactResult:
    content = await upload.read()
    assert_upload_size_within_limit(len(content))

    return await store_prepared_artifact(
        db,
        job=job,
        content=content,
        role=role,
        kind=kind,
        filename=upload.filename or f"{role}.bin",
        content_type=upload.content_type,
        metadata=metadata,
    )


async def store_prepared_artifact(
    db: AsyncSession,
    *,
    job: DocumentJob,
    content: bytes,
    role: str,
    kind: str,
    filename: str,
    content_type: str | None,
    metadata: dict[str, Any] | None = None,
) -> StoredArtifactResult:
    """Persist content that has already passed submission-level validation."""
    assert_upload_size_within_limit(len(content))

    artifact = DocumentArtifact(
        job_id=job.id,
        role=role,
        kind=kind,
        storage_backend="managed",
        filename=_safe_filename(filename),
        content_type=content_type,
        size_bytes=len(content),
        sha256=compute_sha256_bytes(content),
        extra_metadata=metadata or {},
    )
    db.add(artifact)
    await db.flush()

    destination = get_job_artifact_dir(job.id) / f"{artifact.id}-{artifact.filename}"
    destination.write_bytes(content)

    artifact.local_path = str(destination)
    artifact.storage_uri = _managed_storage_uri(job.id, artifact.id, artifact.filename)
    await db.flush()
    return StoredArtifactResult(artifact=artifact, path=destination)


async def sync_managed_output_artifact(
    db: AsyncSession,
    *,
    job: DocumentJob,
    source_path: Path,
    role: str,
    kind: str,
    content_type: str | None = None,
    metadata: dict[str, Any] | None = None,
    filename: str | None = None,
) -> StoredArtifactResult:
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    artifact = DocumentArtifact(
        job_id=job.id,
        role=role,
        kind=kind,
        storage_backend="managed",
        filename=_safe_filename(filename or source_path.name),
        content_type=content_type,
        size_bytes=source_path.stat().st_size,
        sha256=compute_sha256_file(source_path),
        extra_metadata=metadata or {},
    )
    db.add(artifact)
    await db.flush()

    destination = get_job_artifact_dir(job.id) / f"{artifact.id}-{artifact.filename}"
    if source_path.resolve() != destination.resolve():
        shutil.copy2(source_path, destination)

    artifact.local_path = str(destination)
    artifact.storage_uri = _managed_storage_uri(job.id, artifact.id, artifact.filename)
    await db.flush()
    return StoredArtifactResult(artifact=artifact, path=destination)


def resolve_artifact_path(artifact: DocumentArtifact) -> Path:
    if artifact.storage_backend not in MANAGED_STORAGE_BACKENDS:
        raise HTTPException(
            status_code=404,
            detail="Artifact is not available from managed storage",
        )

    if not artifact.local_path:
        raise HTTPException(status_code=404, detail="Artifact file missing")

    path = Path(artifact.local_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing")
    return path


def serialize_metadata(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, sort_keys=True)
