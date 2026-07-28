---
description: Complete production deployment guide for MUTX.
icon: factory
---

# Production Deployment Guide

This guide covers deploying MUTX to production with security, reliability, and scalability in mind.

## Overview

The production stack consists of:

| Component | Purpose | Default Port |
|-----------|---------|--------------|
| **PostgreSQL** | Primary database | 5432 |
| **Redis** | Caching & session store | 6379 |
| **API** | FastAPI backend | 8000 |
| **Frontend** | Next.js web app | 3000 |
| **Nginx** | Reverse proxy & SSL termination | 80/443 |

---

## Prerequisites

### System Requirements

* **CPU**: 2+ cores (4 recommended)
* **RAM**: 4GB minimum, 8GB recommended
* **Disk**: 20GB+ for database and logs
* **OS**: Ubuntu 22.04 LTS or similar Linux distribution
* **Docker**: 24.0+ with docker-compose plugin
* **Domain**: Registered domain with DNS access

### Required Accounts & Keys

* [ ] PostgreSQL database (managed service or self-hosted)
* [ ] Redis instance (managed service or self-hosted)
* [ ] Resend account for transactional email
* [ ] SSL certificate (Let's Encrypt or purchased)
* [ ] Domain pointed to your server IP

---

## Environment Configuration

### Required Environment Variables

Copy `.env.production.example` to `.env.production` and replace every
placeholder. The bundled Compose database is on a private bridge and does not
terminate TLS, so it explicitly uses `DATABASE_SSL_MODE=disable`; managed
databases should use `require` or `verify-full`.

```bash
# Database
POSTGRES_USER=mutx
POSTGRES_PASSWORD=<secure-random-password>
POSTGRES_DB=mutx
DATABASE_URL=postgresql://mutx:<password>@postgres:5432/mutx
DATABASE_SSL_MODE=disable

# Independent secrets (generate each separately)
JWT_SECRET=<minimum-32-character-secret>
SECRET_ENCRYPTION_KEY=<different-minimum-32-character-secret>

# Password-account verification and transactional email
REQUIRE_EMAIL_VERIFICATION=true
RESEND_API_KEY=re_xxxxxxxxxxxx

# Public waitlist abuse protection
NEXT_PUBLIC_TURNSTILE_SITE_KEY=<turnstile-site-key>
TURNSTILE_SECRET_KEY=<turnstile-secret-key>

# Canonical hosts
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_SITE_URL=https://yourdomain.com
FRONTEND_URL=https://app.yourdomain.com
PUBLIC_API_URL=https://api.yourdomain.com
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com,https://pico.yourdomain.com
AUTH_REDIRECT_ORIGINS=https://yourdomain.com,https://app.yourdomain.com,https://pico.yourdomain.com
ALLOWED_HOSTS=api.yourdomain.com,api,localhost,127.0.0.1
MUTX_API_HOST=api.yourdomain.com
MUTX_NETWORK_SUBNET=172.30.40.0/24
FORWARDED_ALLOW_IPS=172.30.40.0/24
MUTX_EDGE_BIND_ADDRESS=0.0.0.0
```

### Security Checklist

- [ ] Use strong, randomly generated passwords (16+ characters)
- [ ] JWT_SECRET is unique and not shared with other deployments
- [ ] `DATABASE_SSL_MODE=disable` only for bundled private Postgres; managed endpoints require TLS
- [ ] `JWT_SECRET` and `SECRET_ENCRYPTION_KEY` are distinct
- [ ] the certificate covers marketing, www, app, Pico, and API hostnames
- [ ] email verification has a working Resend or SMTP provider
- [ ] both Turnstile keys are configured for public waitlist submissions
- [ ] CORS_ORIGINS explicitly lists only your production domains
- [ ] `MUTX_API_HOST` matches the hostname in both API URLs and is included exactly in `ALLOWED_HOSTS`
- [ ] `FORWARDED_ALLOW_IPS` equals this deployment's private Compose bridge CIDR, never `*`
- [ ] host firewall exposes the configurable nginx edge bind on ports 80 and 443
- [ ] No debug or development settings enabled

---

## Deployment Methods

### Option 1: Docker Compose (Recommended for Single Server)

```bash
# Clone and navigate to project
git clone https://github.com/your-org/mutx.git
cd mutx

# Create environment file
cp .env.production.example .env.production
# Edit .env.production with your values

# First installation only: explicitly initialize the empty external volumes.
bash scripts/bootstrap-production-volumes.sh

# Validate secrets, TLS/SAN coverage, persistent-volume identity, migrations,
# health, monitor activity, and then start the production stack.
bash scripts/deploy-production.sh

# Verify services
docker compose --project-name docker --env-file .env.production \
  -f infrastructure/docker/docker-compose.prod.yml ps
```

Do not run the bootstrap script against an existing installation. It refuses
non-empty volumes. The deployment script also refuses missing or empty volumes,
which prevents a project-name change from silently selecting a fresh database.

### Option 2: DigitalOcean with Terraform

See [DigitalOcean Deployment](digitalocean.md) for full instructions.

### Option 3: Managed Platform (Railway)

See [Railway Deployment](railway.md) for full instructions.

### Option 4: Kubernetes with Helm

For container-orchestrated environments, deploy MUTX using the Helm chart at `infrastructure/helm/mutx/`.

```bash
# Install the production release
helm upgrade --install mutx-prod infrastructure/helm/mutx \
  -f infrastructure/helm/mutx/values.prod.yaml \
  --namespace production --create-namespace
```

Key production values overrides (set in `values.prod.yaml` or via `--set`):

```yaml
# values.prod.yaml highlights
api:
  replicaCount: 1
  image:
    repository: registry.example.com/mutx-api
    tag: "1.4.0"
  existingSecret: mutx-prod-api-env
  env:
    ENVIRONMENT: production
    ALLOWED_HOSTS: mutx.example.com,localhost,127.0.0.1
    FORWARDED_ALLOW_IPS: 10.244.0.0/16 # replace with the ingress source/pod CIDR

frontend:
  replicaCount: 2
  image:
    repository: registry.example.com/mutx-frontend
    tag: "1.4.0"
  autoscaling:
    enabled: false

migrations:
  enabled: true
```

The chart does not install PostgreSQL. The migration hook and API currently consume
the same `api.existingSecret`, so its `DATABASE_URL` role must be able to run Alembic
DDL as well as normal application queries; the chart does not yet model a separate
least-privilege migration role.

#### RBAC Configuration

RBAC role enforcement is part of protected route dependencies and needs no
feature flag. If using the mounted Okta SSO flow, configure its provider
credentials and public callback origin:

```yaml
api:
  existingSecret: mutx-api-env
  env:
    PUBLIC_API_URL: "https://api.example.com"
    OKTA_DOMAIN: "https://your-org.okta.com"
    OKTA_CLIENT_ID: "your-client-id"
```

Store `OKTA_CLIENT_SECRET` in `mutx-api-env`, alongside the other API secrets.

The SSO callback validates and links the external identity. Route dependencies then reload the
local user and check persisted `users.roles`; provider role claims do not grant
MUTX privileges. See [Security Architecture](../architecture/security.md#rbac-enforcement)
for role definitions.

#### Generic OIDC Validator Environment Variables

```yaml
api:
  existingSecret: mutx-api-env
  env:
    OIDC_ISSUER: "https://your-idp.example.com"
    OIDC_CLIENT_ID: "mutx-production"
    OIDC_JWKS_URI: "https://your-idp.example.com/.well-known/jwks.json"
```

These values configure the library-level `validate_oidc_token(...)` helper. No
mounted protected route automatically accepts an arbitrary provider bearer
token; interactive SSO requires the provider-specific credentials described
above.

See [Authentication](../api/authentication.md#oidc-token-validation) for the full OIDC validation flow.

---

## SSL/TLS Configuration

### Using Let's Encrypt (Automatic)

For Docker deployments, use the nginx-ssl setup:

```bash
# Create SSL directory
mkdir -p infrastructure/docker/ssl

# Using Certbot
certbot certonly --standalone \
  -d yourdomain.com \
  -d www.yourdomain.com \
  -d app.yourdomain.com \
  -d pico.yourdomain.com \
  -d api.yourdomain.com

# Copy certificates
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem infrastructure/docker/ssl/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem infrastructure/docker/ssl/key.pem

# The canonical nginx.prod.conf already requires TLS 1.2 or TLS 1.3.
docker compose -f infrastructure/docker/docker-compose.prod.yml restart nginx
```

### Manual SSL Configuration

Update `infrastructure/docker/nginx.prod.conf` only when your certificate mount or domains differ:

```nginx
ssl_certificate /etc/nginx/ssl/cert.pem;
ssl_certificate_key /etc/nginx/ssl/key.pem;
```

---

## Health Checks & Monitoring

### API Health Endpoints

MUTX provides two health check endpoints:

| Endpoint | Purpose | Use Case |
|----------|---------|----------|
| `/health` | Liveness probe | Kubernetes liveness, restart detection |
| `/ready` | Readiness probe | Kubernetes readiness, traffic routing |

```bash
# Check liveness
curl https://api.yourdomain.com/health

# Check readiness
curl https://api.yourdomain.com/ready

# /health: {"status":"healthy","database":"ready",...}
# /ready:  {"status":"ready","database":"ready",...}
```

### Prometheus Metrics

The API exposes Prometheus metrics at `/metrics`. Configure your Prometheus to scrape:

```yaml
scrape_configs:
  - job_name: 'mutx-api'
    static_configs:
      - targets: ['api:8000']
```

### Monitoring Stack

Deploy the monitoring stack:

```bash
cd infrastructure
cp .env.monitoring.example .env.monitoring
# Edit .env.monitoring with strong passwords

make monitor-up
```

Access Grafana at `http://localhost:3001` (default credentials: admin/admin).

---

## Database Setup

### Initial Migration

On first deployment, run database migrations:

```bash
# The one-shot migrate service runs before the API. Verify the database is at head:
docker compose -f infrastructure/docker/docker-compose.prod.yml exec api alembic current
```

### Backup Configuration

Set up automated backups for PostgreSQL:

```bash
# Add to crontab
0 2 * * * pg_dump -h postgres -U mutx -Fc mutx > /backups/mutx_$(date +\%Y\%m\%d).pgdump
```

For managed databases (DigitalOcean, AWS RDS), enable automated backups in the console.

---

## Security Hardening

### Network Isolation

The production compose file uses a dedicated bridge network. For additional isolation:

```yaml
networks:
  mutx-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

### Firewall Configuration

If self-hosting, configure UFW:

```bash
# Allow SSH, HTTP, HTTPS
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp

# Enable firewall
ufw enable
```

### Fail2ban (Optional)

Install fail2ban to protect against brute force:

```bash
apt install fail2ban
```

---

## Scaling Considerations

### Vertical Scaling

Add or adjust per-service resource limits in `infrastructure/docker/docker-compose.prod.yml`:

```yaml
deploy:
  resources:
    limits:
      memory: 2G    # Increase for higher load
      cpus: '2.0'
```

### Horizontal Scaling

For horizontal scaling, consider:

1. **Load Balancer**: Add HAProxy or Nginx upstream
2. **Database**: Use managed PostgreSQL (DigitalOcean, AWS RDS)
3. **Redis**: Use managed Redis (Redis Cloud, DigitalOcean)
4. **Session Storage**: Configure Redis for session persistence

### Performance Tuning

For high-traffic deployments:

```bash
# Redis optimization
redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru

# PostgreSQL tuning (postgresql.conf)
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| 502 Bad Gateway | Check nginx logs: `docker compose -f infrastructure/docker/docker-compose.prod.yml logs nginx` |
| Database connection failure | Verify DATABASE_URL and SSL settings |
| JWT errors | Ensure JWT_SECRET matches across restarts |
| CORS errors | Verify CORS_ORIGINS includes your domain |

### Logs

```bash
# All services
docker compose -f infrastructure/docker/docker-compose.prod.yml logs

# Specific service
docker compose -f infrastructure/docker/docker-compose.prod.yml logs -f api
```

### Restart Procedure

```bash
# Full restart
docker compose -f infrastructure/docker/docker-compose.prod.yml restart

# Or rebuild and restart
docker compose -f infrastructure/docker/docker-compose.prod.yml up -d --build
```

---

## Maintenance

### Regular Tasks

- [ ] Monitor disk space (database logs can grow)
- [ ] Review application logs weekly
- [ ] Update images monthly (`docker compose pull`)
- [ ] Test backups quarterly

### Updates

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose -f infrastructure/docker/docker-compose.prod.yml up -d --build
```

---

## Related Documentation

* [Infrastructure Guide](https://github.com/mutx-dev/mutx-dev/blob/main/infrastructure.md)
* [Security Architecture](../architecture/security.md)
* [Docker Guide](docker.md)
* [DigitalOcean Deployment](digitalocean.md)
* [Railway Deployment](railway.md)
