#!/usr/bin/env python3
"""Generate 100 GitHub issues for the MUTX project.

Usage:
    python scripts/create_issues.py              # dry-run (prints issues)
    python scripts/create_issues.py --execute    # creates issues via `gh`
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Issue definition
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    title: str
    body: str
    labels: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Issue catalogue – 100 issues across all project areas
# ---------------------------------------------------------------------------

ISSUES: list[Issue] = [
    # ── area:api  (20 issues) ──────────────────────────────────────────────
    Issue(
        title="feat(api): add pagination to GET /agents endpoint",
        body=(
            "## Problem\n"
            "The `GET /agents` endpoint returns all agents without pagination, "
            "which will not scale for users with many agents.\n\n"
            "## Proposed change\n"
            "Add `limit` and `offset` query parameters with sensible defaults "
            "(e.g. limit=20, max 100).\n\n"
            "## Acceptance criteria\n"
            "- `GET /agents` accepts `limit` and `offset` query params\n"
            "- Response includes `total` count\n"
            "- Default limit is 20\n"
            "- Tests cover pagination edge cases"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): add pagination to GET /deployments endpoint",
        body=(
            "## Problem\n"
            "The `GET /deployments` endpoint returns all deployments without pagination.\n\n"
            "## Proposed change\n"
            "Add `limit` and `offset` query parameters matching the pattern used in "
            "`GET /agents`.\n\n"
            "## Acceptance criteria\n"
            "- `GET /deployments` accepts `limit` and `offset` query params\n"
            "- Response includes `total` count\n"
            "- Tests cover pagination"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): add filtering by status on GET /agents",
        body=(
            "## Problem\n"
            "Operators need to filter agents by status (running, stopped, errored) "
            "but the endpoint does not support filtering.\n\n"
            "## Proposed change\n"
            "Add a `status` query parameter to `GET /agents`.\n\n"
            "## Acceptance criteria\n"
            "- `GET /agents?status=running` returns only running agents\n"
            "- Invalid status values return 422\n"
            "- Tests cover all valid statuses"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): add filtering by status on GET /deployments",
        body=(
            "## Problem\n"
            "Operators need to filter deployments by status (active, stopped, failed) "
            "but the endpoint does not support filtering.\n\n"
            "## Proposed change\n"
            "Add a `status` query parameter to `GET /deployments`.\n\n"
            "## Acceptance criteria\n"
            "- `GET /deployments?status=active` returns only active deployments\n"
            "- Invalid status values return 422\n"
            "- Tests cover all valid statuses"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): return created_at and updated_at on all resource responses",
        body=(
            "## Problem\n"
            "Some API responses omit timestamp fields, making it hard to sort or "
            "audit resources by recency.\n\n"
            "## Proposed change\n"
            "Ensure all resource schemas include `created_at` and `updated_at` as "
            "ISO 8601 strings.\n\n"
            "## Acceptance criteria\n"
            "- Agent, Deployment, Webhook, and API Key responses include timestamps\n"
            "- Timestamps are ISO 8601 format\n"
            "- Existing tests are updated"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): add PATCH /agents/{id} for partial updates",
        body=(
            "## Problem\n"
            "There is no way to partially update an agent's configuration without "
            "re-sending the entire payload.\n\n"
            "## Proposed change\n"
            "Add a `PATCH /agents/{id}` endpoint that accepts partial updates.\n\n"
            "## Acceptance criteria\n"
            "- `PATCH /agents/{id}` accepts partial JSON body\n"
            "- Only provided fields are updated\n"
            "- Returns updated agent\n"
            "- Ownership is enforced\n"
            "- Tests cover partial update scenarios"
        ),
        labels=["area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(api): add PATCH /deployments/{id} for partial updates",
        body=(
            "## Problem\n"
            "Deployment configuration cannot be partially updated.\n\n"
            "## Proposed change\n"
            "Add a `PATCH /deployments/{id}` endpoint for partial updates.\n\n"
            "## Acceptance criteria\n"
            "- `PATCH /deployments/{id}` accepts partial JSON body\n"
            "- Only provided fields are updated\n"
            "- Ownership is enforced\n"
            "- Tests cover scenarios"
        ),
        labels=["area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(api): add deployment events and lifecycle history endpoint",
        body=(
            "## Problem\n"
            "There is no way to see the history of state transitions for a deployment.\n\n"
            "## Proposed change\n"
            "Add `GET /deployments/{id}/events` that returns a time-ordered list "
            "of lifecycle events (created, started, stopped, failed, etc.).\n\n"
            "## Acceptance criteria\n"
            "- Deployment events are recorded on state transitions\n"
            "- `GET /deployments/{id}/events` returns ordered event list\n"
            "- Each event includes timestamp, type, and optional metadata\n"
            "- Tests cover event recording and retrieval"
        ),
        labels=["area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(api): add API key scoping with granular permissions",
        body=(
            "## Problem\n"
            "API keys currently grant full access. Operators need the ability to "
            "create keys with limited scopes.\n\n"
            "## Proposed change\n"
            "Add a `scopes` field to API key creation that limits which operations "
            "the key can perform (e.g. `agents:read`, `deployments:write`).\n\n"
            "## Acceptance criteria\n"
            "- API keys can be created with specific scopes\n"
            "- Scoped keys are rejected for operations outside their scope\n"
            "- Default scope is full access for backward compatibility\n"
            "- Tests cover scope enforcement"
        ),
        labels=["area:api", "area:auth", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(api): add rate limit headers to all responses",
        body=(
            "## Problem\n"
            "Clients have no visibility into their rate limit status.\n\n"
            "## Proposed change\n"
            "Include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and "
            "`X-RateLimit-Reset` headers in all API responses.\n\n"
            "## Acceptance criteria\n"
            "- All responses include rate limit headers\n"
            "- Values accurately reflect current state\n"
            "- Tests verify header presence and values"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="fix(api): return 404 instead of 500 for non-existent agent IDs",
        body=(
            "## Problem\n"
            "Requesting a non-existent agent ID returns a 500 error instead of 404.\n\n"
            "## Reproduction steps\n"
            "1. `GET /agents/nonexistent-uuid`\n"
            "2. Observe 500 response\n\n"
            "## Expected behavior\n"
            "Should return 404 with a clear error message.\n\n"
            "## Acceptance criteria\n"
            "- Non-existent agent ID returns 404\n"
            "- Error body includes resource type and ID\n"
            "- Test covers this case"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="fix(api): return 404 instead of 500 for non-existent deployment IDs",
        body=(
            "## Problem\n"
            "Requesting a non-existent deployment ID returns a 500 error.\n\n"
            "## Reproduction steps\n"
            "1. `GET /deployments/nonexistent-uuid`\n"
            "2. Observe 500 response\n\n"
            "## Expected behavior\n"
            "Should return 404.\n\n"
            "## Acceptance criteria\n"
            "- Non-existent deployment ID returns 404\n"
            "- Error body includes resource type and ID\n"
            "- Test covers this case"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): add search endpoint for agents",
        body=(
            "## Problem\n"
            "Users with many agents cannot search for a specific agent by name.\n\n"
            "## Proposed change\n"
            "Add a `q` query parameter to `GET /agents` for name-based search.\n\n"
            "## Acceptance criteria\n"
            "- `GET /agents?q=my-agent` filters by name substring\n"
            "- Search is case-insensitive\n"
            "- Returns empty list when no matches\n"
            "- Tests cover search behavior"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): add bulk delete endpoint for agents",
        body=(
            "## Problem\n"
            "Cleaning up multiple agents requires individual DELETE requests.\n\n"
            "## Proposed change\n"
            "Add `DELETE /agents/bulk` that accepts an array of agent IDs.\n\n"
            "## Acceptance criteria\n"
            "- Accepts array of agent IDs in request body\n"
            "- Deletes all specified agents in a single transaction\n"
            "- Returns count of deleted agents\n"
            "- Ownership enforced per-agent\n"
            "- Tests cover bulk deletion"
        ),
        labels=["area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(api): add webhook signature verification",
        body=(
            "## Problem\n"
            "Webhook consumers have no way to verify that payloads came from MUTX.\n\n"
            "## Proposed change\n"
            "Sign webhook payloads with HMAC-SHA256 using a per-webhook secret and "
            "include the signature in the `X-MUTX-Signature` header.\n\n"
            "## Acceptance criteria\n"
            "- Webhook payloads include `X-MUTX-Signature` header\n"
            "- Signature can be verified using the webhook secret\n"
            "- Documentation updated with verification example\n"
            "- Tests cover signature generation and verification"
        ),
        labels=["area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(api): add typed agent config schema validation",
        body=(
            "## Problem\n"
            "Agent config is stored as an untyped string blob, allowing invalid "
            "configurations to be persisted.\n\n"
            "## Proposed change\n"
            "Define a typed Pydantic schema for agent config and validate on "
            "create/update.\n\n"
            "## Acceptance criteria\n"
            "- Agent config has a defined Pydantic schema\n"
            "- Invalid configs are rejected with 422\n"
            "- Existing valid configs continue to work\n"
            "- Tests cover schema validation"
        ),
        labels=["area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(api): add health check dependencies to /health endpoint",
        body=(
            "## Problem\n"
            "The `/health` endpoint returns a simple OK but doesn't check database "
            "or other service dependencies.\n\n"
            "## Proposed change\n"
            "Add dependency health checks (database connectivity, etc.) to the "
            "health endpoint with a detailed breakdown.\n\n"
            "## Acceptance criteria\n"
            "- `/health` checks database connectivity\n"
            "- Response includes per-dependency status\n"
            "- Overall status is degraded if any dependency fails\n"
            "- Tests cover healthy and degraded scenarios"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): add request ID tracking across all endpoints",
        body=(
            "## Problem\n"
            "There is no correlation ID for tracing requests through the system.\n\n"
            "## Proposed change\n"
            "Generate a unique request ID for each API request and include it in "
            "the response as `X-Request-ID`. Accept a client-provided ID.\n\n"
            "## Acceptance criteria\n"
            "- All responses include `X-Request-ID` header\n"
            "- Accepts optional `X-Request-ID` from client\n"
            "- ID is included in log entries\n"
            "- Tests verify header behavior"
        ),
        labels=["area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(api): add API versioning strategy",
        body=(
            "## Problem\n"
            "There is no clear API versioning strategy, which creates risk for "
            "breaking changes.\n\n"
            "## Proposed change\n"
            "Document and implement a versioning strategy using URL path prefix "
            "(e.g. `/v1/agents`). Ensure the current routes work under both "
            "versioned and unversioned paths during transition.\n\n"
            "## Acceptance criteria\n"
            "- API routes accessible under `/v1/` prefix\n"
            "- Unversioned routes redirect or alias to `/v1/`\n"
            "- Versioning strategy documented\n"
            "- Tests cover both paths"
        ),
        labels=["area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(api): add OpenAPI spec auto-generation from FastAPI",
        body=(
            "## Problem\n"
            "The OpenAPI spec may drift from the actual FastAPI routes.\n\n"
            "## Proposed change\n"
            "Auto-generate the OpenAPI spec from FastAPI route definitions and "
            "add a CI check to detect drift.\n\n"
            "## Acceptance criteria\n"
            "- OpenAPI spec generated from FastAPI automatically\n"
            "- CI fails if spec is out of date\n"
            "- `scripts/generate_openapi.py` updated to use FastAPI export\n"
            "- Tests verify spec accuracy"
        ),
        labels=["area:api", "area:test", "size:s", "risk:low"],
    ),
    # ── area:web  (18 issues) ──────────────────────────────────────────────
    Issue(
        title="feat(web): add authenticated agent list view to dashboard",
        body=(
            "## Problem\n"
            "The dashboard does not display the user's agents. Operators must use "
            "the API directly to see their agents.\n\n"
            "## Proposed change\n"
            "Add a `/dashboard/agents` page that fetches and displays the "
            "authenticated user's agents in a table.\n\n"
            "## Acceptance criteria\n"
            "- Dashboard shows agent list with name, status, and created date\n"
            "- Data fetched from authenticated API\n"
            "- Empty state shown when no agents exist\n"
            "- Loading and error states handled"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add authenticated deployment list view to dashboard",
        body=(
            "## Problem\n"
            "The dashboard does not display deployments. Operators must use the "
            "API to see deployment status.\n\n"
            "## Proposed change\n"
            "Add a `/dashboard/deployments` page showing the user's deployments.\n\n"
            "## Acceptance criteria\n"
            "- Dashboard shows deployment list with name, status, agent, and date\n"
            "- Data fetched from authenticated API\n"
            "- Empty and error states handled\n"
            "- Links to individual deployment detail"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add agent detail page with config and status",
        body=(
            "## Problem\n"
            "There is no detail view for individual agents in the dashboard.\n\n"
            "## Proposed change\n"
            "Add `/dashboard/agents/[id]` page showing agent details, "
            "configuration, and current status.\n\n"
            "## Acceptance criteria\n"
            "- Agent detail page shows name, status, config, timestamps\n"
            "- Back navigation to agent list\n"
            "- 404 handling for non-existent agents\n"
            "- Loading state while fetching"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add deployment detail page with lifecycle events",
        body=(
            "## Problem\n"
            "There is no detail view for deployments in the dashboard.\n\n"
            "## Proposed change\n"
            "Add `/dashboard/deployments/[id]` page showing deployment details "
            "and lifecycle history.\n\n"
            "## Acceptance criteria\n"
            "- Deployment detail shows status, agent reference, timestamps\n"
            "- Lifecycle events shown in timeline format\n"
            "- 404 handling for non-existent deployments\n"
            "- Loading state"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add API key management page to dashboard",
        body=(
            "## Problem\n"
            "Users cannot manage API keys from the dashboard.\n\n"
            "## Proposed change\n"
            "Add `/dashboard/api-keys` page for creating, viewing, and revoking "
            "API keys.\n\n"
            "## Acceptance criteria\n"
            "- Page lists existing API keys (masked)\n"
            "- Create new key with optional name and scopes\n"
            "- Revoke existing keys\n"
            "- Copy key to clipboard on creation\n"
            "- Confirmation dialog before revocation"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add global search to dashboard navigation",
        body=(
            "## Problem\n"
            "Users cannot quickly find agents or deployments from the dashboard.\n\n"
            "## Proposed change\n"
            "Add a search bar to the dashboard navigation that searches across "
            "agents and deployments.\n\n"
            "## Acceptance criteria\n"
            "- Search bar visible in dashboard header\n"
            "- Results show agents and deployments matching query\n"
            "- Keyboard shortcut (Cmd/Ctrl+K) to focus search\n"
            "- Results link to detail pages"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add dashboard sidebar navigation",
        body=(
            "## Problem\n"
            "The dashboard lacks structured navigation between sections.\n\n"
            "## Proposed change\n"
            "Add a collapsible sidebar with links to Agents, Deployments, "
            "API Keys, Webhooks, and Settings.\n\n"
            "## Acceptance criteria\n"
            "- Sidebar with navigation links\n"
            "- Active page highlighted\n"
            "- Collapsible on mobile\n"
            "- Consistent with existing design system"
        ),
        labels=["area:web", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(web): add real-time status indicators for agents",
        body=(
            "## Problem\n"
            "Agent status in the dashboard is static and requires manual refresh.\n\n"
            "## Proposed change\n"
            "Add color-coded status badges that update periodically or via "
            "server-sent events.\n\n"
            "## Acceptance criteria\n"
            "- Status badges show running (green), stopped (gray), errored (red)\n"
            "- Status updates at least every 30 seconds\n"
            "- Visual indicator when refreshing\n"
            "- Works on agent list and detail pages"
        ),
        labels=["area:web", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(web): add webhook management page to dashboard",
        body=(
            "## Problem\n"
            "Webhook configuration must be done via API. There is no UI.\n\n"
            "## Proposed change\n"
            "Add `/dashboard/webhooks` page for creating, listing, testing, and "
            "deleting webhooks.\n\n"
            "## Acceptance criteria\n"
            "- List existing webhooks with URL, events, and status\n"
            "- Create new webhook with URL and event selection\n"
            "- Test webhook delivery from UI\n"
            "- Delete webhook with confirmation"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add contact form with real persistence",
        body=(
            "## Problem\n"
            "The contact form on the marketing site does not persist submissions.\n\n"
            "## Proposed change\n"
            "Wire the contact form to the API backend so submissions are stored "
            "in the database.\n\n"
            "## Acceptance criteria\n"
            "- Contact form submits to API endpoint\n"
            "- Success/error feedback shown to user\n"
            "- Input validation on client and server\n"
            "- Rate limiting to prevent spam"
        ),
        labels=["area:web", "area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(web): add dark mode toggle to dashboard",
        body=(
            "## Problem\n"
            "The dashboard only has one color theme. Users may prefer dark mode.\n\n"
            "## Proposed change\n"
            "Add a dark mode toggle that persists preference in localStorage and "
            "respects system preference by default.\n\n"
            "## Acceptance criteria\n"
            "- Toggle in dashboard header\n"
            "- Preference persisted across sessions\n"
            "- Respects `prefers-color-scheme` on first visit\n"
            "- All dashboard components styled for both modes"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add error boundary components for dashboard",
        body=(
            "## Problem\n"
            "Unhandled component errors crash the entire dashboard.\n\n"
            "## Proposed change\n"
            "Add React error boundaries around dashboard sections to contain "
            "failures and show recovery options.\n\n"
            "## Acceptance criteria\n"
            "- Error boundaries catch component errors\n"
            "- Friendly error message shown with retry option\n"
            "- Error details logged for debugging\n"
            "- Other dashboard sections remain functional"
        ),
        labels=["area:web", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(web): add loading skeletons for dashboard data",
        body=(
            "## Problem\n"
            "Dashboard pages show nothing or a spinner while data loads, which "
            "feels slow and unprofessional.\n\n"
            "## Proposed change\n"
            "Add skeleton loading states that match the layout of the final content.\n\n"
            "## Acceptance criteria\n"
            "- Agent list shows skeleton rows while loading\n"
            "- Deployment list shows skeleton rows\n"
            "- Detail pages show skeleton layout\n"
            "- Skeletons animate with pulse effect"
        ),
        labels=["area:web", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(web): add toast notification system for dashboard",
        body=(
            "## Problem\n"
            "User actions (create, delete, update) have no clear feedback mechanism.\n\n"
            "## Proposed change\n"
            "Add a toast/notification system for success, error, and info messages.\n\n"
            "## Acceptance criteria\n"
            "- Toast notifications appear on actions\n"
            "- Auto-dismiss after configurable duration\n"
            "- Success (green), error (red), info (blue) variants\n"
            "- Accessible with screen readers"
        ),
        labels=["area:web", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(web): add responsive mobile layout for dashboard",
        body=(
            "## Problem\n"
            "The dashboard is not optimized for mobile viewports.\n\n"
            "## Proposed change\n"
            "Add responsive breakpoints and mobile-friendly layouts for all "
            "dashboard pages.\n\n"
            "## Acceptance criteria\n"
            "- Dashboard is usable on mobile (375px+)\n"
            "- Tables convert to card layout on small screens\n"
            "- Navigation collapses to hamburger menu\n"
            "- Touch targets meet accessibility guidelines"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add user profile and settings page",
        body=(
            "## Problem\n"
            "There is no way for users to view or update their profile from the UI.\n\n"
            "## Proposed change\n"
            "Add `/dashboard/settings` page with profile information and account "
            "settings.\n\n"
            "## Acceptance criteria\n"
            "- Settings page shows user email and display name\n"
            "- Users can update display name\n"
            "- Password change with current password confirmation\n"
            "- Form validation and error handling"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(web): add agent create form to dashboard",
        body=(
            "## Problem\n"
            "Users cannot create agents from the UI and must use the API or CLI.\n\n"
            "## Proposed change\n"
            "Add an agent creation form accessible from the agent list page.\n\n"
            "## Acceptance criteria\n"
            "- Create button on agent list page\n"
            "- Form with name, description, and config fields\n"
            "- Validation and error feedback\n"
            "- Redirect to agent detail on success\n"
            "- Cancel returns to list"
        ),
        labels=["area:web", "size:m", "risk:low"],
    ),
    Issue(
        title="fix(web): fix session expiry handling in dashboard",
        body=(
            "## Problem\n"
            "When the user's session expires, the dashboard shows broken states "
            "instead of redirecting to login.\n\n"
            "## Reproduction steps\n"
            "1. Log in to dashboard\n"
            "2. Wait for session to expire\n"
            "3. Navigate to any page\n"
            "4. Observe broken state\n\n"
            "## Expected behavior\n"
            "Redirect to login with a message.\n\n"
            "## Acceptance criteria\n"
            "- 401 responses trigger redirect to login\n"
            "- Session expired message shown\n"
            "- Return URL preserved for post-login redirect"
        ),
        labels=["area:web", "area:auth", "size:s", "risk:low"],
    ),
    # ── area:cli-sdk  (12 issues) ──────────────────────────────────────────
    Issue(
        title="fix(cli): fix mutx agents create to use current API contract",
        body=(
            "## Problem\n"
            "The `mutx agents create` command uses stale route paths and payload "
            "format that do not match the current API.\n\n"
            "## Proposed change\n"
            "Update the command to use the correct route and payload schema.\n\n"
            "## Acceptance criteria\n"
            "- `mutx agents create --name test` succeeds against running API\n"
            "- Route path matches current FastAPI definition\n"
            "- Tests verify command behavior"
        ),
        labels=["area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="fix(cli): fix mutx deploy create to use current API contract",
        body=(
            "## Problem\n"
            "The `mutx deploy create` command uses stale route paths.\n\n"
            "## Proposed change\n"
            "Update the command to use the correct route and payload.\n\n"
            "## Acceptance criteria\n"
            "- `mutx deploy create` succeeds against running API\n"
            "- Route path matches current FastAPI definition\n"
            "- Tests verify command behavior"
        ),
        labels=["area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(cli): add mutx agents list with table output",
        body=(
            "## Problem\n"
            "The CLI agent listing output is not well-formatted for terminal use.\n\n"
            "## Proposed change\n"
            "Format `mutx agents list` output as a clean table with columns for "
            "ID, name, status, and created date.\n\n"
            "## Acceptance criteria\n"
            "- Output formatted as aligned table\n"
            "- Columns: ID, Name, Status, Created\n"
            "- `--json` flag for machine-readable output\n"
            "- Empty state message when no agents"
        ),
        labels=["area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(cli): add mutx agents delete command",
        body=(
            "## Problem\n"
            "There is no CLI command to delete agents.\n\n"
            "## Proposed change\n"
            "Add `mutx agents delete <id>` command.\n\n"
            "## Acceptance criteria\n"
            "- `mutx agents delete <id>` deletes the agent\n"
            "- Confirmation prompt before deletion\n"
            "- `--force` flag to skip confirmation\n"
            "- Success and error messages\n"
            "- Tests cover command"
        ),
        labels=["area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(cli): add mutx deploy list with status indicators",
        body=(
            "## Problem\n"
            "Deployment listing in the CLI lacks status context.\n\n"
            "## Proposed change\n"
            "Format `mutx deploy list` with colored status indicators.\n\n"
            "## Acceptance criteria\n"
            "- Output formatted as table with colored status\n"
            "- Green for active, red for failed, gray for stopped\n"
            "- `--json` flag for machine output\n"
            "- Tests cover output formatting"
        ),
        labels=["area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(cli): add mutx config command for local settings",
        body=(
            "## Problem\n"
            "Users must set environment variables to configure the CLI.\n\n"
            "## Proposed change\n"
            "Add `mutx config set/get/list` commands that manage a local config "
            "file (~/.mutx/config.json).\n\n"
            "## Acceptance criteria\n"
            "- `mutx config set api_url https://...` persists setting\n"
            "- `mutx config get api_url` retrieves setting\n"
            "- `mutx config list` shows all settings\n"
            "- Config file created automatically\n"
            "- Tests cover config operations"
        ),
        labels=["area:cli-sdk", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(cli): add mutx status command for quick overview",
        body=(
            "## Problem\n"
            "Users have no quick way to see overall system status from the CLI.\n\n"
            "## Proposed change\n"
            "Add `mutx status` command that shows agent count, deployment count, "
            "and API health.\n\n"
            "## Acceptance criteria\n"
            "- Shows total agents and their status breakdown\n"
            "- Shows total deployments and their status breakdown\n"
            "- Shows API connectivity status\n"
            "- Handles offline API gracefully\n"
            "- Tests cover command"
        ),
        labels=["area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(sdk): align MutxClient methods with current API routes",
        body=(
            "## Problem\n"
            "The SDK `MutxClient` has methods that use stale API routes and "
            "parameters.\n\n"
            "## Proposed change\n"
            "Audit all SDK methods and align them with the current FastAPI "
            "contract.\n\n"
            "## Acceptance criteria\n"
            "- All SDK methods use correct API routes\n"
            "- Method signatures match API schemas\n"
            "- Deprecated methods are marked with warnings\n"
            "- Contract tests pass against live API"
        ),
        labels=["area:cli-sdk", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(sdk): add typed response models for all SDK methods",
        body=(
            "## Problem\n"
            "SDK methods return raw dictionaries instead of typed objects.\n\n"
            "## Proposed change\n"
            "Define Pydantic response models for agents, deployments, webhooks, "
            "and API keys. Parse all SDK responses into typed models.\n\n"
            "## Acceptance criteria\n"
            "- Response models defined for all resources\n"
            "- SDK methods return typed objects\n"
            "- Backward-compatible `.dict()` method available\n"
            "- Tests cover model parsing"
        ),
        labels=["area:cli-sdk", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(sdk): add retry logic with exponential backoff",
        body=(
            "## Problem\n"
            "SDK requests fail immediately on transient errors without retrying.\n\n"
            "## Proposed change\n"
            "Add configurable retry logic with exponential backoff for 5xx errors "
            "and connection failures.\n\n"
            "## Acceptance criteria\n"
            "- Retries on 500, 502, 503, 504 status codes\n"
            "- Retries on connection errors\n"
            "- Exponential backoff with jitter\n"
            "- Max retries configurable (default 3)\n"
            "- Tests cover retry behavior"
        ),
        labels=["area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(sdk): add async client support",
        body=(
            "## Problem\n"
            "`MutxAsyncClient` is deprecated but users need async support.\n\n"
            "## Proposed change\n"
            "Rebuild `MutxAsyncClient` with proper async methods matching the "
            "sync client API.\n\n"
            "## Acceptance criteria\n"
            "- All sync methods have async equivalents\n"
            "- Shared configuration between sync and async clients\n"
            "- async client tests using pytest-asyncio\n"
            "- Documentation updated"
        ),
        labels=["area:cli-sdk", "size:m", "risk:medium"],
    ),
    Issue(
        title="fix(sdk): fix base URL default to match production API",
        body=(
            "## Problem\n"
            "The SDK default base URL does not match the current production API "
            "endpoint, causing connection failures for new users.\n\n"
            "## Proposed change\n"
            "Update the default base URL to the correct production endpoint.\n\n"
            "## Acceptance criteria\n"
            "- Default base URL matches production API\n"
            "- Override still works via constructor parameter\n"
            "- Environment variable override works\n"
            "- Tests verify default URL"
        ),
        labels=["area:cli-sdk", "size:s", "risk:low"],
    ),
    # ── area:test  (15 issues) ─────────────────────────────────────────────
    Issue(
        title="test(api): add route tests for GET /agents",
        body=(
            "## Problem\n"
            "The `GET /agents` endpoint lacks test coverage.\n\n"
            "## Proposed change\n"
            "Add pytest tests for the agents list endpoint covering auth, "
            "pagination, and filtering.\n\n"
            "## Acceptance criteria\n"
            "- Test unauthenticated request returns 401\n"
            "- Test authenticated request returns agent list\n"
            "- Test empty list response\n"
            "- Test response schema"
        ),
        labels=["area:test", "area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="test(api): add route tests for POST /agents",
        body=(
            "## Problem\n"
            "The agent creation endpoint lacks test coverage.\n\n"
            "## Proposed change\n"
            "Add pytest tests for agent creation covering validation, auth, "
            "and success paths.\n\n"
            "## Acceptance criteria\n"
            "- Test valid creation returns 201\n"
            "- Test missing required fields returns 422\n"
            "- Test unauthenticated returns 401\n"
            "- Test response includes created agent"
        ),
        labels=["area:test", "area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="test(api): add route tests for GET /deployments",
        body=(
            "## Problem\n"
            "The deployments list endpoint lacks test coverage.\n\n"
            "## Proposed change\n"
            "Add pytest tests for the deployments list endpoint.\n\n"
            "## Acceptance criteria\n"
            "- Test unauthenticated request returns 401\n"
            "- Test authenticated request returns deployment list\n"
            "- Test empty list response\n"
            "- Test response schema"
        ),
        labels=["area:test", "area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="test(api): add route tests for POST /deployments",
        body=(
            "## Problem\n"
            "The deployment creation endpoint lacks test coverage.\n\n"
            "## Proposed change\n"
            "Add pytest tests for deployment creation.\n\n"
            "## Acceptance criteria\n"
            "- Test valid creation returns 201\n"
            "- Test missing fields returns 422\n"
            "- Test unauthenticated returns 401\n"
            "- Test references valid agent"
        ),
        labels=["area:test", "area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="test(api): add route tests for webhook endpoints",
        body=(
            "## Problem\n"
            "Webhook CRUD endpoints lack test coverage.\n\n"
            "## Proposed change\n"
            "Add pytest tests for webhook create, list, get, and delete.\n\n"
            "## Acceptance criteria\n"
            "- Test webhook creation with valid URL\n"
            "- Test webhook listing\n"
            "- Test webhook deletion\n"
            "- Test invalid webhook URL returns 422\n"
            "- Test ownership enforcement"
        ),
        labels=["area:test", "area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="test(api): add route tests for auth endpoints",
        body=(
            "## Problem\n"
            "Auth endpoints (register, login, refresh) lack comprehensive test "
            "coverage.\n\n"
            "## Proposed change\n"
            "Add pytest tests for all auth flows.\n\n"
            "## Acceptance criteria\n"
            "- Test registration with valid credentials\n"
            "- Test duplicate email returns 409\n"
            "- Test login with valid credentials returns token\n"
            "- Test login with invalid credentials returns 401\n"
            "- Test token refresh"
        ),
        labels=["area:test", "area:auth", "size:s", "risk:low"],
    ),
    Issue(
        title="test(api): add route tests for API key endpoints",
        body=(
            "## Problem\n"
            "API key CRUD endpoints lack test coverage.\n\n"
            "## Proposed change\n"
            "Add pytest tests for API key creation, listing, and revocation.\n\n"
            "## Acceptance criteria\n"
            "- Test key creation returns masked key\n"
            "- Test key listing\n"
            "- Test key revocation\n"
            "- Test plan-based quota enforcement\n"
            "- Test ownership"
        ),
        labels=["area:test", "area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="test(cli): add contract tests for all CLI commands",
        body=(
            "## Problem\n"
            "CLI commands lack systematic contract testing.\n\n"
            "## Proposed change\n"
            "Add contract tests that verify CLI commands produce correct API "
            "requests.\n\n"
            "## Acceptance criteria\n"
            "- Tests for agents list, create, delete\n"
            "- Tests for deploy list, create\n"
            "- Tests for auth login, register\n"
            "- Tests verify request method, path, and payload\n"
            "- Tests run without a live API"
        ),
        labels=["area:test", "area:cli-sdk", "size:m", "risk:low"],
    ),
    Issue(
        title="test(sdk): add contract tests for all SDK methods",
        body=(
            "## Problem\n"
            "SDK methods lack systematic contract testing.\n\n"
            "## Proposed change\n"
            "Add contract tests that verify SDK methods produce correct API "
            "requests.\n\n"
            "## Acceptance criteria\n"
            "- Tests for all agent methods\n"
            "- Tests for all deployment methods\n"
            "- Tests for API key methods\n"
            "- Tests verify request format\n"
            "- Tests run without live API"
        ),
        labels=["area:test", "area:cli-sdk", "size:m", "risk:low"],
    ),
    Issue(
        title="test(e2e): add Playwright tests for login flow",
        body=(
            "## Problem\n"
            "The login flow has no E2E test coverage.\n\n"
            "## Proposed change\n"
            "Add Playwright tests for the login page and authentication flow.\n\n"
            "## Acceptance criteria\n"
            "- Test login page renders\n"
            "- Test valid login redirects to dashboard\n"
            "- Test invalid login shows error\n"
            "- Test empty field validation\n"
            "- Tests run against local dev server"
        ),
        labels=["area:test", "area:web", "size:s", "risk:low"],
    ),
    Issue(
        title="test(e2e): add Playwright tests for registration flow",
        body=(
            "## Problem\n"
            "The registration flow has no E2E test coverage.\n\n"
            "## Proposed change\n"
            "Add Playwright tests for the registration page.\n\n"
            "## Acceptance criteria\n"
            "- Test registration page renders\n"
            "- Test valid registration succeeds\n"
            "- Test duplicate email shows error\n"
            "- Test password validation\n"
            "- Tests run against local dev server"
        ),
        labels=["area:test", "area:web", "size:s", "risk:low"],
    ),
    Issue(
        title="test(e2e): add Playwright tests for dashboard agent list",
        body=(
            "## Problem\n"
            "The dashboard agent list has no E2E test coverage.\n\n"
            "## Proposed change\n"
            "Add Playwright tests for the agent list page.\n\n"
            "## Acceptance criteria\n"
            "- Test authenticated access to agent list\n"
            "- Test agent list renders with data\n"
            "- Test empty state\n"
            "- Test navigation to agent detail"
        ),
        labels=["area:test", "area:web", "size:s", "risk:low"],
    ),
    Issue(
        title="test: add CI check for test coverage thresholds",
        body=(
            "## Problem\n"
            "There is no enforcement of test coverage in CI.\n\n"
            "## Proposed change\n"
            "Add a CI step that checks coverage thresholds and fails if they drop "
            "below the minimum.\n\n"
            "## Acceptance criteria\n"
            "- CI runs coverage report\n"
            "- Fails if coverage drops below threshold (e.g. 60%)\n"
            "- Coverage report uploaded as artifact\n"
            "- Threshold is configurable"
        ),
        labels=["area:test", "size:s", "risk:low"],
    ),
    Issue(
        title="test: add mutation testing to identify weak tests",
        body=(
            "## Problem\n"
            "Test suite quality is unknown. Tests may pass but not catch bugs.\n\n"
            "## Proposed change\n"
            "Add mutation testing (e.g. mutmut for Python) to measure test "
            "effectiveness.\n\n"
            "## Acceptance criteria\n"
            "- Mutation testing runs on Python backend tests\n"
            "- Results report generated\n"
            "- High-value surviving mutants identified\n"
            "- Documentation for running locally"
        ),
        labels=["area:test", "size:m", "risk:low"],
    ),
    Issue(
        title="test: add local-first Playwright configuration",
        body=(
            "## Problem\n"
            "Playwright tests currently target the hosted site, not the local dev "
            "server, making local development harder.\n\n"
            "## Proposed change\n"
            "Update Playwright config to default to local dev server and add a "
            "setup script.\n\n"
            "## Acceptance criteria\n"
            "- Playwright defaults to localhost:3000\n"
            "- `npx playwright test` works against local dev\n"
            "- CI can override to hosted URL\n"
            "- Setup script documented"
        ),
        labels=["area:test", "size:s", "risk:low"],
    ),
    # ── area:docs  (10 issues) ─────────────────────────────────────────────
    Issue(
        title="docs: add quickstart guide for new contributors",
        body=(
            "## Problem\n"
            "New contributors lack a clear, step-by-step quickstart to get the "
            "development environment running.\n\n"
            "## Proposed change\n"
            "Update `docs/deployment/quickstart.md` with clear steps from clone "
            "to running tests.\n\n"
            "## Acceptance criteria\n"
            "- Step-by-step from git clone to running dev server\n"
            "- Prerequisite list (Node, Python, Docker)\n"
            "- Troubleshooting section for common issues\n"
            "- Verified by a fresh setup"
        ),
        labels=["area:docs", "size:s", "risk:low"],
    ),
    Issue(
        title="docs: add API reference documentation for all endpoints",
        body=(
            "## Problem\n"
            "API documentation is incomplete and may not match current routes.\n\n"
            "## Proposed change\n"
            "Document all API endpoints with request/response examples.\n\n"
            "## Acceptance criteria\n"
            "- All endpoints documented with method, path, params\n"
            "- Request and response body examples\n"
            "- Authentication requirements noted\n"
            "- Error responses documented"
        ),
        labels=["area:docs", "area:api", "size:m", "risk:low"],
    ),
    Issue(
        title="docs: add CLI command reference",
        body=(
            "## Problem\n"
            "CLI commands are not documented in a reference format.\n\n"
            "## Proposed change\n"
            "Add a CLI reference page with all commands, options, and examples.\n\n"
            "## Acceptance criteria\n"
            "- All commands documented with usage\n"
            "- Options and flags explained\n"
            "- Example output shown\n"
            "- Links to related API docs"
        ),
        labels=["area:docs", "area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="docs: add SDK usage guide with examples",
        body=(
            "## Problem\n"
            "The SDK has no usage guide with real examples.\n\n"
            "## Proposed change\n"
            "Add a SDK guide with common patterns and code examples.\n\n"
            "## Acceptance criteria\n"
            "- Installation instructions\n"
            "- Authentication setup example\n"
            "- Agent CRUD examples\n"
            "- Deployment examples\n"
            "- Error handling patterns"
        ),
        labels=["area:docs", "area:cli-sdk", "size:s", "risk:low"],
    ),
    Issue(
        title="docs: add architecture decision records (ADRs)",
        body=(
            "## Problem\n"
            "Key architectural decisions are not documented, making it hard for "
            "new contributors to understand design rationale.\n\n"
            "## Proposed change\n"
            "Create an ADR directory and document key decisions.\n\n"
            "## Acceptance criteria\n"
            "- `docs/architecture/decisions/` directory created\n"
            "- ADR template added\n"
            "- At least 3 initial ADRs (tech stack, auth, agent model)\n"
            "- Linked from architecture overview"
        ),
        labels=["area:docs", "size:m", "risk:low"],
    ),
    Issue(
        title="docs: add deployment guide for production",
        body=(
            "## Problem\n"
            "There is no guide for deploying MUTX to production environments.\n\n"
            "## Proposed change\n"
            "Add a production deployment guide covering Docker, environment "
            "variables, and database setup.\n\n"
            "## Acceptance criteria\n"
            "- Docker deployment steps\n"
            "- Required environment variables listed\n"
            "- Database migration instructions\n"
            "- Health check verification steps\n"
            "- Security considerations"
        ),
        labels=["area:docs", "area:infra", "size:m", "risk:low"],
    ),
    Issue(
        title="docs: add troubleshooting guide for common issues",
        body=(
            "## Problem\n"
            "Contributors frequently encounter the same issues during setup.\n\n"
            "## Proposed change\n"
            "Add a troubleshooting guide for common problems.\n\n"
            "## Acceptance criteria\n"
            "- Docker setup issues and solutions\n"
            "- Database connection problems\n"
            "- Auth token issues\n"
            "- Port conflicts\n"
            "- Node/Python version mismatches"
        ),
        labels=["area:docs", "size:s", "risk:low"],
    ),
    Issue(
        title="docs: add webhook integration guide",
        body=(
            "## Problem\n"
            "Users don't know how to set up and consume MUTX webhooks.\n\n"
            "## Proposed change\n"
            "Add a webhook guide with setup instructions and payload examples.\n\n"
            "## Acceptance criteria\n"
            "- Webhook setup walkthrough\n"
            "- Available event types listed\n"
            "- Payload format documented\n"
            "- Signature verification example\n"
            "- Retry behavior explained"
        ),
        labels=["area:docs", "area:api", "size:s", "risk:low"],
    ),
    Issue(
        title="docs: add changelog and release notes process",
        body=(
            "## Problem\n"
            "There is no standard process for tracking changes across releases.\n\n"
            "## Proposed change\n"
            "Add a CHANGELOG.md and document the release notes process.\n\n"
            "## Acceptance criteria\n"
            "- CHANGELOG.md created with current entries\n"
            "- Format follows Keep a Changelog convention\n"
            "- Process documented in CONTRIBUTING.md\n"
            "- CI check for changelog updates on PRs"
        ),
        labels=["area:docs", "size:s", "risk:low"],
    ),
    Issue(
        title="docs: add supported-vs-aspirational surface matrix",
        body=(
            "## Problem\n"
            "Contributors cannot easily tell which features are production-ready "
            "versus planned.\n\n"
            "## Proposed change\n"
            "Add a clear matrix showing supported, beta, and planned features.\n\n"
            "## Acceptance criteria\n"
            "- Matrix covers all product surfaces\n"
            "- Clear status labels (supported, beta, planned)\n"
            "- Links to relevant issues for planned features\n"
            "- Updated in project-status.md"
        ),
        labels=["area:docs", "size:s", "risk:low"],
    ),
    # ── area:infra  (10 issues) ────────────────────────────────────────────
    Issue(
        title="feat(infra): add database migration CI check",
        body=(
            "## Problem\n"
            "Database migrations are not validated in CI, risking broken migrations "
            "in production.\n\n"
            "## Proposed change\n"
            "Add a CI step that runs `alembic upgrade head` against a test database "
            "to verify migrations.\n\n"
            "## Acceptance criteria\n"
            "- CI spins up a test PostgreSQL\n"
            "- Runs all migrations to head\n"
            "- Fails if migration errors occur\n"
            "- Runs on PRs that touch migration files"
        ),
        labels=["area:infra", "area:test", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(infra): add Docker health checks to all services",
        body=(
            "## Problem\n"
            "Docker services lack health checks, making it hard to detect "
            "unhealthy containers.\n\n"
            "## Proposed change\n"
            "Add HEALTHCHECK instructions to Dockerfiles and health check "
            "configuration to docker-compose.\n\n"
            "## Acceptance criteria\n"
            "- Frontend container has health check on port 3000\n"
            "- API container has health check on /health\n"
            "- Database container has health check\n"
            "- docker-compose depends_on uses condition: service_healthy"
        ),
        labels=["area:infra", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(infra): add production docker-compose configuration",
        body=(
            "## Problem\n"
            "There is no docker-compose configuration optimized for production.\n\n"
            "## Proposed change\n"
            "Add `infrastructure/docker/docker-compose.prod.yml` with production-optimized settings.\n\n"
            "## Acceptance criteria\n"
            "- Resource limits defined\n"
            "- Restart policies configured\n"
            "- Logging configured\n"
            "- Secrets managed via Docker secrets or env files\n"
            "- Documentation for production deployment"
        ),
        labels=["area:infra", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(infra): add Terraform modules for cloud deployment",
        body=(
            "## Problem\n"
            "Terraform configuration is not modularized, making it hard to "
            "deploy to different environments.\n\n"
            "## Proposed change\n"
            "Refactor Terraform into reusable modules for compute, networking, "
            "and database.\n\n"
            "## Acceptance criteria\n"
            "- Separate modules for compute, networking, database\n"
            "- Environment-specific tfvars\n"
            "- Module documentation\n"
            "- Validation passes"
        ),
        labels=["area:infra", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(infra): add nginx reverse proxy configuration",
        body=(
            "## Problem\n"
            "The nginx configuration needs improvements for production use.\n\n"
            "## Proposed change\n"
            "Update nginx.conf with proper reverse proxy settings, SSL termination, "
            "and caching.\n\n"
            "## Acceptance criteria\n"
            "- Proxy pass to API and frontend services\n"
            "- SSL termination configured\n"
            "- Static asset caching\n"
            "- Security headers added\n"
            "- Rate limiting at proxy level"
        ),
        labels=["area:infra", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(infra): add CI workflow for infrastructure validation",
        body=(
            "## Problem\n"
            "Infrastructure changes are not validated in CI.\n\n"
            "## Proposed change\n"
            "Add CI workflow that validates Terraform, Docker, and Ansible "
            "configurations.\n\n"
            "## Acceptance criteria\n"
            "- `terraform validate` runs in CI\n"
            "- `docker-compose config` validates compose files\n"
            "- `ansible-lint` checks playbooks\n"
            "- Runs on PRs touching infrastructure files"
        ),
        labels=["area:infra", "area:test", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(infra): add backup and restore scripts for database",
        body=(
            "## Problem\n"
            "There are no scripts for backing up and restoring the database.\n\n"
            "## Proposed change\n"
            "Add scripts for PostgreSQL backup and restore with documentation.\n\n"
            "## Acceptance criteria\n"
            "- `scripts/backup-db.sh` creates a compressed backup\n"
            "- `scripts/restore-db.sh` restores from backup\n"
            "- Works with both local and remote databases\n"
            "- Documentation for scheduling backups"
        ),
        labels=["area:infra", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(infra): add container image scanning in CI",
        body=(
            "## Problem\n"
            "Docker images are not scanned for vulnerabilities.\n\n"
            "## Proposed change\n"
            "Add container image scanning to the CI pipeline using Trivy or Snyk.\n\n"
            "## Acceptance criteria\n"
            "- Container images scanned after build\n"
            "- Critical vulnerabilities fail the build\n"
            "- Scan results uploaded as artifact\n"
            "- Suppressions documented for false positives"
        ),
        labels=["area:infra", "area:test", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(infra): add multi-stage Docker build optimization",
        body=(
            "## Problem\n"
            "Docker images may be larger than necessary.\n\n"
            "## Proposed change\n"
            "Optimize the Dockerfile with better multi-stage build practices.\n\n"
            "## Acceptance criteria\n"
            "- Final image contains only runtime dependencies\n"
            "- Image size reduced by at least 20%\n"
            "- Build cache layers optimized\n"
            "- `.dockerignore` updated to exclude dev files"
        ),
        labels=["area:infra", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(infra): add environment variable validation on startup",
        body=(
            "## Problem\n"
            "Missing environment variables cause cryptic runtime errors.\n\n"
            "## Proposed change\n"
            "Add startup validation that checks for required environment variables "
            "and exits with clear error messages.\n\n"
            "## Acceptance criteria\n"
            "- All required env vars checked on startup\n"
            "- Missing vars produce clear error message\n"
            "- Optional vars documented with defaults\n"
            "- `.env.example` kept in sync"
        ),
        labels=["area:infra", "size:s", "risk:low"],
    ),
    # ── area:auth  (5 issues) ──────────────────────────────────────────────
    Issue(
        title="feat(auth): enforce ownership on all agent endpoints",
        body=(
            "## Problem\n"
            "Some agent endpoints do not enforce ownership, allowing users to "
            "access other users' agents.\n\n"
            "## Proposed change\n"
            "Add ownership checks to all agent CRUD endpoints.\n\n"
            "## Acceptance criteria\n"
            "- GET /agents returns only current user's agents\n"
            "- GET/PUT/DELETE /agents/{id} rejects non-owners with 403\n"
            "- Tests cover cross-user access attempts"
        ),
        labels=["area:auth", "area:api", "size:s", "risk:medium"],
    ),
    Issue(
        title="feat(auth): enforce ownership on all deployment endpoints",
        body=(
            "## Problem\n"
            "Some deployment endpoints do not enforce ownership.\n\n"
            "## Proposed change\n"
            "Add ownership checks to all deployment CRUD endpoints.\n\n"
            "## Acceptance criteria\n"
            "- GET /deployments returns only current user's deployments\n"
            "- GET/PUT/DELETE /deployments/{id} rejects non-owners with 403\n"
            "- Tests cover cross-user access"
        ),
        labels=["area:auth", "area:api", "size:s", "risk:medium"],
    ),
    Issue(
        title="feat(auth): add token refresh with sliding expiry",
        body=(
            "## Problem\n"
            "Tokens expire at a fixed time, requiring users to re-authenticate "
            "even during active use.\n\n"
            "## Proposed change\n"
            "Add sliding token expiry that extends the token lifetime on each "
            "authenticated request.\n\n"
            "## Acceptance criteria\n"
            "- Token expiry extends on authenticated requests\n"
            "- Maximum lifetime cap prevents indefinite extension\n"
            "- Refresh endpoint works correctly\n"
            "- Tests cover expiry scenarios"
        ),
        labels=["area:auth", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(auth): add password reset flow",
        body=(
            "## Problem\n"
            "Users who forget their password have no way to reset it.\n\n"
            "## Proposed change\n"
            "Add a password reset flow with email verification.\n\n"
            "## Acceptance criteria\n"
            "- POST /auth/forgot-password sends reset email\n"
            "- POST /auth/reset-password validates token and sets new password\n"
            "- Reset tokens expire after 1 hour\n"
            "- UI pages for forgot and reset password\n"
            "- Tests cover the flow"
        ),
        labels=["area:auth", "area:web", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(auth): remove client-supplied user_id from API payloads",
        body=(
            "## Problem\n"
            "Some endpoints accept `user_id` in the request body instead of "
            "deriving it from the authentication token, which is a security risk.\n\n"
            "## Proposed change\n"
            "Remove `user_id` from request schemas and derive it from the JWT "
            "token.\n\n"
            "## Acceptance criteria\n"
            "- No endpoint accepts `user_id` in request body\n"
            "- User identity derived from auth token\n"
            "- Existing clients updated\n"
            "- Tests verify user_id is ignored if sent"
        ),
        labels=["area:auth", "area:api", "size:s", "risk:medium"],
    ),
    # ── area:runtime  (5 issues) ───────────────────────────────────────────
    Issue(
        title="feat(runtime): add agent execution timeout enforcement",
        body=(
            "## Problem\n"
            "Running agents have no execution timeout, which could lead to "
            "resource exhaustion.\n\n"
            "## Proposed change\n"
            "Add configurable execution timeouts for agent runs.\n\n"
            "## Acceptance criteria\n"
            "- Default timeout of 300 seconds\n"
            "- Timeout configurable per-agent\n"
            "- Timed-out agents are terminated and marked as errored\n"
            "- Timeout event recorded in lifecycle\n"
            "- Tests cover timeout behavior"
        ),
        labels=["area:runtime", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(runtime): add agent resource usage tracking",
        body=(
            "## Problem\n"
            "There is no visibility into how much CPU, memory, or tokens agents "
            "consume.\n\n"
            "## Proposed change\n"
            "Track and expose resource usage metrics per agent execution.\n\n"
            "## Acceptance criteria\n"
            "- Track execution duration\n"
            "- Track token usage (LLM calls)\n"
            "- Usage accessible via API\n"
            "- Usage displayed in dashboard\n"
            "- Tests cover tracking"
        ),
        labels=["area:runtime", "area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(runtime): add agent execution traces API",
        body=(
            "## Problem\n"
            "There is no way to trace what an agent did during execution.\n\n"
            "## Proposed change\n"
            "Add an execution traces API that captures agent actions, decisions, "
            "and outputs.\n\n"
            "## Acceptance criteria\n"
            "- Traces capture each agent step\n"
            "- GET /agents/{id}/traces returns trace list\n"
            "- GET /agents/{id}/traces/{trace_id} returns trace detail\n"
            "- Traces include timestamps and metadata\n"
            "- Tests cover trace API"
        ),
        labels=["area:runtime", "area:api", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(runtime): add graceful agent shutdown",
        body=(
            "## Problem\n"
            "Stopping an agent may interrupt it mid-execution without cleanup.\n\n"
            "## Proposed change\n"
            "Implement graceful shutdown with a configurable grace period.\n\n"
            "## Acceptance criteria\n"
            "- Agent receives shutdown signal\n"
            "- Grace period (default 30s) for cleanup\n"
            "- Forced termination after grace period\n"
            "- Shutdown event recorded\n"
            "- Tests cover graceful and forced shutdown"
        ),
        labels=["area:runtime", "size:m", "risk:medium"],
    ),
    Issue(
        title="feat(runtime): add agent versioning and rollback support",
        body=(
            "## Problem\n"
            "There is no way to version agent configurations or roll back to "
            "previous versions.\n\n"
            "## Proposed change\n"
            "Add version tracking for agent configs with rollback capability.\n\n"
            "## Acceptance criteria\n"
            "- Each agent config update creates a new version\n"
            "- GET /agents/{id}/versions lists all versions\n"
            "- POST /agents/{id}/rollback/{version} restores a version\n"
            "- Tests cover versioning and rollback"
        ),
        labels=["area:runtime", "area:api", "size:m", "risk:medium"],
    ),
    # ── area:ops  (5 issues) ───────────────────────────────────────────────
    Issue(
        title="feat(ops): add Prometheus metrics endpoint",
        body=(
            "## Problem\n"
            "There are no application metrics exposed for monitoring.\n\n"
            "## Proposed change\n"
            "Add a `/metrics` endpoint that exposes Prometheus-compatible metrics.\n\n"
            "## Acceptance criteria\n"
            "- `/metrics` endpoint returns Prometheus format\n"
            "- Request count by route and status\n"
            "- Request latency histograms\n"
            "- Active agent and deployment counts\n"
            "- Tests verify metric format"
        ),
        labels=["area:ops", "area:api", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(ops): add structured JSON logging",
        body=(
            "## Problem\n"
            "Application logs are unstructured, making them hard to parse and "
            "search in log aggregation tools.\n\n"
            "## Proposed change\n"
            "Replace print statements and basic logging with structured JSON "
            "logging.\n\n"
            "## Acceptance criteria\n"
            "- All log output is JSON formatted\n"
            "- Includes timestamp, level, message, and context\n"
            "- Request ID included in request logs\n"
            "- Configurable log level via env var\n"
            "- Tests verify log format"
        ),
        labels=["area:ops", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(ops): add Grafana dashboard templates",
        body=(
            "## Problem\n"
            "There are no pre-built dashboards for monitoring MUTX.\n\n"
            "## Proposed change\n"
            "Add Grafana dashboard JSON templates for key operational views.\n\n"
            "## Acceptance criteria\n"
            "- API overview dashboard (requests, latency, errors)\n"
            "- Agent operations dashboard (counts, status, execution)\n"
            "- Infrastructure dashboard (CPU, memory, disk)\n"
            "- Import instructions documented"
        ),
        labels=["area:ops", "size:m", "risk:low"],
    ),
    Issue(
        title="feat(ops): add alerting rules for critical conditions",
        body=(
            "## Problem\n"
            "There are no alerting rules for detecting critical operational issues.\n\n"
            "## Proposed change\n"
            "Add alerting rules for high error rates, slow responses, and "
            "service outages.\n\n"
            "## Acceptance criteria\n"
            "- Alert on 5xx error rate above threshold\n"
            "- Alert on P99 latency above threshold\n"
            "- Alert on service health check failures\n"
            "- Alert on database connection pool exhaustion\n"
            "- Rules configurable via environment"
        ),
        labels=["area:ops", "size:s", "risk:low"],
    ),
    Issue(
        title="feat(ops): add self-healing for common failure modes",
        body=(
            "## Problem\n"
            "Known failure modes require manual intervention to resolve.\n\n"
            "## Proposed change\n"
            "Add automated recovery for common failure modes like stuck agents "
            "and connection pool exhaustion.\n\n"
            "## Acceptance criteria\n"
            "- Detect stuck agents and restart them\n"
            "- Detect connection pool exhaustion and recycle\n"
            "- Recovery actions logged\n"
            "- Recovery attempts capped to prevent loops\n"
            "- Tests cover detection and recovery"
        ),
        labels=["area:ops", "area:runtime", "size:m", "risk:medium"],
    ),
]

if len(ISSUES) != 100:
    raise ValueError(f"Expected 100 issues, got {len(ISSUES)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def dry_run(issues: list[Issue]) -> None:
    """Print all issues that would be created."""
    for idx, issue in enumerate(issues, 1):
        labels = ", ".join(issue.labels) if issue.labels else "(none)"
        print(f"\n{'=' * 72}")
        print(f"Issue {idx}/100")
        print(f"  Title:  {issue.title}")
        print(f"  Labels: {labels}")
        body_preview = issue.body[:200]
        if len(issue.body) > 200:
            body_preview += "..."
        print(f"  Body:\n{body_preview}")
    print(f"\n{'=' * 72}")
    print(f"Total: {len(issues)} issues ready to create.")
    print("Run with --execute to create them.\n")


def create_issues(issues: list[Issue], repo: str) -> None:
    """Create issues via the `gh` CLI."""
    created = 0
    failed = 0
    for idx, issue in enumerate(issues, 1):
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            issue.title,
            "--body",
            issue.body,
        ]
        for label in issue.labels:
            cmd.extend(["--label", label])

        print(f"[{idx}/{len(issues)}] Creating: {issue.title}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                print(f"  ✓ {url}")
                created += 1
            else:
                print(f"  ✗ {result.stderr.strip()}")
                failed += 1
        except subprocess.TimeoutExpired:
            print("  ✗ Timed out")
            failed += 1
        except Exception as exc:
            print(f"  ✗ {exc}")
            failed += 1

        # Small delay to avoid rate limiting
        if idx < len(issues):
            time.sleep(0.5)

    print(f"\nDone. Created: {created}, Failed: {failed}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 100 GitHub issues for the MUTX project.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create the issues (default is dry-run).",
    )
    parser.add_argument(
        "--repo",
        default="mutx-dev/mutx-dev",
        help="Target repository (default: mutx-dev/mutx-dev).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output issues as JSON (dry-run only).",
    )
    args = parser.parse_args()

    if args.json and not args.execute:
        output = [
            {
                "title": issue.title,
                "body": issue.body,
                "labels": issue.labels,
            }
            for issue in ISSUES
        ]
        print(json.dumps(output, indent=2))
        return 0

    if args.execute:
        create_issues(ISSUES, args.repo)
    else:
        dry_run(ISSUES)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
