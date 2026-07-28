---
description: VPC design, network topology, provisioning flow, and service boundaries.
icon: server
---

# Infrastructure

This document describes the checked-in infrastructure templates and their
target topology. Railway is the current production deployment path. The
DigitalOcean Terraform configuration is an alternate path whose scheduled drift
workflow remains disabled until cloud and remote-state credentials are supplied.
The diagrams below are design views; they do not prove that those resources or
controls are active in a deployed environment.

***

## VPC Design

### Overview

The Terraform template declares one DigitalOcean VPC, project, droplet, data
volume, and firewall for each item in the `customers` input. Supplying unique
CIDRs gives each declared customer a separate VPC in this alternate deployment
path.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         mutx.dev Control Plane                                   │
│                         (Railway + Vercel)                                       │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                        mutx API (FastAPI)                                 │  │
│  │   - Agent management                                                      │  │
│  │   - Deployment orchestration                                              │  │
│  │   - Tenant provisioning                                                  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                      │                                           │
│                                      │ API Calls                                 │
│                                      ▼                                           │
│                         ┌──────────────────────────┐                              │
│                         │  Terraform Cloud/Local  │                              │
│                         │  Provisioning Engine    │                              │
│                         └────────────┬────────────┘                              │
└──────────────────────────────────────┼───────────────────────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
         ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
         │   Tenant VPC A   │ │   Tenant VPC B   │ │   Tenant VPC C   │
         │   (Customer 1)   │ │   (Customer 2)   │ │   (Customer 3)   │
         │   10.0.1.0/24    │ │   10.0.2.0/24    │ │   10.0.3.0/24   │
         └──────────────────┘ └──────────────────┘ └──────────────────┘
```

### VPC Specification

The template exposes the following configuration:

| Parameter            | Value                                   |
| -------------------- | --------------------------------------- |
| **Region** | Shared `region` variable (`nyc1` by default) |
| **VPC CIDR** | Valid CIDR supplied per customer |
| **Compute** | One public/private-addressed droplet per customer |
| **Inbound firewall** | SSH from explicit `admin_cidr`, HTTP/HTTPS publicly, agent port from the customer VPC CIDR |
| **Outbound firewall** | TCP 443 and DNS TCP 53 |
| **Storage** | One attached volume, 100 GB by default and at least 10 GB |

***

## Alternate DigitalOcean Provisioning

### Provisioning Pipeline

The repository's operator-driven flow is Terraform apply, Terraform-output
inventory generation, then Ansible provisioning/deployment. The FastAPI source
does not automatically launch this pipeline from an API request.

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   User Request  │ ───▶ │    Terraform    │ ───▶ │    Ansible      │
│  (API/CLI)      │      │   (IaC)         │      │   (Config)      │
└─────────────────┘      └─────────────────┘      └─────────────────┘
        │                         │                        │
        │                         │                        │
        ▼                         ▼                        ▼
   ┌─────────┐            ┌─────────────┐          ┌─────────────┐
   │ Create  │            │  VPC +      │          │  Docker +   │
   │ Tenant  │            │  Compute    │          │  Services   │
   └─────────┘            └─────────────┘          └─────────────┘
```

### Terraform Configuration

The root configuration in `infrastructure/terraform/` creates:

1. **Networking**: one DigitalOcean VPC and project per configured customer.
2. **Compute**: one droplet with Ubuntu 22.04 by default, public/private
   addresses, customer and optional administrator SSH keys, and cloud-init.
3. **Firewall**: the explicit inbound and outbound rules summarized above.
4. **Storage**: one attached data volume per customer.

The `modules/vault` block is currently a placeholder and does not provision a
Vault server or KV engine. Other module directories are not instantiated by the
root configuration unless explicitly added.

### Ansible Configuration

After Terraform provisions the compute, Ansible configures:

| Playbook area | Current behavior |
| --- | --- |
| **docker role** | Installs Docker and configures its daemon |
| **PostgreSQL tasks** | Install PostgreSQL 15 and create `agent_db`/`agent_user` on agent hosts |
| **Redis tasks** | Install Redis, bind it to all interfaces, and require the configured password on agent hosts |
| **Tailscale tasks** | Run only when `TAILSCALE_AUTH_KEY` is non-empty |
| **UFW/fail2ban tasks** | Apply host rules and install the fail2ban template |
| **agent role** | Used by the separate deployment playbook |

