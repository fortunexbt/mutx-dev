from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
SDK_SOURCE = Path(__file__).parents[1] / "mutx"
EXTERNAL_TOXICITY_ROUTE = "<external:toxicity_api_url>"

# Audited against the routes mounted by src.api.main.PUBLIC_ROUTE_REGISTRATIONS.
# Counts include paired sync/async methods and repeated adapter event hooks so a
# new or modified HTTP call cannot bypass review by reusing an existing route.
SDK_ROUTE_INVENTORY = [
    ("DELETE", "agents/{agent_id}", 2),
    ("DELETE", "api-keys/{key_id}", 2),
    ("DELETE", "assistant/{agent_id}/skills/{skill_id}", 2),
    ("DELETE", "deployments/{deployment_id}", 2),
    ("DELETE", "governance/credentials/backends/{backend_name}", 2),
    ("DELETE", "leads/contacts/{contact_id}", 2),
    ("DELETE", "leads/{lead_id}", 2),
    ("DELETE", "security/sessions/{session_id}", 2),
    ("DELETE", "sessions", 2),
    ("DELETE", "webhooks/{webhook_id}", 2),
    ("GET", "agents", 2),
    ("GET", "agents/commands", 1),
    ("GET", "agents/{agent_id}", 2),
    ("GET", "agents/{agent_id}/config", 2),
    ("GET", "agents/{agent_id}/logs", 2),
    ("GET", "agents/{agent_id}/metrics", 2),
    ("GET", "agents/{agent_id}/resource-usage", 2),
    ("GET", "agents/{agent_id}/status", 1),
    ("GET", "agents/{agent_id}/versions", 2),
    ("GET", "analytics/agents/{agent_id}/summary", 2),
    ("GET", "analytics/budget", 2),
    ("GET", "analytics/costs", 2),
    ("GET", "analytics/summary", 2),
    ("GET", "analytics/timeseries", 2),
    ("GET", "api-keys", 2),
    ("GET", "approvals", 2),
    ("GET", "approvals/reviewers", 2),
    ("GET", "approvals/{request_id}", 3),
    ("GET", "assistant/overview", 2),
    ("GET", "assistant/{agent_id}/channels", 2),
    ("GET", "assistant/{agent_id}/health", 2),
    ("GET", "assistant/{agent_id}/sessions", 2),
    ("GET", "assistant/{agent_id}/skills", 2),
    ("GET", "assistant/{agent_id}/wakeups", 2),
    ("GET", "budgets", 2),
    ("GET", "budgets/usage", 2),
    ("GET", "clawhub/bundles", 2),
    ("GET", "clawhub/skills", 2),
    ("GET", "deployments", 2),
    ("GET", "deployments/{deployment_id}", 2),
    ("GET", "deployments/{deployment_id}/events", 2),
    ("GET", "deployments/{deployment_id}/logs", 2),
    ("GET", "deployments/{deployment_id}/metrics", 2),
    ("GET", "governance/attestations", 2),
    ("GET", "governance/credentials/backends", 2),
    ("GET", "governance/credentials/backends/{backend_name}/health", 2),
    ("GET", "governance/credentials/get/{full_path}", 2),
    ("GET", "governance/credentials/health", 2),
    ("GET", "governance/discovery", 2),
    ("GET", "governance/lifecycle", 2),
    ("GET", "governance/trust", 2),
    ("GET", "leads", 2),
    ("GET", "leads/contacts", 2),
    ("GET", "leads/contacts/{contact_id}", 2),
    ("GET", "leads/{lead_id}", 2),
    ("GET", "observability/runs", 2),
    ("GET", "observability/runs/{run_id}", 2),
    ("GET", "observability/runs/{run_id}/eval", 2),
    ("GET", "observability/runs/{run_id}/provenance", 2),
    ("GET", "onboarding", 2),
    ("GET", "policies/{policy_name}", 1),
    ("GET", "runtime/governance/metrics", 2),
    ("GET", "runtime/governance/status", 2),
    ("GET", "runtime/governance/supervised/", 2),
    ("GET", "runtime/governance/supervised/profiles", 2),
    ("GET", "runtime/governance/supervised/{agent_id}", 2),
    ("GET", "runtime/providers/{provider}", 2),
    ("GET", "scheduler", 2),
    ("GET", "security/approvals", 2),
    ("GET", "security/approvals/{request_id}", 2),
    ("GET", "security/compliance", 2),
    ("GET", "security/metrics", 2),
    ("GET", "security/metrics/prometheus", 2),
    ("GET", "security/receipts/session/{session_id}", 2),
    ("GET", "security/receipts/{receipt_id}", 2),
    ("GET", "security/sessions/{session_id}", 2),
    ("GET", "sessions", 2),
    ("GET", "swarms", 2),
    ("GET", "swarms/blueprints", 2),
    ("GET", "swarms/{swarm_id}", 2),
    ("GET", "templates", 2),
    ("GET", "usage/events", 2),
    ("GET", "usage/events/{event_id}", 2),
    ("GET", "webhooks/", 2),
    ("GET", "webhooks/{webhook_id}", 2),
    ("GET", "webhooks/{webhook_id}/deliveries", 2),
    ("PATCH", "agents/{agent_id}/config", 2),
    ("PATCH", "leads/contacts/{contact_id}", 2),
    ("PATCH", "leads/{lead_id}", 2),
    ("PATCH", "observability/runs/{run_id}/status", 2),
    ("PATCH", "webhooks/{webhook_id}", 2),
    ("POST", EXTERNAL_TOXICITY_ROUTE, 2),
    ("POST", "agents", 2),
    ("POST", "agents/commands/acknowledge", 1),
    ("POST", "agents/heartbeat", 2),
    ("POST", "agents/logs", 2),
    ("POST", "agents/metrics", 2),
    ("POST", "agents/register", 2),
    ("POST", "agents/{agent_id}/deploy", 4),
    ("POST", "agents/{agent_id}/resource-usage", 2),
    ("POST", "agents/{agent_id}/rollback", 2),
    ("POST", "agents/{agent_id}/stop", 2),
    ("POST", "api-keys", 2),
    ("POST", "api-keys/{key_id}/rotate", 2),
    ("POST", "approvals", 3),
    ("POST", "approvals/{request_id}/approve", 2),
    ("POST", "approvals/{request_id}/reject", 2),
    ("POST", "assistant/{agent_id}/skills/{skill_id}", 2),
    ("POST", "clawhub/install", 2),
    ("POST", "clawhub/install-bundle", 2),
    ("POST", "clawhub/uninstall", 2),
    ("POST", "deployments", 2),
    ("POST", "deployments/{deployment_id}/restart", 2),
    ("POST", "deployments/{deployment_id}/scale", 2),
    ("POST", "events", 11),
    ("POST", "governance/attestations/verify", 2),
    ("POST", "governance/credentials/backends", 2),
    ("POST", "governance/discovery/scan", 2),
    ("POST", "governance/lifecycle/{agent_id}", 2),
    ("POST", "governance/trust/{agent_id}", 2),
    ("POST", "ingest/agent-status", 2),
    ("POST", "ingest/deployment", 2),
    ("POST", "ingest/metrics", 2),
    ("POST", "leads", 2),
    ("POST", "leads/contacts", 2),
    ("POST", "observability/runs", 2),
    ("POST", "observability/runs/{run_id}/eval", 2),
    ("POST", "observability/runs/{run_id}/steps", 2),
    ("POST", "onboarding", 2),
    ("POST", "runtime/governance/supervised/start", 2),
    ("POST", "runtime/governance/supervised/{agent_id}/restart", 2),
    ("POST", "runtime/governance/supervised/{agent_id}/stop", 2),
    ("POST", "scheduler/{task_id}/trigger", 2),
    ("POST", "security/actions/evaluate", 2),
    ("POST", "security/approvals/request", 2),
    ("POST", "security/approvals/{request_id}/approve", 2),
    ("POST", "security/approvals/{request_id}/deny", 2),
    ("POST", "security/sessions", 2),
    ("POST", "sessions", 6),
    ("POST", "swarms", 2),
    ("POST", "swarms/{swarm_id}/scale", 2),
    ("POST", "templates/{template_id}/deploy", 2),
    ("POST", "usage/events", 2),
    ("POST", "webhooks/", 2),
    ("POST", "webhooks/{webhook_id}/test", 2),
    ("PUT", "runtime/providers/{provider}", 2),
]


