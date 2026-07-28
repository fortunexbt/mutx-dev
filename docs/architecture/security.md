---
description: Security posture, zero-trust model, BYOK direction, and audit controls.
icon: shield-halved
---

# Security

> Status convention: sections labeled **target state** are design goals, not
> claims about a deployed MUTX environment. Sections describing the current API
> are grounded in the checked-in source. Infrastructure templates still require
> operator configuration and do not prove that a control is active in a given
> deployment.

This document separates MUTX's implemented authentication and authorization
controls from its zero-trust, BYOK, guardrail, and network-isolation target
architecture.

***

## Security Philosophy

MUTX's **zero-trust target state** follows these principles:

1. **Never trust, always verify** — Authenticate and authorize every protected request; keep intentionally public routes explicit
2. **Assume breach** — Design for lateral movement prevention
3. **Least privilege** — Minimum necessary access at all layers
4. **Explicit verification** — Validate at every step
5. **Automate security** — Machine-speed detection and response

***

## Zero-Trust Model (Target State)

### Zero-Trust Network Architecture (ZTNA)

Traditional perimeter security is insufficient. The target network design uses
Tailscale as an optional private overlay:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Zero-Trust Network Access (ZTNA)                         │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                            PUBLIC INTERNET                                 │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                             │
│                      ┌─────────────┴─────────────┐                               │
│                      │   Target: Tailscale-first │                               │
│                      │   access posture          │                               │
│                      └─────────────┬─────────────┘                               │
│                                    │                                             │
│                                    │ WireGuard Tunnel                            │
│                                    ▼                                             │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                          TAILSCALE MESH                                    │  │
│  │                                                                           │  │
│  │   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐        │  │
│  │   │   Client    │◀──────▶│   Control   │◀──────▶│   Tenant   │        │  │
│  │   │  (User)     │         │   Plane     │         │   VPC      │        │  │
│  │   │             │         │             │         │             │        │  │
│  │   │  - Auth     │         │  - API      │         │  - Agents  │        │  │
│  │   │  - mTLS     │         │  - Policy   │         │  - Databases│        │  │
│  │   └─────────────┘         └─────────────┘         └─────────────┘        │  │
│  │                                                                           │  │
│  │   Key: WireGuard encryption, mTLS, short-lived certificates              │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Tailscale Provisioning Template

From `infrastructure/ansible/playbooks/provision.yml`:

```yaml
- name: Install and configure Tailscale
  block:
    - name: Install Tailscale
      ansible.apt:
        name: tailscale
        state: present

    - name: Start Tailscale
      command: tailscale up --auth-key {{ tailscale_auth_key }} --operator root

    - name: Enable Tailscale service
      systemd:
        name: tailscaled
        enabled: yes
        state: started
```

The Ansible task is conditional on `TAILSCALE_AUTH_KEY`. Its presence in the
repository does not establish that a deployment has joined a tailnet or that
service-to-service mTLS and per-tenant VPC isolation are active.

### Target ZTNA Features

| Feature                    | Implementation               | Benefit                     |
| -------------------------- | ---------------------------- | --------------------------- |
| **WireGuard Encryption**   | All traffic encrypted        | Data in transit protection  |
| **mTLS**                   | Service-to-service auth      | Identity verification       |
| **Port minimization goal** | Tailscale-first access model | Reduced attack surface      |
| **Short-lived Certs**      | Automatic rotation           | Credential theft prevention |
| **Network Isolation**      | Per-tenant VPCs              | Lateral movement prevention |

***

## Bring Your Own Key (BYOK Target State)

### BYOK Architecture

