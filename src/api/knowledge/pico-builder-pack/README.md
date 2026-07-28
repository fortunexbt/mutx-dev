# PicoMUTX Builder Pack

This pack is for a Custom GPT that acts as a high-end coach for self-hosted AI agents, with a **Hermes-first** recommendation stance and explicit support for **OpenClaw, NanoClaw, PicoClaw, and Tailscale**.

Refreshed against official docs and release surfaces on **2026-04-15**.

## What goes where

- Put `SYSTEM_PROMPT.md` into the GPT Builder **Instructions** field.
- Upload all other `.md` files as GPT knowledge.
- Enable **web browsing**.
- If your workspace supports reading uploaded files, screenshots, or logs, enable that too.
- Do **not** assume shell access to the user’s machine.
- If you plan to connect external APIs, choose **Apps or Actions**, not both at the same time.

## Current GPT builder reality

Official OpenAI docs now describe GPTs as including:

- instructions
- knowledge
- capabilities
- apps
- actions
- version history

Building and editing GPTs is done on the **web** experience. Knowledge files remain useful even if your workspace also supports ChatGPT Skills; they solve different problems.

## Why the split exists

The instruction field should hold the invariant operating behavior.

The knowledge files hold:

- stack-specific detail
- decision logic
- troubleshooting patterns
- examples
- source references that evolve over time

## File map

1. `SYSTEM_PROMPT.md` — main instruction set for the GPT
2. `BUILDER_SETUP.md` — builder configuration checklist
3. `SCOPE_AND_PERSONA.md` — mission, audience, stance, non-goals
4. `INTERACTION_PROTOCOL.md` — conversation flow
5. `USER_PROFILING.md` — question bank and skill-level detection
6. `INSTALL_FLOW.md` — install workflow across stacks
7. `TROUBLESHOOTING_FLOW.md` — diagnostic tree
8. `COMMAND_FORMAT.md` — command and output formatting rules
9. `WEB_RESEARCH_POLICY.md` — source hierarchy and recency rules
10. `SAFETY_POLICY.md` — confirmations, secrets, and exposure rules
11. `TAILSCALE_PLAYBOOK.md` — secure networking guidance
12. `HERMES.md` — Hermes product profile and cues
13. `OPENCLAW.md` — OpenClaw product profile and cues
14. `NANOCLAW.md` — NanoClaw product profile and cues
15. `PICOCLAW.md` — PicoClaw product profile and cues
16. `DECISION_MATRIX.md` — which stack to recommend
17. `SKILL.md` — condensed operational behavior
18. `TOOLS.md` — conceptual tool-selection logic
19. `EXAMPLES.md` — style calibration examples
20. `README.md` — this file
21. `CUSTOMGPT_INSTRUCTIONS_UPDATED.md` — an expanded replacement for the old PicoMUTX instruction block
22. `UPDATE_NOTES.md` — what changed in every file

## Recommended GPT naming

- PicoMUTX Agent Ops Guide
- PicoMUTX Self-Hosted Agent Coach
- PicoMUTX Install & Repair Mentor
- PicoMUTX Hermes + Claw Stack Guide

## Update rhythm

Refresh the pack when:

- install commands change
- runtime floors change
- provider auth paths change
- new releases introduce or remove major features
- Tailscale guidance changes materially
- OpenAI GPT builder behavior changes in a way that affects knowledge / actions / capabilities

## Current product notes worth knowing

- Hermes now has official Termux docs, a local dashboard, an OpenAI-compatible API server, and six terminal backends.
- OpenClaw now recommends Node 24, uses stricter config validation, and has clearer auth-profile and Tailscale dashboard flows.
- NanoClaw v2 now uses the shell-driven `nanoclaw.sh` bootstrap with OneCLI, Docker, and Claude Code.
- PicoClaw now has config schema v2, `.security.yml`, Android APK install, a mature launcher/TUI split, and official Docker Compose flows.

## Recommended validation before publishing

Test at least these:

- a beginner asks for the “best” stack with no details
- an advanced user asks for direct Hermes VPS commands
- a user posts a broken OpenClaw dashboard or channel login
- a user hits NanoClaw OneCLI, container, or v1-to-v2 migration confusion
- a user wants PicoClaw on low-cost hardware or Android
- a user wants private remote access via Tailscale instead of opening ports

## Failure conditions

The GPT is not ready if it:

- answers from stale memory when current docs matter
- recommends public exposure before private networking
- mixes shells in one code block
- invents tool access or machine state
- ignores stack-specific auth/runtime changes
- asks for real name or email without a real operational need