### Inventory Structure

```ini
# infrastructure/ansible/inventory.ini (static example)
[agents]
agent-01 ansible_host=10.0.1.10 ansible_user=ubuntu
agent-02 ansible_host=10.0.1.11 ansible_user=ubuntu
agent-03 ansible_host=10.0.1.12 ansible_user=ubuntu

[monitoring]
monitor-01 ansible_host=10.0.2.10 ansible_user=ubuntu

[all:vars]
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args='-o StrictHostKeyChecking=no'
```

The Make targets call `scripts/generate-inventory.sh`, which writes
`inventory.generated.ini` from applied Terraform outputs, uses each droplet's
public address with the `root` user, and sets `StrictHostKeyChecking=accept-new`.

***

## Network Topology

### Target Network Diagram

```
                              ┌─────────────────────────────────────┐
                              │         Public Internet             │
                              └─────────────────────────────────────┘
                                           │
                                           │ HTTPS/WSS
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EDGE (Vercel/Railway)                               │
│                         ┌──────────────────────────┐                             │
│                         │  TLS Termination         │                             │
│                         │  DDoS Protection         │                             │
│                         │  CDN (Static Assets)     │                             │
│                         └──────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           │ Private Network
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         CONTROL PLANE (Railway)                                  │
│                         ┌──────────────────────────┐                             │
│                         │  mutx API (FastAPI)      │                             │
│                         │  PostgreSQL (Metadata)   │                             │
│                         │  Redis (Queue/Cache)     │                             │
│                         └──────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           │ Tailscale ZTNA
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           TENANT VPC (10.0.1.0/24)                               │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                         Agent Subnet (10.0.1.0/24)                       │  │
│   │                                                                           │  │
│   │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │  │
│   │   │   Agent 01   │    │   Agent 02   │    │   Agent 03   │              │  │
│   │   │   10.0.1.10  │    │   10.0.1.11  │    │   10.0.1.12  │              │  │
│   │   │  ┌────────┐  │    │  ┌────────┐  │    │  ┌────────┐  │              │  │
│   │   │  │Docker  │  │    │  │Docker  │  │    │  │Docker  │  │              │  │
│   │   │  │Agent 10│  │    │  │n8n     │  │    │  │LangChn │  │              │  │
│   │   │  └────────┘  │    │  └────────┘  │    │  └────────┘  │              │  │
│   │   └──────────────┘    └──────────────┘    └──────────────┘              │  │
│   │                                                                           │  │
│   │   ┌────────────────────────────────────────────────────────────────┐     │  │
│   │   │  EvalView Guard (10.0.1.5) - Local LLM Judge                 │     │  │
│   │   │  ┌─────────────────────────────────────────────────────────┐ │     │  │
│   │   │  │  Input Validation  │  Output Sanitization  │ Anomaly    │ │     │  │
│   │   │  │                    │                      │ Detection  │ │     │  │
│   │   │  └─────────────────────────────────────────────────────────┘ │     │  │
│   │   └────────────────────────────────────────────────────────────────┘     │  │
│   │                                                                           │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                     Data Services Subnet (10.0.1.128/25)                │  │
│   │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │  │
│   │   │ PostgreSQL   │    │    Redis     │    │  Vector DB   │              │  │
│   │   │   10.0.1.130 │    │   10.0.1.131 │    │   10.0.1.132 │              │  │
│   │   │  (pgvector)  │    │   (Cache)    │    │  (Embeddings)│              │  │
│   │   └──────────────┘    └──────────────┘    └──────────────┘              │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                     Management Subnet (10.0.2.0/24)                     │  │
│   │   ┌──────────────┐    ┌──────────────┐                                  │  │
│   │   │  Monitoring  │    │  Tailscale   │                                  │  │
│   │   │   10.0.2.10  │    │   Gateway   │                                  │  │
│   │   └──────────────┘    └──────────────┘                                  │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Illustrative IP Address Allocation

These ranges are not created by the current Terraform modules; customer CIDRs
come from input and the template creates no component-level subnets.

| Range         | Purpose       | Hosts                        |
| ------------- | ------------- | ---------------------------- |
| 10.0.1.0/27   | Reserved      | -                            |
| 10.0.1.32/27  | Agent pool    | 30 agents                    |
| 10.0.1.64/27  | EvalView      | 1 guardrail VM               |
| 10.0.1.128/27 | Data services | PostgreSQL, Redis, Vector DB |
| 10.0.1.192/26 | Reserved      | Future use                   |
| 10.0.2.0/24   | Management    | Monitoring, Tailscale node   |

***

## Security Zones (Target State)

### Zone Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SECURITY ZONES                                     │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                           ZONE 0: UNTRUSTED                                │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Public Internet                                                    │  │  │
│  │  │  - No direct access to tenant resources                            │  │  │
│  │  │  - All traffic through edge + Tailscale                            │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                         │
│                                        ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                           ZONE 1: SEMI-TRUSTED                           │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Control Plane (Railway)                                           │  │  │
│  │  │  - mutx API                                                        │  │  │
│  │  │  - Tenant management                                               │  │  │
│  │  │  - Terraform orchestration                                         │  │  │
│  │  │  Auth: JWT, API keys                                               │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                         │
│                              Tailscale ZTNA                                     │
│                                        ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                           ZONE 2: TRUSTED                                 │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Tenant VPC (Isolated)                                             │  │  │
│  │  │                                                                     │  │  │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │  │  │
│  │  │  │  DMZ Layer  │  │  App Layer  │  │ Data Layer │                 │  │  │
│  │  │  │  (EvalView) │  │  (Agents)   │  │  (DBs)     │                 │  │  │
│  │  │  │             │  │             │  │             │                 │  │  │
│  │  │  │  - Input    │  │  - Agent 10 │  │  - PostgreSQL│                │  │  │
│  │  │  │    filter   │  │  - n8n      │  │  - Redis   │                 │  │  │
│  │  │  │  - Output   │  │  - LangChain│  │  - Vector  │                 │  │  │
│  │  │  │    sanitize│  │             │  │    Store   │                 │  │  │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘                 │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Host Firewall Rules (UFW)

From `infrastructure/ansible/playbooks/provision.yml`:

```yaml
ufw_rules:
  - rule: allow
    port: "22"
    src: "{{ admin_cidr }}"
    comment: "SSH"
  - rule: allow
    port: "5432"
    src: "{{ private_cidr }}"
    comment: "PostgreSQL"
  - rule: allow
    port: "6379"
    src: "{{ private_cidr }}"
    comment: "Redis"
  - rule: allow
    port: "8080"
    src: "{{ private_cidr }}"
    comment: "Agent API"