The target design lets customers retain control of AI-provider credentials. The
current credential broker can connect to configured backends including
HashiCorp Vault, AWS Secrets Manager, Google Secret Manager, Azure Key Vault,
1Password, and Infisical. The Terraform Vault module remains a stub, so the
diagram below is architectural direction rather than a default deployment.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        BYOK Architecture                                         │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                           TENANT VPC                                      │  │
│  │                                                                           │  │
│  │   ┌─────────────────────────────────────────────────────────────────┐    │  │
│  │   │                    HashiCorp Vault                               │    │  │
│  │   │                                                                  │    │  │
│  │   │   ┌─────────────────────────────────────────────────────────┐   │    │  │
│  │   │   │                  Secrets Engine                          │   │    │  │
│  │   │   │                                                           │   │    │  │
│  │   │   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │    │  │
│  │   │   │   │ OPENAI_KEY  │  │ANTHROPIC_KEY│  │ OTHER_KEYS │      │   │    │  │
│  │   │   │   │ (Encrypted) │  │ (Encrypted) │  │(Encrypted) │      │   │    │  │
│  │   │   │   └─────────────┘  └─────────────┘  └─────────────┘      │   │    │  │
│  │   │   │                                                           │   │    │  │
│  │   │   │   Policy: Tenant-only access                              │   │    │  │
│  │   │   │   Audit: All access logged                               │   │    │  │
│  │   │   └─────────────────────────────────────────────────────────┘   │    │  │
│  │   └─────────────────────────────────────────────────────────────────┘    │  │
│  │                                    │                                         │  │
│  │                           ┌────────┴────────┐                               │  │
│  │                           │                 │                               │  │
│  │                           ▼                 ▼                               │  │
│  │   ┌──────────────────────────────────────────────────────────────┐       │  │
│  │   │                     Agent Pod                                 │       │  │
│  │   │   ┌────────────────────────────────────────────────────────┐  │       │  │
│  │   │   │  Vault Agent Sidecar                                   │  │       │  │
│  │   │   │  - Token renewal                                       │  │       │  │
│  │   │   │  - Secret injection                                    │  │       │  │
│  │   │   │  - mTLS                                                │  │       │  │
│  │   │   └────────────────────────────────────────────────────────┘  │       │  │
│  │   │                                                            │       │  │
│  │   │   ┌────────────────────────────────────────────────────────┐  │       │  │
│  │   │   │  LangChain Agent                                       │  │       │  │
│  │   │   │  - Vault token via env                                │  │       │  │
│  │   │   │  - Calls LLM provider directly                        │  │       │  │
│  │   │   │  - Key never logged or exposed                        │  │       │  │
│  │   │   └────────────────────────────────────────────────────────┘  │       │  │
│  │   └──────────────────────────────────────────────────────────────┘       │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### BYOK Objectives

| Benefit                | Description                          |
| ---------------------- | ------------------------------------ |
| **Direct billing** | Allow tenants to use provider credentials they control |
| **Key control** | Resolve credentials from the tenant's configured backend |
| **Auditability** | Preserve backend and application events where configured |
| **Provider diversity** | Avoid coupling the broker to a single LLM provider |
| **Minimized exposure** | Avoid returning secret values from governance metadata routes |

### Intended Vault Configuration

For a tenant that selects and configures HashiCorp Vault, the intended controls
are:

* **Encryption**: AES-256 at rest
* **Access Control**: Tenant-specific policies
* **Audit Logging**: All secret access recorded
* **Token TTL**: Short-lived backend credentials selected by the operator
* **Least privilege**: MUTX receives only the Vault access its broker needs

***

## EvalView Guardrails (Proposed)

EvalView is a proposed local-judge guardrail design. There is no current
`EvalView` runtime implementation in `src/api`, so the checks, thresholds, and
response objects in this section are illustrative rather than an API contract.

