---
description: Install, configure, and operate MUTX through the assistant-first CLI and TUI.
icon: terminal
---

# CLI Command Reference

The MUTX CLI distribution lives at repo root and installs only the `mutx` entrypoint from
`pyproject.toml`. Backend queue workers are server modules and are not included in the CLI wheel;
run them from a full backend installation with `python -m src.api.document_worker` or
`python -m src.api.reasoning_worker`.

## Install

Fastest macOS path:

```bash
brew tap mutx-dev/homebrew-tap
brew install mutx
mutx setup hosted
```

This path installs MUTX through Homebrew, then hands onboarding off to the CLI itself.

🦞 The setup handoff now enters a MUTX-owned wizard. Hosted is the recommended lane, OpenClaw is the default personal assistant runtime, and MUTX tracks the real upstream OpenClaw home rather than relocating it.

Editable local install with the operator TUI:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev,tui]"
```

Homebrew install from the third-party tap:

```bash
brew tap mutx-dev/homebrew-tap
brew install mutx
```

The published tap is updated from `cli-vX.Y.Z` release tags. Pushing `main` by itself does not move Homebrew.

The tap formula is expected to smoke-test the package with non-networked command help such as `mutx --help`, `mutx setup --help`, and `mutx doctor --help`.

If Homebrew says `mutx` is installed but not linked, there is usually an older `mutx` shim already present in `/opt/homebrew/bin`. Relink the Homebrew binary with:

```bash
brew link --overwrite mutx
hash -r
which mutx
```

If you want to inspect the conflict before overwriting:

```bash
brew link --overwrite mutx --dry-run
```

If `mutx` still fails with `ModuleNotFoundError: No module named 'cli'`, your shell is still resolving the stale wrapper rather than the Homebrew-managed executable.

## Configuration

The CLI stores configuration in `~/.mutx/config.json` and reuses the existing `CLIConfig` shape from [`cli/config.py`](https://github.com/mutx-dev/mutx-dev/blob/main/cli/config.py):

```json
{
  "api_url": "http://localhost:8000",
  "access_token": null,
  "refresh_token": null,
  "assistant_defaults": {
    "provider": "openclaw",
    "template": "personal_assistant",
    "runtime": "openclaw",
    "model": "openai/gpt-5"
  }
}
```

Config precedence is:

1. CLI flag
2. `MUTX_API_URL`
3. config file
4. default

You can override the API URL per command:

```bash
mutx --api-url http://localhost:8000 doctor
```

Or with an environment variable:

```bash
export MUTX_API_URL=http://localhost:8000
```

## Canonical Setup Flow

Recommended direct setup:

```bash
mutx setup hosted --install-openclaw --open-tui
```

Advanced local operator:

```bash
mutx setup local --install-openclaw --open-tui
```

If OpenClaw already exists on the machine and you just want MUTX to adopt it for tracking:

```bash
mutx setup hosted --import-openclaw
mutx setup local --import-openclaw
```

Hosted setup authenticates against the configured control plane. Local setup can provision a managed localhost stack under `~/.mutx/runtime/local-control`, start `http://localhost:8000`, bootstrap a trusted local operator session, deploy `Personal Assistant`, and open the TUI without asking for email or password.

Both lanes now:

* keep MUTX in charge of the flow
* detect an existing OpenClaw install and import its binary/home paths into MUTX tracking
* install OpenClaw on demand
* resume upstream `openclaw onboard --install-daemon` when needed
* track the runtime in `~/.mutx/providers/openclaw`
* sync a last-seen provider snapshot back to the control plane for the web dashboard
* keep local OpenClaw gateway keys on the operator machine instead of uploading them

## Core Commands

### Setup + health

| Command | Description |
| ------- | ----------- |
| `mutx setup hosted` | Authenticate against a hosted control plane and deploy `Personal Assistant` |
| `mutx setup local` | Bootstrap a local operator session and deploy `Personal Assistant` |
| `mutx doctor` | Show config source, auth state, API reachability, provider runtime health, and assistant summary |
| `mutx runtime list` | List local provider runtimes tracked under `~/.mutx/providers` |
| `mutx runtime inspect <provider>` | Inspect the local manifest plus the last synced remote snapshot |
| `mutx runtime resync <provider>` | Push the local provider snapshot back to the API/dashboard |
| `mutx runtime open <provider> --surface tui|configure` | Suspend back into the upstream OpenClaw TUI or configurator, then return to MUTX |

### Auth

| Command | Description |
| ------- | ----------- |
| `mutx auth login` | Login to MUTX |
| `mutx auth register` | Create a user account |
| `mutx auth logout` | Clear local tokens |
| `mutx auth whoami` | Show current user info |
| `mutx auth status` | Show local auth state |

### Assistants

| Command | Description |
| ------- | ----------- |
| `mutx assistant overview` | Show the current Personal Assistant summary |
| `mutx assistant sessions` | List known assistant sessions |
| `mutx assistant channels --agent-id <id>` | Show assistant channel bindings |
| `mutx assistant health --agent-id <id>` | Show assistant gateway health |
| `mutx assistant skills list --agent-id <id>` | List available and installed skills |
| `mutx assistant skills install --agent-id <id> --skill-id <skill>` | Install a skill |
| `mutx assistant skills remove --agent-id <id> --skill-id <skill>` | Remove a skill |
| `mutx clawhub list` | Browse the full MUTX + Orchestra skill catalog |
| `mutx clawhub bundles` | List curated Orchestra Research skill bundles |
| `mutx clawhub install-bundle --agent-id <id> --bundle-id <bundle>` | Install a curated bundle |

