# Install Flow

## Default install phases

1. **Choose the right agent**
   - If undecided, use `DECISION_MATRIX.md`.
2. **Confirm the host**
   - OS, hardware, always-on vs laptop, local vs remote.
3. **Confirm the model path**
   - hosted API, OpenAI-compatible endpoint, or local model.
4. **Install the core agent**
   - use the latest official docs for current commands
5. **Run onboarding/setup**
   - provider, gateway, channels, or profile setup
6. **Add remote access if needed**
   - prefer Tailscale before public exposure
7. **Verify a minimal success path**
   - one local prompt or health check first
8. **Add extras**
   - channels, API server, cron, skills, memory tuning
9. **Snapshot the working state**
   - save config location, version, and rollback notes

## Per-agent install cues

### Hermes
Use Hermes when the user wants a persistent, self-improving agent. Validate:
- install method
- provider setup
- gateway or CLI mode
- profile strategy
- whether API server or MCP mode is needed

### OpenClaw
Use OpenClaw when the user wants strong channel support or a visual workspace workflow. Validate:
- Node runtime and install path
- onboarding or setup flow
- gateway state
- channel login flow
- companion app vs CLI workflow

### NanoClaw
Use NanoClaw when the user wants a smaller, container-isolated stack. Validate:
- Git / fork / clone path
- Claude Code availability
- Docker or container prereqs
- whether the v2 `nanoclaw.sh` bootstrap completed
- whether container services came up cleanly

### PicoClaw
Use PicoClaw when the user wants lightweight deployment or edge hardware. Validate:
- install mode: binary, source, Docker, or launcher
- config version
- model provider config
- workspace restrictions
- gateway or agent mode

## Verification standard

Every install answer should include:
- one exact command or action
- one expected result
- one next action after success
- one fallback if the expected result does not happen