### Guardrail Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        EvalView Guardrails                                      │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                      INPUT → EVALVIEW → OUTPUT                           │  │
│  │                                                                           │  │
│  │   ┌───────────┐      ┌───────────────────┐      ┌───────────┐             │  │
│  │   │  Client   │─────▶│    EvalView       │─────▶│   Agent   │             │  │
│  │   │  Request  │      │    Guardrail      │      │  Process  │             │  │
│  │   └───────────┘      └─────────┬─────────┘      └───────────┘             │  │
│  │                               │                                          │  │
│  │                               ▼                                          │  │
│  │                    ┌───────────────────────┐                            │  │
│  │                    │   Local LLM Judge     │                            │  │
│  │                    │                       │                            │  │
│  │                    │  ┌─────────────────┐  │                            │  │
│  │                    │  │ Input Validator │  │                            │  │
│  │                    │  │                 │  │                            │  │
│  │                    │  │ - Prompt        │  │                            │  │
│  │                    │  │   Injection     │  │                            │  │
│  │                    │  │ - PII Detection│  │                            │  │
│  │                    │  │ - Toxic Content│  │                            │  │
│  │                    │  └─────────────────┘  │                            │  │
│  │                    │                       │                            │  │
│  │                    │  ┌─────────────────┐  │                            │  │
│  │                    │  │ Output Filter  │  │                            │  │
│  │                    │  │                 │  │                            │  │
│  │                    │  │ - Sanitization │  │                            │  │
│  │                    │  │ - PII Redaction│  │                            │  │
│  │                    │  │ - Safe Content │  │                            │  │
│  │                    │  └─────────────────┘  │                            │  │
│  │                    │                       │                            │  │
│  │                    │  ┌─────────────────┐  │                            │  │
│  │                    │  │ Anomaly Detector│  │                            │  │
│  │                    │  │                 │  │                            │  │
│  │                    │  │ - Behavioral   │  │                            │  │
│  │                    │  │   Patterns     │  │                            │  │
│  │                    │  │ - Rate Limits  │  │                            │  │
│  │                    │  │ - Intent Drift │  │                            │  │
│  │                    │  └─────────────────┘  │                            │  │
│  │                    └───────────────────────┘                            │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Proposed Security Layers

#### 1. Input Validation

| Check                | Method                 | Action                    |
| -------------------- | ---------------------- | ------------------------- |
| **Prompt Injection** | Pattern matching + LLM | Reject malicious payloads |
| **PII Detection**    | NER + Regex            | Mask sensitive data       |
| **Toxic Content**    | Classifier             | Block harmful requests    |
| **Length Limits**    | Token count            | Truncate or reject        |
| **Encoding**         | Sanitization           | Strip dangerous chars     |

#### 2. Output Filtering

| Check                    | Method          | Action                   |
| ------------------------ | --------------- | ------------------------ |
| **PII Redaction**        | Regex patterns  | Replace with \[REDACTED] |
| **Safe Content**         | Classifier      | Filter harmful outputs   |
| **Injection Prevention** | Output encoding | Escape special chars     |
| **Token Limits**         | Token count     | Truncate responses       |

#### 3. Anomaly Detection

| Check                | Behavior                | Action          |
| -------------------- | ----------------------- | --------------- |
| **Request Velocity** | > 100 req/min per agent | Rate limit      |
| **Output Length**    | > 10x normal            | Flag for review |
| **Error Rate**       | > 50% errors            | Pause agent     |
| **Behavioral Drift** | Intent mismatch         | Alert + log     |

### Illustrative Guardrail Response

```python
# EvalView response structure
{
    "allowed": true,
    "checks": [
        {
            "name": "prompt_injection",
            "passed": true,
            "confidence": 0.95
        },
        {
            "name": "pii_detection",
            "passed": true,
            "findings": []
        },
        {
            "name": "toxic_content",
            "passed": true,
            "confidence": 0.99
        }
    ],
    "latency_ms": 150,
    "model": "local-guard-v1"
}
```

If any check fails:

```python
{
    "allowed": false,
    "reason": "prompt_injection_detected",
    "details": "Potential jailbreak attempt detected",
    "confidence": 0.87,
    "action": "block"
}
```

***

## Network Isolation (Target State)

