"""Deterministic security checks for MCP server and tool definitions.

The scanner treats all server-provided metadata as untrusted.  It never starts
a server, resolves a URL, or executes a command.  Findings are intentionally
limited to high-signal static evidence so that callers can make a registration
decision without delegating that decision to an LLM.

The accepted tool shape follows the stable MCP 2025-11-25 specification:
https://modelcontextprotocol.io/specification/2025-11-25/server/tools
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import ipaddress
import json
import re
import unicodedata
from urllib.parse import parse_qsl, urlsplit


MAX_DEFINITION_BYTES = 512 * 1024
MAX_SCHEMA_DEPTH = 12
MAX_SCHEMA_NODES = 2_000
MAX_EVIDENCE_LENGTH = 180


class MCPFindingSeverity(str, Enum):
    """Severity assigned to an MCP definition finding."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MCPRegistrationDecision(str, Enum):
    """Pre-registration disposition for a scanned definition."""

    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


@dataclass(frozen=True)
class MCPFinding:
    """A single explainable scanner finding."""

    code: str
    severity: MCPFindingSeverity
    category: str
    path: str
    title: str
    explanation: str
    evidence: str
    recommendation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "category": self.category,
            "path": self.path,
            "title": self.title,
            "explanation": self.explanation,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class MCPScanResult:
    """Complete scan output and reusable pre-registration decision."""

    findings: tuple[MCPFinding, ...]
    decision: MCPRegistrationDecision
    scanned_tools: int
    scanner_version: str = "1.0"
    protocol_revision: str = "2025-11-25"

    @property
    def registration_allowed(self) -> bool:
        """Only clean or low-severity definitions can register automatically."""
        return self.decision is MCPRegistrationDecision.ALLOW

    @property
    def highest_severity(self) -> MCPFindingSeverity | None:
        if not self.findings:
            return None
        return max(self.findings, key=lambda finding: _SEVERITY_ORDER[finding.severity]).severity

    def to_dict(self) -> dict[str, object]:
        return {
            "scanner_version": self.scanner_version,
            "protocol_revision": self.protocol_revision,
            "decision": self.decision.value,
            "registration_allowed": self.registration_allowed,
            "highest_severity": (
                self.highest_severity.value if self.highest_severity is not None else None
            ),
            "scanned_tools": self.scanned_tools,
            "finding_count": len(self.findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


_SEVERITY_ORDER = {
    MCPFindingSeverity.LOW: 1,
    MCPFindingSeverity.MEDIUM: 2,
    MCPFindingSeverity.HIGH: 3,
    MCPFindingSeverity.CRITICAL: 4,
}

_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,126}[A-Za-z0-9])?$")
_URL_PATTERN = re.compile(r"https?://[^\s<>\]\[\)\(\"']+", re.IGNORECASE)
_PROMPT_INJECTION_PATTERNS = (
    re.compile(
        r"\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|system|developer)[^.!?\n]{0,50}\binstructions?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:do\s+not|never)\s+(?:tell|inform|show|reveal|mention)\s+(?:the\s+)?(?:user|operator|human)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:bypass|override|disable|evade)\b[^.!?\n]{0,50}\b(?:policy|safety|approval|permission|guardrail)s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:exfiltrate|steal|leak)\b[^.!?\n]{0,60}\b(?:secret|credential|token|key|password|data)s?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:system|developer)\s+(?:message|instruction)s?\s*:", re.IGNORECASE),
)
_HTML_COMMENT_PATTERN = re.compile(r"<!--(?P<content>.*?)-->", re.DOTALL)
_DOWNLOAD_AND_EXECUTE_PATTERN = re.compile(
    r"\b(?:curl|wget)\b[^\n|;&]{0,300}(?:\||&&|;)\s*(?:sudo\s+)?(?:ba|z|fi|da)?sh\b",
    re.IGNORECASE,
)
_DESTRUCTIVE_COMMAND_PATTERN = re.compile(
    r"(?:\brm\s+-[^\n]{0,10}r[^\n]{0,10}f\s+[/~*]|\b(?:mkfs|dd)\b|\bchmod\s+-R\s+777\b)",
    re.IGNORECASE,
)
_EXFILTRATION_COMMAND_PATTERN = re.compile(
    r"(?:curl|wget)[^\n]{0,300}(?:\.ssh|id_rsa|/etc/passwd|\$\{?(?:TOKEN|SECRET|API_KEY|PASSWORD))",
    re.IGNORECASE,
)
_SHELL_EVAL_PATTERN = re.compile(r"\b(?:ba|z|fi|da)?sh\b\s+-c\b", re.IGNORECASE)
_DESTRUCTIVE_WORDS = re.compile(
    r"\b(?:delete|destroy|drop|erase|overwrite|purge|remove|reset|revoke|terminate|wipe)\b",
    re.IGNORECASE,
)
_MUTATING_WORDS = re.compile(
    r"\b(?:create|deploy|execute|install|modify|publish|send|update|upload|write)\b",
    re.IGNORECASE,
)
_COMMAND_TOOL_WORDS = re.compile(
    r"(?:^|[_.-])(?:bash|cmd|command|exec|execute|powershell|shell|terminal)(?:$|[_.-])",
    re.IGNORECASE,
)
_FILESYSTEM_TOOL_WORDS = re.compile(
    r"(?:^|[_.-])(?:file|filesystem|fs|read|write|delete|remove)(?:$|[_.-])",
    re.IGNORECASE,
)
_NETWORK_TOOL_WORDS = re.compile(
    r"(?:^|[_.-])(?:browse|fetch|http|request|scrape|url|web)(?:$|[_.-])",
    re.IGNORECASE,
)
_SHORTENER_HOSTS = frozenset(
    {"bit.ly", "buff.ly", "is.gd", "ow.ly", "t.co", "tinyurl.com", "urlzs.com"}
)
_CLOUD_METADATA_HOSTS = frozenset({"169.254.169.254", "metadata.google.internal"})
_HIGH_RISK_PERMISSIONS = frozenset(
    {
        "admin",
        "all permissions",
        "privileged",
        "root",
        "sudo",
        "unrestricted",
        "*",
    }
)
_HIGH_RISK_PERMISSION_PHRASES = ("docker socket", "host filesystem", "host network")
_BROAD_PERMISSION_NAMES = frozenset(
    {
        "credential",
        "credentials",
        "environment",
        "filesystem",
        "network",
        "secret",
        "secrets",
        "ssh",
    }
)
_CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "Α": "a",
        "А": "a",
        "е": "e",
        "Ε": "e",
        "і": "i",
        "Ι": "i",
        "ο": "o",
        "О": "o",
        "о": "o",
        "ρ": "p",
        "Р": "p",
        "с": "c",
        "С": "c",
        "х": "x",
        "Х": "x",
        "у": "y",
        "Υ": "y",
        "０": "0",
        "１": "1",
        "３": "3",
        "５": "5",
    }
)


