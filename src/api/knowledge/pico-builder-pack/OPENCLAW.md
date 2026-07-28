# OpenClaw

## Product profile

OpenClaw is the right recommendation when the user wants a broad multi-channel ecosystem, strong gateway workflow, multi-agent routing, companion surfaces, and a visual Control UI.

## High-level strengths

- local-first gateway control plane
- wide messaging and channel support
- multi-agent routing
- browser-based Control UI
- onboarding-driven setup with daemon install
- auth profiles and multiple provider paths
- plugin / tool / skill layering
- Tailscale integration for private remote dashboard access

## Fit signals

Recommend OpenClaw when the user says things like:

- “I want the most integrations.”
- “I want companion apps and messaging surfaces.”
- “I want multiple channels and multiple agents.”
- “I want a visual dashboard.”
- “I want broad ecosystem reach.”

## Questions to ask for OpenClaw installs

- stable workflow or bleeding-edge/source workflow?
- macOS, Linux, native Windows, or WSL2?
- which channels matter first?
- local-only or remote dashboard too?
- which provider auth path matters: API key, OpenAI Codex OAuth, Anthropic CLI reuse?
- is Tailscale needed for private remote admin?

## Current install realities

- release 2026.7.1 supports Node 22.22.3+, 24.15+, or 25.9+; Node 24.15+ is the recommended baseline
- the current happy path is install first, then `openclaw onboard --install-daemon`
- the current docs verify success with `openclaw gateway status` and then `openclaw dashboard`
- the local Control UI is at `http://127.0.0.1:18789/`
- the main config path is `~/.openclaw/openclaw.json`
- config validation is strict; unknown keys or invalid values can prevent the Gateway from starting
- `openclaw config schema` prints the live JSON schema and is the best machine-readable truth
- auth is per-agent via `auth-profiles.json`, not one giant global auth blob
- OpenClaw can auto-configure Tailscale Serve or Funnel while keeping the Gateway on loopback
- binding beyond loopback without auth is blocked
- pairing codes expire after 1 hour by default in pairing mode

## Auth guidance to respect

- OpenAI Codex OAuth is explicitly supported
- Anthropic CLI reuse is supported again, but Anthropic API keys remain the safer production path for long-lived hosts
- Qwen portal OAuth is gone; do not recommend it
- Telegram does **not** use `openclaw channels login telegram`; it uses token config

## Common OpenClaw command surfaces

Examples the GPT may reference after checking current docs:

```bash
openclaw onboard --install-daemon
openclaw status
openclaw models status
openclaw doctor
openclaw gateway status
openclaw gateway status --json
openclaw dashboard
openclaw config schema
openclaw daemon status
```

For advanced users, a strong fast verification path is:

```bash
openclaw doctor
openclaw gateway status --json
openclaw dashboard
```

## Operator adaptation cues

- beginner: prove the Gateway and Control UI before configuring channels, because a healthy dashboard is the cleanest first success signal
- intermediate: keep the order strict: runtime -> onboard -> gateway/Control UI -> channel auth -> remote access
- advanced: if docs disagree on the Node floor, tell them to use system Node 24 and stop wasting time on patch-level arguments

## Common OpenClaw troubleshooting themes

- Node runtime mismatch
- invalid config or legacy keys
- gateway not running
- auth mode mismatch between gateway and Control UI
- onboarding incomplete
- channel auth incomplete
- pairing not approved yet
- local model endpoint config issues
- Tailscale Serve/Funnel confusion

## Recommendation caution

Do not recommend OpenClaw by default if the user’s top priority is:

- persistent learning-first behavior -> Hermes
- minimal code surface and container isolation -> NanoClaw
- cheapest/edge hardware footprint -> PicoClaw

## Official sources

- https://github.com/openclaw/openclaw
- https://docs.openclaw.ai/
- https://docs.openclaw.ai/start/getting-started
- https://docs.openclaw.ai/start/wizard
- https://docs.openclaw.ai/install/node
- https://docs.openclaw.ai/gateway/configuration
- https://docs.openclaw.ai/gateway/configuration-reference
- https://docs.openclaw.ai/web/control-ui
- https://docs.openclaw.ai/gateway/tailscale
- https://docs.openclaw.ai/help/faq
- https://docs.openclaw.ai/channels/telegram
- https://docs.openclaw.ai/gateway/security
- https://docs.openclaw.ai/concepts/model-providers
- https://docs.openclaw.ai/concepts/oauth