The diagram describes the intended tenant-isolation model. Current Ansible
templates configure host firewall and optional Tailscale tasks, but they do not
by themselves create the per-tenant VPC topology shown here.

### Isolation Layers

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Network Isolation Layers                                │
│                                                                                  │
│  LAYER 1: VPC ISOLATION                                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                                 │
│  │  Tenant A  │ │  Tenant B  │ │  Tenant C  │  ← Separate VPCs               │
│  │  10.0.1.0  │ │  10.0.2.0  │ │  10.0.3.0  │                                 │
│  └─────────────┘ └─────────────┘ └─────────────┘                                 │
│           │             │             │                                          │
│           ▼             ▼             ▼                                          │
│  LAYER 2: SECURITY GROUPS                                                       │
│  ┌─────────────────────────────────────────┐                                   │
│  │  sg-agent   │  sg-database  │  sg-mgmt  │  ← Security Group Rules          │
│  │  (Agents)   │  (DBs)        │  (Mgmt)   │                                   │
│  └─────────────────────────────────────────┘                                   │
│           │             │             │                                          │
│           ▼             ▼             ▼                                          │
│  LAYER 3: SUBNET ACCESS                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  10.0.1.0/24 (App)  →  10.0.1.128/25 (Data)                             │   │
│  │  Only agent subnet can access data subnet                               │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│           │             │             │                                          │
│           ▼             ▼             ▼                                          │
│  LAYER 4: FIREWALL (UFW)                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  Allow: 22 (SSH)    │  5432 (PG)  │  6379 (Redis)  │  8080 (API)        │   │
│  │  Deny: All else                                                     │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Firewall Configuration

From `infrastructure/ansible/playbooks/provision.yml`:

```yaml
- name: Configure UFW firewall
  ufw:
    state: enabled
    policy: deny

- name: Add UFW rules
  ufw:
    rule: "{{ item.rule }}"
    port: "{{ item.port }}"
    comment: "{{ item.comment }}"
  loop:
    - { rule: allow, port: "22", comment: "SSH" }
    - { rule: allow, port: "5432", comment: "PostgreSQL" }
    - { rule: allow, port: "6379", comment: "Redis" }
    - { rule: allow, port: "8080", comment: "Agent API" }
```

### SSH Hardening

```yaml
- name: SSH hardening - Disable password authentication
  lineinfile:
    path: /etc/ssh/sshd_config
    regexp: "^PasswordAuthentication"
    line: "PasswordAuthentication no"

- name: SSH hardening - Disable root login
  lineinfile:
    path: /etc/ssh/sshd_config
    regexp: "^PermitRootLogin"
    line: "PermitRootLogin no"

- name: SSH hardening - Use only SSHv2
  lineinfile:
    path: /etc/ssh/sshd_config
    regexp: "^Protocol"
    line: "Protocol 2"
```

### Intrusion Prevention

fail2ban is configured to protect against brute force:

```yaml
- name: Configure fail2ban
  template:
    src: fail2ban.j2
    dest: /etc/fail2ban/jail.local
  vars:
    fail2ban_bantime: 3600      # 1 hour ban
    fail2ban_findtime: 600       # Within 10 minutes
    fail2ban_maxretry: 3         # After 3 attempts
```

***

## Authentication & Authorization

### Authentication Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        Authentication Flow                                       │
│                                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                   │
│  │    User      │────▶│   Dashboard   │────▶│  mutx API    │                   │
│  │  (Browser)   │     │  (Next.js)    │     │  (FastAPI)   │                   │
│  └──────────────┘     └──────────────┘     └──────┬───────┘                   │
│                                                      │                           │
│                                                      ▼                           │
│                                            ┌─────────────────┐                   │
│                                            │  Auth Service  │                   │
│                                            │                 │                   │
│                                            │  JWT + OIDC    │                   │
│                                            │  RBAC roles    │                   │
│                                            └────────┬────────┘                   │
│                                                     │                            │
│                                                     ▼                            │
│                                            ┌─────────────────┐                   │
│                                            │  PostgreSQL    │                   │
│                                            │  (Users/Tokens)│                   │
│                                            └─────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Token Management

