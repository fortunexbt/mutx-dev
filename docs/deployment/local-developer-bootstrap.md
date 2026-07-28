---
description: Comprehensive local setup flow from prerequisites to validated API access.
icon: wrench
---

# Local Developer Bootstrap

Use this guide when setting up the repository for local development the first time.

## 1. Prerequisites

Install the following on your machine:

* Git
* Node.js `>=24.15.0`
* npm `>=11.12.1 <12` (the repository pins `npm@11.12.1`)
* Python `3.10+`
* Docker + Docker Compose v2
* `make` and `curl` (recommended for local verification commands)

Quick check:

```bash
git --version
node -v
npm -v
python3 --version
docker --version
docker compose version
make --version
curl --version
```

## 2. Clone and Setup

```bash
git clone https://github.com/mutx-dev/mutx-dev.git
cd mutx-dev

# Frontend dependencies from the committed package-lock.json
npm ci --legacy-peer-deps

# Python deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev,tui]"
```

## 3. Environment Configuration

Create your local environment file:

```bash
cp .env.example .env
```

Minimum values to confirm in `.env`:

```bash
DATABASE_URL=postgresql://mutx:mutx_password@localhost:5432/mutx
DATABASE_SSL_MODE=disable
JWT_SECRET=replace-with-a-stable-secret
NEXT_PUBLIC_SITE_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development
```

Generate a local JWT secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Optional integration keys (safe to leave empty for local bootstrap):

* `RESEND_API_KEY`
* `TELEGRAM_BOT_TOKEN`
* `NEXT_PUBLIC_TURNSTILE_SITE_KEY`
* `TURNSTILE_SECRET_KEY`

Note: `./scripts/dev.sh` auto-creates `.env` from `.env.example` and generates a `JWT_SECRET` if `.env` is missing.

## 4. Running Locally

Preferred one-command flow:

```bash
make dev
```

Equivalent Make target:

```bash
make dev-up
```

Use `make dev-up` when you want the stack detached, `make dev-logs` to follow logs, and `make dev-stop` to stop it.

This starts PostgreSQL, Redis, FastAPI, and Next.js via Docker Compose.

Local URLs:

* Frontend: `http://localhost:3000`
* Dashboard: `http://localhost:3000/dashboard`
* API: `http://localhost:8000`
* API docs: `http://localhost:8000/docs`

Manual split-process mode (optional):

```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres redis

# Terminal 1 (API)
source .venv/bin/activate
uvicorn src.api.main:app --reload --port 8000

# Terminal 2 (web)
npm run dev
```

## 5. Testing the Setup

Basic API health checks:

```bash
./scripts/test-api.sh
```

Auth bootstrap without manual curl token plumbing:

```bash
make test-auth
make test-api-auth
```

`make test-auth` registers/logs in a test user and prints a ready-to-use token.

If you want to drive the Python CLI or `mutx tui` with the canonical assistant-first flow, use:

```bash
mutx setup local --name "Local Operator" --no-input
```

`make test-api-auth` runs authenticated endpoint checks through `scripts/test-api.sh --with-auth`.

Full repository validation:

```bash
npm run lint
npm run typecheck
./scripts/test.sh
```

Skip Playwright when you only need local API + build checks:

```bash
MUTX_SKIP_PLAYWRIGHT=1 ./scripts/test.sh
```

For common local failures, see [Common Issues](../troubleshooting/common-issues.md).
