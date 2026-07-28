from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.generate_openapi import build_openapi_document


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
HTML_HREF_RE = re.compile(r'href="([^"]+)"')
SKIP_PARTS = {
    ".git",
    ".next",
    ".terraform",
    ".venv",
    ".venv-sdktest",
    ".worktrees",
    "__pycache__",
    "archive",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "venv",
}
STALE_REFERENCES = (
    "ROADMAP.md",
    "WHITEPAPER.md",
    "MANIFESTO.md",
    "SUPPORT.md",
    "github.com/fortunexbt/mutx.dev",
    "app/app/[[...slug]]/page.tsx",
    "/v1/contacts",
    "there is no global `/v1` backend prefix",
    "docs/contracts/api/index.md",
)
API_DOC_EXPECTATIONS = {
    "docs/api/index.md": ["/v1/auth/*", "/v1/agents", "/v1/deployments", "/v1/leads/contacts"],
    "docs/api/authentication.md": [
        "/v1/auth/register",
        "/v1/auth/local-bootstrap",
        "/v1/auth/refresh",
    ],
    "docs/api/agents.md": [
        "/v1/agents/register",
        "/v1/agents/{agent_id}/resource-usage",
        "/v1/agents/{agent_id}/rollback",
    ],
    "docs/api/deployments.md": [
        "/v1/deployments/{deployment_id}/events",
        "/v1/deployments/{deployment_id}/versions",
        "/v1/deployments/{deployment_id}/rollback",
    ],
    "docs/api/api-keys.md": [
        "/v1/api-keys",
        "/v1/api-keys/{key_id}/rotate",
        "mutx_live_",
    ],
    "docs/api/webhooks.md": [
        "/v1/webhooks/",
        "/v1/ingest/agent-status",
        "X-Webhook-Signature",
    ],
    "docs/api/leads.md": ["/v1/leads", "/v1/leads/contacts"],
}
OPENAPI_METHODS = {"delete", "get", "head", "options", "patch", "post", "put"}


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def get_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        relative_parts = path.relative_to(ROOT).parts
        if any(part in SKIP_PARTS for part in relative_parts):
            continue
        files.append(path)
    return sorted(files)


def assert_exact_case(path: Path) -> None:
    relative = path.relative_to(ROOT)
    current = ROOT
    for part in relative.parts:
        names = {child.name for child in current.iterdir()}
        assert part in names, f"{relative} does not match on-disk casing"
        current = current / part