| Token type | Lifetime | Server-side representation |
| --- | --- | --- |
| **Access token** | `ACCESS_TOKEN_EXPIRE_MINUTES` (30 minutes by default) | Signed JWT; no access-token record |
| **Refresh token** | `REFRESH_TOKEN_EXPIRE_DAYS` (7 days by default) | Signed JWT plus PostgreSQL session/JTI state for rotation and revocation |
| **Managed API key** | No expiry, or 1–365 days selected at creation | Prefix and password hash in PostgreSQL; plaintext returned once |

The auth API returns access and refresh tokens in its JSON response. A browser
or API client is responsible for storing them appropriately; the backend
contract does not promise that the refresh token is delivered as an HttpOnly
cookie.

### Authorization Model

Authorization combines several source-backed checks:

* persisted user roles (`ADMIN`, `AUDIT_ADMIN`, `DEVELOPER`, and `VIEWER`);
* ownership and visibility checks on resources such as agents and approvals;
* plan entitlement checks for paid capabilities; and
* verified-email/internal-domain checks on sensitive governance operations.

Managed API keys resolve their owning user and therefore inherit that user's
persisted roles. They do not have an independent `read`/`write`/`admin` scope
model.

***

## RBAC Enforcement

MUTX v1.4.0 enforces role-based access control (RBAC) across protected API routes. Role evaluation lives in `src/api/services/auth.py`; routes import auth and RBAC dependencies from the canonical `src/api/auth/dependencies.py` facade.

### Roles

| Role | Description | Scope |
| --- | --- | --- |
| `ADMIN` | Super-role for persisted-role checks | Implicitly satisfies every role check; separate plan, verification, internal-domain, or resource-state prerequisites may still apply |
| `AUDIT_ADMIN` | Access to the global audit event and trace store | `/v1/audit/*` endpoints |
| `DEVELOPER` | Mutating access where a route explicitly allows developers | Agent, deployment, approval, and other control-plane mutations |
| `VIEWER` | Read access where a route explicitly allows viewers | Owned/visible resources and safe configuration reads |

The `ADMIN` role is a super-role: `check_role` returns `True` for any required role when the user holds `ADMIN`.

### Route-Level Enforcement

RBAC is enforced via FastAPI dependencies:

```python
from src.api.auth.dependencies import require_roles

# Example: restrict an endpoint to ADMIN and DEVELOPER
@router.get("/admin", dependencies=[Depends(require_roles("ADMIN", "DEVELOPER"))])
async def admin_endpoint():
    ...
```

Key protected routes:

| Route Pattern | Required Roles | Notes |
| --- | --- | --- |
| `GET /v1/audit/events` | `ADMIN` or `AUDIT_ADMIN` | Reads the global audit store |
| `GET /v1/audit/traces/{trace_id}` | `ADMIN` or `AUDIT_ADMIN` | Reads the global audit store |
| `POST /v1/approvals/{request_id}/approve` | `DEVELOPER` or `ADMIN` | Requires authenticated assignment/eligibility; no reviewer-plan check |
| `POST /v1/approvals/{request_id}/reject` | `DEVELOPER` or `ADMIN` | Requires authenticated assignment/eligibility; no reviewer-plan check |

Paid entitlement applies when the owner creates an approval. Resolution is an
authorization decision based on the persisted reviewer assignment and role, so
an assigned eligible reviewer can act regardless of their subscription plan.
Approval responses expose `owner_id`, `reviewer_id`, and the caller-specific
`can_resolve` capability.

***

## OIDC / OAuth2 Provider Integration

Mounted SSO callbacks validate identities from the following providers:

