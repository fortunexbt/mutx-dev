import pytest
from pydantic import ValidationError

from src.api.config import Settings


def test_production_accepts_jwt_secret_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ENVIRONMENT=production\n"
        "JWT_SECRET=abcdefghijklmnopqrstuvwxyz123456\n"
        "DATABASE_URL=postgresql://postgres:postgres@db:5432/mutx\n"
        "SECRET_ENCRYPTION_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"
        f"RECEIPT_SIGNING_PRIVATE_KEY={'01' * 32}\n"
        "FORWARDED_ALLOW_IPS=10.0.0.1\n"
    )

    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("jwt_secret", raising=False)
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.jwt_secret == "abcdefghijklmnopqrstuvwxyz123456"


def test_production_requires_persistent_receipt_signing_key(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-32")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "test-secret-key-that-is-32-bytes-long!")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod:secret@db.example.com:5432/mutx")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.1")
    monkeypatch.delenv("RECEIPT_SIGNING_PRIVATE_KEY", raising=False)

    with pytest.raises(
        ValidationError,
        match="RECEIPT_SIGNING_PRIVATE_KEY environment variable must be set in production",
    ):
        Settings(_env_file=None)


@pytest.mark.parametrize("private_key", ["not-hex", "01"])
def test_receipt_signing_key_must_be_a_32_byte_hex_seed(monkeypatch, private_key):
    monkeypatch.setenv("RECEIPT_SIGNING_PRIVATE_KEY", private_key)

    with pytest.raises(ValidationError, match="RECEIPT_SIGNING_PRIVATE_KEY"):
        Settings(_env_file=None)


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
