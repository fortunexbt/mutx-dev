# MUTX Helm chart

This chart deploys the MUTX web product as separate Next.js and FastAPI workloads. It
does not install PostgreSQL, Redis, an ingress controller, a certificate manager, an
OpenTelemetry collector, or a secret manager.

## Runtime shape

The chart contains 13 template files and renders these application components:

| Component | Default | Image/command | Port or purpose |
| --- | --- | --- | --- |
| Frontend | 1 replica | `mutx-frontend:1.4.0` | Next.js on `3000` |
| API | 1 replica | `mutx-api:1.4.0` | FastAPI on `8000` |
| Monitor | 1 replica | `python -m src.api.monitor_worker` | Singleton database monitor |
| Document worker | Disabled | `python -m src.api.document_worker` | Optional document queue consumer |
| Reasoning worker | Disabled | `python -m src.api.reasoning_worker` | Optional reasoning queue consumer |
| Migration | Disabled | `alembic upgrade head` | Optional pre-install/pre-upgrade hook |

The frontend receives an internal URL for the API Service. When ingress is enabled,
`/v1`, `/health`, `/ready`, and `/metrics` route to FastAPI; `/` routes to Next.js.
The API liveness path is `/health`, while readiness uses the database-aware `/ready`
path. The frontend uses a TCP liveness check and an HTTP `/` readiness check.
The monitor writes a successful-cycle heartbeat and all three monitor probes reject
a missing or stale heartbeat; repeated cycle failures terminate the worker for restart.

## Prerequisites

- Kubernetes 1.24 or newer
- Helm 3 or 4
- Separately built frontend and API images from `Dockerfile` (or
  `infrastructure/docker/Dockerfile.frontend`) and
  `infrastructure/docker/Dockerfile.api.production`
- A reachable PostgreSQL database for staging and production
- An existing Kubernetes Secret for staging/production API credentials

The `registry.example.com/*` repositories in the environment overlays are deliberate
placeholders. Override them with images built from this repository before installing.

## Render and validate

Rendering does not contact a cluster:

```bash
helm lint infrastructure/helm/mutx
helm lint infrastructure/helm/mutx -f infrastructure/helm/mutx/values.prod.yaml
helm template mutx infrastructure/helm/mutx
helm template mutx-prod infrastructure/helm/mutx \
  -f infrastructure/helm/mutx/values.prod.yaml
python -m unittest discover -s infrastructure/helm/mutx/tests -v
```

The default values are a development render, not a self-contained stack: no database
is installed and no `DATABASE_URL` is supplied. Use the repository's development
Compose stack when an all-in-one local environment is wanted.

## Production secret

`values.prod.yaml` expects an externally managed Secret named `mutx-prod-api-env`.
It must exist before Helm runs because the migration is a pre-install/pre-upgrade
hook. At minimum it needs:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mutx-prod-api-env
type: Opaque
stringData:
  DATABASE_URL: postgresql://mutx:replace-me@postgres.example.com:5432/mutx
  JWT_SECRET: replace-with-at-least-32-random-characters
  SECRET_ENCRYPTION_KEY: replace-with-a-distinct-fernet-key
```

Do not commit real values. Create the Secret through the cluster's secret delivery
system. If OIDC is configured, provide `OIDC_ISSUER`, `OIDC_CLIENT_ID`, and
`OIDC_JWKS_URI` together in the API Secret. `api.secretEnv` can create a chart-owned
Secret for non-production use, but it is mutually exclusive with
`api.existingSecret`. Frontend-only credentials belong in
`frontend.existingSecret` or `frontend.secretEnv`.

The chart does not install PostgreSQL or create database roles. The migration hook and
API currently read the same `api.existingSecret`; consequently its `DATABASE_URL` role
must have Alembic DDL privileges in addition to runtime DML privileges.

Install only after replacing the image repositories, hostname, TLS Secret, and API
Secret name as appropriate:

```bash
helm upgrade --install mutx-prod infrastructure/helm/mutx \
  -f infrastructure/helm/mutx/values.prod.yaml \
  --namespace mutx --create-namespace \
  --wait --timeout 10m