def extract_local_links(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    links = MARKDOWN_LINK_RE.findall(content) + HTML_HREF_RE.findall(content)
    local_links: list[str] = []
    for link in links:
        cleaned = link.strip().strip("<>").split("#", 1)[0].split("?", 1)[0]
        if not cleaned:
            continue
        if cleaned.startswith(("http://", "https://", "mailto:", "tel:", "#")):
            continue
        local_links.append(cleaned)
    return local_links


def _try_resolve(candidate: Path) -> Path | None:
    """Try multiple resolution strategies for a docs-style path."""
    if candidate.exists():
        return candidate
    # Many docs links omit the .md extension (web-style routing).
    with_md = Path(str(candidate) + ".md")
    if with_md.exists():
        return with_md
    # Directory-style links resolve to README.md or index.md inside.
    for index in (candidate / "README.md", candidate / "index.md"):
        if index.exists():
            return index
    # Next.js app routes: /ai-agent-approvals -> app/ai-agent-approvals/
    app_candidate = (
        ROOT / "app" / candidate.relative_to(ROOT) if candidate.is_relative_to(ROOT) else None
    )
    if app_candidate and app_candidate.exists():
        return app_candidate
    return None


def resolve_local_link(source: Path, target: str) -> Path:
    if target.startswith("/"):
        resolved = ROOT / target.lstrip("/")
        fallback = _try_resolve(resolved)
        if fallback is not None:
            return fallback
    else:
        resolved = (source.parent / target).resolve()
    return resolved


def test_canonical_quickstart_surfaces_share_assistant_first_commands() -> None:
    readme = read_text("README.md")
    quickstart = read_text("docs/deployment/quickstart.md")
    install_surface = read_text("components/site/InstallSurface.tsx")
    landing_content = read_text("components/site/marketing/RebrandHomePage.tsx")
    landing_content += read_text("components/site/PublicFooter.tsx")
    install_script = read_text("public/install.sh")

    for content in (quickstart, install_surface):
        assert "curl -fsSL https://mutx.dev/install.sh | bash" in content
        assert "OpenClaw" in content

    assert "brew tap mutx-dev/homebrew-tap && brew install mutx" in readme
    assert "mutx setup hosted" in readme

    for content in (readme, quickstart):
        assert "mutx setup hosted" in content
        assert "mutx setup local" in content
        assert "mutx doctor" in content

    assert "personal_assistant" in quickstart or "Personal Assistant" in quickstart, (
        "Expected the deployment quickstart to mention the personal assistant using either "
        "'personal_assistant' or 'Personal Assistant'."
    )

    assert "/download" in landing_content
    assert "/releases" in landing_content
    assert "Check Mac availability" in landing_content
    assert "Releases" in landing_content
    assert "run_setup_handoff" in install_script
    assert "MUTX_OPEN_TUI" in install_script
    assert "mutx login" not in install_script


def test_quickstart_redirect_points_to_canonical_doc() -> None:
    quickstart_redirect = read_text("docs/quickstart.md")

    assert "Deployment Quickstart" in quickstart_redirect
    assert "/docs/deployment/quickstart" in quickstart_redirect


def test_readme_uses_access_token_config_shape() -> None:
    readme = read_text("README.md")

    assert "brew tap mutx-dev/homebrew-tap && brew install mutx" in readme
    assert "mutx setup hosted" in readme
    assert "mutx doctor" in readme


def test_readme_keeps_demo_gif() -> None:
    readme = read_text("README.md")

    assert "![MUTX dashboard demo](public/demo.gif)" in readme


def test_readme_keeps_gitbook_card_targets() -> None:
    readme = read_text("README.md")

    assert "docs/manifesto.md" in readme
    assert "docs/whitepaper.md" in readme
    assert "docs/api/reference.md" in readme
    assert "docs/api/reference.md" in readme


def test_docs_hub_keeps_repo_backed_cards() -> None:
    docs_hub = read_text("docs/README.md")

    assert 'data-card-target data-type="content-ref"' in docs_hub
    assert 'data-card-cover data-type="files"' in docs_hub
    assert "../public/landing/wiring-bay.png" in docs_hub
    assert "docs/releases/v1.4.md" in read_text("SUMMARY.md")
    assert "docs/releases/v1.5-checklist.md" in read_text("SUMMARY.md")
    assert "./releases/v1.4.md" in read_text("docs/changelog-status.md")
    assert "./releases/v1.5-checklist.md" in read_text("docs/changelog-status.md")
    assert "releases/v1.4.md" in docs_hub
    assert "releases/v1.5-checklist.md" in docs_hub


def test_v13_release_notes_page_keeps_soft_launch_truth() -> None:
    release_notes = read_text("docs/releases/v1.3.md")

    assert "mutx.dev/releases" in release_notes
    assert "mutx.dev/download" in release_notes
    assert "/download/macos/arm64" in release_notes
    assert "app.mutx.dev/dashboard" in release_notes
    assert "app.mutx.dev/control/*" in release_notes
    assert "Railway" in release_notes
    assert "GitHub Releases" in release_notes


def test_public_agents_guidance_mentions_v1_contract() -> None:
    agents_md = read_text("AGENTS.md")

    assert "/v1/*" in agents_md
    assert "there is no global `/v1` backend prefix" not in agents_md


def test_markdown_links_resolve_with_exact_case() -> None:
    for markdown_file in get_markdown_files():
        for link in extract_local_links(markdown_file):
            resolved = resolve_local_link(markdown_file, link)
            assert resolved.exists(), (
                f"{markdown_file.relative_to(ROOT)} links to missing target {link}"
            )
            assert_exact_case(resolved)


def test_docs_do_not_contain_known_stale_references() -> None:
    extra_files = [ROOT / ".github/ISSUE_TEMPLATE/config.yml"]
    files_to_scan = get_markdown_files() + extra_files

    for path in files_to_scan:
        content = path.read_text(encoding="utf-8")
        for stale in STALE_REFERENCES:
            assert stale not in content, f"{path.relative_to(ROOT)} still contains {stale}"


def test_summary_points_only_to_existing_public_docs() -> None:
    summary = read_text("SUMMARY.md")

    assert ".github.md" not in summary
    assert "pull_request_template" not in summary

    summary_path = ROOT / "SUMMARY.md"
    for link in extract_local_links(summary_path):
        resolved = resolve_local_link(summary_path, link)
        assert resolved.is_file(), f"SUMMARY.md points to non-file target {link}"
        assert_exact_case(resolved)


def test_gitbook_config_keeps_legacy_contract_redirect() -> None:
    gitbook_config = read_text(".gitbook.yaml")

    assert "root: ./" in gitbook_config
    assert "readme: README.md" in gitbook_config
    assert "summary: SUMMARY.md" in gitbook_config
    assert '"docs/contracts/api": docs/api/reference.md' in gitbook_config


def test_public_api_docs_reference_current_routes() -> None:
    for relative_path, expected_strings in API_DOC_EXPECTATIONS.items():
        content = read_text(relative_path)
        for expected in expected_strings:
            assert expected in content, f"{relative_path} is missing {expected}"


def test_contract_stubs_point_back_to_docs_api() -> None:
    for path in sorted((ROOT / "docs/contracts/api").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        assert "../../api/" in content or "../../api" in content
        assert "canonical" in content.lower() or "compatibility" in content.lower()


def test_openapi_snapshot_matches_current_app_contract() -> None:
    from src.api.main import app

    snapshot = json.loads(read_text("docs/api/openapi.json"))
    generated = build_openapi_document()
    live_paths = app.openapi()["paths"]

    assert snapshot == generated
    assert set(generated["paths"]) == set(live_paths)
    assert "/v1/leads/contacts" in generated["paths"]
    assert "/v1/contacts" not in generated["paths"]


def test_claim_matrix_statistics_match_generated_contract() -> None:
    snapshot = json.loads(read_text("docs/api/openapi.json"))
    matrix = read_text("docs/claim-to-reality-gap-matrix.md")
    paths = snapshot["paths"]
    operations = [
        operation
        for path_item in paths.values()
        for method, operation in path_item.items()
        if method in OPENAPI_METHODS
    ]
    families = {
        f"/v1/{path.split('/')[2]}"
        for path in paths
        if path.startswith("/v1/") and len(path.split("/")) > 2
    }
    public = sum(operation.get("security") == [] for operation in operations)
    optional = sum(
        bool(operation.get("security")) and {} in operation["security"] for operation in operations
    )
    required = len(operations) - public - optional

    assert f"**Total top-level `/v1` families:** {len(families)}" in matrix
    assert f"**Total OpenAPI paths:** {len(paths)}" in matrix
    assert f"**Total endpoint-method pairs:** {len(operations)}" in matrix
    assert f"| Required-auth operations | {required} |" in matrix
    assert f"| Optional-auth operations | {optional} |" in matrix
    assert f"| Public operations | {public} |" in matrix


def test_public_auth_docs_match_current_identity_boundaries() -> None:
    auth = read_text("docs/api/authentication.md")
    api_keys = read_text("docs/api/api-keys.md")
    rbac = read_text("docs/architecture/rbac.md")

    assert "registration still does not issue tokens" in auth
    assert '"state": "SERVER_ISSUED_STATE"' in auth
    assert "do not directly accept an arbitrary provider bearer token" in auth
    assert "protected user-principal routes" in api_keys
    assert "`mutx_agent_...` credentials" in api_keys
    for role in ("ADMIN", "AUDIT_ADMIN", "DEVELOPER", "VIEWER"):
        assert f"`{role}`" in rbac
    assert "Provider role/group claims" in rbac
    assert "do not" in rbac


def test_governance_and_lifecycle_docs_use_current_route_shapes() -> None:
    reference = read_text("docs/api/reference.md")
    deployments = read_text("docs/api/deployments.md")
    webhooks = read_text("docs/api/webhooks.md")
    governance = read_text("docs/governance.md")
    whitepaper = read_text("docs/whitepaper.md")

    assert "/v1/runtime/governance/supervised" in reference
    assert "/v1/governance/supervision" not in reference + whitepaper
    assert "/v1/runtime/governance/metrics" in governance
    assert "/v1/policies/stream" not in whitepaper
    assert "running, ready, or failed deployment" in deployments
    assert "Restart stopped, failed, or killed" not in deployments
    assert "30 seconds, 5 minutes, 30 minutes, and 2 hours" in webhooks


# ---------------------------------------------------------------------------
# Frontend code quality guards — prevent lint-regression of underscore-imports
# ---------------------------------------------------------------------------


def test_no_invalid_underscore_imports_from_external_modules() -> None:
    """
    Fail if any .tsx/.ts file imports a symbol with a leading underscore
    directly from an external module without using 'as' alias syntax.

    Valid:   import { useEffect }          from "react"
    Valid:   import { Play as _Play }        from "lucide-react"  (explicit alias)
    Invalid: import { _useEffect }          from "react"           (invalid)
    Invalid: import { _Play }               from "lucide-react"   (invalid)
    """
    import re
    from pathlib import Path

    # Pattern: import { or import * as ... from "external"
    # that has a name starting with _ without being aliased
    # We look for lines like: import { _Name ... } from "..."
    # where _Name is NOT preceded by "Name as"

    invalid_pattern = re.compile(r'^import \{\s*([^}]+)\}\s*from\s+"([^"]+)"')
    alias_pattern = re.compile(r"\b(\w+)\s+as\s+_\w+\b")

    src_files = list(Path("components").rglob("*.tsx")) + list(Path("components").rglob("*.ts"))
    src_files += list(Path("app").rglob("*.tsx")) + list(Path("app").rglob("*.ts"))

    violations = []
    for f in src_files:
        if f.is_file() and not any(p in str(f) for p in ["node_modules", ".next"]):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                m = invalid_pattern.match(line.strip())
                if not m:
                    continue
                imports_str, module = m.group(1), m.group(2)
                # Skip type-only imports
                if "type" in imports_str or module.startswith("@types"):
                    continue
                # Find all underscore-prefixed names in the import list
                names = [n.strip().rstrip(",") for n in imports_str.split()]
                for name in names:
                    if name.startswith("_") and len(name) > 1:
                        # Check if this is an alias: "Foo as _Foo"
                        # In that case the raw name doesn't start with _
                        if f"{name.lstrip('_')} as {name}" not in imports_str:
                            # Also skip if it's explicitly aliased the other way: "Foo as _Bar"
                            if not alias_pattern.search(imports_str):
                                violations.append(
                                    f"{f}:{line_no}: '{name}' imported from '{module}' — "
                                    "invalid underscore-prefix without alias"
                                )

    if violations:
        lines = "\n".join(violations[:10])
        raise AssertionError(f"Invalid underscore imports found:\n{lines}")
