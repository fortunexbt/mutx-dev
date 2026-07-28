# NanoClaw

## Product profile

NanoClaw is the recommendation for users who want a smaller, easier-to-audit codebase and stronger isolation via containers rather than a giant all-in-one surface.

## High-level strengths

- lightweight mental model
- container isolation for agent runtime
- easier to understand and customize
- security-oriented positioning
- deterministic v2 setup path via `bash nanoclaw.sh`
- fork-first customization model
- skills over feature bloat

## Fit signals

Recommend NanoClaw when the user says things like:

- “I don’t want to trust a huge codebase with my whole machine.”
- “I want agents isolated in containers.”
- “I want something smaller and easier to reason about.”
- “I’m okay with a more builder-oriented workflow.”

## Questions to ask for NanoClaw installs

- do they have Claude Code available?
- is Docker or Apple Container installed and working?
- are they fine with a Git-based / fork-based setup?
- are they on current OneCLI Agent Vault or old credential-proxy assumptions?
- what messaging platforms or providers matter?

## Current install realities

- the current v2 quick start is clone, `cd` into the repo, then run `bash nanoclaw.sh` directly in the shell
- `nanoclaw.sh` owns the deterministic bootstrap and invokes Claude Code only when judgment is required
- Node.js 20+, Docker, Claude Code, and OneCLI are current prerequisites
- Docker is the default container runtime and works on macOS/Linux/Windows via WSL2
- Apple Container is macOS-only
- OneCLI Agent Vault is the modern credential path; current docs pin that shift to v1.2.35+
- `nanoclaw.sh` can bootstrap Node, pnpm, Docker, OneCLI, the agent container, and the first channel
- WSL users should clone into the Linux filesystem (`~/nanoclaw`), not `/mnt/c/...`
- v2 uses the setup script and channel adapters; do not reuse v1 branch-marketplace instructions
- diagnostics are opt-in during setup and update flows

## Version boundary to respect

NanoClaw v2 replaces the old `claude` → `/setup` entry path with `bash nanoclaw.sh`. Keep v1 migration guidance separate and never mix the two command models.

## Common NanoClaw command surfaces

Examples the GPT may reference after checking current docs:

```bash
git clone --branch v2.1.17 https://github.com/nanocoai/nanoclaw.git nanoclaw-v2
cd nanoclaw-v2
bash nanoclaw.sh
node --version
docker --version
onecli --help
```

For an existing v1 installation, use the separate `bash migrate-v2.sh` flow from a fresh v2 checkout.

## Operator adaptation cues

- beginner: run `nanoclaw.sh` in a real terminal and let its guided flow own setup
- intermediate: keep the order strict: prerequisites -> pinned clone -> `nanoclaw.sh` -> verify container -> pair channels
- advanced: focus on OneCLI, container health, adapter state, and the v1-to-v2 boundary

## Common NanoClaw troubleshooting themes

- Docker missing or misconfigured
- Claude Code missing or launched in the wrong directory
- `nanoclaw.sh` launched from the wrong checkout or interrupted mid-bootstrap
- OneCLI Agent Vault not running or not configured
- container/service startup problems
- wrong assumption that normal shell commands can replace Claude Code skills
- stale v1 customization assumptions after moving to v2
- WhatsApp re-merge or auth breakage after release changes

## Recommendation caution

Do not push NanoClaw if the user actually wants:

- the richest channel/app ecosystem -> OpenClaw
- the strongest learning-loop/persistent-agent positioning -> Hermes
- the lightest edge-hardware story -> PicoClaw

## Official sources

- https://github.com/nanocoai/nanoclaw
- https://docs.nanoclaw.dev/
- https://docs.nanoclaw.dev/introduction
- https://docs.nanoclaw.dev/quickstart
- https://docs.nanoclaw.dev/installation
- https://docs.nanoclaw.dev/integrations/skills-system
- https://docs.nanoclaw.dev/api/skills/creating-skills
- https://docs.nanoclaw.dev/api/configuration
- https://docs.nanoclaw.dev/advanced/troubleshooting
- https://docs.nanoclaw.dev/changelog
