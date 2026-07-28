---
description: Managed hosting path for deploying MUTX on Railway.
icon: train
---

# Railway Deployment

Deploy to Railway for managed hosting.

## Railway Setup

### 1. Install Railway CLI

```bash
# macOS
brew install railway

# Or using npm
npm install -g @railway/cli

# Login
railway login

# Verify
railway whoami
```

### 2. Initialize Project

```bash
# Create new project
railway init

# Or link existing
railway link
```

### 3. Add Database

```bash
# Add PostgreSQL
railway add postgresql

# Add Redis
railway add redis
```

## Environment Variables

### Required Variables

Set these in Railway dashboard (Settings → Variables):

```bash
# Database (auto-populated by Railway)
DATABASE_URL=postgresql://...  # Auto-configured

# Only set this if your Railway PostgreSQL endpoint rejects SSL upgrade attempts
# DATABASE_SSL_MODE=disable

# JWT
JWT_SECRET=your-secure-jwt-secret-min-32-chars
SECRET_ENCRYPTION_KEY=your-distinct-fernet-key

# Exact API hosts and Railway edge proxy trust. Never use `*` for either value.
ALLOWED_HOSTS=api.yourdomain.com,your-api-production.up.railway.app,your-api.railway.internal
FORWARDED_ALLOW_IPS=100.0.0.0/8

# Optional startup behavior
DATABASE_REQUIRED_ON_STARTUP=false

# Site URLs
NEXT_PUBLIC_SITE_URL=https://your-app.railway.app

# Frontend -> API routing
# For a single Railway service, NEXT_PUBLIC_API_URL can stay public.
# For split frontend/backend Railway services, prefer the backend private domain here.
INTERNAL_API_URL=http://your-backend.railway.internal:8080

# Optional public API URL if you intentionally expose the backend directly.
NEXT_PUBLIC_API_URL=https://api.yourdomain.com

# Email verification is fail-closed in production: configure Resend or both
# SMTP_USER and SMTP_PASSWORD whenever REQUIRE_EMAIL_VERIFICATION=true.
REQUIRE_EMAIL_VERIFICATION=true
RESEND_API_KEY=re_your_resend_api_key
RESEND_FROM_EMAIL="MUTX <hello@yourdomain.com>"
```

`SECRET_ENCRYPTION_KEY` must differ from `JWT_SECRET`. Replace the generated
Railway hostnames above with the exact domains shown by the API service. Railway
terminates TLS at its edge; `100.0.0.0/8` is the documented private proxy range
for Railway-hosted reverse proxies. Do not use a wildcard forwarded trust value.
Run the Settings probe before promoting:

```bash
railway run --service <api-service-id> \
  python -c 'from src.api.config import Settings; Settings(); print("settings ok")'
```

### Railway JSON Config

The API service uses a Dockerfile-based deployment and a liveness health check:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "infrastructure/docker/Dockerfile.backend"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10,
    "healthcheckPath": "/health",
    "healthcheckTimeout": 60
  }
}
```

`/health` is a liveness endpoint and returns `200` even while the app is still retrying database startup. Use `/ready` to confirm the database is connected before sending traffic that depends on PostgreSQL.

## Database Setup

### 1. Create Database

In Railway dashboard:

1. Go to your project
2. Click "New" → "Database" → "PostgreSQL"
3. Note the connection string

### 2. Initialize the Schema

```bash
# The API currently bootstraps its tables on startup.
# You can still run ad hoc database commands with Railway CLI if needed.
```

### 3. Seed Data (Optional)

```bash
railway run python -m src.api.seed
```

## Deploy

### 1. Deploy to Railway

```bash
# Deploy the linked service
railway up

# Or with environment
railway up --environment production
```

### 2. View Deployment

```bash
# Open in browser
railway open

# View logs
railway logs

# Follow logs
railway logs -f
```

### 3. Verify Deployment

```bash
# Get deployment URL
railway url

