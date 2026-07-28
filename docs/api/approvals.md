# Approvals API

MUTX exposes one durable approval workflow through the canonical
`/v1/approvals` routes. The compatibility routes under
`/v1/security/approvals` read and mutate the same database records.

## Identity, entitlement, and assignment

- The authenticated user is the approval owner; callers cannot supply `owner_id`.
- Creating an approval is a paid owner capability and requires the route's
  developer/admin role.
- A request can be assigned with `reviewer_id`. Use
  `GET /v1/approvals/reviewers` from that entitled creator context to discover
  active eligible reviewers.
- Resolving an approval requires an authenticated developer/admin who is
  eligible for that record. An explicitly assigned developer can resolve even
  when their own subscription is free; the paid entitlement was checked when
  the owner created the request.
- Owners cannot resolve their own requests.

Every approval response includes `owner_id`, `reviewer_id`, and
`can_resolve`. `can_resolve` is computed for the authenticated caller from the
current status, assignment, ownership, and persisted roles. Clients must use it
to decide whether to render approval actions, but the server remains the final
authorization boundary.

## Canonical routes

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/v1/approvals` | Create a durable approval; accepts optional `reviewer_id` |
| `GET` | `/v1/approvals` | List approvals visible to the caller |
| `GET` | `/v1/approvals/reviewers` | List active users eligible for assignment |
| `GET` | `/v1/approvals/{request_id}` | Read one visible approval |
| `POST` | `/v1/approvals/{request_id}/approve` | Approve by request ID |
| `POST` | `/v1/approvals/{request_id}/reject` | Reject by request ID |

## Legacy security compatibility

The legacy creation shape remains available at
`POST /v1/security/approvals/request`. It accepts the tool/action context and
optional `reviewer_id`, then creates a canonical durable approval.

The corresponding read and mutation routes use `request_id`:

- `GET /v1/security/approvals/{request_id}`
- `POST /v1/security/approvals/{request_id}/approve`
- `POST /v1/security/approvals/{request_id}/deny`

No approval secret or one-time bearer token is returned or accepted. The
ordinary authenticated principal plus persisted assignment/role checks govern
resolution.

## Governed runtime DEFER

The in-process governed tool runtime does not yet have a durable serialized
continuation that can safely resume an arbitrary handler. A `DEFER` decision
therefore fails closed before the handler runs and returns `resumable: false`;
it does not create a ghost approval. Applications that need a resumable flow
must create a canonical approval and bind its resolution to their own durable,
idempotent job continuation.
