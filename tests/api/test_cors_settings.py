import pytest
from pydantic import ValidationError

from src.api.config import Settings
from src.security.receipts import ReceiptGenerator


TEST_RECEIPT_KEY_ID = "mutx-platform-test"
TEST_RECEIPT_PRIVATE_KEY = "01" * 32
TEST_RECEIPT_PUBLIC_KEY = ReceiptGenerator.public_key_bytes(TEST_RECEIPT_PRIVATE_KEY).hex()


def _set_receipt_signing_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECEIPT_SIGNING_KEY_ID", TEST_RECEIPT_KEY_ID)
    monkeypatch.setenv("RECEIPT_SIGNING_PRIVATE_KEY", TEST_RECEIPT_PRIVATE_KEY)
    monkeypatch.setenv(
        "RECEIPT_TRUSTED_PUBLIC_KEYS",
        f'{{"{TEST_RECEIPT_KEY_ID}":"{TEST_RECEIPT_PUBLIC_KEY}"}}',
    )


def test_cors_origins_accepts_comma_separated_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "abcdefghijklmnopqrstuvwxyz123456")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://app.example.com, https://admin.example.com",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_cors_origins_accepts_json_array_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "abcdefghijklmnopqrstuvwxyz123456")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["https://app.example.com", "https://admin.example.com"]',
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_cors_origins_rejects_invalid_json_array_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "abcdefghijklmnopqrstuvwxyz123456")
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.example.com"')

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_forwarded_allow_ips_accepts_comma_separated_env(monkeypatch):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.1, 10.0.0.2")

    settings = Settings(_env_file=None)

    assert settings.forwarded_allow_ips == ["10.0.0.1", "10.0.0.2"]


def test_allowed_hosts_accepts_comma_separated_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com, *.railway.internal")

    settings = Settings(_env_file=None)

    assert settings.allowed_hosts == ["api.example.com", "*.railway.internal"]


def test_supervised_profiles_accepts_json_object_env(monkeypatch):
    monkeypatch.setenv(
        "GOVERNANCE_SUPERVISED_PROFILES",
        '{"assistant-runner":{"command":["python","agent.py"],"env":{"LOG_LEVEL":"info"}}}',
    )

    settings = Settings(_env_file=None)

    assert settings.governance_supervised_profiles == {
        "assistant-runner": {
            "command": ["python", "agent.py"],
            "env": {"LOG_LEVEL": "info"},
        }
    }


def test_production_rejects_when_forwarded_allow_ips_trusts_all(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-32")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "test-secret-key-that-is-32-bytes-long!")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod:***@db.example.com:5432/mutx")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")

    with pytest.raises(
        ValidationError,
        match="FORWARDED_ALLOW_IPS must not trust all proxy sources",
    ):
        Settings(_env_file=None)


def test_production_rejects_invalid_forwarded_proxy_network(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-32")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "test-secret-key-that-is-32-bytes-long!")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod:***@db.example.com:5432/mutx")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "not-a-network")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")

    with pytest.raises(
        ValidationError,
        match="FORWARDED_ALLOW_IPS entries must be valid IP addresses or CIDRs",
    ):
        Settings(_env_file=None)


def test_production_rejects_wildcard_allowed_host(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-32")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "test-secret-key-that-is-32-bytes-long!")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod:***@db.example.com:5432/mutx")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.*.example.com")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.0/8")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")

    with pytest.raises(ValidationError, match="ALLOWED_HOSTS contains permissive entries"):
        Settings(_env_file=None)


def test_production_rejects_when_secret_encryption_key_matches_jwt_secret(monkeypatch):
    shared_secret = "abcdefghijklmnopqrstuvwxyz123456"
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", shared_secret)
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", shared_secret)
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod:***@db.example.com:5432/mutx")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.1")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")

    with pytest.raises(
        ValidationError,
        match="SECRET_ENCRYPTION_KEY must not match JWT_SECRET",
    ):
        Settings(_env_file=None)


def test_api_docs_are_disabled_in_production_by_default(monkeypatch):
    _set_receipt_signing_environment(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-32")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "test-secret-key-that-is-32-bytes-long!")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod:***@db.example.com:5432/mutx")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.1")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    monkeypatch.setenv("AUTH_REDIRECT_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")

    settings = Settings(_env_file=None)

    assert settings.expose_api_docs_in_production is False