def _redact_evidence(value: object) -> str:
    """Return a compact excerpt without echoing likely secret values."""
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    text = re.sub(
        r"(?i)\b(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([?&][\w.-]*(?:key|password|secret|token)=)[^&#\s]+",
        r"\1<redacted>",
        text,
    )
    if len(text) > MAX_EVIDENCE_LENGTH:
        return f"{text[: MAX_EVIDENCE_LENGTH - 1]}…"
    return text


def _contains_hidden_control_characters(value: str) -> list[str]:
    found: list[str] = []
    for character in value:
        category = unicodedata.category(character)
        if category == "Cf" or (category == "Cc" and character not in "\t\r\n"):
            found.append(f"U+{ord(character):04X}")
    return sorted(set(found))


def _name_skeleton(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(_CONFUSABLES).casefold()
    return re.sub(r"[_.-]", "", normalized)


def _name_collision_skeleton(value: str) -> str:
    return unicodedata.normalize("NFKC", value).translate(_CONFUSABLES).casefold()


def _unpinned_package_from_command(command: str) -> str | None:
    tokens = command.strip().split()
    if not tokens or tokens[0].casefold() not in {"npx", "uvx"}:
        return None
    package = next((token for token in tokens[1:] if not token.startswith("-")), None)
    if not package:
        return None
    if package.startswith("@"):
        _, separator, version = package.rpartition("@")
        pinned = bool(separator and re.fullmatch(r"v?\d+(?:\.\d+){0,3}(?:[-+][\w.-]+)?", version))
    else:
        _, separator, version = package.rpartition("@")
        pinned = bool(separator and re.fullmatch(r"v?\d+(?:\.\d+){0,3}(?:[-+][\w.-]+)?", version))
    return None if pinned else package


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    left_index = right_index = differences = 0
    while left_index < len(left) and right_index < len(right):
        if left[left_index] == right[right_index]:
            left_index += 1
            right_index += 1
            continue
        differences += 1
        if differences > 1:
            return False
        right_index += 1
    return True


def _resolve_local_schema_ref(
    definition: Mapping[str, object], root_schema: Mapping[str, object]
) -> Mapping[str, object]:
    """Resolve bounded document-local JSON Schema references without I/O."""
    current = definition
    seen: set[str] = set()
    for _ in range(MAX_SCHEMA_DEPTH):
        reference = current.get("$ref")
        if not isinstance(reference, str) or not reference.startswith("#/"):
            return current
        if reference in seen:
            return definition
        seen.add(reference)

        target: object = root_schema
        for raw_token in reference[2:].split("/"):
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, Mapping) or token not in target:
                return definition
            target = target[token]
        if not isinstance(target, Mapping):
            return definition

        siblings = {key: value for key, value in current.items() if key != "$ref"}
        current = {**target, **siblings}
    return definition


