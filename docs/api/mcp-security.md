# MCP Definition Scanning

`POST /v1/security/mcp/scan` performs deterministic static analysis of an MCP
server configuration and its advertised tools. The endpoint requires the same
Bearer-token or managed API-key authentication as the rest of the public
security API. It does not contact the server, resolve URLs, or execute startup
commands.

The accepted tool fields follow the stable
[MCP 2025-11-25 tool definition](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
MCP explicitly treats tool metadata and annotations as untrusted. The scanner
also follows the protocol's
[security guidance for local servers](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
by identifying high-signal startup-command and overbroad-capability risks.

## Request

```json
{
  "server": {
    "name": "weather.example",
    "transport": "streamable_http",
    "url": "https://mcp.example.com/v1",
    "requestedPermissions": ["network:api.weather.example"],
    "tools": [
      {
        "name": "weather.current",
        "description": "Return current weather for a city.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "city": {"type": "string", "maxLength": 120}
          },
          "required": ["city"],
          "additionalProperties": false
        },
        "annotations": {
          "readOnlyHint": true,
          "openWorldHint": true
        }
      }
    ]
  },
  "trustedToolNames": ["weather.current"]
}
```

`trustedToolNames` is optional. Typosquatting checks compare only against that
caller-supplied baseline; the scanner does not guess a universal list of
legitimate tools.

Do not submit live secrets. Environment values are discarded before scanning
and are never returned, but callers should send placeholder values or variable
names in definition-audit workflows.

## Result And Registration Policy

Every finding includes a stable code, severity, category, JSON-pointer-like
path, redacted evidence, explanation, and recommendation.

| Decision | Meaning | `registration_allowed` |
| --- | --- | --- |
| `allow` | No findings above low severity | `true` |
| `review` | At least one medium finding; operator review is required | `false` |
| `deny` | At least one high or critical finding | `false` |

The reusable backend hook is
`src.api.services.mcp_scanner.evaluate_mcp_registration`. MUTX does not
currently persist or launch registered MCP servers, so there is no registration
handler to wire today. Any future MCP registry must call this hook before it
stores a definition or starts a process.

## Detection Scope

The scanner reports:

- prompt-injection and hidden-instruction phrases in descriptions and schemas;
- invisible Unicode controls, nonstandard names, normalized collisions, and
  caller-grounded typosquatting;
- download-and-execute, destructive, shell-evaluation, and apparent
  credential-exfiltration command shapes;
- credential-bearing, metadata-service, Punycode, shortened, or unencrypted
  remote URLs;
- privileged declared permissions and schemas exposing unrestricted commands,
  filesystem paths, or network destinations;
- contradictions between described behavior and MCP tool annotations.

This is a static preflight control, not malware analysis, publisher
verification, a runtime sandbox, or proof of safety. Operators must still use
explicit consent, least-privilege execution, network policy, and server
provenance checks.
