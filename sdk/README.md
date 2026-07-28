# mutx Python SDK

Python SDK for mutx.dev.

## Install

```bash
pip install mutx
```

## Usage

```python
from mutx import MutxClient

with MutxClient(api_key="your-api-key") as client:
    agents = client.agents.list()
    print(agents)
```

## Legacy runtime security

The `/v1/security` resource derives the owner from the authenticated principal.
Do not pass `user_id` or a reviewer identity when resolving; those fields are
not part of the decision contract. Approval creation may provide an explicit
`reviewer_id`, discoverable through `client.approvals.list_reviewers()`. The
`agent_id` must identify a persisted agent owned by the principal, and actions
must reference a security session created for the same agent. Decisions use the
returned request ID and authenticated assignment/role—never an approval token.

```python
with MutxClient(api_key="your-api-key") as client:
    client.security.create_session("run-123", agent_id="owned-agent-uuid")
    evaluation = client.security.evaluate_action(
        "file_read",
        {"path": "/tmp/report.txt"},
        agent_id="owned-agent-uuid",
        session_id="run-123",
    )
    receipt = client.security.get_receipt(evaluation.receipt_id)
    approval = client.security.request_approval(
        "file_read",
        {"path": "/tmp/report.txt"},
        agent_id="owned-agent-uuid",
        session_id="run-123",
        reviewer_id=client.approvals.list_reviewers()[0].id,
    )
    client.security.approve(approval.request_id, comment="Reviewed")
```

## Paginated lists

`agents.list()`, `api_keys.list()`, and `approvals.list()` return a typed `Page`
with `items`, `total`, `skip`, `limit`, and `has_more` attributes. A page still
supports iteration, indexing, `len(page)`, and comparison with a list, so common
code written for older SDK releases continues to work:

```python
with MutxClient(api_key="your-api-key") as client:
    page = client.agents.list(skip=0, limit=25)
    for agent in page:
        print(agent.name)
    print(f"showing {len(page)} of {page.total}; more={page.has_more}")
```

For compatibility with legacy MUTX servers, the SDK also accepts a bare JSON
list. Those results set `is_legacy=True`; because the response did not provide
pagination metadata, `total` and `has_more` are `None`. Canonical envelope
responses are validated and malformed mappings raise `PageEnvelopeError`.

## Base URLs

`MutxClient` accepts either an API origin such as `https://api.mutx.dev` or a
URL already ending in `/v1`. The SDK normalizes both forms to exactly one `/v1`
segment. The same behavior applies to the exported agent-runtime clients and
framework adapters.

## Async client status

The package does not export a general-purpose `MutxAsyncClient`. `MutxClient`
is synchronous. For async resource calls, construct the resource with an owned
`httpx.AsyncClient` whose base URL includes `/v1`:

```python
import httpx

from mutx.agents import Agents
from mutx.security import Security

async with httpx.AsyncClient(
    base_url="https://api.mutx.dev/v1",
    headers={"Authorization": "Bearer your-api-key"},
) as http:
    agents = await Agents(http).alist()
    security = Security(http)
    receipts = await security.aget_session_receipts("run-123", limit=25, offset=0)
```

The exported `MutxAgentClient` is a separate, fully asynchronous agent-runtime
client. Sync methods on resource classes and `a*` methods on those same classes
intentionally reject the wrong `httpx` client type.
