# Hermes

## Product profile

Hermes is the default recommendation in this pack when the user wants a persistent agent that improves over time rather than acting like a fresh stateless assistant each session.

## High-level strengths

- built-in learning loop
- persistent sessions and cross-session recall
- strong CLI plus gateway-oriented workflow
- dashboard and API server options
- profiles for isolated instances
- cron / scheduled automation support
- multiple terminal backends
- good diagnostics and state export

## Fit signals

Recommend Hermes when the user says things like:

- “I want the best general personal agent.”
- “I want something that gets better over time.”
- “I want one always-on agent hub.”
- “I want memory, sessions, and skills.”
- “I want it on a VPS or always-on mini PC.”

## Questions to ask for Hermes installs

- CLI only, dashboard, gateway, API server, or more than one?
- local machine, VPS, WSL2, or Android via Termux?
- one instance or multiple profiles?
- hosted model provider or local endpoint?
- local backend or isolated backend like Docker?
- will Tailscale be used for private admin access?

## Current install realities

- the current audited release tag is v2026.7.20 (package 0.19.0) and requires Python >=3.11,<3.14
- the official fast path is the one-line install script documented on the Hermes docs site
- Linux, macOS, WSL2, and Android via Termux are supported paths in current docs
- native Windows is not the primary path; use WSL2 instead
- the dashboard binds to `127.0.0.1:9119` and has no built-in auth
- the API server exposes Hermes as an OpenAI-compatible endpoint on `127.0.0.1:8642` when enabled
- six terminal backends are documented: local, Docker, SSH, Daytona, Singularity, Modal
- `AGENTS.md` is a first-class context file and is loaded automatically
- the local backend is not a sandbox; for untrusted code, recommend Docker or another isolated backend

## Common Hermes command surfaces

Examples the GPT may reference after checking current docs:

```bash
hermes
hermes setup
hermes model
hermes auth
hermes gateway
hermes dashboard
hermes status
hermes dump
hermes doctor
hermes profile create <name>
hermes update
```

For advanced users, the safest current sanity-check sequence is:

```bash
hermes doctor
hermes status
hermes dump
```

## Operator adaptation cues

- beginner: prove the CLI first, then `hermes setup`, then add dashboard/gateway/API extras
- intermediate: keep the order strict: install -> provider/model -> local success -> remote access -> extras
- advanced: assume they want the shortest proof path, but still give one checkpoint for install health, one for model/auth, and one for gateway state

## Common Hermes troubleshooting themes

- provider config mismatch
- local backend used when the user expected container isolation
- dashboard exposed beyond localhost without realizing it has no auth
- wrong profile / wrong `HERMES_HOME`
- missing optional tool dependencies from the manual install path
- config drift after updates
- remote access set up before local success was verified

## When not to recommend Hermes first

Do not force Hermes if the user mainly needs:

- the widest messaging/channel ecosystem and app surfaces -> OpenClaw may fit better
- smaller, more auditable container isolation -> NanoClaw may fit better
- ultra-lightweight edge deployment -> PicoClaw may fit better

## Official sources

- https://github.com/NousResearch/hermes-agent
- https://github.com/NousResearch/hermes-agent/releases
- https://hermes-agent.nousresearch.com/docs/getting-started/installation
- https://hermes-agent.nousresearch.com/docs/getting-started/termux
- https://hermes-agent.nousresearch.com/docs/reference/cli-commands
- https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard
- https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
- https://hermes-agent.nousresearch.com/docs/user-guide/configuration
- https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files
