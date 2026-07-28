from __future__ import annotations

from dataclasses import dataclass, field

from src.api.config import get_settings
from src.api.models.schemas import (
    DocumentTemplateFieldResponse,
    DocumentTemplateOutputResponse,
    DocumentTemplateResponse,
)


@dataclass(frozen=True)
class DocumentTemplateField:
    name: str
    type: str
    description: str
    required: bool = True
    accepts_multiple: bool = False


@dataclass(frozen=True)
class DocumentTemplateOutput:
    role: str
    kind: str
    description: str


@dataclass(frozen=True)
class DocumentTemplateDefinition:
    id: str
    name: str
    summary: str
    description: str
    inputs: tuple[DocumentTemplateField, ...] = field(default_factory=tuple)
    outputs: tuple[DocumentTemplateOutput, ...] = field(default_factory=tuple)
    supports_managed: bool = True
    supports_local: bool = True

    def to_response(self) -> DocumentTemplateResponse:
        return DocumentTemplateResponse(
            id=self.id,
            name=self.name,
            summary=self.summary,
            description=self.description,
            supports_managed=self.supports_managed,
            supports_local=self.supports_local,
            max_upload_bytes=get_settings().document_max_upload_mb * 1024 * 1024,
            inputs=[
                DocumentTemplateFieldResponse(
                    name=item.name,
                    type=item.type,
                    description=item.description,
                    required=item.required,
                    accepts_multiple=item.accepts_multiple,
                )
                for item in self.inputs
            ],
            outputs=[
                DocumentTemplateOutputResponse(
                    role=item.role,
                    kind=item.kind,
                    description=item.description,
                )
                for item in self.outputs
            ],
        )


DOCUMENT_TEMPLATE_CATALOG: dict[str, DocumentTemplateDefinition] = {
    "document_analysis": DocumentTemplateDefinition(
        id="document_analysis",
        name="Document Analysis",
        summary="Turn raw documents into a markdown briefing and structured summary.",
        description=(
            "Analyze one or more source documents, produce an operator-readable markdown report, "
            "and capture a structured JSON summary for downstream automation."
        ),
        inputs=(
            DocumentTemplateField(
                name="documents",
                type="artifact",
                description="One or more source documents to analyze.",
                accepts_multiple=True,
            ),
            DocumentTemplateField(
                name="instructions",
                type="string",
                description="Optional analyst instructions for the workflow.",
                required=False,
            ),
        ),
        outputs=(
            DocumentTemplateOutput(
                role="report",
                kind="markdown",
                description="Operator-readable markdown report.",
            ),
            DocumentTemplateOutput(
                role="summary",
                kind="json",
                description="Structured JSON summary.",
            ),
        ),
    ),
    "contract_comparison": DocumentTemplateDefinition(
        id="contract_comparison",
        name="Contract Comparison",
        summary="Compare a base contract against a comparison copy and flag material deltas.",
        description=(
            "Compare a baseline contract and a second draft, then produce a markdown delta report "
            "plus structured JSON describing material changes."
        ),
        inputs=(
            DocumentTemplateField(
                name="base_document",
                type="artifact",
                description="Baseline contract or governing version.",
            ),
            DocumentTemplateField(
                name="comparison_document",
                type="artifact",
                description="Updated contract or draft to compare against the baseline.",
            ),
            DocumentTemplateField(
                name="instructions",
                type="string",
                description="Optional comparison focus areas.",
                required=False,
            ),
        ),
        outputs=(
            DocumentTemplateOutput(
                role="report",
                kind="markdown",
                description="Markdown comparison report.",
            ),
            DocumentTemplateOutput(
                role="summary",
                kind="json",
                description="Structured change summary.",
            ),
        ),
    ),
    "invoice_extraction": DocumentTemplateDefinition(
        id="invoice_extraction",
        name="Invoice Extraction",
        summary="Extract invoice fields into a workbook and structured JSON.",
        description=(
            "Read one or more invoices, normalize the extracted fields into a workbook, "
            "and emit a structured JSON summary for downstream systems."
        ),
        inputs=(
            DocumentTemplateField(
                name="documents",
                type="artifact",
                description="One or more invoice files.",
                accepts_multiple=True,
            ),
        ),
        outputs=(
            DocumentTemplateOutput(
                role="workbook",
                kind="xlsx",
                description="Normalized workbook of invoice rows.",
            ),
            DocumentTemplateOutput(
                role="summary",
                kind="json",
                description="Structured extraction metadata.",
            ),
        ),
    ),
    "document_redaction": DocumentTemplateDefinition(
        id="document_redaction",
        name="Document Redaction",
        summary="Apply a redaction policy and emit redacted files with verification notes.",
        description=(
            "Apply a redaction policy to one or more source files, persist redacted outputs, "
            "and emit a verification report with structured redaction metadata."
        ),
        inputs=(
            DocumentTemplateField(
                name="documents",
                type="artifact",
                description="Documents that should be redacted.",
                accepts_multiple=True,
            ),
            DocumentTemplateField(
                name="redaction_policy",
                type="string",
                description="Plain-language policy describing what must be redacted.",
            ),
        ),
        outputs=(
            DocumentTemplateOutput(
                role="redacted_document",
                kind="file",
                description="Redacted file output.",
            ),
            DocumentTemplateOutput(
                role="verification_report",
                kind="markdown",
                description="Verification report for the applied redactions.",
            ),
            DocumentTemplateOutput(
                role="summary",
                kind="json",
                description="Structured redaction summary.",
            ),
        ),
    ),
}


def list_document_templates() -> list[DocumentTemplateResponse]:
    return [definition.to_response() for definition in DOCUMENT_TEMPLATE_CATALOG.values()]


def get_document_template(template_id: str) -> DocumentTemplateDefinition | None:
    return DOCUMENT_TEMPLATE_CATALOG.get(template_id)