def _schema_properties(
    schema: Mapping[str, object],
    names: set[str],
    *,
    root_schema: Mapping[str, object] | None = None,
    path: str = "/inputSchema",
    depth: int = 0,
    active_refs: frozenset[str] = frozenset(),
) -> Iterable[tuple[str, Mapping[str, object], str]]:
    """Yield matching properties nested in objects, arrays, and compositions."""
    if depth > MAX_SCHEMA_DEPTH:
        return
    if root_schema is None:
        root_schema = schema

    reference = schema.get("$ref")
    if isinstance(reference, str) and reference in active_refs:
        return
    next_refs = active_refs | ({reference} if isinstance(reference, str) else set())
    resolved = _resolve_local_schema_ref(schema, root_schema)

    properties = resolved.get("properties")
    if isinstance(properties, Mapping):
        for raw_name, raw_definition in properties.items():
            if not isinstance(raw_definition, Mapping):
                continue
            name = str(raw_name)
            escaped_name = name.replace("~", "~0").replace("/", "~1")
            property_path = f"{path}/properties/{escaped_name}"
            resolved_definition = _resolve_local_schema_ref(raw_definition, root_schema)
            if name.casefold() in names:
                yield name, resolved_definition, property_path
            yield from _schema_properties(
                raw_definition,
                names,
                root_schema=root_schema,
                path=property_path,
                depth=depth + 1,
                active_refs=frozenset(next_refs),
            )

    items = resolved.get("items")
    if isinstance(items, Mapping):
        yield from _schema_properties(
            items,
            names,
            root_schema=root_schema,
            path=f"{path}/items",
            depth=depth + 1,
            active_refs=frozenset(next_refs),
        )

    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = resolved.get(keyword)
        if isinstance(branches, Sequence) and not isinstance(branches, (str, bytes, bytearray)):
            for index, branch in enumerate(branches):
                if isinstance(branch, Mapping):
                    yield from _schema_properties(
                        branch,
                        names,
                        root_schema=root_schema,
                        path=f"{path}/{keyword}/{index}",
                        depth=depth + 1,
                        active_refs=frozenset(next_refs),
                    )


def _is_unrestricted_string(definition: Mapping[str, object]) -> bool:
    declared_type = definition.get("type")
    if declared_type not in (None, "string"):
        return False
    # Shape validation (format, length, regex) does not provide a destination or
    # operation allowlist. Only explicit finite values can prove that this field
    # does not accept an arbitrary command/path/URL.
    return not any(key in definition for key in {"const", "enum"})


@dataclass
class _TraversalState:
    """Mutable limits shared by one bounded metadata traversal."""

    nodes: int = 0
    truncated_path: str | None = None
    truncated_reason: str | None = None

    def truncate(self, path: str, reason: str) -> None:
        if self.truncated_path is None:
            self.truncated_path = path
            self.truncated_reason = reason


def _iter_schema_strings(
    value: object,
    *,
    path: str,
    depth: int = 0,
    state: _TraversalState | None = None,
) -> Iterable[tuple[str, str]]:
    """Yield schema strings with hard bounds against adversarial nesting."""
    if state is None:
        state = _TraversalState()
    if depth > MAX_SCHEMA_DEPTH:
        state.truncate(path, f"metadata depth exceeds {MAX_SCHEMA_DEPTH}")
        return
    if state.nodes >= MAX_SCHEMA_NODES:
        state.truncate(path, f"metadata traversal exceeds {MAX_SCHEMA_NODES} nodes")
        return
    state.nodes += 1
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, Mapping):
        for key, nested in value.items():
            if state.nodes >= MAX_SCHEMA_NODES:
                state.truncate(path, f"metadata traversal exceeds {MAX_SCHEMA_NODES} nodes")
                return
            key_path = f"{path}/{str(key).replace('~', '~0').replace('/', '~1')}"
            yield key_path, str(key)
            yield from _iter_schema_strings(
                nested,
                path=key_path,
                depth=depth + 1,
                state=state,
            )
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            yield from _iter_schema_strings(
                nested,
                path=f"{path}/{index}",
                depth=depth + 1,
                state=state,
            )


