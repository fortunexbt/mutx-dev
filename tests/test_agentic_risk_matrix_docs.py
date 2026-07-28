import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "docs" / "security" / "agentic_risk_matrix.md"
COMPETITIVE_NOTES_PATH = REPO_ROOT / "docs" / "gtm" / "competitive_notes.md"

OFFICIAL_RISKS = {
    "ASI01": "Agent Goal Hijack",
    "ASI02": "Tool Misuse & Exploitation",
    "ASI03": "Identity & Privilege Abuse",
    "ASI04": "Agentic Supply Chain Vulnerabilities",
    "ASI05": "Unexpected Code Execution",
    "ASI06": "Memory & Context Poisoning",
    "ASI07": "Insecure Inter-Agent Communication",
    "ASI08": "Cascading Failures",
    "ASI09": "Human-Agent Trust Exploitation",
    "ASI10": "Rogue Agents",
}


def _matrix_rows(matrix: str) -> dict[str, tuple[str, str]]:
    row_pattern = re.compile(
        r"^\| (ASI(?:0[1-9]|10)) \| ([^|]+?) \| (Partial|Gap) \|",
        re.MULTILINE,
    )
    return {
        risk_id: (name.strip(), status) for risk_id, name, status in row_pattern.findall(matrix)
    }


def test_agentic_risk_matrix_uses_the_complete_official_taxonomy() -> None:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    rows = _matrix_rows(matrix)

    assert list(rows) == list(OFFICIAL_RISKS)
    assert {risk_id: name for risk_id, (name, _status) in rows.items()} == OFFICIAL_RISKS
    assert sum(status == "Partial" for _name, status in rows.values()) == 8
    assert sum(status == "Gap" for _name, status in rows.values()) == 2


def test_agentic_risk_matrix_preserves_truthful_claim_boundaries() -> None:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    competitive_notes = COMPETITIVE_NOTES_PATH.read_text(encoding="utf-8")
    normalized_matrix = " ".join(matrix.split())

    assert "not an OWASP certification" in normalized_matrix
    assert "not comprehensive coverage" in normalized_matrix
    assert "../security/agentic_risk_matrix.md" in competitive_notes
    assert "not 10/10 coverage" in competitive_notes


def test_agentic_risk_matrix_local_evidence_links_exist() -> None:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    local_targets = re.findall(r"\]\(((?:\.\./)+[^)#]+)\)", matrix)

    assert local_targets
    for target in local_targets:
        assert (MATRIX_PATH.parent / target).resolve().is_file(), target
