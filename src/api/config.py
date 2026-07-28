from functools import lru_cache
from json import JSONDecodeError, loads
import os
import secrets
from typing import Optional

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV"),
    )
    database_url: str = Field(
        default="postgresql://user:password@localhost:5432/mutx",
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
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    refresh_token_max_sliding_days: int = 30  # Max days for sliding expiry
    expose_api_docs_in_production: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "EXPOSE_API_DOCS_IN_PRODUCTION",
            "ENABLE_API_DOCS_IN_PRODUCTION",
        ),
        description="Expose /docs, /redoc, and /openapi.json in production.",
    )
    require_email_verification: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "REQUIRE_EMAIL_VERIFICATION",
        ),
        description="Require email verification before allowing password-based login.",
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
    governance_supervised_agent_launcher: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOVERNANCE_SUPERVISED_AGENT_LAUNCHER",
            "SUPERVISED_AGENT_LAUNCHER",
        ),
        description="Path to the agent launcher generated by `faramesh apply`.",
    )
    forwarded_allow_ips: list[str] | str = Field(
        default_factory=lambda: ["*"],
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

    @field_validator("cors_origins", mode="before")
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

    @model_validator(mode="after")
    def validate_environment_variables(self) -> "Settings":
        """Validate required environment variables on startup."""
        errors: list[str] = []
        warnings: list[str] = []

        # Check if running in production
        is_production = self.environment.lower() in ("production", "prod")

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

        # Validate database URL format
        if self.database_url:
            db_url = self.database_url.lower()
            if db_url.startswith(("sqlite://", "sqlite+")):
                if is_production:
                    errors.append("DATABASE_URL must use PostgreSQL in production")
            elif not db_url.startswith(("postgresql://", "postgres://")):
                errors.append(
                    f"DATABASE_URL must be a valid PostgreSQL connection string, "
                    f"got: {self.database_url[:50]}..."
                )

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
            # Check for default/insecure values
            if self.database_url == "postgresql://user:***@localhost:5432/mutx":
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
            wildcard_hosts = [
                h for h in hosts_list if h.startswith("*") or h == "test" or h == "testserver"
            ]
            if wildcard_hosts:
                warnings.append(
                    f"ALLOWED_HOSTS contains permissive entries: {wildcard_hosts}. "
                    "Review and restrict for production."
                )

            if "*" in self.forwarded_allow_ips:
                errors.append(
                    "FORWARDED_ALLOW_IPS must not trust all proxy sources ('*') in production. "
                    "Set explicit ingress proxy IPs instead."
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
        return self.environment.lower() in ("production", "prod")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
