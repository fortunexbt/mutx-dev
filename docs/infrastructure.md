---
description: Validation-first guide to Terraform, Ansible, Docker Compose, and monitoring.
icon: server
---

# MUTX Infrastructure

Production-readiness baseline for Terraform, Ansible, Docker Compose, and monitoring.

## Layout

* `terraform/` – DigitalOcean VPC + droplet + firewall provisioning
* `ansible/` – host hardening and container deployment playbooks
* `helm/` – Kubernetes Helm chart for MUTX deployment
* `monitoring/` – Prometheus + Grafana config

## Terraform (DigitalOcean)

```bash
cd infrastructure
make tf-fmt
make tf-validate
make ansible-inventory

# Staging
make tf-plan-staging

# Production
make tf-plan-production

# Apply from terraform/ after reviewing plan
cd terraform
terraform apply -var-file=environments/production/terraform.tfvars
```

## Health Checks

The API exposes two health check endpoints for Kubernetes/production use:

- `/health` - Liveness probe, returns 200 if the service is alive
- `/ready` - Readiness probe, returns 503 if not ready to accept traffic

Both endpoints check database connectivity status.

### Notes

* Backend is environment-scoped via `terraform/environments/<env>/backend.hcl`.
* Keep `admin_cidr` scoped to VPN/home-office CIDR. Avoid `0.0.0.0/0` in production.
* Customer IDs must be unique.
* Customer VPC CIDRs are validated at plan time.

## Ansible Provisioning

```bash
cd infrastructure
make ansible-provision
make ansible-deploy-agent
```

Install Ansible collections and lint before applying:

```bash
cd infrastructure
make ansible-deps
make ansible-lint
```

Required environment variables before running playbooks:

* `POSTGRES_PASSWORD`
* `REDIS_PASSWORD`
* `AGENT_API_KEY`
* `AGENT_SECRET_KEY`
* `ADMIN_CIDR` (recommended, defaults to `0.0.0.0/0`)
* `PRIVATE_CIDR` (optional, defaults to `10.0.0.0/8`)
* `TAILSCALE_AUTH_KEY` (optional)

## Monitoring Stack

```bash
cp .env.monitoring.example .env.monitoring
# set strong credentials/passwords
cd infrastructure
make monitor-up
```

The monitoring compose file binds UI and exporter ports to localhost by default. Stop it with `cd infrastructure && make monitor-down`. Prometheus now loads alerting rules from `infrastructure/monitoring/prometheus/alerts.yml` and scrapes the API via `host.docker.internal:8000` (works for local Docker Desktop + Linux host-gateway mapping). Grafana provisioning and dashboard mounts are resolved relative to `infrastructure/docker/docker-compose.monitoring.yml`, so the stack reads from `../monitoring/grafana/...` when launched from `infrastructure/`.

## CI Drift Detection

Railway is the current production deployment path. The Terraform DigitalOcean configuration remains an alternate deployment path and its drift workflow is intentionally dormant until real cloud and remote-state credentials are configured.

* Workflow: `.github/workflows/infrastructure-drift.yml`
* Trigger: manual dispatch at any time; daily cron only when the repository variable `ENABLE_TERRAFORM_DRIFT` is set to `true`
* Disabled schedule: reports readiness and skips the Terraform matrix instead of producing a false drift failure
* Enabled behavior: uploads plan artifacts and fails when drift is detected
* Manual safety: dispatch remains fail-closed when any required secret is missing

Required GitHub secrets before enabling the schedule:

* `DO_TOKEN`
* `TF_STATE_ACCESS_KEY_ID`
* `TF_STATE_SECRET_ACCESS_KEY`

Store these as repository or organization Actions secrets. The workflow does not
currently declare GitHub environments, so environment-scoped secrets are not
available to its matrix jobs. If environments and approval gates are added later,
update the workflow and this guidance together.

## Extra Validation Targets

From `infrastructure/`:

```bash
# Drift-style exit codes (0=no changes, 2=changes)
make tf-plan-staging-detailed
make tf-plan-production-detailed

# Validate Prometheus config + alert rules
make monitor-validate
```

These infrastructure checks are explicit jobs in the authoritative `.github/workflows/ci.yml` flow. Pull requests select them through the infrastructure path filter, while `main`, merge-queue, and manual runs execute them unconditionally. Terraform drift remains separate because it requires live cloud and remote-state credentials. See `docs/ci.md` for the required-check contract.

## Next Hardening Items

* Replace static inventory usage with Terraform-generated inventory by default in Ansible playbook wrappers.
* Wire alert delivery (Alertmanager/notification channel) for critical rules.
* Default local Alertmanager routing now drops alerts unless they are explicitly labeled `notify="webhook"`, preventing noisy failed webhook retries in dev setups without a receiver.
* Add automated backup/restore verification for PostgreSQL and Redis volumes.