class MCPDefinitionScanner:
    """Static, side-effect-free MCP server definition scanner."""

    def __init__(self, trusted_tool_names: Iterable[str] = ()) -> None:
        self._trusted_names = tuple(
            (name, _name_skeleton(name)) for name in trusted_tool_names if name.strip()
        )
        self._findings: list[MCPFinding] = []
        self._finding_keys: set[tuple[str, str]] = set()

    def scan(self, definition: Mapping[str, object]) -> MCPScanResult:
        """Scan one definition and return a pre-registration disposition."""
        self._findings = []
        self._finding_keys = set()

        encoded_size = len(
            json.dumps(definition, ensure_ascii=False, separators=(",", ":"), default=str).encode(
                "utf-8"
            )
        )
        if encoded_size > MAX_DEFINITION_BYTES:
            self._add(
                code="definition_too_large",
                severity=MCPFindingSeverity.HIGH,
                category="resource_limits",
                path="/server",
                title="Definition exceeds the scanner size limit",
                explanation=(
                    f"The serialized definition is {encoded_size} bytes; the limit is "
                    f"{MAX_DEFINITION_BYTES} bytes. Oversized metadata can exhaust clients."
                ),
                evidence=f"{encoded_size} bytes",
                recommendation="Reduce the tool set or schema metadata before registration.",
            )

        self._scan_server_metadata(definition)
        tools = definition.get("tools", [])
        tool_list = tools if isinstance(tools, Sequence) and not isinstance(tools, str) else []
        self._scan_tools(tool_list)

        findings = tuple(
            sorted(
                self._findings,
                key=lambda item: (-_SEVERITY_ORDER[item.severity], item.path, item.code),
            )
        )
        highest = max(
            (_SEVERITY_ORDER[finding.severity] for finding in findings),
            default=0,
        )
        if highest >= _SEVERITY_ORDER[MCPFindingSeverity.HIGH]:
            decision = MCPRegistrationDecision.DENY
        elif highest >= _SEVERITY_ORDER[MCPFindingSeverity.MEDIUM]:
            decision = MCPRegistrationDecision.REVIEW
        else:
            decision = MCPRegistrationDecision.ALLOW

        return MCPScanResult(
            findings=findings,
            decision=decision,
            scanned_tools=len(tool_list),
        )

    def _add(
        self,
        *,
        code: str,
        severity: MCPFindingSeverity,
        category: str,
        path: str,
        title: str,
        explanation: str,
        evidence: object,
        recommendation: str,
    ) -> None:
        key = (code, path)
        if key in self._finding_keys:
            return
        self._finding_keys.add(key)
        self._findings.append(
            MCPFinding(
                code=code,
                severity=severity,
                category=category,
                path=path,
                title=title,
                explanation=explanation,
                evidence=_redact_evidence(evidence),
                recommendation=recommendation,
            )
        )

    def _scan_server_metadata(self, definition: Mapping[str, object]) -> None:
        for field in ("name", "description", "command"):
            value = definition.get(field)
            if isinstance(value, str):
                self._scan_text(value, path=f"/server/{field}", name_context=field == "name")
                if field in {"description", "command"}:
                    self._scan_urls_in_text(value, f"/server/{field}")
                if field == "description":
                    self._scan_command(value, f"/server/{field}", description_context=True)

        command_parts = [definition.get("command", "")]
        args = definition.get("args", [])
        if isinstance(args, Sequence) and not isinstance(args, str):
            command_parts.extend(str(arg) for arg in args)
            for index, arg in enumerate(args):
                if isinstance(arg, str):
                    self._scan_text(arg, path=f"/server/args/{index}")
                    self._scan_urls_in_text(arg, f"/server/args/{index}")
        command = " ".join(str(part) for part in command_parts if part).strip()
        if command:
            self._scan_command(command, "/server/command")

        url = definition.get("url")
        if isinstance(url, str) and url:
            self._scan_url(url, "/server/url", configured_transport=True)

        permissions = definition.get(
            "requestedPermissions", definition.get("requested_permissions", [])
        )
        if isinstance(permissions, Sequence) and not isinstance(permissions, str):
            for index, permission in enumerate(permissions):
                if isinstance(permission, str):
                    self._scan_permission(permission, f"/server/requestedPermissions/{index}")

    def _scan_tools(self, tools: Sequence[object]) -> None:
        seen_names: dict[str, int] = {}
        seen_skeletons: dict[str, tuple[str, int]] = {}
        known_fields = {
            "annotations",
            "description",
            "execution",
            "icons",
            "inputSchema",
            "input_schema",
            "name",
            "outputSchema",
            "output_schema",
            "title",
        }
        for index, raw_tool in enumerate(tools):
            if not isinstance(raw_tool, Mapping):
                continue
            path = f"/server/tools/{index}"
            name = raw_tool.get("name", "")
            if not isinstance(name, str):
                continue

            self._scan_tool_name(name, path, seen_names, seen_skeletons)
            description = raw_tool.get("description")
            title = raw_tool.get("title")
            if isinstance(title, str):
                self._scan_text(title, path=f"{path}/title")
                self._scan_urls_in_text(title, f"{path}/title")
            if isinstance(description, str):
                self._scan_text(description, path=f"{path}/description")
                self._scan_urls_in_text(description, f"{path}/description")
                self._scan_command(description, f"{path}/description", description_context=True)

            schema = raw_tool.get("inputSchema", raw_tool.get("input_schema", {}))
            if isinstance(schema, Mapping):
                self._scan_schema(name, description or "", schema, path)
                self._scan_untrusted_tree(schema, path=f"{path}/inputSchema")

            output_schema = raw_tool.get("outputSchema", raw_tool.get("output_schema"))
            if isinstance(output_schema, Mapping):
                self._scan_untrusted_tree(output_schema, path=f"{path}/outputSchema")

            annotations = raw_tool.get("annotations")
            if isinstance(annotations, Mapping):
                self._scan_untrusted_tree(annotations, path=f"{path}/annotations")
                self._scan_annotations(name, description or "", schema, annotations, path)

            execution = raw_tool.get("execution")
            if isinstance(execution, Mapping):
                self._scan_untrusted_tree(execution, path=f"{path}/execution")

            icons = raw_tool.get("icons", [])
            if isinstance(icons, Sequence) and not isinstance(icons, str):
                for icon_index, icon in enumerate(icons):
                    if isinstance(icon, Mapping) and isinstance(icon.get("src"), str):
                        self._scan_url(
                            icon["src"],
                            f"{path}/icons/{icon_index}/src",
                            configured_transport=False,
                            allow_data_image=True,
                        )

            extensions = {
                field: extension_value
                for field, extension_value in raw_tool.items()
                if field not in known_fields
            }
            if extensions:
                self._scan_untrusted_tree(extensions, path=path)

    def _scan_untrusted_tree(self, value: object, *, path: str) -> None:
        """Scan every string in a bounded metadata tree and fail closed on truncation."""
        state = _TraversalState()
        for nested_path, text in _iter_schema_strings(value, path=path, state=state):
            self._scan_text(text, path=nested_path)
            self._scan_urls_in_text(text, nested_path)
            self._scan_command(text, nested_path, description_context=True)

        if state.truncated_path is not None:
            self._add(
                code="scan_traversal_limit_exceeded",
                severity=MCPFindingSeverity.HIGH,
                category="resource_limits",
                path=state.truncated_path,
                title="Metadata could not be scanned completely",
                explanation=(
                    "The definition exceeded a bounded metadata traversal limit. Unscanned "
                    "server-controlled content cannot be considered safe for automatic registration."
                ),
                evidence=state.truncated_reason or "metadata traversal was truncated",
                recommendation=(
                    "Reject the definition or reduce its metadata depth and size, then scan it again."
                ),
            )

    def _scan_tool_name(
        self,
        name: str,
        path: str,
        seen_names: dict[str, int],
        seen_skeletons: dict[str, tuple[str, int]],
    ) -> None:
        name_path = f"{path}/name"
        self._scan_text(name, path=name_path, name_context=True)
        if not _TOOL_NAME_PATTERN.fullmatch(name):
            self._add(
                code="deceptive_or_nonstandard_name",
                severity=MCPFindingSeverity.MEDIUM,
                category="name_integrity",
                path=name_path,
                title="Tool name is nonstandard or visually deceptive",
                explanation=(
                    "Stable MCP tool names use 1-128 ASCII letters, digits, underscores, "
                    "hyphens, or dots and begin and end with an alphanumeric character. Other "
                    "characters reduce interoperability and can hide lookalike names."
                ),
                evidence=name,
                recommendation="Rename the tool using the stable MCP tool-name character set.",
            )

        if name in seen_names:
            self._add(
                code="duplicate_tool_name",
                severity=MCPFindingSeverity.HIGH,
                category="name_integrity",
                path=name_path,
                title="Duplicate tool name",
                explanation=(
                    f"This name duplicates tool index {seen_names[name]}; dispatch becomes "
                    "ambiguous and a later definition could shadow the first."
                ),
                evidence=name,
                recommendation="Give every tool a unique name within the server.",
            )
        else:
            seen_names[name] = int(path.rsplit("/", 1)[-1])

        skeleton = _name_skeleton(name)
        collision_skeleton = _name_collision_skeleton(name)
        collision = seen_skeletons.get(collision_skeleton)
        if collision and collision[0] != name:
            self._add(
                code="confusable_tool_name_collision",
                severity=MCPFindingSeverity.HIGH,
                category="name_integrity",
                path=name_path,
                title="Tool name collides after confusable normalization",
                explanation=(
                    f"The name is visually confusable with tool '{collision[0]}' at index "
                    f"{collision[1]}. This can disguise tool substitution."
                ),
                evidence=name,
                recommendation="Use visibly distinct ASCII names and remove the collision.",
            )
        else:
            seen_skeletons[collision_skeleton] = (name, int(path.rsplit("/", 1)[-1]))

        if len(skeleton) >= 4:
            for trusted_name, trusted_skeleton in self._trusted_names:
                if skeleton != trusted_skeleton and _edit_distance_at_most_one(
                    skeleton, trusted_skeleton
                ):
                    self._add(
                        code="trusted_name_typosquat",
                        severity=MCPFindingSeverity.MEDIUM,
                        category="name_integrity",
                        path=name_path,
                        title="Tool name resembles a trusted tool",
                        explanation=(
                            f"The normalized name is one edit from trusted tool "
                            f"'{trusted_name}'. This may be a typo or an attempted substitution."
                        ),
                        evidence=name,
                        recommendation="Verify the publisher and rename the tool if intentional.",
                    )

    def _scan_text(self, value: str, *, path: str, name_context: bool = False) -> None:
        controls = _contains_hidden_control_characters(value)
        if controls:
            self._add(
                code="hidden_control_characters",
                severity=(MCPFindingSeverity.HIGH if name_context else MCPFindingSeverity.MEDIUM),
                category="hidden_instructions",
                path=path,
                title="Hidden Unicode control characters",
                explanation=(
                    "Invisible formatting or control characters can conceal instructions or make "
                    "metadata render differently from the text a model receives."
                ),
                evidence=", ".join(controls),
                recommendation="Remove control characters and review the normalized plain text.",
            )

        for pattern in _PROMPT_INJECTION_PATTERNS:
            match = pattern.search(value)
            if match:
                self._add(
                    code="prompt_injection_instruction",
                    severity=MCPFindingSeverity.HIGH,
                    category="tool_poisoning",
                    path=path,
                    title="Instruction attempts to override operator control",
                    explanation=(
                        "Tool metadata contains a high-signal instruction to override policy, hide "
                        "behavior, or mishandle secrets. MCP metadata is untrusted model input."
                    ),
                    evidence=match.group(0),
                    recommendation="Reject the definition and require a factual tool description.",
                )
                break

        for comment in _HTML_COMMENT_PATTERN.finditer(value):
            content = comment.group("content")
            if any(pattern.search(content) for pattern in _PROMPT_INJECTION_PATTERNS):
                self._add(
                    code="hidden_prompt_instruction",
                    severity=MCPFindingSeverity.HIGH,
                    category="hidden_instructions",
                    path=path,
                    title="Prompt instruction hidden in an HTML comment",
                    explanation=(
                        "The rendered description can hide this instruction from an operator while "
                        "still exposing it to downstream processors or models."
                    ),
                    evidence=content,
                    recommendation="Reject the definition and remove hidden instructions.",
                )

    def _scan_command(self, command: str, path: str, *, description_context: bool = False) -> None:
        checks = (
            (
                _DOWNLOAD_AND_EXECUTE_PATTERN,
                "download_and_execute_command",
                "Downloads remote content into a shell",
                "Download the artifact separately, pin its version, and verify its digest before execution.",
            ),
            (
                _DESTRUCTIVE_COMMAND_PATTERN,
                "destructive_startup_command",
                "Contains a destructive host command",
                "Remove destructive operations from startup and run the server in a least-privilege sandbox.",
            ),
            (
                _EXFILTRATION_COMMAND_PATTERN,
                "credential_exfiltration_command",
                "Command appears to transmit sensitive host data",
                "Reject the definition and investigate its source.",
            ),
            (
                _SHELL_EVAL_PATTERN,
                "shell_eval_command",
                "Invokes a command-string shell",
                "Use a fixed executable and argument vector instead of a shell command string.",
            ),
        )
        for pattern, code, title, recommendation in checks:
            match = pattern.search(command)
            if match:
                self._add(
                    code=code,
                    severity=MCPFindingSeverity.HIGH,
                    category="suspicious_command",
                    path=path,
                    title=title,
                    explanation=(
                        "Local MCP servers run with the client's privileges; this static command "
                        "shape creates a direct host-compromise risk."
                    ),
                    evidence=match.group(0),
                    recommendation=recommendation,
                )

        if not description_context:
            unpinned_package = _unpinned_package_from_command(command)
            if unpinned_package:
                self._add(
                    code="unpinned_package_runner",
                    severity=MCPFindingSeverity.LOW,
                    category="supply_chain",
                    path=path,
                    title="Package runner is not version-pinned",
                    explanation=(
                        "Installing a mutable package name at startup can silently execute a newly "
                        "published release. This is a supply-chain warning, not proof of malice."
                    ),
                    evidence=unpinned_package,
                    recommendation="Pin an exact package version and verify the publisher.",
                )

    def _scan_urls_in_text(self, value: str, path: str) -> None:
        for match in _URL_PATTERN.finditer(value):
            self._scan_url(match.group(0).rstrip(".,;:"), path, configured_transport=False)

    def _scan_url(
        self,
        url: str,
        path: str,
        *,
        configured_transport: bool,
        allow_data_image: bool = False,
    ) -> None:
        if allow_data_image and url.casefold().startswith("data:"):
            media_type = url[5:].split(",", 1)[0].split(";", 1)[0].casefold()
            if media_type == "image/svg+xml":
                self._add(
                    code="active_svg_icon",
                    severity=MCPFindingSeverity.MEDIUM,
                    category="suspicious_url",
                    path=path,
                    title="Inline SVG icon requires active-content controls",
                    explanation=(
                        "The MCP specification warns that SVG icons can contain executable "
                        "JavaScript. Static scanning does not decode or sanitize the payload."
                    ),
                    evidence=media_type,
                    recommendation="Prefer PNG/WebP or sanitize and render SVG in an isolated context.",
                )
            elif media_type not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
                self._add(
                    code="unsupported_inline_icon_type",
                    severity=MCPFindingSeverity.MEDIUM,
                    category="suspicious_url",
                    path=path,
                    title="Inline icon uses an unexpected media type",
                    explanation="Only standard raster image data URIs are accepted automatically.",
                    evidence=media_type or "<missing>",
                    recommendation="Use a PNG, JPEG, or WebP data URI.",
                )
            return
        try:
            parsed = urlsplit(url)
        except ValueError:
            parsed = None
        if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.hostname:
            self._add(
                code="invalid_or_unsupported_url",
                severity=MCPFindingSeverity.MEDIUM,
                category="suspicious_url",
                path=path,
                title="URL is invalid or uses an unsupported scheme",
                explanation="Remote MCP endpoints should use a well-formed HTTP or HTTPS URL.",
                evidence=url,
                recommendation="Use an explicit HTTPS endpoint or a local stdio transport.",
            )
            return

        hostname = parsed.hostname.casefold()
        if parsed.username or parsed.password:
            self._add(
                code="url_embeds_credentials",
                severity=MCPFindingSeverity.HIGH,
                category="suspicious_url",
                path=path,
                title="URL embeds credentials",
                explanation="Credentials in URLs leak through logs, histories, and error reports.",
                evidence=f"{parsed.scheme}://<credentials>@{hostname}{parsed.path}",
                recommendation="Remove credentials and use the MCP authorization flow.",
            )

        sensitive_query_keys = sorted(
            {
                key
                for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
                if re.search(
                    r"(?:api[_-]?key|authorization|password|secret|token)", key, re.IGNORECASE
                )
            }
        )
        if sensitive_query_keys:
            self._add(
                code="url_query_credentials",
                severity=MCPFindingSeverity.HIGH,
                category="suspicious_url",
                path=path,
                title="URL places credentials in its query string",
                explanation="URL query values leak through logs, histories, referrers, and caches.",
                evidence=", ".join(sensitive_query_keys),
                recommendation="Remove credentials and use authorization headers or MCP OAuth.",
            )

        if hostname in _CLOUD_METADATA_HOSTS:
            self._add(
                code="cloud_metadata_url",
                severity=MCPFindingSeverity.HIGH,
                category="suspicious_url",
                path=path,
                title="URL targets a cloud metadata service",
                explanation="Metadata services can expose workload credentials and identity tokens.",
                evidence=url,
                recommendation="Reject this endpoint and block metadata ranges with egress policy.",
            )
        elif any(label.startswith("xn--") for label in hostname.split(".")):
            self._add(
                code="punycode_hostname",
                severity=MCPFindingSeverity.MEDIUM,
                category="suspicious_url",
                path=path,
                title="Hostname uses Punycode",
                explanation=(
                    "Internationalized hostnames can be legitimate but also support visual-domain "
                    "impersonation; publisher verification is required."
                ),
                evidence=hostname,
                recommendation="Verify the decoded hostname and publisher before registration.",
            )
        elif hostname in _SHORTENER_HOSTS:
            self._add(
                code="shortened_url",
                severity=MCPFindingSeverity.LOW,
                category="suspicious_url",
                path=path,
                title="URL hides its final destination",
                explanation="A URL shortener prevents static verification of the destination.",
                evidence=hostname,
                recommendation="Replace the shortened URL with its reviewed final destination.",
            )

        if configured_transport and self._is_nonpublic_address(hostname):
            self._add(
                code="private_network_endpoint",
                severity=MCPFindingSeverity.MEDIUM,
                category="suspicious_url",
                path=path,
                title="Remote MCP endpoint targets a non-public address",
                explanation=(
                    "Private, link-local, or reserved destinations can cross a client network trust "
                    "boundary. They can be legitimate, but require an explicit operator decision."
                ),
                evidence=hostname,
                recommendation="Allowlist the exact endpoint and isolate it from sensitive services.",
            )

        if configured_transport and parsed.scheme == "http" and not self._is_loopback(hostname):
            self._add(
                code="unencrypted_remote_transport",
                severity=MCPFindingSeverity.MEDIUM,
                category="transport_security",
                path=path,
                title="Remote MCP transport is unencrypted",
                explanation="A non-loopback HTTP endpoint exposes MCP traffic to interception.",
                evidence=url,
                recommendation="Use HTTPS with certificate validation for remote transports.",
            )

    @staticmethod
    def _is_loopback(hostname: str) -> bool:
        if hostname in {"localhost", "localhost.localdomain"}:
            return True
        try:
            return ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False

    @classmethod
    def _is_nonpublic_address(cls, hostname: str) -> bool:
        if cls._is_loopback(hostname) or hostname in _CLOUD_METADATA_HOSTS:
            return False
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return False
        return not address.is_global

    def _scan_permission(self, permission: str, path: str) -> None:
        normalized = unicodedata.normalize("NFKC", permission).casefold().strip()
        privileged = normalized in _HIGH_RISK_PERMISSIONS or any(
            phrase in normalized for phrase in _HIGH_RISK_PERMISSION_PHRASES
        )
        broad = normalized in _BROAD_PERMISSION_NAMES or normalized.endswith(
            (":any", ":all", ":*", "=any", "=all", "=*", ":/")
        )
        if privileged:
            self._add(
                code="excessive_host_permission",
                severity=MCPFindingSeverity.HIGH,
                category="excessive_permissions",
                path=path,
                title="Server requests a privileged host capability",
                explanation=(
                    "This permission can cross the MCP sandbox boundary or grant broad control of "
                    "the client host."
                ),
                evidence=permission,
                recommendation="Replace it with the minimum directory, network, or operation scope.",
            )
        elif broad:
            self._add(
                code="broad_host_permission",
                severity=MCPFindingSeverity.MEDIUM,
                category="excessive_permissions",
                path=path,
                title="Server requests a broad host capability",
                explanation=(
                    "The declared permission is broader than a specific resource grant and needs "
                    "operator review."
                ),
                evidence=permission,
                recommendation="Scope the permission to named resources and document why it is needed.",
            )

    def _scan_schema(
        self,
        name: str,
        description: str,
        schema: Mapping[str, object],
        path: str,
    ) -> None:
        command_context = bool(
            _COMMAND_TOOL_WORDS.search(name)
            or re.search(r"\b(?:command|shell|terminal)\b", description, re.IGNORECASE)
        )
        if command_context:
            for property_name, definition, property_path in _schema_properties(
                schema, {"cmd", "command", "script", "shell"}
            ):
                if _is_unrestricted_string(definition):
                    self._add(
                        code="arbitrary_command_capability",
                        severity=MCPFindingSeverity.HIGH,
                        category="excessive_permissions",
                        path=f"{path}{property_path}",
                        title="Tool accepts an unrestricted host command",
                        explanation=(
                            "An unconstrained command string gives the model the effective "
                            "privileges of the MCP server process."
                        ),
                        evidence=property_name,
                        recommendation="Replace arbitrary commands with an allowlisted operation enum.",
                    )

        filesystem_context = bool(
            _FILESYSTEM_TOOL_WORDS.search(name)
            or re.search(r"\bfile(?:system)?\b", description, re.IGNORECASE)
        )
        if filesystem_context:
            for property_name, definition, property_path in _schema_properties(
                schema, {"file", "file_path", "filepath", "path"}
            ):
                if _is_unrestricted_string(definition):
                    self._add(
                        code="unbounded_filesystem_path",
                        severity=MCPFindingSeverity.MEDIUM,
                        category="excessive_permissions",
                        path=f"{path}{property_path}",
                        title="Filesystem path is not constrained",
                        explanation=(
                            "The schema permits arbitrary host paths. A legitimate filesystem tool "
                            "should be rooted to an operator-approved directory at runtime."
                        ),
                        evidence=property_name,
                        recommendation=(
                            "Enforce an approved root directory and reject traversal after resolution."
                        ),
                    )

        network_context = bool(
            _NETWORK_TOOL_WORDS.search(name)
            or re.search(r"\b(?:fetch|request|url|web)\b", description, re.IGNORECASE)
        )
        if network_context:
            for property_name, definition, property_path in _schema_properties(
                schema, {"endpoint", "target", "uri", "url"}
            ):
                if _is_unrestricted_string(definition):
                    self._add(
                        code="unbounded_network_target",
                        severity=MCPFindingSeverity.MEDIUM,
                        category="excessive_permissions",
                        path=f"{path}{property_path}",
                        title="Network target is not constrained",
                        explanation=(
                            "An arbitrary URL can expose internal services or cloud metadata to "
                            "SSRF. The schema alone cannot prove runtime protections."
                        ),
                        evidence=property_name,
                        recommendation=(
                            "Use a destination allowlist and block private, loopback, and metadata ranges."
                        ),
                    )

        if not isinstance(schema.get("type"), str) or schema.get("type") != "object":
            self._add(
                code="invalid_tool_input_schema_root",
                severity=MCPFindingSeverity.MEDIUM,
                category="schema_integrity",
                path=f"{path}/inputSchema/type",
                title="Tool input schema root is not an object",
                explanation="MCP 2025-11-25 requires an object at the input schema root.",
                evidence=schema.get("type", "<missing>"),
                recommendation="Set inputSchema.type to 'object' and validate its properties.",
            )

    def _scan_annotations(
        self,
        name: str,
        description: str,
        schema: object,
        annotations: Mapping[str, object],
        path: str,
    ) -> None:
        behavior = f"{name} {description}"
        destructive = bool(_DESTRUCTIVE_WORDS.search(behavior))
        mutating = destructive or bool(_MUTATING_WORDS.search(behavior))
        behavior_match = _DESTRUCTIVE_WORDS.search(behavior) or _MUTATING_WORDS.search(behavior)
        behavior_evidence = behavior_match.group(0) if behavior_match else name

        if annotations.get("readOnlyHint") is True and mutating:
            self._add(
                code="deceptive_read_only_annotation",
                severity=MCPFindingSeverity.HIGH,
                category="annotation_integrity",
                path=f"{path}/annotations/readOnlyHint",
                title="Read-only annotation contradicts described behavior",
                explanation=(
                    "The tool is labeled read-only while its name or description describes a "
                    "state-changing action. MCP annotations are untrusted hints."
                ),
                evidence=f"readOnlyHint=true; behavior={behavior_evidence}",
                recommendation="Reject the definition or correct and independently verify the annotation.",
            )

        if annotations.get("destructiveHint") is False and destructive:
            self._add(
                code="deceptive_destructive_annotation",
                severity=MCPFindingSeverity.HIGH,
                category="annotation_integrity",
                path=f"{path}/annotations/destructiveHint",
                title="Non-destructive annotation contradicts described behavior",
                explanation="The tool describes a destructive operation but claims it is non-destructive.",
                evidence=f"destructiveHint=false; behavior={behavior_evidence}",
                recommendation="Treat the tool as destructive and require explicit approval.",
            )

        url_property = (
            next(_schema_properties(schema, {"endpoint", "target", "uri", "url"}), None)
            if isinstance(schema, Mapping)
            else None
        )
        if annotations.get("openWorldHint") is False and (
            url_property or _NETWORK_TOOL_WORDS.search(name)
        ):
            self._add(
                code="deceptive_open_world_annotation",
                severity=MCPFindingSeverity.MEDIUM,
                category="annotation_integrity",
                path=f"{path}/annotations/openWorldHint",
                title="Closed-world annotation conflicts with network behavior",
                explanation="The definition appears able to contact arbitrary external entities.",
                evidence=f"openWorldHint=false; tool={name}",
                recommendation="Correct the hint and apply explicit network egress policy.",
            )


def scan_mcp_definition(
    definition: Mapping[str, object], *, trusted_tool_names: Iterable[str] = ()
) -> MCPScanResult:
    """Scan a definition without applying a separate registration threshold."""
    return MCPDefinitionScanner(trusted_tool_names=trusted_tool_names).scan(definition)


def evaluate_mcp_registration(
    definition: Mapping[str, object], *, trusted_tool_names: Iterable[str] = ()
) -> MCPScanResult:
    """Reusable pre-registration policy hook.

    ``registration_allowed`` is true only for clean or low-severity findings.
    Medium findings require an explicit operator review, while high and critical
    findings deny registration.  MUTX does not currently persist MCP server
    registrations, so future registration code must call this hook before any
    server is stored or launched.
    """
    return scan_mcp_definition(definition, trusted_tool_names=trusted_tool_names)


__all__ = [
    "MAX_DEFINITION_BYTES",
    "MCPDefinitionScanner",
    "MCPFinding",
    "MCPFindingSeverity",
    "MCPRegistrationDecision",
    "MCPScanResult",
    "evaluate_mcp_registration",
    "scan_mcp_definition",
]
