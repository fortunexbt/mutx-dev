# OpenClaw

## Product profile

OpenClaw is the right recommendation when the user wants a broad multi-channel ecosystem, strong gateway workflow, multi-agent routing, companion apps, and a visual workspace/canvas style interface.

## High-level strengths

- local-first gateway control plane
- wide messaging and channel support
- multi-agent routing
- live canvas / visual workspace
- onboarding-driven setup
- companion apps
- strong channel/login workflow

## Fit signals

Recommend OpenClaw when the user says things like:
- “I want the most integrations.”
- “I want companion apps and messaging surfaces.”
- “I want multiple channels and multiple agents.”
- “I want the canvas / visual workspace idea.”
- “I want broad ecosystem reach.”

## Questions to ask for OpenClaw installs

- stable workflow or bleeding-edge/source workflow?
- macOS, Linux, or WSL?
- which channels matter first?
- CLI-only or app-attached workflow?
- do they need local models, hosted models, or both?
- is Tailscale needed for private remote admin?

## Common OpenClaw command surfaces

Examples the GPT may reference after checking current docs:
```bash
openclaw onboard
openclaw channels login
openclaw health
openclaw gateway
```

For install flows, current docs should be checked because the installer scripts and onboarding flow can change.

## Common OpenClaw troubleshooting themes

- Node runtime mismatch
- gateway not running
- onboarding incomplete
- channel auth incomplete
- app connected to the wrong mode
- local model endpoint config issues

## Recommendation caution

Do not recommend OpenClaw by default if the user’s top priority is:
- persistent learning-first behavior -> Hermes
- minimal code surface and container isolation -> NanoClaw
- cheapest/edge hardware footprint -> PicoClaw

## Official sources

- https://github.com/openclaw/openclaw
- https://docs.openclaw.ai/
- https://docs.openclaw.ai/install
- https://docs.openclaw.ai/start/getting-started
- https://docs.openclaw.ai/start/onboarding
- https://docs.openclaw.ai/gateway/local-models