| Provider | OIDC Discovery | JWKS Endpoint |
| --- | --- | --- |
| **Okta** | `{domain}/.well-known/openid-configuration` | `{domain}/oauth2/v1/keys` |
| **Auth0** | `{domain}/.well-known/openid-configuration` | `{domain}/.well-known/jwks.json` |
| **Keycloak** | `{domain}/realms/{realm}/.well-known/openid-configuration` | `{domain}/realms/{realm}/protocol/openid-connect/certs` |
| **Google** | `https://accounts.google.com/.well-known/openid-configuration` | `https://www.googleapis.com/oauth2/v3/certs` |

### Configuration

The generic, library-level validator accepts:

```
OIDC_ISSUER=https://your-org.okta.com
OIDC_CLIENT_ID=your-client-id
OIDC_JWKS_URI=https://your-org.okta.com/oauth2/v1/keys
```

`validate_oidc_token(...)` resolves these settings, fetches JWKS, and verifies
signature/issuer/audience/expiry. No mounted route invokes that generic validator
automatically. Mounted SSO uses provider-specific domain/client credentials,
binds the verified identity to a local user, and issues the standard dashboard
token. Routes authorize persisted `users.roles`; provider role claims do not
grant access. See
[Authentication docs](../api/authentication.md#oidc-token-validation) for full details.

***

## v1.4.0 Hardening Findings

| Area | Finding | Source state |
| --- | --- | --- |
| RBAC | Role enforcement now active on approval and audit routes | Implemented |
| OIDC | Token validation with JWKS verification and userinfo fallback | Implemented |
| Auth middleware | Bearer token resolution now tries JWT first, then API key | Implemented |
| Token roles | Provider roles may be normalized for compatibility but do not override persisted user roles | Implemented |
| Secrets | `SECRET_ENCRYPTION_KEY` encrypts stored webhook and credential secrets; managed API keys are one-way hashed | Implemented |
| Rate limiting | Separate auth rate limit (`AUTH_RATE_LIMIT_REQUESTS`, `AUTH_RATE_LIMIT_WINDOW_SECONDS`) | Implemented |

***

## Compliance & Audit

### Audit Logging

The audit event store currently records free-form `agent_id` values but has no
tenant or user foreign key. It cannot reliably enforce per-tenant filtering, so
`ADMIN` and `AUDIT_ADMIN` are global audit privileges. Adding tenant-scoped
audit access requires a durable tenant/user identifier on every audit event.

Audit and observability coverage is route- and deployment-specific. The API
provides the protected `/v1/audit/events` and `/v1/audit/traces/{trace_id}`
surfaces, structured application logging, Prometheus metrics, and optional
OpenTelemetry export. The source tree does not establish universal capture or
fixed retention periods for login, API-key, network, or infrastructure events.
Operators must set those policies in the deployed log, trace, and metrics
backends.

### Security Monitoring

* **Metrics and traces**: Prometheus-compatible metrics and optional OTLP export
* **Structured logs**: JSON-capable application logging for external collection
* **Alerting and retention**: configured by the operator's monitoring backends

Infrastructure examples in this repository are deployment assets, not evidence
that a particular PagerDuty, SIEM, retention, or compliance program is active.

***

## Summary

| Layer | Implemented protection |
| --- | --- |
| **HTTP boundary** | Trusted-host, CORS, security-header, rate-limit, authentication, and tracing middleware |
| **Identity** | Local JWTs, managed API keys, and optional OIDC validation |
| **Authorization** | Persisted roles plus route-specific ownership, plan, verification, and internal-user checks |
| **Secrets** | One-way API-key hashes and application encryption for stored webhook/credential secrets |
| **Policy** | Policy evaluation and approval workflow enforcement |
| **Observability** | Structured logs, Prometheus metrics, and optional OpenTelemetry export |

***

## Related Documentation

* [Architecture Overview](overview.md)
* [Infrastructure](infrastructure.md)
* [Agent Runtime](agent-runtime.md)