def _route_from_call(path: Path, call: ast.Call) -> str:
    argument = call.args[0]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    if (
        isinstance(argument, ast.Call)
        and isinstance(argument.func, ast.Name)
        and argument.func.id == "api_path"
        and argument.args
        and isinstance(argument.args[0], ast.Constant)
        and isinstance(argument.args[0].value, str)
    ):
        return argument.args[0].value
    if path.name == "guardrails.py" and ast.unparse(argument) == "self.toxicity_api_url":
        return EXTERNAL_TOXICITY_ROUTE
    return f"<unclassified:{path.name}:{call.lineno}:{ast.unparse(argument)}>"


def _discover_http_calls() -> Counter[tuple[str, str]]:
    discovered: Counter[tuple[str, str]] = Counter()
    for path in SDK_SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
                or node.func.attr not in HTTP_METHODS
                or not node.args
            ):
                continue
            receiver = ast.unparse(node.func.value).lower()
            if not any(marker in receiver for marker in ("client", "http", "session")):
                continue
            discovered[(node.func.attr.upper(), _route_from_call(path, node))] += 1
    return discovered


def test_sdk_route_inventory_covers_every_http_call() -> None:
    expected = Counter({(method, route): count for method, route, count in SDK_ROUTE_INVENTORY})
    assert _discover_http_calls() == expected


def test_mounted_routes_are_relative_to_exactly_one_v1_base() -> None:
    for _, route, _ in SDK_ROUTE_INVENTORY:
        if route == EXTERNAL_TOXICITY_ROUTE:
            continue
        assert route
        assert not route.startswith("/")
        assert route != "v1"
        assert not route.startswith("v1/")
        assert "newsletter" not in route
