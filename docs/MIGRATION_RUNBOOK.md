# Database Migration Runbook

This document describes the procedures for running database migrations in MUTX production and development environments.

## Overview

MUTX uses [Alembic](https://alembic.sqlalchemy.org/) for database migrations, which allows for version-controlled schema changes with the ability to roll back when necessary.

## Prerequisites

- Python 3.10+
- `psycopg2-binary` installed (for PostgreSQL support)
- Access to the database (DATABASE_URL environment variable)
- Backup of the database before running migrations in production

## Configuration

The migration system is configured via `alembic.ini`:

```ini
[alembic]
script_location = src/api/models/migrations
```

The database connection is read from the `DATABASE_URL` environment variable.

## Common Operations

### 1. Check Current Migration Status

```bash
# Show current revision
alembic current

# Show migration history
alembic history --verbose

# Show pending migrations (not yet applied)
alembic check
```

### 2. Create a New Migration

When you modify models in `src/api/models/models.py`:

```bash
# Auto-generate migration based on model changes
alembic revision --autogenerate -m "description of changes"

# Create empty migration (for manual changes)
alembic revision -m "description of changes"
```

After creating, review the generated migration file in `src/api/models/migrations/versions/`.

### 3. Apply Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply a specific number of migrations
alembic upgrade +1

# Apply up to a specific revision
alembic upgrade <revision_id>
```

### 4. Rollback Migrations

```bash
# Rollback the last migration
alembic downgrade -1

# Rollback to a specific revision
alembic downgrade <revision_id>

# Rollback all migrations (dangerous!)
alembic downgrade base
```

### 5. Rollback Procedures (Emergency)

#### Emergency Rollback Process

If a migration causes issues in production:

1. **Identify the problem migration:**
   ```bash
   alembic history --verbose
   ```

2. **Take a database backup immediately:**
   ```bash
   pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

3. **Rollback the problematic migration:**
   ```bash
   alembic downgrade -1
   ```

4. **Verify the rollback:**
   ```bash
   alembic current
   # Should show the previous revision
   ```

5. **Test in staging before proceeding**

#### Point-in-Time Recovery

If you need to recover to a specific state:

1. Find the target revision:
   ```bash
   alembic history | grep <timestamp_or_revision>
   ```

2. Rollback to that revision:
   ```bash
   alembic downgrade <revision>
   ```

## Production Deployment

### Pre-Migration Checklist

- [ ] Backup database
- [ ] Review migration changes
- [ ] Test in staging environment
- [ ] Schedule maintenance window if needed
- [ ] Notify stakeholders

### Deployment Steps

1. **Deploy code with new migration:**
   ```bash
   git pull origin main
   ```

2. **Run migrations (with timeout):**
   ```bash
   timeout 300 alembic upgrade head
   ```

3. **Verify migration:**
   ```bash
   alembic current
   ```

4. **Monitor application logs:**
   ```bash
   tail -f logs/app.log | grep -i error
   ```

### Rollback Steps (Production)

If issues occur:

1. **Stop the application** (to prevent new writes)
2. **Rollback migration:**
   ```bash
   alembic downgrade -1
   ```
3. **Restore database if needed:**
   ```bash
   psql $DATABASE_URL < backup_YYYYMMDD_HHMMSS.sql
   ```
4. **Deploy previous version**
5. **Restart application**

## Development

### Initial Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
alembic upgrade head
```

### Creating Migrations

```bash
# After modifying models
alembic revision --autogenerate -m "add new field to agents"

# Review the generated file
cat src/api/models/migrations/versions/$(ls -t src/api/models/migrations/versions/ | head -1)
```

### Testing Migrations

```bash
# Test upgrade
alembic upgrade head

# Test downgrade
alembic downgrade -1

# Test upgrade again (to return to current state)
alembic upgrade head
```

## Migration Best Practices

1. **Always use transactions** for multi-step changes within a single migration
2. **Keep migrations small** - one logical change per migration
3. **Never modify existing migrations** - create new ones to fix issues
4. **Test both upgrade and downgrade** paths
5. **Use meaningful migration names**
6. **Add comments** for complex operations

## Troubleshooting

### "Target database is not up to date"

```bash
# Check current state
alembic current
alembic history

# Stamp to a specific version if needed
alembic stamp <revision>
```

### Migration fails with "relation already exists"

- Check if the table was created outside of Alembic
- Use `op.create_table_if_not_exists()` or check before creating

### Long-running migrations

For large tables, consider:
- Adding indexes after initial table creation
- Using `batch_alter_table()` for SQLite compatibility
- Running during low-traffic periods

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `DATABASE_SSL_MODE` | SSL mode for connection (disable, require, verify-full) |

## Migration: v1.3 → v1.4

### RBAC Enforcement

v1.4 adds persisted-role checks to protected control-plane routes:

- Protected routes declare authentication, ownership, plan, internal-user, or role
  dependencies in `src/api/routes/`.
- Public probes, account-entry routes, and lead capture remain anonymous by design.
- Managed API keys resolve their owning database user; they do not carry an
  independent role set.
- Review `src/api/auth/dependencies.py` and `src/api/services/auth.py` for the
  enforcement layer and role semantics.

### OIDC Token Validation

v1.4 introduces OIDC token validation. New required environment variables:

```
OIDC_ISSUER=https://your-idp.example.com
OIDC_CLIENT_ID=your-client-id
OIDC_JWKS_URI=https://your-idp.example.com/.well-known/jwks.json
```

If OIDC is not configured, JWT-based auth continues to work. OIDC is additive.

### API Key Changes (CrewAI / SDK)

The `MUTX_API_KEY` environment variable is now required for SDK and adapter usage. Previously some flows accepted inline keys. Update your setup:

```python
import os
from mutx import MutxClient

client = MutxClient(
    api_url=os.environ["MUTX_API_URL"],
    api_key=os.environ["MUTX_API_KEY"],
)
```

Set `MUTX_API_KEY` in your environment or `.env` file. Get the key from `mutx.dev/dashboard` under API keys.

### Helm Deployment Option

v1.4 ships a Kubernetes Helm chart. To deploy with Helm:

```bash
helm install mutx infrastructure/helm/mutx \
  --set secrets.databaseUrl=$DATABASE_URL \
  --set secrets.oidcIssuer=$OIDC_ISSUER \
  --set secrets.oidcClientId=$OIDC_CLIENT_ID \
  --set secrets.oidcJwksUri=$OIDC_JWKS_URI
```

See `infrastructure/helm/mutx/README.md` for full configuration.

### Database Migrations

Run the standard migration after upgrading:

```bash
alembic upgrade head
```

## Related Files

- `alembic.ini` - Alembic configuration
- `src/api/models/models.py` - SQLAlchemy models
- `src/api/models/migrations/` - Migration scripts
- `src/api/database.py` - Database connection setup
