from __future__ import annotations

from importlib.metadata import version
from inspect import signature
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import tomllib

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version
import pytest

from src.api.services import document_engine


ROOT = Path(__file__).resolve().parents[1]
PREDICT_RLM_COMPATIBILITY_RANGE = SpecifierSet(">=0.7.3,<1")
_NO_INSTRUCTION_INPUT = object()


def _ready(tmp_path: Path) -> document_engine.EngineReadiness:
    return document_engine.EngineReadiness(
        enabled=True,
        python_ok=True,
        predict_rlm_available=True,
        deno_available=True,
        credentials_ok=True,
        ready=True,
        driver="predict_rlm",
        artifacts_dir=str(tmp_path),
        missing_requirements=(),
        configured_model_providers=("openai",),
    )


def _artifact(path: Path, role: str, artifact_id: str) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "role": role,
        "kind": "file",
        "filename": path.name,
        "storage_backend": "local_reference",
        "local_path": str(path),
        "storage_uri": None,
        "content_type": "application/pdf",
        "metadata": {},
    }


def test_predict_rlm_is_backend_only_dependency() -> None:
    backend_requirements = [
        Requirement(line)
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    predict_requirements = [
        requirement for requirement in backend_requirements if requirement.name == "predict-rlm"
    ]

    assert len(predict_requirements) == 1
    assert predict_requirements[0].specifier == PREDICT_RLM_COMPATIBILITY_RANGE

    root_project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    root_requirements = list(root_project["dependencies"])
    for extra_requirements in root_project.get("optional-dependencies", {}).values():
        root_requirements.extend(extra_requirements)
    assert all(Requirement(item).name != "predict-rlm" for item in root_requirements)


def test_predict_rlm_public_api_meets_v073_contract() -> None:
    from predict_rlm import File, PredictRLM, Skill

    assert Version(version("predict-rlm")) in PREDICT_RLM_COMPATIBILITY_RANGE
    assert File(path="/tmp/input.pdf").path == "/tmp/input.pdf"
    assert Skill(name="pdf", packages=["pymupdf"]).packages == ["pymupdf"]

    constructor_parameters = signature(PredictRLM.__init__).parameters
    assert {"signature", "lm", "sub_lm", "skills", "output_dir"}.issubset(constructor_parameters)


@pytest.mark.parametrize(
    (
        "template_id",
        "expected_roles",
        "parameters",
        "expected_user_instructions",
    ),
    [
        pytest.param(
            "document_analysis",
            {"report", "summary"},
            {"instructions": "Prioritize material findings"},
            "Prioritize material findings",
            id="analysis-instructions",
        ),
        pytest.param(
            "document_analysis",
            {"report", "summary"},
            {},
            None,
            id="analysis-optional-instructions-omitted",
        ),
        pytest.param(
            "contract_comparison",
            {"report", "summary"},
            {"instructions": "Prioritize material findings"},
            "Prioritize material findings",
            id="comparison-instructions",
        ),
        pytest.param(
            "contract_comparison",
            {"report", "summary"},
            {},
            None,
            id="comparison-optional-instructions-omitted",
        ),
        pytest.param(
            "invoice_extraction",
            {"workbook", "summary"},
            {},
            _NO_INSTRUCTION_INPUT,
            id="invoice",
        ),
        pytest.param(
            "document_redaction",
            {"redacted_document", "verification_report", "summary"},
            {"redaction_policy": "Remove secrets"},
            _NO_INSTRUCTION_INPUT,
            id="redaction",
        ),
    ],
)
def test_document_templates_execute_against_v073_public_types(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    template_id: str,
    expected_roles: set[str],
    parameters: dict[str, str],
    expected_user_instructions: object | str | None,
) -> None:
    import predict_rlm
    from predict_rlm import File, Skill

    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"%PDF-1.7\n")
    comparison_path = tmp_path / "comparison.pdf"
    comparison_path.write_bytes(b"%PDF-1.7\n")
    output_dir = tmp_path / "outputs"
    calls: list[dict[str, Any]] = []

    class CompatiblePredictRLM:
        def __init__(self, rlm_signature: type[Any], **kwargs: Any) -> None:
            self.signature_name = rlm_signature.__name__
            calls.append({"signature": rlm_signature, "options": kwargs})

        def __call__(self, **kwargs: Any) -> SimpleNamespace:
            calls[-1]["inputs"] = kwargs
            output_dir.mkdir(parents=True, exist_ok=True)
            summary = {"signature": self.signature_name}

            if self.signature_name == "ExtractInvoices":
                workbook = output_dir / "invoices.xlsx"
                workbook.write_bytes(b"workbook")
                return SimpleNamespace(workbook=File(path=str(workbook)), summary=summary)
            if self.signature_name == "RedactDocuments":
                redacted = output_dir / "redacted.pdf"
                redacted.write_bytes(b"%PDF-1.7\n")
                report = output_dir / "verification.md"
                report.write_text("# Verification\n", encoding="utf-8")
                return SimpleNamespace(
                    redacted_documents=[File(path=str(redacted))],
                    verification_report=File(path=str(report)),
                    summary=summary,
                )

            report = output_dir / "report.md"
            report.write_text("# Report\n", encoding="utf-8")
            return SimpleNamespace(report=File(path=str(report)), summary=summary)

    monkeypatch.setattr(predict_rlm, "PredictRLM", CompatiblePredictRLM)
    monkeypatch.setattr(document_engine, "get_document_engine_readiness", lambda: _ready(tmp_path))
    monkeypatch.setattr(
        document_engine.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )

    artifacts = [_artifact(input_path, "documents", "input")]
    if template_id == "contract_comparison":
        artifacts = [
            _artifact(input_path, "base_document", "base"),
            _artifact(comparison_path, "comparison_document", "comparison"),
        ]

    result = document_engine.execute_document_manifest(
        {
            "job_id": "compatibility-test",
            "template_id": template_id,
            "template_name": template_id.replace("_", " ").title(),
            "parameters": parameters,
            "artifacts": artifacts,
            "output_dir": str(output_dir),
        }
    )

    assert result.status == "completed"
    assert result.driver == "predict_rlm"
    assert {artifact.role for artifact in result.artifacts} == expected_roles
    assert all(artifact.path.exists() for artifact in result.artifacts)
    assert calls and all(isinstance(skill, Skill) for skill in calls[0]["options"]["skills"])

    runtime_inputs = calls[0]["inputs"]
    assert "instructions" not in runtime_inputs
    if expected_user_instructions is _NO_INSTRUCTION_INPUT:
        assert "user_instructions" not in runtime_inputs
    else:
        assert runtime_inputs["user_instructions"] == expected_user_instructions
    file_values = [
        item
        for value in runtime_inputs.values()
        for item in (value if isinstance(value, list) else [value])
        if isinstance(item, File)
    ]
    assert file_values
