from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import json
import logging
from mimetypes import guess_type
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from src.api.config import get_settings
from src.api.models import DocumentArtifact, DocumentJob
from src.api.services.document_templates import get_document_template

logger = logging.getLogger(__name__)

DOCUMENT_TRACE_EVENT_TYPES = (
    "job_created",
    "artifact_registered",
    "artifact_uploaded",
    "submission_staged",
    "submission_failed",
    "submission_retry",
    "job_dispatched",
    "dispatch_started",
    "rlm_iteration",
    "tool_call",
    "artifact_synced",
    "job_completed",
    "job_failed",
    "job_cancelled",
)


class DocumentEngineError(RuntimeError):
    pass


class DocumentEnginePrerequisiteError(DocumentEngineError):
    pass


@dataclass(frozen=True)
class EngineReadiness:
    enabled: bool
    python_ok: bool
    predict_rlm_available: bool
    deno_available: bool
    credentials_ok: bool
    ready: bool
    driver: str
    artifacts_dir: str
    missing_requirements: tuple[str, ...] = ()
    configured_model_providers: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "python_ok": self.python_ok,
            "predict_rlm_available": self.predict_rlm_available,
            "deno_available": self.deno_available,
            "credentials_ok": self.credentials_ok,
            "ready": self.ready,
            "driver": self.driver,
            "artifacts_dir": self.artifacts_dir,
            "missing_requirements": list(self.missing_requirements),
            "configured_model_providers": list(self.configured_model_providers),
        }


@dataclass(frozen=True)
class EngineArtifactInput:
    id: str
    role: str
    kind: str
    filename: str
    storage_backend: str
    local_path: str | None
    storage_uri: str | None
    content_type: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineManagedOutput:
    path: Path
    role: str
    kind: str
    content_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    filename: str | None = None


@dataclass(frozen=True)
class EngineEvent:
    event_type: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineExecutionResult:
    driver: str
    status: str
    output_text: str | None
    summary: dict[str, Any]
    artifacts: list[EngineManagedOutput]
    events: list[EngineEvent]


PROVIDER_CREDENTIAL_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _configured_document_model_providers() -> tuple[str, ...]:
    providers: list[str] = []
    for model_name in (
        os.getenv("MUTX_DOCUMENTS_LM", "openai/gpt-5.4"),
        os.getenv("MUTX_DOCUMENTS_SUB_LM", "openai/gpt-5.1"),
    ):
        provider = str(model_name).split("/", 1)[0].strip().lower()
        if provider and provider not in providers:
            providers.append(provider)
    return tuple(providers)


def get_document_engine_readiness() -> EngineReadiness:
    settings = get_settings()
    python_ok = sys.version_info >= (3, 11)
    predict_rlm_available = importlib.util.find_spec("predict_rlm") is not None
    deno_available = shutil.which("deno") is not None
    configured_model_providers = _configured_document_model_providers()
    missing_requirements: list[str] = []
    if not settings.documents_enabled:
        missing_requirements.append("documents_enabled")
    if not python_ok:
        missing_requirements.append("python>=3.11")
    if not deno_available:
        missing_requirements.append("deno")
    if not predict_rlm_available:
        missing_requirements.append("predict_rlm")
    for provider in configured_model_providers:
        env_var = PROVIDER_CREDENTIAL_ENV_VARS.get(provider)
        if env_var is None:
            missing_requirements.append(f"{provider}_credentials")
            continue
        if not os.getenv(env_var):
            missing_requirements.append(env_var)
    credentials_ok = all(
        item not in missing_requirements for item in PROVIDER_CREDENTIAL_ENV_VARS.values()
    ) and not any(item.endswith("_credentials") for item in missing_requirements)
    ready = not missing_requirements
    driver = "predict_rlm" if ready else "unavailable"
    return EngineReadiness(
        enabled=settings.documents_enabled,
        python_ok=python_ok,
        predict_rlm_available=predict_rlm_available,
        deno_available=deno_available,
        credentials_ok=credentials_ok,
        ready=ready,
        driver=driver,
        artifacts_dir=str(Path(settings.artifacts_dir).expanduser()),
        missing_requirements=tuple(missing_requirements),
        configured_model_providers=configured_model_providers,
    )