# Test health endpoint
curl https://your-app.railway.app/health
```

## Custom Domain

### 1. Add Domain

In Railway dashboard:

1. Go to project → Settings → Domains
2. Add custom domain (e.g., mutx.dev)
3. Note the CNAME record

### 2. Configure DNS

Add CNAME record:

```
Type: CNAME
Name: mutx.dev
Value: your-app.railway.app
```

### 3. SSL

Railway automatically provisions Let's Encrypt SSL.

## Multiple Services

For a more complete setup, create multiple Railway services:

### Service 1: Frontend (Next.js)

```json
{
  "name": "frontend",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "numReplicas": 2,
    "startCommand": "npm run start"
  }
}
```

### Service 2: API (FastAPI)

Use the checked-in backend Dockerfile:

```text
infrastructure/docker/Dockerfile.backend
```

Railway service configs in this repo already point at the canonical backend and frontend Dockerfiles under `infrastructure/docker/`.

## Production Promotion

MUTX v1.3 treats Railway as the production host for:

- `mutx.dev`
- `app.mutx.dev`
- `api.mutx.dev`

The repo now includes a production-promotion lane for Railway so web/app rollout does not depend on a local operator shell.

### GitHub Actions secrets

Set these repository secrets before using the Railway promotion workflow:

- `RAILWAY_TOKEN`
- `RAILWAY_PROJECT_ID`
- `RAILWAY_FRONTEND_SERVICE_ID`
- `RAILWAY_API_SERVICE_ID`
- `RAILWAY_ENVIRONMENT_ID`

The reusable promotion workflow accepts these optional URL overrides from the
authoritative release workflow:

- `site_url`
- `app_url`
- `api_url`
- `docs_release_url`
- `release_identity_url`

The promotion workflow cannot be dispatched directly. A manual stable promotion starts from
`release.yml` and requires `confirm_production` to equal `PROMOTE <release-tag>`; the release
workflow then passes an immutable tag and commit to the reusable promotion lane after its release
gates complete.

### Promotion flow

The workflow validates the tag, package version, and full commit SHA before invoking
`scripts/promote-railway-production.sh`. It installs the reviewed Railway CLI release from the
upstream binary archive only after verifying its published SHA-256 digest. Uploads run in attached
CI mode and must reach a successful deployment for both API and frontend. The API publishes the exact identity at
`/release`; the frontend publishes it at `/mutx-release.json`. Promotion and final verification
poll both endpoints and fail if either remains stale, has extra fields, or differs from the
validated tag, version, or SHA. API health alone is not release identity proof.

### Live production note

Live production project: `zooming-youth`.

Live Railway production currently runs the backend without an explicit healthcheckPath/healthcheckTimeout in the deployed service manifest, even though repo-side examples may show those fields. Do not change backend Railway healthcheck behavior casually from repo config alone.

Live Railway production currently serves these custom domains:

- frontend custom domains: `mutx.dev`, `app.mutx.dev`
- backend custom domain: `api.mutx.dev`

Live Railway production also uses this backend preDeployCommand:

```bash
python -m pip install -q psycopg2-binary alembic && python -m alembic upgrade head
```

Treat the backend preDeployCommand as production-critical until Railway and repo config are intentionally reconciled. Use live Railway service manifests as the source of truth before changing production deployment behavior.

The verification step should confirm:

- `https://mutx.dev`
- `https://mutx.dev/download/macos`
- `https://app.mutx.dev/login`
- `https://app.mutx.dev/register`
- `https://app.mutx.dev/dashboard`
- `https://api.mutx.dev/health`
- `https://api.mutx.dev/ready`
- `https://mutx.dev/docs/releases/v1.3`

The checked-in `railway-api.json` and `railway-frontend.json` are the repo-side
manifests. The API image starts Uvicorn with `--proxy-headers` and expands
`FORWARDED_ALLOW_IPS` from the service environment; an unset value fails startup.

## Troubleshooting

### Build Failed

```bash
# Check build logs
railway logs --type build
```

### Service Not Starting

```bash
# Check runtime logs
railway logs --type runtime

# Common issues:
# - Missing environment variables
# - Port not exposed
# - Build command incorrect
```

### Database Connection

```bash
# Verify DATABASE_URL
railway variables | grep DATABASE

# Optional: disable SSL if the proxy rejects SSL upgrades
railway variables set DATABASE_SSL_MODE=disable
```

### Custom Domain Not Working

```bash
# Verify DNS propagation
dig yourdomain.com

# Check Railway domain status
railway domain list
```

## Maintenance

### Update Deployment

```bash
# Deploy new version
git push railway main

# Or trigger manually
railway up
```

### Rollback

In Railway dashboard:

1. Go to Deployments
2. Find previous deployment
3. Click "Redeploy"

### Scale

In Railway dashboard:

* Go to Settings → Scaling
* Adjust replicas (max 20 on Pro plan)

## Quick Reference

```bash
# Login
railway login

# Initialize
railway init

# Deploy
railway up

# View logs
railway logs

# Add service
railway add postgresql

# Variables
railway variables

# Custom domain
railway domain add yourdomain.com
```

## Auth And Onboarding Checklist

The hosted onboarding flow now depends on the backend email + OAuth contract, not just password auth.

For the live Railway project `zooming-youth`, set these backend variables on the API service:

```bash
FRONTEND_URL=https://app.mutx.dev
CORS_ORIGINS=https://mutx.dev,https://app.mutx.dev,https://pico.mutx.dev
REQUIRE_EMAIL_VERIFICATION=true
EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS=72

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
DISCORD_CLIENT_ID=...
DISCORD_CLIENT_SECRET=...
```

Set `FRONTEND_URL` to the host that should own email verification and password-reset links. `CORS_ORIGINS` should include every frontend host that can initiate auth or OAuth callbacks.

### OAuth callback URIs

Register the callback URIs on each provider app for every frontend host you plan to serve auth from. Current routes terminate at:

- `https://app.mutx.dev/api/auth/oauth/google/callback`
- `https://app.mutx.dev/api/auth/oauth/github/callback`
- `https://app.mutx.dev/api/auth/oauth/discord/callback`

If Pico moves onto its own authenticated host later, register the equivalent `https://pico.mutx.dev/api/auth/oauth/{provider}/callback` endpoints before switching traffic.

### Database and migrations

The backend Railway service already runs `alembic upgrade head` from the source-controlled [railway.json](https://github.com/mutx-dev/mutx-dev/blob/main/railway.json) before startup, so the external-auth identity table is deployed alongside the API. Keep that pre-start migration step in place for the `zooming-youth` backend service.
