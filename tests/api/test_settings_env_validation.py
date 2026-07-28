import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from src.api.config import Settings
from src.security.receipts import ReceiptGenerator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_RECEIPT_KEY_ID = "mutx-platform-test"
TEST_RECEIPT_PRIVATE_KEY = "01" * 32
TEST_RECEIPT_PUBLIC_KEY = ReceiptGenerator.public_key_bytes(TEST_RECEIPT_PRIVATE_KEY).hex()
TEST_RECEIPT_REGISTRY = f'{{"{TEST_RECEIPT_KEY_ID}":"{TEST_RECEIPT_PUBLIC_KEY}"}}'


def test_default_dotenv_loading_can_be_disabled_for_deterministic_tools(tmp_path):
    (tmp_path / ".env").write_text("LOG_LEVEL=DEBUG\n")
    environment = os.environ.copy()
    environment.pop("LOG_LEVEL", None)
    environment["MUTX_SETTINGS_ENV_FILE"] = ""
    environment["PYTHONPATH"] = str(PROJECT_ROOT)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.api.config import Settings; print(Settings().log_level)",
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "INFO"


def test_production_accepts_jwt_secret_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ENVIRONMENT=production\n"
        "JWT_SECRET=abcdefghijklmnopqrstuvwxyz123456\n"
        "DATABASE_URL=postgresql://postgres:postgres@db:5432/mutx\n"
        "SECRET_ENCRYPTION_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"
        f"RECEIPT_SIGNING_KEY_ID={TEST_RECEIPT_KEY_ID}\n"
        f"RECEIPT_SIGNING_PRIVATE_KEY={TEST_RECEIPT_PRIVATE_KEY}\n"
        f"RECEIPT_TRUSTED_PUBLIC_KEYS={TEST_RECEIPT_REGISTRY}\n"
        "FORWARDED_ALLOW_IPS=10.0.0.1\n"
        "RESEND_API_KEY=re_test_configured\n"
        "RESEND_FROM_EMAIL=MUTX <noreply@mutx.dev>\n"
        "ALLOWED_HOSTS=api.example.com\n"
        "FRONTEND_URL=https://app.example.com\n"
        "AUTH_REDIRECT_ORIGINS=https://app.example.com\n"
        "REQUIRE_EMAIL_VERIFICATION=false\n"
    )

    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("jwt_secret", raising=False)
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.jwt_secret == "abcdefghijklmnopqrstuvwxyz123456"


def test_production_rejects_auto_generated_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("jwt_secret", raising=False)

    with pytest.raises(
        ValidationError, match="JWT_SECRET environment variable must be set in production"
    ):
        Settings(_env_file=None)


def test_rejects_short_provided_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "too-short")

    with pytest.raises(ValidationError, match="JWT_SECRET must be at least 32 characters long"):
        Settings(_env_file=None)


def _set_valid_production_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-32")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "separate-encryption-key-that-is-long-enough")
    monkeypatch.setenv("RECEIPT_SIGNING_KEY_ID", TEST_RECEIPT_KEY_ID)
    monkeypatch.setenv("RECEIPT_SIGNING_PRIVATE_KEY", TEST_RECEIPT_PRIVATE_KEY)
    monkeypatch.setenv("RECEIPT_TRUSTED_PUBLIC_KEYS", TEST_RECEIPT_REGISTRY)
    monkeypatch.setenv("DATABASE_URL", "postgresql://mutx:database-secret@db:5432/mutx")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.1")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.mutx.dev")
    monkeypatch.setenv("FRONTEND_URL", "https://app.mutx.dev")
    monkeypatch.setenv("AUTH_REDIRECT_ORIGINS", "https://app.mutx.dev")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    for name in (
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL",
        "SMTP_HOST",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_production_requires_transactional_email_when_verification_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_environment(monkeypatch)

    with pytest.raises(ValidationError, match="Email verification requires either"):
        Settings(_env_file=None)


def test_production_accepts_complete_smtp_for_required_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_environment(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@example.com")

    settings = Settings(_env_file=None)

    assert settings.smtp_host == "smtp.example.com"


def test_production_accepts_resend_for_required_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_environment(monkeypatch)
    monkeypatch.setenv("RESEND_API_KEY", "re_test_configured")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "MUTX <noreply@mutx.dev>")

    settings = Settings(_env_file=None)

    assert settings.resend_api_key == "re_test_configured"


def test_production_rejects_implicit_database_placeholder_when_startup_is_deferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_environment(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_REQUIRED_ON_STARTUP", "false")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_configured")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "MUTX <noreply@mutx.dev>")

    with pytest.raises(ValidationError, match="DATABASE_URL appears to be using default values"):
        Settings(_env_file=None)


def test_database_validation_errors_redact_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "mysql://database-user:do-not-expose-this@db.example.com:3306/mutx",
    )

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    error = str(exc_info.value)
    assert "DATABASE_URL must be a valid PostgreSQL connection string" in error
    assert "database-user" not in error
    assert "do-not-expose-this" not in error


