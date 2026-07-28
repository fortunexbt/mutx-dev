from functools import lru_cache
from ipaddress import ip_address, ip_network
from json import JSONDecodeError, loads
import os
import secrets
from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_SETTINGS_ENV_FILE = os.getenv("MUTX_SETTINGS_ENV_FILE", ".env").strip() or None
_DEFAULT_DATABASE_URL = "postgresql://user:password@localhost:5432/mutx"
_SUPPORTED_ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})


def _is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False

    normalized = hostname.strip().casefold().rstrip(".")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        address = ip_address(normalized)
        return address.is_loopback or bool(
            address.version == 6 and address.ipv4_mapped and address.ipv4_mapped.is_loopback
        )
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_SETTINGS_ENV_FILE,
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV"),
    )
    database_url: str = Field(
        default=_DEFAULT_DATABASE_URL,
        validation_alias=AliasChoices("DATABASE_URL", "DB_URL"),
    )
    database_ssl_mode: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_SSL_MODE", "DB_SSL_MODE"),
    )
    api_host: str = "0.0.0.0"  # nosec B104 - server bind address; host validation is separate.
    api_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("API_PORT", "PORT"),
    )
    web_concurrency: int = Field(
        default=1,
        ge=1,
        validation_alias=AliasChoices("WEB_CONCURRENCY", "UVICORN_WORKERS"),
        description="Number of API worker processes serving this database.",
    )
    cors_origins: list[str] | str = [
        "http://localhost:3000",
        "http://app.localhost:3000",
        "http://pico.localhost:3000",
        "https://mutx.dev",
        "https://app.mutx.dev",
        "https://pico.mutx.dev",
    ]
    allowed_hosts: list[str] | str = [
        "localhost",
        "127.0.0.1",
        "[::1]",
        "test",
        "testserver",
        "api.mutx.dev",
        "*.up.railway.app",
        "*.railway.internal",
    ]
    log_level: str = "INFO"
    json_logging: bool = Field(
        default=False,
        validation_alias=AliasChoices("JSON_LOGGING", "LOG_JSON"),
        description="Enable structured JSON logging output",
    )
    log_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LOG_FILE", "LOG_PATH"),
        description="Optional file path for log output",
    )
    jwt_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    secret_encryption_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SECRET_ENCRYPTION_KEY"),
    )
    receipt_signing_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RECEIPT_SIGNING_KEY_ID"),
        description="Immutable platform Ed25519 key ID bound into newly signed receipts.",
    )
    receipt_signing_private_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RECEIPT_SIGNING_PRIVATE_KEY"),
        description="Hex-encoded raw platform Ed25519 private key used to sign receipts.",
        repr=False,
    )
    receipt_trusted_public_keys: dict[str, str] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("RECEIPT_TRUSTED_PUBLIC_KEYS"),
        description="JSON object mapping trusted receipt key IDs to raw Ed25519 public keys.",
    )
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    refresh_token_max_sliding_days: int = 30  # Max days for sliding expiry
    refresh_token_rotation_grace_seconds: int = Field(
        default=10,
        ge=1,
        le=60,
        validation_alias=AliasChoices("REFRESH_TOKEN_ROTATION_GRACE_SECONDS"),
        description="Short overlap window for idempotent refresh-token rotation retries.",
    )
    expose_api_docs_in_production: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "EXPOSE_API_DOCS_IN_PRODUCTION",
            "ENABLE_API_DOCS_IN_PRODUCTION",
        ),
        description="Expose /docs, /redoc, and /openapi.json in production.",
    )
    require_email_verification: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "REQUIRE_EMAIL_VERIFICATION",
        ),
        description="Require email verification before allowing password-account access.",
    )
    email_verification_token_expire_hours: int = Field(
        default=72,
        ge=1,
        validation_alias=AliasChoices(
            "EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS",
        ),
    )
    # Email settings
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_email: str = Field(default="noreply@mutx.dev")
    smtp_from_name: str = Field(default="MUTX")
    # Frontend URL for email links
    frontend_url: str = Field(default="http://localhost:3000")
    auth_redirect_origins: list[str] | str = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://app.localhost:3000",
            "http://pico.localhost:3000",
            "https://mutx.dev",
            "https://app.mutx.dev",
            "https://pico.mutx.dev",
        ],
        validation_alias=AliasChoices("AUTH_REDIRECT_ORIGINS"),
        description="Exact browser origins allowed for auth links and OAuth callbacks.",
    )
    public_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PUBLIC_API_URL", "API_PUBLIC_URL"),
        description="Public API origin used for OAuth/SSO callbacks.",
    )
    oauth_state_ttl_seconds: int = Field(
        default=600,
        ge=60,
        le=1800,
        validation_alias=AliasChoices("OAUTH_STATE_TTL_SECONDS"),
    )
    pico_tutor_model: str = Field(
        default="gpt-5-mini",
        validation_alias=AliasChoices("PICO_TUTOR_MODEL"),
    )
    google_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_ID"),
    )
    google_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_SECRET"),
    )
    github_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GITHUB_CLIENT_ID"),
    )
    github_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GITHUB_CLIENT_SECRET"),
    )
    discord_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DISCORD_CLIENT_ID"),
    )
    discord_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DISCORD_CLIENT_SECRET"),
    )
    apple_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APPLE_CLIENT_ID"),
    )
    apple_team_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APPLE_TEAM_ID"),
    )
    apple_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APPLE_KEY_ID"),
    )
    apple_private_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APPLE_PRIVATE_KEY"),
    )
    okta_domain: str | None = Field(default=None, validation_alias=AliasChoices("OKTA_DOMAIN"))
    okta_client_id: str | None = Field(
        default=None, validation_alias=AliasChoices("OKTA_CLIENT_ID")
    )
    okta_client_secret: str | None = Field(
        default=None, validation_alias=AliasChoices("OKTA_CLIENT_SECRET")
    )
    auth0_domain: str | None = Field(default=None, validation_alias=AliasChoices("AUTH0_DOMAIN"))
    auth0_client_id: str | None = Field(
        default=None, validation_alias=AliasChoices("AUTH0_CLIENT_ID")
    )
    auth0_client_secret: str | None = Field(
        default=None, validation_alias=AliasChoices("AUTH0_CLIENT_SECRET")
    )
    keycloak_domain: str | None = Field(
        default=None, validation_alias=AliasChoices("KEYCLOAK_DOMAIN")
    )
    keycloak_realm: str | None = Field(
        default=None, validation_alias=AliasChoices("KEYCLOAK_REALM")
    )
    keycloak_client_id: str | None = Field(
        default=None, validation_alias=AliasChoices("KEYCLOAK_CLIENT_ID")
    )
    keycloak_client_secret: str | None = Field(
        default=None, validation_alias=AliasChoices("KEYCLOAK_CLIENT_SECRET")
    )
    oidc_issuer: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OIDC_ISSUER"),
        description="Expected issuer for externally issued OIDC tokens.",
    )
    oidc_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OIDC_CLIENT_ID"),
        description="Expected audience for externally issued OIDC tokens.",
    )
    oidc_jwks_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OIDC_JWKS_URI"),
        description="JWKS endpoint used to verify externally issued OIDC tokens.",
    )
    database_required_on_startup: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DATABASE_REQUIRED_ON_STARTUP",
            "DB_REQUIRED_ON_STARTUP",
        ),
    )
    database_init_retry_interval_seconds: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices(
            "DATABASE_INIT_RETRY_INTERVAL_SECONDS",
            "DB_INIT_RETRY_INTERVAL_SECONDS",
        ),
    )
    database_connect_timeout_seconds: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices(
            "DATABASE_CONNECT_TIMEOUT_SECONDS",
            "DB_CONNECT_TIMEOUT_SECONDS",
        ),
    )
    # Rate limiting
    rate_limit_requests: int = Field(
        default=100,
        ge=1,
        description="Number of requests allowed per time window",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        description="Time window in seconds for rate limiting",
    )
    auth_rate_limit_requests: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices(
            "AUTH_RATE_LIMIT_REQUESTS",
        ),
        description="Number of auth-sensitive requests allowed per time window",
    )
    auth_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices(
            "AUTH_RATE_LIMIT_WINDOW_SECONDS",
        ),
        description="Time window in seconds for auth-sensitive rate limiting",
    )
    rate_limit_backend: Literal["memory", "redis"] | None = Field(
        default=None,
        validation_alias=AliasChoices("RATE_LIMIT_BACKEND"),
        description="Rate-limit backend; defaults to Redis in production and memory otherwise.",
    )
    redis_url: str = Field(
        default="redis://redis:6379/0",
        validation_alias=AliasChoices("REDIS_URL"),
        description="Redis connection URL shared by distributed API rate limiting.",
    )
    rate_limit_redis_key_prefix: str = Field(
        default="mutx:rate-limit:v1",
        min_length=1,
        max_length=64,
        validation_alias=AliasChoices("RATE_LIMIT_REDIS_KEY_PREFIX"),
    )
    rate_limit_redis_max_connections: int = Field(
        default=20,
        ge=1,
        le=1000,
        validation_alias=AliasChoices("RATE_LIMIT_REDIS_MAX_CONNECTIONS"),
    )
    rate_limit_redis_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        le=30,
        validation_alias=AliasChoices("RATE_LIMIT_REDIS_TIMEOUT_SECONDS"),
    )
    rate_limit_memory_max_buckets: int = Field(
        default=10_000,
        ge=1,
        le=1_000_000,
        validation_alias=AliasChoices("RATE_LIMIT_MEMORY_MAX_BUCKETS"),
        description="Hard bucket cap for the development/test in-memory backend.",
    )

    internal_user_email_domains: list[str] = Field(
        default=["mutx.dev"],
        validation_alias=AliasChoices(
            "INTERNAL_USER_EMAIL_DOMAINS",
            "ADMIN_EMAIL_DOMAINS",
        ),
        description="Email domains allowed to access internal-only endpoints.",
    )
    governance_supervised_command_allowlist: list[str] | str = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "GOVERNANCE_SUPERVISED_COMMAND_ALLOWLIST",
            "SUPERVISED_COMMAND_ALLOWLIST",
        ),
        description="Allowed executable basenames for governance-supervised process launch.",
    )
    governance_supervised_env_allowlist: list[str] | str = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "GOVERNANCE_SUPERVISED_ENV_ALLOWLIST",
            "SUPERVISED_ENV_ALLOWLIST",
        ),
        description="Allowed environment variable names for governance-supervised process launch.",
    )
    governance_supervised_allow_direct_commands: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "GOVERNANCE_SUPERVISED_ALLOW_DIRECT_COMMANDS",
            "SUPERVISED_ALLOW_DIRECT_COMMANDS",
        ),
        description="Allow direct raw command launch via governance supervision APIs.",
    )
    governance_supervised_profiles: dict[str, object] | str = Field(
        default_factory=dict,
        validation_alias=AliasChoices(
            "GOVERNANCE_SUPERVISED_PROFILES",
            "SUPERVISED_PROFILES",
        ),
        description="JSON object mapping supervised launch profile names to command/env/policy definitions.",
    )
    governance_supervised_policy_dir: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOVERNANCE_SUPERVISED_POLICY_DIR",
            "SUPERVISED_POLICY_DIR",
        ),
        description="Optional directory that bounds user-selectable Faramesh policy files.",
    )
    forwarded_allow_ips: list[str] | str = Field(
        default_factory=lambda: ["127.0.0.1"],
        validation_alias=AliasChoices("FORWARDED_ALLOW_IPS"),
        description="Trusted proxy IPs for forwarded headers.",
    )
    background_monitor_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "BACKGROUND_MONITOR_ENABLED",
            "ENABLE_BACKGROUND_MONITOR",
        ),
    )
    monitor_heartbeat_file: str = Field(
        default="/tmp/mutx-monitor-heartbeat",
        validation_alias=AliasChoices("MONITOR_HEARTBEAT_FILE"),
    )
    monitor_heartbeat_max_age_seconds: int = Field(
        default=30,
        ge=1,
        validation_alias=AliasChoices("MONITOR_HEARTBEAT_MAX_AGE_SECONDS"),
    )
    monitor_max_consecutive_failures: int = Field(
        default=3,
        ge=1,
        validation_alias=AliasChoices("MONITOR_MAX_CONSECUTIVE_FAILURES"),
    )
    enable_rag_api: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ENABLE_RAG_API",
            "RAG_API_ENABLED",
        ),
    )
    documents_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MUTX_DOCUMENTS_ENABLED",
            "DOCUMENTS_ENABLED",
        ),
    )
    artifacts_dir: str = Field(
        default_factory=lambda: os.path.join(os.getcwd(), ".mutx-artifacts"),
        validation_alias=AliasChoices(
            "MUTX_ARTIFACTS_DIR",
            "ARTIFACTS_DIR",
        ),
    )
    document_max_upload_mb: int = Field(
        default=25,
        ge=1,
        validation_alias=AliasChoices(
            "MUTX_DOCUMENT_MAX_UPLOAD_MB",
            "DOCUMENT_MAX_UPLOAD_MB",
        ),
    )
    document_worker_poll_seconds: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices(
            "MUTX_DOCUMENT_WORKER_POLL_SECONDS",
            "DOCUMENT_WORKER_POLL_SECONDS",
        ),
    )
    reasoning_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MUTX_REASONING_ENABLED",
            "REASONING_ENABLED",
        ),
    )
    reasoning_max_upload_mb: int = Field(
        default=25,
        ge=1,
        validation_alias=AliasChoices(
            "MUTX_REASONING_MAX_UPLOAD_MB",
            "REASONING_MAX_UPLOAD_MB",
        ),
    )
    reasoning_worker_poll_seconds: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices(
            "MUTX_REASONING_WORKER_POLL_SECONDS",
            "REASONING_WORKER_POLL_SECONDS",
        ),
    )

    # Lead pipeline notifications
    lead_discord_webhook_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "LEAD_DISCORD_WEBHOOK_URL",
            "DISCORD_LEAD_WEBHOOK_URL",
        ),
        description="Discord webhook URL for lead capture notifications.",
    )
    resend_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("RESEND_API_KEY", "RESEND_API_KEY"),
    )
    resend_from_email: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("RESEND_FROM_EMAIL"),
    )
    resend_lead_alert_email: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("RESEND_LEAD_ALERT_EMAIL"),
    )
    resend_audience_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("RESEND_AUDIENCE_ID"),
    )

    # Store whether JWT_SECRET was user-provided or auto-generated
    _jwt_secret_was_auto_generated: bool = False

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("ENVIRONMENT must be a string")

        normalized = value.strip().casefold()
        if normalized == "prod":
            normalized = "production"
        if normalized not in _SUPPORTED_ENVIRONMENTS:
            supported = ", ".join(sorted(_SUPPORTED_ENVIRONMENTS))
            raise ValueError(f"ENVIRONMENT must be one of: {supported}")
        return normalized

    @field_validator("cors_origins", "auth_redirect_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        raw_value = value.strip()
        if not raw_value:
            return []

        if raw_value.startswith("["):
            try:
                parsed_value = loads(raw_value)
            except JSONDecodeError as exc:
                raise ValueError(
                    "CORS_ORIGINS must be a JSON array or comma-separated list"
                ) from exc
            if not isinstance(parsed_value, list):
                raise ValueError("CORS_ORIGINS JSON value must be an array")
            return [
                origin.strip()
                for origin in parsed_value
                if isinstance(origin, str) and origin.strip()
            ]

        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]

    @field_validator(
        "governance_supervised_command_allowlist",
        "governance_supervised_env_allowlist",
        "forwarded_allow_ips",
        "allowed_hosts",
        mode="before",
    )
    @classmethod
    def parse_string_list(cls, value: object) -> object:
        if value is None:
            return []

        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]

        if not isinstance(value, str):
            raise ValueError("Expected a JSON array or comma-separated string")

        raw_value = value.strip()
        if not raw_value:
            return []

        if raw_value.startswith("["):
            try:
                parsed_value = loads(raw_value)
            except JSONDecodeError as exc:
                raise ValueError("Value must be a JSON array or comma-separated list") from exc
            if not isinstance(parsed_value, list):
                raise ValueError("JSON value must be an array")
            return [item.strip() for item in parsed_value if isinstance(item, str) and item.strip()]

        return [item.strip() for item in raw_value.split(",") if item.strip()]

    @field_validator("governance_supervised_profiles", mode="before")
    @classmethod
    def parse_json_mapping(cls, value: object) -> object:
        if value is None:
            return {}

        if isinstance(value, dict):
            return value

        if not isinstance(value, str):
            raise ValueError("Expected a JSON object")

        raw_value = value.strip()
        if not raw_value:
            return {}

        try:
            parsed_value = loads(raw_value)
        except JSONDecodeError as exc:
            raise ValueError("Value must be a JSON object") from exc

        if not isinstance(parsed_value, dict):
            raise ValueError("JSON value must be an object")

        return parsed_value

    @field_validator("receipt_trusted_public_keys", mode="before")
    @classmethod
    def parse_receipt_trusted_public_keys(cls, value: object) -> object:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            raise ValueError("RECEIPT_TRUSTED_PUBLIC_KEYS must be a JSON object")
        try:
            parsed_value = loads(value)
        except JSONDecodeError as exc:
            raise ValueError("RECEIPT_TRUSTED_PUBLIC_KEYS must be a JSON object") from exc
        if not isinstance(parsed_value, dict):
            raise ValueError("RECEIPT_TRUSTED_PUBLIC_KEYS must be a JSON object")
        return parsed_value

    @field_validator(
        "frontend_url",
        "public_api_url",
        "okta_domain",
        "auth0_domain",
        "keycloak_domain",
        mode="after",
    )
    @classmethod
    def validate_auth_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None

        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Auth origins must be absolute HTTP(S) origins without paths")
        return value.rstrip("/")

    @field_validator("auth_redirect_origins", mode="after")
    @classmethod
    def validate_auth_redirect_origins(cls, value: list[str] | str) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("AUTH_REDIRECT_ORIGINS must contain at least one origin")

        normalized: list[str] = []
        for origin in value:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("AUTH_REDIRECT_ORIGINS entries must be absolute HTTP(S) origins")
            normalized.append(origin.rstrip("/"))
        return list(dict.fromkeys(normalized))

    @field_validator("oidc_issuer", "oidc_jwks_uri", mode="after")
    @classmethod
    def validate_oidc_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OIDC URLs must be absolute HTTP(S) URLs")
        return value

    @field_validator("pico_tutor_model", mode="after")
    @classmethod
    def validate_pico_tutor_model(cls, value: str) -> str:
        normalized = value.strip()
        model_identifier = normalized.removeprefix("openai/")
        if (
            not model_identifier
            or any(character.isspace() for character in normalized)
            or model_identifier.startswith("/")
        ):
            raise ValueError("PICO_TUTOR_MODEL must be a non-empty model identifier")
        return normalized

    @field_validator("redis_url", mode="after")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname or parsed.fragment:
            raise ValueError("REDIS_URL must be a valid redis:// or rediss:// URL")
        return value

    @field_validator("rate_limit_redis_key_prefix", mode="after")
    @classmethod
    def validate_rate_limit_redis_key_prefix(cls, value: str) -> str:
        allowed_characters = frozenset(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:_-"
        )
        if any(character not in allowed_characters for character in value):
            raise ValueError(
                "RATE_LIMIT_REDIS_KEY_PREFIX may contain only letters, numbers, ':', '_', or '-'"
            )
        return value

    @model_validator(mode="after")
    def validate_environment_variables(self) -> "Settings":
        """Validate required environment variables on startup."""
        errors: list[str] = []
        warnings: list[str] = []

        # Check if running in production
        is_production = self.environment == "production"

        # Validate JWT_SECRET
        jwt_secret_was_provided = "jwt_secret" in self.model_fields_set
        if not jwt_secret_was_provided:
            # JWT_SECRET was not set, using auto-generated default
            self._jwt_secret_was_auto_generated = True
            if is_production:
                errors.append(
                    "JWT_SECRET environment variable must be set in production. "
                    'Generate one with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
                )
            else:
                warnings.append(
                    "JWT_SECRET is not set; using auto-generated secret. "
                    "This is fine for development but should be set in production."
                )
        elif len(self.jwt_secret) < 32:
            errors.append(
                f"JWT_SECRET must be at least 32 characters long, got {len(self.jwt_secret)}"
            )

        # Validate SECRET_ENCRYPTION_KEY (required in production for credential encryption)
        if not self.secret_encryption_key:
            if is_production:
                errors.append(
                    "SECRET_ENCRYPTION_KEY environment variable must be set in production. "
                    'Generate one with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                )
            else:
                warnings.append(
                    "SECRET_ENCRYPTION_KEY is not set; falling back to JWT secret for encryption. "
                    "This is not recommended — set a dedicated encryption key for production."
                )
        elif self.secret_encryption_key == self.jwt_secret:
            errors.append(
                "SECRET_ENCRYPTION_KEY must not match JWT_SECRET. "
                "Use a dedicated encryption key to keep token signing and secret encryption separate."
            )

        receipt_signing_values = {
            "RECEIPT_SIGNING_KEY_ID": self.receipt_signing_key_id,
            "RECEIPT_SIGNING_PRIVATE_KEY": self.receipt_signing_private_key,
            "RECEIPT_TRUSTED_PUBLIC_KEYS": self.receipt_trusted_public_keys,
        }
        if is_production and not all(receipt_signing_values.values()):
            missing = ", ".join(name for name, value in receipt_signing_values.items() if not value)
            errors.append(
                "Production receipt signing requires a platform Ed25519 key and trusted "
                f"public key registry. Missing: {missing}"
            )
        if any(receipt_signing_values.values()):
            try:
                from src.security.receipts import ReceiptGenerator

                ReceiptGenerator(
                    signing_private_key=self.receipt_signing_private_key,
                    signing_key_id=self.receipt_signing_key_id,
                    trusted_public_keys=self.receipt_trusted_public_keys,
                    signing_required=is_production,
                )
            except (RuntimeError, ValueError) as exc:
                errors.append(f"Receipt signing configuration is invalid: {exc}")

        # OIDC is optional, but partial configuration is unsafe and unusable.
        oidc_values = {
            "OIDC_ISSUER": self.oidc_issuer,
            "OIDC_CLIENT_ID": self.oidc_client_id,
            "OIDC_JWKS_URI": self.oidc_jwks_uri,
        }
        if any(oidc_values.values()) and not all(oidc_values.values()):
            missing = ", ".join(name for name, value in oidc_values.items() if not value)
            errors.append(
                f"OIDC configuration must be provided as a complete set. Missing: {missing}"
            )

        provider_groups = {
            "Google OAuth": {
                "GOOGLE_CLIENT_ID": self.google_client_id,
                "GOOGLE_CLIENT_SECRET": self.google_client_secret,
            },
            "GitHub OAuth": {
                "GITHUB_CLIENT_ID": self.github_client_id,
                "GITHUB_CLIENT_SECRET": self.github_client_secret,
            },
            "Discord OAuth": {
                "DISCORD_CLIENT_ID": self.discord_client_id,
                "DISCORD_CLIENT_SECRET": self.discord_client_secret,
            },
            "Apple OAuth": {
                "APPLE_CLIENT_ID": self.apple_client_id,
                "APPLE_TEAM_ID": self.apple_team_id,
                "APPLE_KEY_ID": self.apple_key_id,
                "APPLE_PRIVATE_KEY": self.apple_private_key,
            },
            "Okta SSO": {
                "OKTA_DOMAIN": self.okta_domain,
                "OKTA_CLIENT_ID": self.okta_client_id,
                "OKTA_CLIENT_SECRET": self.okta_client_secret,
            },
            "Auth0 SSO": {
                "AUTH0_DOMAIN": self.auth0_domain,
                "AUTH0_CLIENT_ID": self.auth0_client_id,
                "AUTH0_CLIENT_SECRET": self.auth0_client_secret,
            },
            "Keycloak SSO": {
                "KEYCLOAK_DOMAIN": self.keycloak_domain,
                "KEYCLOAK_REALM": self.keycloak_realm,
                "KEYCLOAK_CLIENT_ID": self.keycloak_client_id,
                "KEYCLOAK_CLIENT_SECRET": self.keycloak_client_secret,
            },
        }
        for label, values in provider_groups.items():
            if any(values.values()) and not all(values.values()):
                missing = ", ".join(name for name, value in values.items() if not value)
                errors.append(f"{label} configuration is incomplete. Missing: {missing}")

        legacy_sso_configured = any(
            (
                self.okta_domain,
                self.okta_client_id,
                self.okta_client_secret,
                self.auth0_domain,
                self.auth0_client_id,
                self.auth0_client_secret,
                self.keycloak_domain,
                self.keycloak_realm,
                self.keycloak_client_id,
                self.keycloak_client_secret,
            )
        )
        if legacy_sso_configured and not self.public_api_url:
            errors.append("PUBLIC_API_URL must be configured when SSO is enabled")

        auth_origins = [
            value
            for value in (
                self.public_api_url,
                self.okta_domain,
                self.auth0_domain,
                self.keycloak_domain,
                self.oidc_issuer,
                self.oidc_jwks_uri,
            )
            if value
        ]
        if is_production:
            if self.rate_limit_backend == "memory":
                errors.append("RATE_LIMIT_BACKEND must be redis in production")

            frontend_url_was_provided = "frontend_url" in self.model_fields_set
            frontend_host = urlsplit(self.frontend_url).hostname
            if not frontend_url_was_provided:
                errors.append("FRONTEND_URL must be explicitly configured in production")
            elif urlsplit(self.frontend_url).scheme != "https" or _is_loopback_hostname(
                frontend_host
            ):
                errors.append(
                    "FRONTEND_URL must use HTTPS and a non-loopback hostname in production"
                )

            insecure_origins = [
                value for value in auth_origins if urlsplit(value).scheme != "https"
            ]
            if insecure_origins:
                errors.append("OAuth, SSO, and OIDC URLs must use HTTPS in production")

            redirect_origins = (
                self.auth_redirect_origins if isinstance(self.auth_redirect_origins, list) else []
            )
            insecure_redirect_origins = [
                origin
                for origin in redirect_origins
                if urlsplit(origin).scheme != "https"
                or _is_loopback_hostname(urlsplit(origin).hostname)
            ]
            if insecure_redirect_origins:
                errors.append(
                    "AUTH_REDIRECT_ORIGINS must contain only HTTPS, non-loopback origins "
                    "in production"
                )
            if self.frontend_url not in redirect_origins:
                errors.append(
                    "AUTH_REDIRECT_ORIGINS must include the canonical FRONTEND_URL in production"
                )

            resend_configured = bool(
                self.resend_api_key
                and self.resend_api_key.strip()
                and self.resend_from_email
                and self.resend_from_email.strip()
            )
            smtp_configured = bool(
                self.smtp_host.strip()
                and self.smtp_port
                and self.smtp_user.strip()
                and self.smtp_password.strip()
                and self.smtp_from_email.strip()
            )
            if self.require_email_verification and not (resend_configured or smtp_configured):
                errors.append(
                    "Email verification requires either RESEND_API_KEY and "
                    "RESEND_FROM_EMAIL or complete SMTP settings in production"
                )

        # Validate DATABASE_URL when database is required on startup
        if self.database_required_on_startup:
            db_env_value = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
            if db_env_value is None:
                # Using default value - likely not configured
                if "postgresql://user:password@localhost" in self.database_url:
                    errors.append(
                        "DATABASE_URL environment variable must be set when "
                        "DATABASE_REQUIRED_ON_STARTUP is true"
                    )

        # Validate database URL format without reflecting credentials in errors.
        if self.database_url:
            db_url = self.database_url.lower()
            if db_url.startswith(("sqlite://", "sqlite+")):
                if is_production:
                    errors.append("DATABASE_URL must use PostgreSQL in production")
                if self.web_concurrency != 1:
                    errors.append(
                        "SQLite requires WEB_CONCURRENCY=1 because process-local coordination "
                        "cannot protect durable session updates across workers"
                    )
            elif not db_url.startswith(("postgresql://", "postgres://")):
                errors.append("DATABASE_URL must be a valid PostgreSQL connection string")

        # Enforce SSL for database connections in production
        if is_production and self.database_url:
            db_url_lower = self.database_url.lower()
            if db_url_lower.startswith(("postgresql://", "postgres://")):
                has_ssl_in_url = "sslmode=" in db_url_lower or "ssl=" in db_url_lower
                if not self.database_ssl_mode and not has_ssl_in_url:
                    warnings.append(
                        "DATABASE_SSL_MODE is not set in production. "
                        "Database connections may be unencrypted. "
                        "Set DATABASE_SSL_MODE=require for production."
                    )

        # Production-specific validations
        if is_production:
            # Deferred startup must not turn the development placeholder into a
            # production database configuration.
            database_url_was_provided = "database_url" in self.model_fields_set
            if not database_url_was_provided or self.database_url == _DEFAULT_DATABASE_URL:
                errors.append(
                    "DATABASE_URL appears to be using default values. "
                    "Please configure a production database."
                )

            # Check CORS origins for production
            if "localhost" in str(self.cors_origins):
                warnings.append(
                    "CORS_ORIGINS contains localhost origins. "
                    "This may not be suitable for production."
                )

            # Check allowed hosts for overly permissive patterns
            hosts_list = (
                self.allowed_hosts if isinstance(self.allowed_hosts, list) else [self.allowed_hosts]
            )
            wildcard_hosts = [h for h in hosts_list if "*" in h or h == "test" or h == "testserver"]
            if wildcard_hosts:
                errors.append(
                    f"ALLOWED_HOSTS contains permissive entries: {wildcard_hosts}. "
                    "Set exact production hostnames instead."
                )

            forwarded_allow_ips = (
                self.forwarded_allow_ips
                if isinstance(self.forwarded_allow_ips, list)
                else [self.forwarded_allow_ips]
            )
            if not forwarded_allow_ips:
                errors.append(
                    "FORWARDED_ALLOW_IPS must contain deployment-specific trusted proxy "
                    "addresses or CIDRs in production."
                )
            elif "*" in forwarded_allow_ips:
                errors.append(
                    "FORWARDED_ALLOW_IPS must not trust all proxy sources ('*') in production. "
                    "Set explicit ingress proxy IPs instead."
                )
            else:
                invalid_proxy_networks: list[str] = []
                for proxy_network in forwarded_allow_ips:
                    try:
                        ip_network(proxy_network, strict=False)
                    except ValueError:
                        invalid_proxy_networks.append(proxy_network)
                if invalid_proxy_networks:
                    errors.append(
                        "FORWARDED_ALLOW_IPS entries must be valid IP addresses or CIDRs: "
                        f"{invalid_proxy_networks}"
                    )

        # Raise errors if any
        if errors:
            error_message = "Environment variable validation failed:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
            raise ValueError(error_message)

        # Log warnings (these will be captured by the caller)
        if warnings:
            warning_message = "Environment variable warnings:\n" + "\n".join(
                f"  - {w}" for w in warnings
            )
            import logging

            logging.warning(warning_message)

        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