```

`ADMIN_CIDR` defaults to `0.0.0.0/0` in the Ansible playbook, so operators must
set it explicitly before treating SSH as restricted. `PRIVATE_CIDR` defaults to
`10.0.0.0/8`; these rules do not depend on Tailscale being enabled.

### Proposed Network Segmentation

The component mapping below belongs to the target topology. In particular,
there is no current EvalView service or Terraform-created DMZ/data subnet.

| Component            | Zone | Access               | Notes                   |
| -------------------- | ---- | -------------------- | ----------------------- |
| **EvalView Guard**   | DMZ  | Agents → Guard → Out | Input/output validation |
| **Agent Containers** | App  | Guard → Agent        | Tool execution          |
| **PostgreSQL**       | Data | Agent → DB           | Via Unix socket         |
| **Redis**            | Data | Agent → Redis        | Password protected      |
| **Tailscale**        | Mgmt | All                  | WireGuard mesh          |

***

## Service Communication

### Internal Communication Target

The target topology calls for:

1. **Private Networking**: 10.0.x.x addresses
2. **Service Mesh**: Tailscale for encryption
3. **Authentication**: Service-specific tokens

### External Communication Target

These are intended communication patterns, not guarantees enforced across every
current deployment. Credential location depends on the broker backend selected
by the operator.

| Direction                | Method      | Security           |
| ------------------------ | ----------- | ------------------ |
| **Agent → LLM Provider** | HTTPS       | API key in Vault   |
| **Agent → Vector DB**    | Unix socket | Local only         |
| **Tenant → Agent**       | Tailscale   | WireGuard + Auth   |
| **Control → Tenant**     | Tailscale   | mTLS via Tailscale |

***

## Next Steps

* [Agent Runtime](agent-runtime.md)
* [Security](security.md)
