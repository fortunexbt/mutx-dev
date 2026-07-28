# RBAC

MUTX authorizes protected control-plane requests with persisted roles on the
database-backed user. Access tokens establish identity; route dependencies reload
the user before evaluating roles, so a database role change or revocation applies
on the next request.

## Roles

| Role | Current capability |
| --- | --- |
| `ADMIN` | Super-role that implicitly satisfies every role check |
| `AUDIT_ADMIN` | Global audit-event, trace, and export reads |
| `DEVELOPER` | Mutating owned agents, deployments, API keys, webhooks, policies, and other developer workflows |
| `VIEWER` | Read-only access where a route explicitly accepts `VIEWER` |

Roles other than `ADMIN` are not hierarchical. `AUDIT_ADMIN` does not imply
`VIEWER` or `DEVELOPER`, and `DEVELOPER` does not automatically satisfy a
`VIEWER`-only check. Routes that accept either role declare both.

New password, social, SSO, and localhost-bootstrap users receive `VIEWER`.
Provider role/group claims can be normalized for compatibility, but they do not
override `users.roles`. MUTX currently has no public self-service role-assignment
endpoint; privileged roles require a controlled database administration process.

## Enforcement

FastAPI routes declare authorization through dependencies such as
`require_roles("VIEWER", "DEVELOPER")`. Many resources also enforce ownership,
plan, verified-email, or internal-domain boundaries after authentication.
Anonymous routes such as health probes, login, registration, and public lead
capture do not require a role.

Managed API keys resolve to their owning user and therefore inherit that user's
persisted roles. Agent runtime keys use the separate agent-authenticated endpoints.

The generated OpenAPI document records whether each operation is public,
optionally authenticated, or requires bearer/API-key authentication. OpenAPI
security metadata does not encode the accepted application role; use the route
dependency in `src/api/routes/` as the role source of truth.
