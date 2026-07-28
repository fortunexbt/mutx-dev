# Troubleshooting Flow

## Golden rule

Diagnose the failing layer before proposing fixes.

## Failing layers

1. Install / prerequisites
2. Runtime / service startup
3. Auth / credential store / provider login
4. Model or local-runtime connection
5. Channel or gateway integration
6. Dashboard / browser / Control UI
7. Networking / Tailscale / DNS / reachability
8. Filesystem / permissions / sandbox
9. Version drift / config mismatch
10. User expectation mismatch

## Diagnostic method

### Step 1: Identify the layer

Ask:

- what is the first thing that fails?
- what still works?
- did this ever work before?

### Step 2: Request the smallest decisive signal

Examples:

- one command output
- one log tail
- one stack trace
- one config excerpt
- one screenshot of the relevant page

Good examples:

- `hermes doctor`
- `openclaw gateway status --json`
- `openclaw doctor`
- `tailscale status`
- `/debug` output in NanoClaw
- the relevant section of `~/.picoclaw/config.json`

### Step 3: Propose the most likely fix first

Do not give a shopping list of guesses.

### Step 4: Re-verify

Ask for the output of the verification step.

## Common patterns by layer

### Install failure

Check:

- runtime version
- wrong shell or wrong OS guide
- missing package manager
- build tools missing
- permissions
- antivirus / macOS Gatekeeper / WSL weirdness

### Runtime failure

Check:

- service actually started
- logs location
- missing env or secret store
- wrong config path
- unsupported provider selection
- port conflict
- bind address mismatch

### Auth / credential failure

Check:

- API key presence
- OAuth/CLI login freshness
- credential store path
- per-agent or per-profile auth separation
- old vs new auth path assumptions

Examples:

- OpenClaw auth is per-agent.
- NanoClaw v1.2.35+ may require OneCLI instead of old `.env` assumptions.
- PicoClaw may split secrets into `.security.yml`.

### Model/provider failure

Check:

- model name spelling
- provider base URL
- local model server actually running
- firewall or proxy issues
- allowlist / routing config that silently chooses a different model

### Dashboard / browser failure

Check:

- local vs remote origin
- auth mode mismatch
- token/password drift
- loopback binding
- browser secure-context assumptions
- reverse proxy or Tailscale behavior

### Networking / Tailscale failure

Check:

- logged into the correct tailnet
- device online
- hostname resolution
- service binding address
- firewall
- wrong port
- user trying to reach `localhost` from another machine
- Serve vs Funnel confusion

### Channel integration failure

Check:

- auth completed
- correct bot/app credentials
- callback URL or webhook reachability
- gateway running
- mention or allowlist policy
- pairing not approved yet
- channel-specific quirks like Telegram token config vs login wizard

### Filesystem / sandbox failure

Check:

- wrong WSL path
- container runtime access
- workspace restriction
- missing mounts
- root-owned files blocking updates
- unsafe assumption that the host is writable from inside a sandbox

### Version drift / config mismatch

Check:

- docs vs installed version
- schema changes
- new secret store or config path
- deprecated provider auth paths
- breaking release notes

## Stack-specific fast pivots

### Hermes

- `hermes doctor`
- `hermes status`
- `hermes dump`
- backend set to local when the user expected Docker isolation
- dashboard exposed beyond localhost without realizing it has no built-in auth

### OpenClaw

- `openclaw doctor`
- `openclaw gateway status --json`
- config schema violation
- auth mode mismatch between gateway and Control UI
- Tailscale Serve/Funnel confusion
- pairing code not approved yet

### NanoClaw

- v1 `/setup` guidance used against a v2 checkout
- Docker / Apple Container missing
- OneCLI migration not completed
- skill branch or channel fork not merged
- service not actually running

### PicoClaw

- launcher works locally but not remotely because it binds to localhost
- config schema version mismatch
- secrets stored in the wrong file
- `restrict_to_workspace` blocking expected access
- Android/public-mode confusion
- Gatekeeper blocking launcher on macOS

## Recovery philosophy

Prefer:

- one fix
- one verification
- one next branch

Over:

- five guesses
- no verification
- no decision point
