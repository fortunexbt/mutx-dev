# Agents

The `/v1/agents*` surface covers control-plane CRUD for user-owned agents and runtime-compatible endpoints for agent registration, heartbeats, metrics, logs, commands, status, and version history.

## Routes

| Route | Purpose |
| --- | --- |
| `POST /v1/agents` | Create an agent owned by the authenticated user |
| `GET /v1/agents` | List owned agents |
| `GET /v1/agents/{agent_id}` | Get agent detail including deployments |
| `GET /v1/agents/{agent_id}/config` | Read normalized config and config version |
| `PATCH /v1/agents/{agent_id}/config` | Validate and update config, then bump version |
| `DELETE /v1/agents/{agent_id}` | Delete an owned agent |
| `POST /v1/agents/{agent_id}/deploy` | Legacy agent-scoped deployment shortcut |
| `POST /v1/agents/{agent_id}/stop` | Stop running or deploying deployments for the agent |
| `GET /v1/agents/{agent_id}/logs` | List logs for the agent |
| `GET /v1/agents/{agent_id}/metrics` | List metrics for the agent |
| `POST /v1/agents/{agent_id}/resource-usage` | Record token and cost usage |
| `GET /v1/agents/{agent_id}/resource-usage` | List recorded resource usage |
| `GET /v1/agents/{agent_id}/versions` | List agent config versions |
| `POST /v1/agents/{agent_id}/rollback` | Roll back to a prior agent version |
| `POST /v1/agents/register` | Runtime-style agent registration + API key issuance |
| `POST /v1/agents/heartbeat` | Report runtime status |
| `POST /v1/agents/metrics` | Report metrics |
| `POST /v1/agents/logs` | Send runtime logs |
| `GET /v1/agents/commands` | Poll pending commands for the authenticated agent |
| `POST /v1/agents/commands/acknowledge` | Acknowledge command completion |
| `GET /v1/agents/{agent_id}/status` | Return runtime status for the authenticated agent |

## Create An Agent

Ownership comes from the authenticated user principal. Do not send `user_id` in
the request body. User JWTs and managed API keys are accepted through Bearer
authentication; managed keys may also use `X-API-Key`.
Creation, config changes, deployment shortcuts, stop, resource writes, rollback,
and deletion require `DEVELOPER` (or `ADMIN`). Owned reads accept `VIEWER` or
`DEVELOPER` (and `ADMIN`).

`config` can be a JSON object or a JSON string. The backend validates it against the selected `type`.

```bash
BASE_URL=http://localhost:8000

curl -X POST "$BASE_URL/v1/agents" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Personal Assistant",
    "description": "Default assistant deployment",
    "type": "openclaw",
    "config": {
      "runtime": "personal_assistant",
      "template": "personal_assistant",
      "workspace": "default",
      "model": "openai/gpt-5",
      "safety_mode": "pairing"
    }
  }'
```

Example response:

```json
{
  "id": "uuid",
  "name": "Personal Assistant",
  "description": "Default assistant deployment",
  "type": "openclaw",
  "status": "creating",
  "config": {
    "name": "Personal Assistant",
    "runtime": "personal_assistant",
    "template": "personal_assistant",
    "workspace": "default",
    "model": "openai/gpt-5",
    "safety_mode": "pairing",
    "version": 1
  },
  "config_version": 1,
  "created_at": "2026-03-22T12:00:00Z",
  "updated_at": "2026-03-22T12:00:00Z",
  "user_id": "uuid"
}
```

## Config Validation

Current typed config families:

- `openai`
- `anthropic`
- `langchain`
- `custom`
- `openclaw`

Unknown keys are rejected for typed configs. Successful config patches increment `config_version`.

## Config Response

`GET /v1/agents/{agent_id}/config` returns the agent's normalized config with its current version. The `config` shape matches the agent's `type`:

```json
{
  "agent_id": "uuid",
  "type": "openclaw",
  "config": {
    "runtime": "personal_assistant",
    "template": "personal_assistant",
    "assistant_id": null,
    "workspace": "default",
    "model": "openai/gpt-5",
    "safety_mode": "pairing",
    "version": 1
  },
  "config_version": 1,
  "updated_at": "2026-03-22T12:00:00Z"
}
```

The config shape matches the agent's `type`. An `openclaw` config always includes `runtime`, `template`, `assistant_id`, `workspace`, `model`, and `safety_mode`.

## List And Inspect Agents

```bash
curl "$BASE_URL/v1/agents?skip=0&limit=20" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl "$BASE_URL/v1/agents/YOUR_AGENT_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl "$BASE_URL/v1/agents/YOUR_AGENT_ID/config" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Update Config

```bash
curl -X PATCH "$BASE_URL/v1/agents/YOUR_AGENT_ID/config" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "runtime": "personal_assistant",
      "template": "personal_assistant",
      "workspace": "default",
      "model": "openai/gpt-5",
      "safety_mode": "pairing",
      "channels": {
        "terminal": {
          "label": "Terminal",
          "enabled": true,
          "mode": "pairing"
        }
      }
    }
  }'
```

## Deploy, Stop, And Delete

`POST /v1/agents/{agent_id}/deploy` is still mounted, but the canonical full deployment create path is [`POST /v1/deployments`](./deployments.md).

```bash
curl -X POST "$BASE_URL/v1/agents/YOUR_AGENT_ID/deploy" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl -X POST "$BASE_URL/v1/agents/YOUR_AGENT_ID/stop" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl -X DELETE "$BASE_URL/v1/agents/YOUR_AGENT_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Logs, Metrics, And Resource Usage

```bash
curl "$BASE_URL/v1/agents/YOUR_AGENT_ID/logs?limit=100&level=info" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl "$BASE_URL/v1/agents/YOUR_AGENT_ID/metrics?limit=100" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl "$BASE_URL/v1/agents/YOUR_AGENT_ID/resource-usage?limit=50" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Resource usage records accept:

- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `api_calls`
- `cost_usd`
- `model`
- `extra_metadata`
- `period_start`
- `period_end`

## Versions And Rollback

```bash
curl "$BASE_URL/v1/agents/YOUR_AGENT_ID/versions" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl -X POST "$BASE_URL/v1/agents/YOUR_AGENT_ID/rollback" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"version":1}'
```

## Runtime Registration Notes

`POST /v1/agents/register` is the runtime-facing registration entrypoint.

It returns a runtime payload containing:

- `agent_id`
- `api_key`
- `status`
- `message`

Use the OpenAPI snapshot for the exact runtime request and response shapes if you are integrating at that layer.

The returned `mutx_agent_...` key is a Bearer credential for heartbeat, metrics,
logs, command polling/acknowledgement, and runtime status. Those six
agent-authenticated operations do not accept the managed-user `X-API-Key`
header.
