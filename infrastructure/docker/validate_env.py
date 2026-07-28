#!/usr/bin/env python3
"""
Environment variable validation script for MUTX API production.
Run this before starting the container to validate configuration.
"""

import os
import sys


def validate_required_vars() -> list[str]:
    """Validate required environment variables."""
    required = [
        "DATABASE_URL",
        "JWT_SECRET",
        "RECEIPT_SIGNING_PRIVATE_KEY",
    ]

    missing = []
    for var in required:
        if not os.environ.get(var):
            missing.append(var)

    return missing


def validate_jwt_secret() -> bool:
    """Validate JWT_SECRET meets minimum requirements."""
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if len(jwt_secret) < 32:
        return False
    return True


def validate_database_url() -> bool:
    """Validate DATABASE_URL format."""
    db_url = os.environ.get("DATABASE_URL", "")
    valid_prefixes = ("postgresql://", "postgres://")
    if not db_url.startswith(valid_prefixes):
        return False
    return True


def validate_receipt_signing_key() -> bool:
    """Validate the persistent Ed25519 receipt signing seed."""
    private_key = os.environ.get("RECEIPT_SIGNING_PRIVATE_KEY", "")
    try:
        return len(bytes.fromhex(private_key)) == 32
    except ValueError:
        return False


def main() -> int:
    """Run all validations and return exit code."""
    errors = []

    # Check required variables
    missing = validate_required_vars()
    if missing:
        errors.append(f"Missing required environment variables: {', '.join(missing)}")

    # Validate JWT_SECRET
    if os.environ.get("JWT_SECRET") and not validate_jwt_secret():
        errors.append("JWT_SECRET must be at least 32 characters")

    if os.environ.get("RECEIPT_SIGNING_PRIVATE_KEY") and not validate_receipt_signing_key():
        errors.append("RECEIPT_SIGNING_PRIVATE_KEY must be a 64-character hex seed")

    # Validate DATABASE_URL
    if os.environ.get("DATABASE_URL") and not validate_database_url():
        errors.append(
            "DATABASE_URL must be a valid PostgreSQL connection string (postgresql://...)"
        )

    if errors:
        print("Environment validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Environment validation PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
