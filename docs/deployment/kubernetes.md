# Kubernetes Deployment Guide for MUTX

This guide covers deploying MUTX to Kubernetes using Helm charts or raw YAML manifests.

## Prerequisites

- Helm 3.x installed ([Install Guide](https://helm.sh/docs/intro/install/))
- Kubernetes 1.24+ cluster
- kubectl configured to access your Kubernetes cluster
- Docker image `mutx/mutx` pushed to your registry (or use the default)

## Helm Chart

The canonical Helm chart lives at `infrastructure/helm/mutx/`. See the [Helm chart README](https://github.com/mutx-dev/mutx-dev/blob/main/infrastructure/helm/mutx/README.md) for the full configuration reference.

## Helm Deployment

### Staging Environment

```bash
# Install or upgrade the staging release
make helm-install-staging

# Or using helm directly
helm upgrade --install mutx-staging infrastructure/helm/mutx \
  -f infrastructure/helm/mutx/values.staging.yaml \
  --namespace staging --create-namespace
```

### Production Environment

```bash
# Install or upgrade the production release
make helm-install-prod

# Or using helm directly
helm upgrade --install mutx-prod infrastructure/helm/mutx \
  -f infrastructure/helm/mutx/values.prod.yaml \
  --namespace production --create-namespace
```

## Raw YAML Deployment

For environments without Helm, apply the raw YAML manifests:

```bash
# Apply all Kubernetes manifests
kubectl apply -f infrastructure/kubernetes/

# Or individually
kubectl apply -f infrastructure/kubernetes/configmap.yaml
kubectl apply -f infrastructure/kubernetes/deployment.yaml
kubectl apply -f infrastructure/kubernetes/service.yaml
kubectl apply -f infrastructure/kubernetes/ingress.yaml
kubectl apply -f infrastructure/kubernetes/hpa.yaml
```

## Configuration

### Environment Variables

Configure non-secrets through `api.env` and `frontend.env`. Put credentials in
an existing Secret referenced by `api.existingSecret` (recommended for
production) or in `api.secretEnv` for non-production use:

```yaml
api:
  existingSecret: mutx-api-env
  env:
    ENVIRONMENT: production
    LOG_LEVEL: INFO
    ALLOWED_HOSTS: mutx.example.com,localhost,127.0.0.1
    FORWARDED_ALLOW_IPS: 10.244.0.0/16 # exact ingress source/pod CIDR
frontend:
  env:
    NODE_ENV: production
```

The `mutx-api-env` Secret must contain `DATABASE_URL`, `JWT_SECRET`, and a
distinct `SECRET_ENCRYPTION_KEY`. The chart does not install PostgreSQL. Its
Alembic hook and API use the same Secret and database role, so that role must
currently have both migration DDL and runtime DML privileges.

### RBAC Setup

MUTX uses four persisted roles: `ADMIN`, `AUDIT_ADMIN`, `DEVELOPER`, and
`VIEWER`. RBAC is always enforced by protected route dependencies and does not
need OIDC to be enabled. Password, social OAuth, and SSO identities all resolve
to a local database user whose `users.roles` value is authoritative.

To enable the mounted Okta SSO flow, for example, set provider-specific
credentials and the public API origin in your Helm values:

```yaml
# values.yaml or -f override
api:
  existingSecret: mutx-api-env
  env:
    PUBLIC_API_URL: "https://api.example.com"
    OKTA_DOMAIN: "https://your-org.okta.com"
    OKTA_CLIENT_ID: "0oa1abc2def3ghi4jkl5"
```

Add `OKTA_CLIENT_SECRET` to `mutx-api-env`; do not place it under `api.env`.

Provider role claims from `roles`, `groups`, `custom:roles`,
`realm_access.roles`, or `resource_access.roles` may be normalized for legacy
compatibility, but they do not grant MUTX privileges. Assign elevated roles through
a controlled database administration process after the external identity is linked.

See [Security Architecture](../architecture/security.md#rbac-enforcement) for the full role reference.

### Generic OIDC Validator Configuration

The library-level `validate_oidc_token(...)` utility uses the following values:

```yaml
api:
  existingSecret: mutx-api-env
  env:
    OIDC_ISSUER: "https://your-org.okta.com"
    OIDC_CLIENT_ID: "0oa1abc2def3ghi4jkl5"
    OIDC_JWKS_URI: "https://your-org.okta.com/oauth2/v1/keys"
```

These values do not make protected routes accept provider bearer tokens and are
not a replacement for the provider-specific SSO credentials above. The generic
validator can be pointed at any compatible issuer/JWKS pair; the mounted SSO
routes have built-in support for:

| Provider | Mounted SSO settings |
| --- | --- |
| Okta | `OKTA_DOMAIN`, `OKTA_CLIENT_ID`, `OKTA_CLIENT_SECRET` |
| Auth0 | `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` |
| Keycloak | `KEYCLOAK_DOMAIN`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` |
| Google | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |

See [Authentication](../api/authentication.md#oidc-token-validation) for the validation flow.

### Ingress Configuration

Enable ingress in values.yaml:

```yaml
ingress:
  enabled: true
  className: nginx
  host: mutx.example.com
  tls:
    enabled: true
    secretName: mutx-tls
```

Ensure your ingress controller is installed and the TLS secret exists.

### Autoscaling

The Horizontal Pod Autoscaler (HPA) is disabled by default. Enable it:

```yaml
frontend:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 75
```

## Resource Defaults

| Overlay / component | CPU request | Memory request | CPU limit | Memory limit | Replicas |
| --- | --- | --- | --- | --- | --- |
| Default API | 100m | 256Mi | 1000m | 1Gi | 1 |
| Default frontend | 100m | 256Mi | 500m | 512Mi | 1 |
| Staging API | 100m | 256Mi | 1000m | 1Gi | 1 |
| Production API | 500m | 1Gi | 2000m | 2Gi | 1 |
| Production frontend | 250m | 512Mi | 1000m | 1Gi | 2 |

## Verify Deployment

```bash
# Check pod status
kubectl get pods -n staging  # or production

# View logs
kubectl logs -n staging -l app.kubernetes.io/name=mutx

# Run the rendered Helm test hook for an installed release
helm test mutx-prod --namespace production --logs
```

## Helm Lint

Validate the Helm chart:

```bash
make helm-lint

# Or directly
helm lint infrastructure/helm/mutx/
```