def test_railway_production_settings_probe_requires_complete_security_and_email_contract(
    monkeypatch,
):
    production_environment = {
        "ENVIRONMENT": "production",
        "JWT_SECRET": "test-jwt-secret-that-is-long-enough-32",
        "SECRET_ENCRYPTION_KEY": "test-encryption-secret-that-is-distinct-32",
        "RECEIPT_SIGNING_KEY_ID": TEST_RECEIPT_KEY_ID,
        "RECEIPT_SIGNING_PRIVATE_KEY": TEST_RECEIPT_PRIVATE_KEY,
        "RECEIPT_TRUSTED_PUBLIC_KEYS": TEST_RECEIPT_REGISTRY,
        "DATABASE_URL": "postgresql://mutx:secret@railway-postgres:5432/mutx",
        "DATABASE_SSL_MODE": "require",
        "ALLOWED_HOSTS": "api.mutx.dev,api-production.railway.internal",
        "FORWARDED_ALLOW_IPS": "100.0.0.0/8",
        "CORS_ORIGINS": "https://app.mutx.dev",
        "FRONTEND_URL": "https://app.mutx.dev",
        "AUTH_REDIRECT_ORIGINS": "https://app.mutx.dev",
        "REQUIRE_EMAIL_VERIFICATION": "true",
        "RESEND_API_KEY": "re_test_delivery_provider",
        "RESEND_FROM_EMAIL": "MUTX <hello@mutx.dev>",
    }
    for name, value in production_environment.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.secret_encryption_key == production_environment["SECRET_ENCRYPTION_KEY"]
    assert settings.forwarded_allow_ips == ["100.0.0.0/8"]
    assert settings.require_email_verification is True
    assert settings.resend_api_key == "re_test_delivery_provider"


def test_production_requires_platform_receipt_signing_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_environment(monkeypatch)
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")
    for name in (
        "RECEIPT_SIGNING_KEY_ID",
        "RECEIPT_SIGNING_PRIVATE_KEY",
        "RECEIPT_TRUSTED_PUBLIC_KEYS",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(
        ValidationError,
        match="Production receipt signing requires a platform Ed25519 key",
    ):
        Settings(_env_file=None)


def test_receipt_signing_key_must_match_trusted_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RECEIPT_SIGNING_KEY_ID", TEST_RECEIPT_KEY_ID)
    monkeypatch.setenv("RECEIPT_SIGNING_PRIVATE_KEY", TEST_RECEIPT_PRIVATE_KEY)
    monkeypatch.setenv(
        "RECEIPT_TRUSTED_PUBLIC_KEYS",
        f'{{"{TEST_RECEIPT_KEY_ID}":"{"02" * 32}"}}',
    )

    with pytest.raises(
        ValidationError,
        match="does not match its trusted public key",
    ):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("raw_environment", "expected"),
    [
        (" development ", "development"),
        ("TEST", "test"),
        (" StAgInG ", "staging"),
    ],
)
def test_environment_normalizes_supported_nonproduction_values(
    monkeypatch: pytest.MonkeyPatch,
    raw_environment: str,
    expected: str,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", raw_environment)

    assert Settings(_env_file=None).environment == expected


def test_environment_rejects_unknown_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "productoin")

    with pytest.raises(ValidationError, match="ENVIRONMENT must be one of"):
        Settings(_env_file=None)


def test_sqlite_accepts_one_api_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./mutx-test.db")
    monkeypatch.setenv("WEB_CONCURRENCY", "1")

    assert Settings(_env_file=None).web_concurrency == 1


def test_sqlite_rejects_multiple_api_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./mutx-test.db")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")

    with pytest.raises(ValidationError, match="SQLite requires WEB_CONCURRENCY=1"):
        Settings(_env_file=None)


@pytest.mark.parametrize("model", ["   ", "openai/", "gpt model"])
def test_pico_tutor_model_rejects_empty_or_whitespace_identifiers(
    monkeypatch: pytest.MonkeyPatch,
    model: str,
) -> None:
    monkeypatch.setenv("PICO_TUTOR_MODEL", model)

    with pytest.raises(ValidationError, match="PICO_TUTOR_MODEL"):
        Settings(_env_file=None)


def test_padded_case_production_alias_cannot_bypass_requirements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", " PrOd ")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(
        ValidationError,
        match="JWT_SECRET environment variable must be set in production",
    ):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "frontend_url",
    [
        "http://app.mutx.dev",
        "https://localhost",
        "https://localhost.",
        "https://127.0.0.1",
        "https://[::1]",
        "https://[::ffff:127.0.0.1]",
    ],
)
def test_production_rejects_insecure_or_loopback_frontend_url(
    monkeypatch: pytest.MonkeyPatch,
    frontend_url: str,
) -> None:
    _set_valid_production_environment(monkeypatch)
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")
    monkeypatch.setenv("FRONTEND_URL", frontend_url)
    monkeypatch.setenv("AUTH_REDIRECT_ORIGINS", frontend_url)

    with pytest.raises(ValidationError, match="FRONTEND_URL must use HTTPS"):
        Settings(_env_file=None)


def test_production_requires_explicit_frontend_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_environment(monkeypatch)
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.setenv("AUTH_REDIRECT_ORIGINS", "https://app.mutx.dev")

    with pytest.raises(ValidationError, match="FRONTEND_URL must be explicitly configured"):
        Settings(_env_file=None)


def test_production_frontend_must_be_in_redirect_origin_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_environment(monkeypatch)
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")
    monkeypatch.setenv("AUTH_REDIRECT_ORIGINS", "https://pico.mutx.dev")

    with pytest.raises(ValidationError, match="must include the canonical FRONTEND_URL"):
        Settings(_env_file=None)
