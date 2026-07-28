---
description: Local and production Docker workflows for running the MUTX stack.
icon: box
---

# Docker Guide

This repo ships both a local development compose file and a production-oriented compose file.

## Local Development Compose

Start everything:

```bash
docker compose -f infrastructure/docker/docker-compose.yml up --build
```

Run only data services in the background:

```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres redis
```

The local compose file currently starts:

* `postgres` on `5432`
* `redis` on `6379`
* `api` on `8000`
* `frontend` on `3000`

## Useful Commands

```bash
docker compose -f infrastructure/docker/docker-compose.yml ps
docker compose -f infrastructure/docker/docker-compose.yml logs -f api
docker compose -f infrastructure/docker/docker-compose.yml logs -f frontend
docker compose -f infrastructure/docker/docker-compose.yml restart api
docker compose -f infrastructure/docker/docker-compose.yml build api
docker compose -f infrastructure/docker/docker-compose.yml down
docker compose -f infrastructure/docker/docker-compose.yml down -v
```

## Validate the Local Stack

Once the containers are up:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
open http://localhost:3000
```

## Production Compose

The production file in this repo is:

```
infrastructure/docker/docker-compose.prod.yml
```

Bring it up with:

```bash
docker compose -f infrastructure/docker/docker-compose.prod.yml up -d --build
```

Inspect it with:

```bash
docker compose -f infrastructure/docker/docker-compose.prod.yml ps
docker compose -f infrastructure/docker/docker-compose.prod.yml logs -f api
```

## Environment Variables

Typical values for local container work:

```bash
DATABASE_URL=postgresql://mutx:mutx_password@postgres:5432/mutx
API_HOST=0.0.0.0
API_PORT=8000
JWT_SECRET=dev-secret-change-in-production
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

## Testing Notes

* The `api` image installs `requirements.txt`, not the root dev extras, so `pytest` is not available in that container by default.
* `npm test` runs the Jest unit suite in `tests/unit`.
* Playwright targets the local standalone app server from `playwright.config.ts`; run `npm run build` before e2e checks so `.next/standalone` exists.

For verification, prefer host commands such as:

```bash
npm run lint
npm run build
npx playwright test --list
```
