# Install Flow

## Default install phases

1. **Choose the right stack**
   - If undecided, use `DECISION_MATRIX.md`.

2. **Confirm the host**
   - OS, hardware, always-on vs laptop, local vs remote.

3. **Confirm the model path**
   - For hosted providers: prefer official OAuth / CLI-backed login only when the docs clearly support it.
   - Otherwise use API keys with cost and storage guidance.
   - Do not proceed until the auth method is clear.

4. **Install the core stack**
   - use the latest official docs for current commands

5. **Run onboarding/setup**
   - provider, gateway, channels, or profile setup

6. **Verify a minimal local success path**
   - one local prompt or health check first

7. **Add remote access if needed**
   - prefer Tailscale before public exposure

8. **Add extras**
   - channels, API server, cron, skills, memory tuning

9. **Snapshot the working state**
   - save config location, version, auth method, and rollback notes

## Adapt by operator level

### Beginner

- explain one new term at a time: gateway, provider, profile, daemon, container
- give one shell block, one expected result, and one next action per step
- include where the user should run the command and what screen or file they should see next

### Intermediate

- show the order of operations up front so they do not configure channels before the core runtime works
- call out the two or three common pitfalls for that stack
- keep branches explicit: “if this passes, do X; if not, capture Y”

### Advanced

- start with assumptions and the shortest working path
- keep verification, but compress it into fast checkpoints
- prefer commands first, then the one or two likely debug pivots

## Per-stack install cues

### Hermes

Use Hermes when the user wants a persistent, self-improving agent. Validate:

- platform: Linux, macOS, WSL2, or Android via Termux
- install method: official install script vs manual `uv` path
- setup path: prove `hermes` or run `hermes setup` first, then provider/model, then gateway extras if needed
- runtime mode: CLI only, dashboard, API server, messaging gateway, or multiple
- backend choice: local vs Docker vs remote/sandboxed backends
- profile strategy and whether migration from OpenClaw matters

### OpenClaw

Use OpenClaw when the user wants strong channel support or a visual workspace workflow. Validate:

- Node runtime and install path: Node 24.15+ preferred; 22.22.3+ and 25.9+ are also supported
- onboarding path: install first, then `openclaw onboard`; add `--install-daemon` when they want the gateway to stay running
- first verification path: `openclaw gateway status`, then `openclaw dashboard`, before spending time on channel auth
- gateway state and whether the user expects the Control UI / dashboard
- channel login flow and DM pairing policy
- whether the gateway service is being daemonized from a stable system Node rather than a throwaway shell manager
- native Windows vs WSL2, because both are supported but WSL2 is usually steadier

### NanoClaw

Use NanoClaw when the user wants a smaller, container-isolated stack. Validate:

- fork / clone path, because the current happy path is fork-first
- Claude Code, OneCLI, and Docker availability before running the v2 `nanoclaw.sh` bootstrap
- Node 20+ plus Apple Container or Docker prerequisites
- OneCLI Agent Vault status for modern installs
- whether `nanoclaw.sh` completed, the container is healthy, and the selected channel adapter paired successfully
- whether the container runtime came up cleanly and the main channel or task loop actually responds

### PicoClaw

Use PicoClaw when the user wants lightweight deployment or edge hardware. Validate:

- install mode: website download, launcher, Docker, source, or Android APK
- whether the user wants JSON-first setup or the launcher at `http://localhost:18800`
- whether they only need the core binary or are actually building launcher / Web UI components
- model provider config in `~/.picoclaw/config.json` or `.security.yml`
- workspace and sandbox expectations
- gateway mode vs direct `picoclaw agent` use
- whether `-public` or other non-default exposure is actually required

## Package generation

When the coach has collected minimum signal (stack + os + provider + goal), generate a verified setup ZIP:

### What goes in the ZIP

| Stack | Stack-specific file |
|-------|---------------------|
| Hermes | `AGENTS.md` |
| OpenClaw | no MUTX-owned runtime config |
| NanoClaw | no MUTX-owned runtime config |
| PicoClaw | no MUTX-owned runtime config |

Every ZIP also contains:
- `upstream.lock.json` — exact repository, release, commit, version, and runtime contract
- `install.sh` — release-pinned install and upstream onboarding commands
- `.env.template` — secret-name reference only; it is never sourced automatically
- `README.md` — personalized install guide with exact commands for their OS + provider
- `kb/` — the shared install flow, update notes, and current stack-specific reference
- `tailscale-setup.sh` — included only if networking == tailscale

Runtime configuration is not generated by MUTX. The pinned upstream onboarding flow owns
`config.yaml`, `openclaw.json`, Docker/Container configuration, PicoClaw security files,
and channel setup so the ZIP cannot silently drift from the installed release schema.

### README.md is the key deliverable

Generated from the conversation context:
- Exact install commands for their OS
- Exact provider config steps
- Exact channel setup steps (if channels selected)
- Verification commands
- "Come back to pico.mutx.dev if anything breaks"

### Post-download instructions

Tell the user:
1. Download and uncompress the ZIP
2. Open README.md and follow the steps
3. If anything breaks, come back — session is saved
4. Never share .env files or API keys in chat

## Verification standard

Every install answer should include:

- one exact command or action
- one expected result
- one next action after success
- one fallback if the expected result does not happen

Do not drop verification just because the user is advanced. Shorten the wording, not the proof.