### Agents + deployments

| Command | Description |
| ------- | ----------- |
| `mutx agent list` | List agents |
| `mutx agent create --template personal_assistant` | Create the starter assistant without the one-shot setup flow |
| `mutx agent deploy <agent_id>` | Deploy an agent |
| `mutx deployment list` | List deployments |
| `mutx deployment create --agent-id <id>` | Create a deployment |

### Document workflows

| Command | Description |
| ------- | ----------- |
| `mutx documents templates` | List available `predict-rlm` document templates |
| `mutx documents list` | List document jobs |
| `mutx documents get <job-id>` | Inspect a specific document job |
| `mutx documents run --template-id <id> --mode managed|local` | Create a document job, register or upload inputs, and dispatch it |
| `mutx documents download-artifact <job-id> <artifact-id>` | Download a managed output artifact |

Document workflows require `MUTX_DOCUMENTS_ENABLED=true`, `predict-rlm`, `deno`, and valid model credentials. See [Document Workflows](./document-workflows.md) for the full runtime contract and credit trail.

### Reasoning workflows

| Command | Description |
| ------- | ----------- |
| `mutx reasoning templates` | List reasoning workflow templates |
| `mutx reasoning list` | List reasoning jobs |
| `mutx reasoning run --template-id <id>` | Start a reasoning job |

### Scheduled tasks

| Command | Description |
| ------- | ----------- |
| `mutx scheduler list` | List scheduled tasks |
| `mutx scheduler get <schedule_id>` | Get a scheduled task by ID |

### Budgets

| Command | Description |
| ------- | ----------- |
| `mutx budgets list` | List budgets |
| `mutx budgets get <budget_id>` | Get a budget by ID |

### Usage

| Command | Description |
| ------- | ----------- |
| `mutx usage summary --period <period>` | Show overall usage summary |
| `mutx usage by-agent --limit <n>` | Show usage breakdown by agent |

### Governance

| Command | Description |
| ------- | ----------- |
| `mutx governance status` | Show Faramesh daemon health and policy status |
| `mutx governance decisions --limit <n>` | Show recent governance decisions |

### Observability

| Command | Description |
| ------- | ----------- |
| `mutx observability runs list` | List agent runs |
| `mutx observability runs get <run_id>` | Get a specific run |

### Security

| Command | Description |
| ------- | ----------- |
| `mutx security evaluate --agent-id <id> --session-id <id> <tool_name>` | Evaluate a tool call against security policy |
| `mutx security approvals list` | List pending approvals visible to the authenticated caller |
| `mutx security approvals approve <request_id>` | Approve an eligible assigned request by durable request ID |
| `mutx security approvals deny <request_id>` | Deny an eligible assigned request by durable request ID |

Approval decisions use the CLI's ordinary authenticated session plus persisted
role and reviewer assignment. There is no separate approval bearer token.

### Webhooks

| Command | Description |
| ------- | ----------- |
| `mutx webhooks list` | List webhook destinations |
| `mutx webhooks create` | Create a webhook destination |
| `mutx webhooks delete <webhook_id>` | Delete a webhook |

### Self-update

| Command | Description |
| ------- | ----------- |
| `mutx update check` | Check for CLI updates |
| `mutx update apply` | Apply available CLI updates |

### Compatibility commands

The older flat commands remain available for compatibility:

* `mutx login`
* `mutx logout`
* `mutx whoami`
* `mutx status`
* legacy `agents` and `deploy` groups

## Operator TUI

Launch the first-party Textual shell with:

```bash
mutx tui
```

The TUI now centers the assistant-first operator path:

* `Setup`: auth state, provider cards, wizard steps, runtime pointers, and starter deployment entrypoint
  Existing OpenClaw installs expose `Import Existing OpenClaw 🦞`, a repair path, and `Open OpenClaw TUI 🦞`.
* `Assistant`: assistant overview, status, and deployment context
* `Deployments`: deployment inventory and controls
* `Control Plane`: sessions and gateway detail

Key bindings:

* `r` refresh the active pane
* `d` deploy the default assistant from setup
* `x` restart the selected deployment
* `s` scale the selected deployment
* `backspace` delete the selected deployment
* `q` quit

If no local auth is stored, the TUI still launches and shows the local CLI state instead of crashing.

## Smoke Validation

Local editable install and command smoke:

```bash
pip install -e ".[dev,tui]"
mutx doctor --output json
mutx --help
```

Local stack validation:

```bash
make dev-up
mutx setup local --name "Local Operator" --install-openclaw --no-input
mutx doctor
mutx assistant overview
mutx runtime inspect openclaw
mutx runtime open openclaw --surface tui
mutx tui
```

Targeted contract coverage:

```bash
pytest tests/test_cli_auth_and_tui.py tests/test_cli_setup_and_doctor.py
```

## Release Truth

* The CLI distribution version is the root [`pyproject.toml`](https://github.com/mutx-dev/mutx-dev/blob/main/pyproject.toml) version.
* The recommended CLI git tag format is `cli-vX.Y.Z`.
* The Homebrew tap formula should point at the matching `cli-vX.Y.Z` source archive and use `mutx --help` as its non-network test.
* The SDK has its own package metadata under [`sdk/pyproject.toml`](https://github.com/mutx-dev/mutx-dev/blob/main/sdk/pyproject.toml); do not treat SDK and CLI release tags as the same thing.