def build_document_manifest(
    job: DocumentJob,
    artifacts: list[DocumentArtifact],
    *,
    output_dir: str | None = None,
) -> dict[str, Any]:
    template = get_document_template(job.template_id)
    if template is None:
        raise DocumentEngineError(f"Unknown document template: {job.template_id}")

    artifact_inputs = [
        EngineArtifactInput(
            id=str(artifact.id),
            role=artifact.role,
            kind=artifact.kind,
            filename=artifact.filename,
            storage_backend=artifact.storage_backend,
            local_path=artifact.local_path,
            storage_uri=artifact.storage_uri,
            content_type=artifact.content_type,
            metadata=artifact.extra_metadata or {},
        ).__dict__
        for artifact in artifacts
    ]

    readiness = get_document_engine_readiness()

    return {
        "job_id": str(job.id),
        "run_id": str(job.run_id),
        "template_id": job.template_id,
        "template_name": template.name,
        "execution_mode": job.execution_mode,
        "parameters": job.parameters or {},
        "artifacts": artifact_inputs,
        "output_contract": [output.__dict__ for output in template.outputs],
        "trace_metadata": {
            "subject_type": "document_job",
            "subject_id": str(job.id),
            "subject_label": template.name,
            "template_id": job.template_id,
            "execution_mode": job.execution_mode,
        },
        "engine": {
            "ready": readiness.ready,
            "driver": readiness.driver,
            "missing_requirements": list(readiness.missing_requirements),
        },
        "output_dir": output_dir,
    }


