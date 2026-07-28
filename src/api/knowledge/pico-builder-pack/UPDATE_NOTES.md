# Update Notes

Refreshed on 2026-07-22.

Every uploaded `.md` file was changed with at least one real improvement. The pack now reflects current official docs more closely and also tightens behavior where the old pack was weak or contradictory.

## File-by-file changes

### `SYSTEM_PROMPT.md`
- Rewritten around current stack realities.
- Added current Hermes/OpenClaw/NanoClaw/PicoClaw/Tailscale facts.
- Added stronger install, troubleshooting, and telemetry guardrails.

### `SKILL.md`
- Bumped to version 2.0.0.
- Added version-sensitive browse triggers and safer defaults.
- Tightened operational behavior.

### `TOOLS.md`
- Expanded browsing order and conflict handling.
- Added screenshot/log/config reasoning guidance.
- Strengthened the “no remote shell assumption”.

### `WEB_RESEARCH_POLICY.md`
- Added stronger recency rules for provider auth, billing, and schema changes.
- Added builder-specific OpenAI docs rule.
- Added better fallback behavior when browsing is inconclusive.

### `USER_PROFILING.md`
- Added stack-specific question banks for Hermes/OpenClaw/NanoClaw/PicoClaw.
- Added more advanced-signal detection.
- Improved pacing rules.

### `TROUBLESHOOTING_FLOW.md`
- Added more precise failing layers.
- Added stack-specific fast pivots.
- Added auth/credential-store diagnostics and version-drift checks.

### `TAILSCALE_PLAYBOOK.md`
- Added Serve vs Funnel nuance, identity headers, SSH Console beta, and safer defaults.
- Tightened remote-admin guidance.
- Updated diagnostic commands and public-sharing rules.

### `SCOPE_AND_PERSONA.md`
- Broadened scope to dashboards, launchers, API servers, and memory/skills.
- Sharpened working style and non-goals.

### `SAFETY_POLICY.md`
- Added provider-auth nuances for OpenClaw, NanoClaw, PicoClaw, and Hermes.
- Added telemetry/privacy guidance.
- Added supply-chain caution for plugins and skills.

### `README.md`
- Updated to current GPT builder concepts.
- Added a cleaner file map and update rhythm.
- Added current product notes and validation advice.

### `BUILDER_SETUP.md`
- Updated for current GPT builder behavior.
- Added apps vs actions rule, web-only build/edit note, and admin/workspace caveats.
- Added stronger acceptance tests.

### `INTERACTION_PROTOCOL.md`
- Added a freshness check in the turn loop.
- Added evidence-first handling and conflict handling.
- Reduced generic-question drift.

### `INSTALL_FLOW.md`
- Reworked install order and stack-specific cues.
- Added current auth/runtime distinctions.
- Improved verification discipline.

### `COMMAND_FORMAT.md`
- Added multi-platform splitting rules.
- Improved verification and rollback expectations.
- Added clearer risky-command handling.

### `DECISION_MATRIX.md`
- Added stronger tradeoff language and tie-breakers.
- Updated stack distinctions with current product realities.
- Preserved the Hermes-first default while making the exceptions clearer.

### `EXAMPLES.md`
- Replaced the retired NanoClaw v1 `/setup` path with the v2 `nanoclaw.sh` bootstrap.
- Refreshed the audited release locks to Hermes v2026.7.20, OpenClaw v2026.7.1, NanoClaw v2.1.17, and PicoClaw v0.3.1.
- Removed guessed runtime configs, a nonexistent mutable NanoClaw image, and unpinned installer paths from generated packages.
- Added Tailscale remote-dashboard example.
- Improved examples for fast-path vs diagnostic-path behavior.

### `HERMES.md`
- Updated for current dashboard, API server, Termux, context-files, and backend realities.
- Added better product fit signals and cautions.
- Added official links for the new surfaces.

### `OPENCLAW.md`
- Updated for Node 24, Control UI, strict config validation, auth profiles, Tailscale, and provider-auth changes.
- Added current troubleshooting themes and auth guidance.
- Clarified Telegram and pairing behavior.

### `NANOCLAW.md`
- Updated for OneCLI Agent Vault, Claude Code workflow, branch-based skills, and modern installation requirements.
- Added better troubleshooting and architecture notes.
- Added guidance for WSL and channel forks.

### `PICOCLAW.md`
- Updated for config schema 2, `.security.yml`, launcher/TUI split, Docker, Android, and core-vs-launcher build requirements.
- Added stronger security and remote-access caveats.
- Clarified modern command surfaces and troubleshooting.

## Biggest instruction fix

The old custom instruction block had a real contradiction:

- it said not to request personal data by default
- then forced USER telemetry with “user name & email”

That is now fixed. The updated instruction set makes telemetry conditional, tool-aware, redacted, and optional when no compatible embed tool exists.
