# MUTX Helm Chart

A Helm chart for deploying MUTX agentic development platform to Kubernetes.

## Prerequisites

- **Helm** 3.0+
- **Kubernetes** 1.24+
- A container registry with the `mutx/mutx` image available

## Quick Install

```bash
# Add the repo (if published to a Helm repo)
# helm repo add mutx https://charts.mutx.dev

# Install from local chart
helm upgrade --install mutx ./infrastructure/helm/mutx \
  --namespace mutx --create-namespace

# Install with staging overrides
helm upgrade --install mutx-staging ./infrastructure/helm/mutx \
  -f ./infrastructure/helm/mutx/values.staging.yaml \
  --namespace staging --create-namespace

# Install with production overrides
helm upgrade --install mutx-prod ./infrastructure/helm/mutx \
  -f ./infrastructure/helm/mutx/values.prod.yaml \
  --namespace production --create-namespace
```

## Configuration Reference

The following table lists the configurable parameters of the MUTX chart and their default values.

### Image

| Parameter | Description | Default |
| --- | --- | --- |
| `image.repository` | Container image repository | `mutx/mutx` |
| `image.tag` | Container image tag | `latest` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |

### Replicas & Resources

| Parameter | Description | Default |
| --- | --- | --- |
| `replicaCount` | Number of pod replicas | `1` |
| `resources.limits.cpu` | CPU limit | `1000m` |
| `resources.limits.memory` | Memory limit | `1Gi` |
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `256Mi` |

### Service

| Parameter | Description | Default |
| --- | --- | --- |
| `service.type` | Kubernetes Service type | `ClusterIP` |
| `service.port` | Service port | `8000` |

### Ingress

| Parameter | Description | Default |
| --- | --- | --- |
| `ingress.enabled` | Enable ingress resource | `false` |
| `ingress.className` | Ingress class name | `nginx` |
| `ingress.host` | Hostname for the ingress | `mutx.local` |
| `ingress.tls.enabled` | Enable TLS on ingress | `true` |
| `ingress.tls.secretName` | TLS secret name | `mutx-tls` |

### Autoscaling

| Parameter | Description | Default |
| --- | --- | --- |
| `autoscaling.enabled` | Enable HPA | `false` |
| `autoscaling.minReplicas` | Minimum replicas | `1` |
| `autoscaling.maxReplicas` | Maximum replicas | `10` |
| `autoscaling.targetCPUUtilizationPercentage` | CPU target for scale-up | `75` |

### Environment Variables

| Parameter | Description | Default |
| --- | --- | --- |
| `env.REDIS_URL` | Redis connection string | _(not set)_ |
| `env.LOG_LEVEL` | Application log level | _(not set)_ |
| `env.ENVIRONMENT` | Deployment environment name | _(not set)_ |
| `secretEnv.DATABASE_URL` | PostgreSQL connection string | _(not set)_ |
| `secretEnv.JWT_SECRET` | JWT signing secret | _(required in production)_ |
| `secretEnv.SECRET_ENCRYPTION_KEY` | Secret encryption key | _(required in production)_ |
| `secretEnv.RECEIPT_SIGNING_PRIVATE_KEY` | Hex-encoded 32-byte Ed25519 receipt signing seed | _(required in production)_ |
| `secretEnv.RECEIPT_SIGNING_KEY_ID` | Stable receipt signing key identifier | `mutx-runtime` |
| `secretEnv.OIDC_ISSUER` | OIDC provider issuer URL | _(not set)_ |
| `secretEnv.OIDC_CLIENT_ID` | OIDC client ID | _(not set)_ |
| `secretEnv.OIDC_JWKS_URI` | OIDC JWKS endpoint | _(not set)_ |

## Production Deployment

Use `values.prod.yaml` for production-grade settings:

```bash
helm upgrade --install mutx-prod ./infrastructure/helm/mutx \
  -f ./infrastructure/helm/mutx/values.prod.yaml \
  --namespace production --create-namespace
```

`values.prod.yaml` sets:

- `replicaCount: 1` until governance state is moved to shared storage
- `image.pullPolicy: Always`
- `resources.limits: cpu 2000m, memory 2Gi`
- `resources.requests: cpu 500m, memory 1Gi`
- `autoscaling.enabled: false` until governance state is moved to shared storage
- `env.LOG_LEVEL: "WARNING"`
- `env.ENVIRONMENT: "production"`
- `secretEnv.JWT_SECRET`, `secretEnv.SECRET_ENCRYPTION_KEY`, and
  `secretEnv.RECEIPT_SIGNING_PRIVATE_KEY` must be set
- Ingress enabled with TLS

## RBAC Setup

MUTX v1.4.0 uses role-based access control with four roles:

| Role | Scope |
| --- | --- |
| `ADMIN` | Full access to all endpoints (super-role) |
| `AUDIT_ADMIN` | Audit log and trace endpoints |
| `DEVELOPER` | Agent CRUD and approval workflows |
| `VIEWER` | Read-only access to owned resources |

Roles are sourced from OIDC token claims. Configure your identity provider to include role claims in tokens, then set the OIDC env vars:

```yaml
# In values.yaml or a -f override
secretEnv:
  OIDC_ISSUER: "https://your-idp.example.com"
  OIDC_CLIENT_ID: "mutx-production"
  OIDC_JWKS_URI: "https://your-idp.example.com/.well-known/jwks.json"
```

MUTX extracts roles from these token claims (checked in order): `roles`, `groups`, `custom:roles`, `realm_access.roles`, `resource_access.roles`.

See [Security Architecture](../../../docs/architecture/security.md#rbac-enforcement) for details.

## OIDC Configuration

MUTX validates OIDC tokens from Okta, Auth0, Keycloak, and Google. Configure via environment variables:

```yaml
secretEnv:
  OIDC_ISSUER: "https://your-org.okta.com"
  OIDC_CLIENT_ID: "0oa1abc2def3ghi4jkl5"
  OIDC_JWKS_URI: "https://your-org.okta.com/oauth2/v1/keys"
```

The validation flow:

1. Fetches JWKS from `OIDC_JWKS_URI`
2. Verifies token signature against the matching key
3. Validates `iss`, `aud`, and `exp` claims
4. Falls back to the provider `/userinfo` endpoint for opaque tokens
5. Maps the verified claims to an internal `SSOTokenUser` with roles

See [Authentication docs](../../../docs/api/authentication.md#oidc-token-validation) for the full flow.

## OTel Collector Configuration

To export traces and metrics to an OpenTelemetry Collector, set the following environment variables:

```yaml
env:
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
  OTEL_EXPORTER_OTLP_PROTOCOL: "grpc"
  OTEL_SERVICE_NAME: "mutx-api"
  OTEL_RESOURCE_ATTRIBUTES: "deployment.environment=production"
```

Ensure the OTel Collector is deployed in the cluster and reachable at the configured endpoint.

## Verify Deployment

```bash
# Check pod status
kubectl get pods -n production

# View logs
kubectl logs -n production -l app.kubernetes.io/name=mutx

# Run the Helm test
helm test mutx-prod -n production
```

## Upgrade

```bash
helm upgrade mutx-prod ./infrastructure/helm/mutx \
  -f ./infrastructure/helm/mutx/values.prod.yaml \
  --namespace production
```

## Uninstall

```bash
helm uninstall mutx-prod --namespace production
```
