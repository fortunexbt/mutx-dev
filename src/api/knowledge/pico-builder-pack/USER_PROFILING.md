# User Profiling

## Skill-level detection

### Beginner signals

- says they are new
- asks what an agent, gateway, daemon, profile, or workspace is
- asks where to paste commands
- provides no environment details
- is uncomfortable with SSH, Docker, or terminals
- wants screenshots or exact click paths

### Intermediate signals

- can name OS, runtime, and provider
- understands repos, installs, env files, and config paths
- can paste logs and run commands
- wants shorter explanations
- knows the difference between local and remote access

### Advanced signals

- asks for the fastest path
- names exact versions, ports, containers, services, or auth paths
- pastes stack traces or config fragments
- asks for flags, alternatives, or migration strategy
- mentions things like WSL path location, systemd user units, OneCLI, `.security.yml`, `gateway.bind`, or `allowedOrigins`

## High-signal question bank

Pick **4–8** of the highest-signal questions. Do not ask all of them by default.

### If the user is undecided

- What matters most: learning over time, channel breadth, security isolation, or tiny footprint?
- Where will the agent run: laptop, mini PC, VPS, homelab, edge device, or Android?
- Do you want CLI, messaging apps, browser UI, or an API endpoint?
- Are you optimizing for simplicity, power, security, or cost?

### If the user wants a fresh install

- Which stack are we targeting?
- What OS and environment are you on?
- Fresh machine or existing install?
- Which provider or local model runtime do you plan to use?
- Do you want remote access, and if so should it stay private?

### If the user is stuck

- What exact step fails first?
- What exact error do you see?
- What changed right before the failure?
- What already works?
- Paste one decisive signal: command output, log tail, config excerpt, or screenshot.

### If Tailscale is involved

- Is the agent local, on a VPS, or on homelab hardware?
- Do you want private access only or public internet exposure too?
- Are you trying to reach SSH, a Control UI, a launcher UI, an API server, or a chat backend?
- Is the service bound to localhost only?

### If Hermes is involved

- CLI only, messaging gateway, dashboard, API server, or some combination?
- Which backend: local, Docker, SSH, Modal, Daytona, Singularity?
- Are you using a single profile or multiple profiles?

### If OpenClaw is involved

- Are you doing local Control UI, channel auth, remote dashboard access, or all three?
- Do you want daemon install?
- Which provider auth path do you want: API key, OpenAI Codex OAuth, Anthropic CLI reuse, or something else?

### If NanoClaw is involved

- Do you already have Claude Code working?
- Docker or Apple Container?
- Are you on v1.2.35+ and using OneCLI Agent Vault yet?
- Are you on NanoClaw v2 and running `nanoclaw.sh`, or following an older v1 `/setup` guide?

### If PicoClaw is involved

- Precompiled binary, launcher, Docker, source build, or Android APK?
- Do you want the Web UI, TUI, or pure CLI?
- Are you editing `config.json`, `.security.yml`, or both?
- Do you need gateway mode, agent mode, or both?

## Adaptation rules

- Beginner: fewer questions, more explanation.
- Intermediate: medium detail, prioritize order of operations.
- Advanced: fewer words, more diagnostic leverage.
- Once the user supplies decisive evidence, move from discovery to action.

## Output pacing

Never ask nine setup questions and stop.

After the minimum decisive questions, move the user forward with the next command, screen, or config snippet.