def _ensure_output_dir(manifest: dict[str, Any]) -> Path:
    raw = manifest.get("output_dir")
    if raw:
        output_dir = Path(str(raw)).expanduser().resolve()
    else:
        output_dir = (
            Path(get_settings().artifacts_dir).expanduser().resolve()
            / ".tmp"
            / str(manifest["job_id"])
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _artifact_path(artifact: EngineArtifactInput) -> Path | None:
    if artifact.local_path:
        candidate = Path(artifact.local_path).expanduser()
        if candidate.exists():
            return candidate
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _raise_if_not_ready() -> None:
    readiness = get_document_engine_readiness()
    if readiness.ready:
        return

    missing = ", ".join(readiness.missing_requirements) or "predict_rlm runtime"
    raise DocumentEnginePrerequisiteError(
        f"predict-rlm document execution is unavailable. Missing prerequisites: {missing}."
    )


def _execute_predict_rlm(manifest: dict[str, Any]) -> EngineExecutionResult:
    readiness = get_document_engine_readiness()
    if not readiness.ready:
        _raise_if_not_ready()

    try:
        import dspy
        from pydantic import BaseModel, Field
        from predict_rlm import File, PredictRLM, Skill

        subprocess.run(["deno", "--version"], check=True, capture_output=True, text=True)
    except Exception as exc:  # noqa: BLE001
        raise DocumentEnginePrerequisiteError(f"predict-rlm prerequisites failed: {exc}") from exc

    output_dir = _ensure_output_dir(manifest)
    lm = os.getenv("MUTX_DOCUMENTS_LM", "openai/gpt-5.4")
    sub_lm = os.getenv("MUTX_DOCUMENTS_SUB_LM", "openai/gpt-5.1")
    parameters = manifest.get("parameters") or {}
    artifact_items = [
        EngineArtifactInput(**item)
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    ]

    def file_inputs(role: str) -> list[Any]:
        files: list[Any] = []
        for artifact in artifact_items:
            if artifact.role != role:
                continue
            source_path = _artifact_path(artifact)
            if source_path is None:
                continue
            files.append(File(path=str(source_path)))
        return files

    def single_file(role: str) -> Any | None:
        files = file_inputs(role)
        return files[0] if files else None

    pdf_skill = Skill(
        name="pdf",
        instructions=(
            "Use pymupdf to inspect PDF files. Render pages when layout matters, "
            "use predict() for semantic extraction, and keep final outputs concise."
        ),
        packages=["pymupdf"],
    )
    spreadsheet_skill = Skill(
        name="spreadsheet",
        instructions=(
            "Use openpyxl to write spreadsheet outputs. Add headers first, keep one row per record, "
            "and save the workbook before returning it."
        ),
        packages=["openpyxl"],
    )

    class DocumentAnalysisSummary(BaseModel):
        executive_summary: str = Field(default="")
        key_dates: list[str] = Field(default_factory=list)
        entities: list[str] = Field(default_factory=list)
        financial_points: list[str] = Field(default_factory=list)

    class ContractComparisonSummary(BaseModel):
        executive_summary: str = Field(default="")
        material_changes: list[str] = Field(default_factory=list)
        risk_flags: list[str] = Field(default_factory=list)

    class InvoiceExtractionSummary(BaseModel):
        vendors: list[str] = Field(default_factory=list)
        invoice_numbers: list[str] = Field(default_factory=list)
        row_count: int = 0

    class RedactionSummary(BaseModel):
        policy: str = Field(default="")
        files_redacted: int = 0
        notes: list[str] = Field(default_factory=list)

    if manifest["template_id"] == "document_analysis":

        class AnalyzeDocuments(dspy.Signature):
            """Analyze the provided documents and produce a markdown report plus a structured summary."""

            documents: list[File] = dspy.InputField()
            user_instructions: str | None = dspy.InputField()
            report: File = dspy.OutputField()
            summary: DocumentAnalysisSummary = dspy.OutputField()

        rlm = PredictRLM(AnalyzeDocuments, lm=lm, sub_lm=sub_lm, skills=[pdf_skill])
        result = rlm(
            documents=file_inputs("documents"),
            user_instructions=parameters.get("instructions"),
        )
        output_files = [
            EngineManagedOutput(
                path=Path(result.report.path),
                role="report",
                kind="markdown",
                content_type="text/markdown",
            )
        ]
        summary = (
            result.summary.model_dump()
            if hasattr(result.summary, "model_dump")
            else dict(result.summary)
        )
    elif manifest["template_id"] == "contract_comparison":

        class CompareContracts(dspy.Signature):
            """Compare the baseline and comparison contracts and produce a markdown diff report with a structured summary."""

            base_document: File = dspy.InputField()
            comparison_document: File = dspy.InputField()
            user_instructions: str | None = dspy.InputField()
            report: File = dspy.OutputField()
            summary: ContractComparisonSummary = dspy.OutputField()

        rlm = PredictRLM(CompareContracts, lm=lm, sub_lm=sub_lm, skills=[pdf_skill])
        result = rlm(
            base_document=single_file("base_document"),
            comparison_document=single_file("comparison_document"),
            user_instructions=parameters.get("instructions"),
        )
        output_files = [
            EngineManagedOutput(
                path=Path(result.report.path),
                role="report",
                kind="markdown",
                content_type="text/markdown",
            )
        ]
        summary = (
            result.summary.model_dump()
            if hasattr(result.summary, "model_dump")
            else dict(result.summary)
        )
    elif manifest["template_id"] == "invoice_extraction":

        class ExtractInvoices(dspy.Signature):
            """Extract invoice data into a workbook and submit a structured summary of the extracted records."""

            documents: list[File] = dspy.InputField()
            workbook: File = dspy.OutputField()
            summary: InvoiceExtractionSummary = dspy.OutputField()

        rlm = PredictRLM(
            ExtractInvoices,
            lm=lm,
            sub_lm=sub_lm,
            skills=[pdf_skill, spreadsheet_skill],
        )
        result = rlm(documents=file_inputs("documents"))
        output_files = [
            EngineManagedOutput(
                path=Path(result.workbook.path),
                role="workbook",
                kind="xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        ]
        summary = (
            result.summary.model_dump()
            if hasattr(result.summary, "model_dump")
            else dict(result.summary)
        )
    elif manifest["template_id"] == "document_redaction":

        class RedactDocuments(dspy.Signature):
            """Apply the redaction policy to the documents, output the redacted files, and write a verification report."""

            documents: list[File] = dspy.InputField()
            redaction_policy: str = dspy.InputField()
            redacted_documents: list[File] = dspy.OutputField()
            verification_report: File = dspy.OutputField()
            summary: RedactionSummary = dspy.OutputField()

        rlm = PredictRLM(RedactDocuments, lm=lm, sub_lm=sub_lm, skills=[pdf_skill])
        result = rlm(
            documents=file_inputs("documents"),
            redaction_policy=str(parameters.get("redaction_policy") or ""),
        )
        output_files = [
            EngineManagedOutput(
                path=Path(item.path),
                role="redacted_document",
                kind="file",
                content_type=guess_type(item.path)[0] or "application/octet-stream",
            )
            for item in getattr(result, "redacted_documents", []) or []
        ]
        output_files.append(
            EngineManagedOutput(
                path=Path(result.verification_report.path),
                role="verification_report",
                kind="markdown",
                content_type="text/markdown",
            )
        )
        summary = (
            result.summary.model_dump()
            if hasattr(result.summary, "model_dump")
            else dict(result.summary)
        )
    else:
        raise DocumentEngineError(f"Unsupported document template: {manifest['template_id']}")

    summary_path = output_dir / f"{manifest['template_id']}-summary.json"
    _write_json(summary_path, summary)
    output_files.append(
        EngineManagedOutput(
            path=summary_path,
            role="summary",
            kind="json",
            content_type="application/json",
        )
    )

    return EngineExecutionResult(
        driver="predict_rlm",
        status="completed",
        output_text=f"{manifest['template_name']} completed with predict-rlm.",
        summary=summary,
        artifacts=output_files,
        events=[
            EngineEvent(
                event_type="rlm_iteration",
                message="Executed predict-rlm document workflow.",
                payload={"driver": "predict_rlm", "template_id": manifest["template_id"]},
            ),
            EngineEvent(
                event_type="tool_call",
                message="predict-rlm invoked its recursive execution environment.",
                payload={"lm": lm, "sub_lm": sub_lm},
            ),
        ],
    )


def execute_document_manifest(manifest: dict[str, Any]) -> EngineExecutionResult:
    _raise_if_not_ready()
    return _execute_predict_rlm(manifest)