```

The migration hook runs before application resources. A failed migration fails the
Helm operation. The hook deliberately uses the namespace's `default` ServiceAccount
with token mounting disabled, because the chart-created ServiceAccount does not exist
yet during a pre-install hook. Set `migrations.serviceAccountName` to another
pre-existing, unprivileged ServiceAccount if the namespace removes the default one.

## Configuration

### Images and processes

| Parameter | Default | Meaning |
| --- | --- | --- |
| `api.image.repository` | `mutx-api` | FastAPI/worker image |
| `api.image.tag` | `1.4.0` | API image tag |
| `api.port` | `8000` | FastAPI container port |
| `api.service.port` | `8000` | API Service port |
| `api.replicaCount` | `1` | API pod replicas; currently constrained to one |
| `frontend.image.repository` | `mutx-frontend` | Next.js image |
| `frontend.image.tag` | `1.4.0` | Frontend image tag |
| `frontend.port` | `3000` | Next.js container port |
| `frontend.service.port` | `3000` | Frontend Service port |
| `frontend.replicaCount` | `1` | Frontend pod replicas when its HPA is off |
| `workers.monitor.enabled` | `true` | Run the singleton monitor outside the API |
| `migrations.enabled` | `false` | Run Alembic as a Helm hook |

`api.env` and `frontend.env` accept non-secret environment variables. The chart owns
the process-critical `API_PORT`, `PORT`, `HOSTNAME`, `INTERNAL_API_URL`,
`BACKGROUND_MONITOR_ENABLED`, `MUTX_DOCUMENTS_ENABLED`, `MUTX_REASONING_ENABLED`,
`MUTX_HOME`, `MUTX_ARTIFACTS_DIR`, and `PYTHONPATH` values; entries with those names
in an `env` map are overridden by explicit container environment variables.

### Queue workers

Setting `features.documents=true` or `features.reasoning=true` enables the matching
FastAPI feature. With no standalone worker, its queue consumer runs inside the single
API process, matching `src/api/main.py`. Enabling `workers.document` or
`workers.reasoning` renders the corresponding standalone process and disables that
in-process consumer while keeping the API feature available.

Standalone artifact workers require persistent `ReadWriteMany` storage so uploads
and generated artifacts resolve to the same paths in API and worker pods. Worker
replicas are limited to one because the current database claim operation is not a
multi-consumer locking primitive.

### Persistence

| Parameter | Default | Meaning |
| --- | --- | --- |
| `persistence.enabled` | `false` | Create or mount a PVC for API-local state |
| `persistence.existingClaim` | empty | Reuse an existing claim instead of creating one |
| `persistence.accessModes` | `[ReadWriteOnce]` | Claim access modes |
| `persistence.size` | `10Gi` | Requested capacity |
| `persistence.retain` | `true` | Add Helm's keep policy to a chart-created PVC |
| `persistence.mountPath` | `/var/lib/mutx` | API and artifact-worker data directory |

The mounted data directory is the API working directory and contains the local audit
database. `MUTX_HOME` and `MUTX_ARTIFACTS_DIR` are placed beneath it for credential
broker configuration and managed artifacts. With persistence disabled, an
`emptyDir` is used and all of that local state is lost with the pod. A retained PVC
is not deleted by `helm uninstall`; remove it explicitly only after preserving data.

`ReadWriteOnce` is suitable for the production overlay's single API pod. Standalone
artifact workers are rejected unless `ReadWriteMany` is declared, because they must
mount the same claim as the API. The storage class must actually support that mode.

### Ingress and scaling

| Parameter | Default | Meaning |
| --- | --- | --- |
| `ingress.enabled` | `false` | Render the unified product Ingress |
| `ingress.className` | empty | Ingress controller class |
| `ingress.host` | `mutx.local` | Shared frontend/API hostname |
| `ingress.tls.enabled` | `false` | Configure TLS on the Ingress |
| `frontend.autoscaling.enabled` | `false` | Render a frontend CPU HPA |

The frontend HPA uses `autoscaling/v2` and CPU utilization against its configured CPU
request. When enabled, the frontend Deployment omits `spec.replicas`. The chart does
not autoscale the API or workers: the API still owns pod-local SQLite audit and
credential-broker files, and the current queue claim operations are not safe
multi-consumer locks. `api.replicaCount` and every worker replica count are therefore
schema-constrained to one.

Set `api.env.ALLOWED_HOSTS` and `api.env.CORS_ORIGINS` to the ingress hostname.
`FORWARDED_ALLOW_IPS` defaults to loopback for development. Production rendering
rejects wildcard and loopback-only values; replace the overlay example with only the
addresses or CIDRs used by that cluster's ingress proxies.

## ServiceAccount and application RBAC

The chart creates an unprivileged ServiceAccount and disables token automounting on
all workloads. It intentionally creates no Kubernetes Role, ClusterRole, or binding:
MUTX does not call the Kubernetes API in this deployment shape.

MUTX's `ADMIN`, `AUDIT_ADMIN`, `DEVELOPER`, and `VIEWER` permissions are application
RBAC roles derived from authenticated claims. They are unrelated to Kubernetes RBAC.
OIDC is optional, but its three settings must be supplied as a complete set.

## Helm test

After the release is ready, verify both services:

```bash
helm test mutx-prod --namespace mutx --logs
```

The test is a `batch/v1` Job. It checks FastAPI `/ready` and the Next.js root page;
it does not mutate application data.
