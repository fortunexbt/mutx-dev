"""Distributed rate limiting middleware for the API."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
import hmac
from ipaddress import ip_address
import logging
import math
import time
from typing import Protocol, cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.config import Settings, get_settings
from src.api.models.error_schemas import RateLimitErrorResponse

logger = logging.getLogger(__name__)

settings = get_settings()


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of one atomic rate-limit check."""

    allowed: bool
    count: int
    remaining: int
    reset_after_seconds: float


class RateLimitBackendUnavailable(RuntimeError):
    """Raised when the configured rate-limit backend cannot make a decision."""


class RateLimitBackend(Protocol):
    async def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision: ...

    async def ping(self) -> None: ...

    async def close(self) -> None: ...


class RedisClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...

    async def ping(self) -> object: ...

    async def aclose(self) -> None: ...


@dataclass
class _MemoryBucket:
    count: int
    reset_at: float


class InMemoryRateLimitBackend:
    """Bounded, process-local backend intended only for development and tests."""

    def __init__(
        self,
        *,
        max_buckets: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_buckets = max_buckets
        self._clock = clock
        self._buckets: OrderedDict[str, _MemoryBucket] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)

    async def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        async with self._lock:
            now = self._clock()
            bucket = self._buckets.get(key)

            if bucket is not None and bucket.reset_at <= now:
                del self._buckets[key]
                bucket = None

            if bucket is None:
                if len(self._buckets) >= self.max_buckets:
                    self._buckets.popitem(last=False)
                bucket = _MemoryBucket(count=1, reset_at=now + window_seconds)
                self._buckets[key] = bucket
                allowed = True
            else:
                self._buckets.move_to_end(key)
                allowed = bucket.count < limit
                if allowed:
                    bucket.count += 1

            return RateLimitDecision(
                allowed=allowed,
                count=bucket.count,
                remaining=max(0, limit - bucket.count),
                reset_after_seconds=max(0.001, bucket.reset_at - now),
            )

    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        return None


class RedisRateLimitBackend:
    """Atomic fixed-window limiter backed by one shared async Redis client."""

    _CHECK_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]))
local ttl = redis.call('PTTL', KEYS[1])
local window_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

if current == nil or ttl <= 0 then
    redis.call('SET', KEYS[1], 1, 'PX', window_ms)
    return {1, window_ms, 1}
end

if current >= limit then
    return {current, ttl, 0}
end

current = redis.call('INCR', KEYS[1])
return {current, ttl, 1}
""".strip()

    def __init__(self, client: RedisClient) -> None:
        self._client = client

    async def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        try:
            raw_result = await self._client.eval(
                self._CHECK_SCRIPT,
                1,
                key,
                window_seconds * 1000,
                limit,
            )
            result = cast(list[object] | tuple[object, ...], raw_result)
            count = int(result[0])
            ttl_ms = int(result[1])
            allowed = bool(int(result[2]))
            if count < 1 or ttl_ms < 1:
                raise ValueError("Redis returned an invalid rate-limit result")
        except Exception as exc:
            raise RateLimitBackendUnavailable("Redis rate-limit check failed") from exc

        return RateLimitDecision(
            allowed=allowed,
            count=count,
            remaining=max(0, limit - count),
            reset_after_seconds=ttl_ms / 1000,
        )

    async def ping(self) -> None:
        try:
            await self._client.ping()
        except Exception as exc:
            raise RateLimitBackendUnavailable("Redis rate-limit backend is unavailable") from exc

    async def close(self) -> None:
        await self._client.aclose()


def _resolved_backend_name(config: Settings) -> str:
    if config.rate_limit_backend is not None:
        return config.rate_limit_backend
    return "redis" if config.is_production else "memory"


def _create_redis_client(config: Settings) -> RedisClient:
    try:
        from redis.asyncio import Redis
    except ImportError as exc:  # pragma: no cover - exercised in dependency smoke checks
        raise RateLimitBackendUnavailable(
            "The redis package is required for Redis rate limiting"
        ) from exc

    return Redis.from_url(
        config.redis_url,
        decode_responses=False,
        max_connections=config.rate_limit_redis_max_connections,
        socket_connect_timeout=config.rate_limit_redis_timeout_seconds,
        socket_timeout=config.rate_limit_redis_timeout_seconds,
        health_check_interval=30,
    )


async def start_rate_limiting(
    app: FastAPI,
    *,
    config: Settings = settings,
    redis_client_factory: Callable[[Settings], RedisClient] = _create_redis_client,
) -> None:
    """Create and verify the process-wide backend during application startup."""
    backend = getattr(app.state, "rate_limit_backend", None)
    backend_name = _resolved_backend_name(config)

    try:
        if backend is None:
            if backend_name == "memory":
                backend = InMemoryRateLimitBackend(max_buckets=config.rate_limit_memory_max_buckets)
            else:
                backend = RedisRateLimitBackend(redis_client_factory(config))
        await backend.ping()
    except RateLimitBackendUnavailable as exc:
        if backend is not None:
            try:
                await backend.close()
            except Exception:
                logger.warning("Failed to close unavailable rate-limit backend", exc_info=True)
        raise RuntimeError("Required rate-limit backend is unavailable") from exc

    app.state.rate_limit_backend = backend
    logger.info("Rate-limit backend initialized: %s", backend_name)


async def close_rate_limiting(app: FastAPI) -> None:
    """Close the lifecycle-managed backend client/pool."""
    backend = getattr(app.state, "rate_limit_backend", None)
    app.state.rate_limit_backend = None
    if backend is None:
        return
    try:
        await backend.close()
    except Exception:
        logger.warning("Failed to close rate-limit backend", exc_info=True)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply the configured rate-limit policy before dispatching API requests."""

    AUTH_SENSITIVE_PATHS = frozenset(
        {
            "/v1/auth/register",
            "/v1/auth/login",
            "/v1/auth/local-bootstrap",
            "/v1/auth/refresh",
            "/v1/auth/forgot-password",
            "/v1/auth/reset-password",
            "/v1/auth/verify-email",
            "/v1/auth/resend-verification",
            "/v1/auth/oauth/google/exchange",
            "/v1/auth/oauth/github/exchange",
            "/v1/auth/oauth/discord/exchange",
        }
    )
    EXEMPT_PATHS = frozenset({"/", "/health", "/ready", "/metrics"})

    def __init__(
        self,
        app: FastAPI,
        requests: int | None = None,
        window_seconds: int | None = None,
        auth_requests: int | None = None,
        auth_window_seconds: int | None = None,
        backend: RateLimitBackend | None = None,
        key_prefix: str | None = None,
        use_app_backend: bool = False,
    ) -> None:
        super().__init__(app)
        self.requests = requests or settings.rate_limit_requests
        self.window_seconds = window_seconds or settings.rate_limit_window_seconds
        self.auth_requests = auth_requests or settings.auth_rate_limit_requests
        self.auth_window_seconds = auth_window_seconds or settings.auth_rate_limit_window_seconds
        self.key_prefix = key_prefix or settings.rate_limit_redis_key_prefix
        self._identity_hash_key = hmac.digest(
            settings.jwt_secret.encode("utf-8"),
            f"mutx-rate-limit:{self.key_prefix}".encode("utf-8"),
            "sha256",
        )
        self._backend = backend
        if (
            backend is None
            and not use_app_backend
            and any(
                value is not None
                for value in (requests, window_seconds, auth_requests, auth_window_seconds)
            )
        ):
            self._backend = InMemoryRateLimitBackend(
                max_buckets=settings.rate_limit_memory_max_buckets
            )

    def _get_client_ip(self, request: Request) -> str:
        """Use only the peer identity already resolved by the trusted ASGI server."""
        if request.client is None:
            return "unknown"
        try:
            return ip_address(request.client.host).compressed
        except ValueError:
            return request.client.host.strip().lower() or "unknown"

    def _get_client_identifier(self, request: Request) -> str:
        """Prefer authenticated principal context, otherwise use the trusted peer IP."""
        auth_api_key_identifier = getattr(request.state, "auth_api_key_identifier", None)
        if auth_api_key_identifier:
            return f"api_key:{auth_api_key_identifier}"

        auth_user_id = getattr(request.state, "auth_user_id", None)
        if auth_user_id:
            return f"user:{auth_user_id}"

        return f"ip:{self._get_client_ip(request)}"

    def _fingerprint(self, client_id: str) -> str:
        """Return a non-reversible shorthand suitable for structured logs."""
        return self._identity_digest(client_id)[:16]

    def _mask_client_for_logging(self, client_id: str) -> str:
        return self._fingerprint(client_id)

    def _build_bucket_key(self, policy_name: str, client_id: str) -> str:
        digest = self._identity_digest(client_id)
        return f"{self.key_prefix}:{policy_name}:{digest}"

    def _identity_digest(self, client_id: str) -> str:
        """Pseudonymize an authenticated identifier with a deployment-scoped key."""
        return hmac.digest(
            self._identity_hash_key,
            client_id.encode("utf-8"),
            "sha256",
        ).hex()

    @classmethod
    def _resolve_policy(cls, path: str) -> tuple[str, bool]:
        if path in cls.AUTH_SENSITIVE_PATHS:
            return ("auth", True)
        return ("default", False)

    def _backend_for_request(self, request: Request) -> RateLimitBackend:
        backend = self._backend or getattr(request.app.state, "rate_limit_backend", None)
        if backend is None:
            raise RateLimitBackendUnavailable("Rate-limit backend has not been initialized")
        return backend

    @staticmethod
    def _rate_limit_headers(
        *,
        limit: int,
        remaining: int,
        reset_after_seconds: float,
        window_seconds: int,
    ) -> dict[str, str]:
        reset_after = max(1, math.ceil(reset_after_seconds))
        reset_at = math.ceil(time.time() + reset_after_seconds)
        return {
            "RateLimit-Limit": str(limit),
            "RateLimit-Remaining": str(remaining),
            "RateLimit-Reset": str(reset_after),
            "RateLimit-Policy": f"{limit};w={window_seconds}",
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process one request with an atomic backend decision."""
        path = request.url.path
        if request.method.upper() == "OPTIONS" or path in self.EXEMPT_PATHS:
            return await call_next(request)

        client_id = self._get_client_identifier(request)
        policy_name, is_auth_policy = self._resolve_policy(path)
        window_seconds = self.auth_window_seconds if is_auth_policy else self.window_seconds
        limit = self.auth_requests if is_auth_policy else self.requests
        bucket_key = self._build_bucket_key(policy_name, client_id)

        try:
            decision = await self._backend_for_request(request).check(
                bucket_key,
                limit=limit,
                window_seconds=window_seconds,
            )
        except RateLimitBackendUnavailable:
            logger.error("Rate-limit backend unavailable; rejecting request", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "error_code": "RATE_LIMIT_UNAVAILABLE",
                    "message": "Request rate limiting is temporarily unavailable.",
                },
                headers={"Retry-After": "1"},
            )

        headers = self._rate_limit_headers(
            limit=limit,
            remaining=decision.remaining,
            reset_after_seconds=decision.reset_after_seconds,
            window_seconds=window_seconds,
        )

        if not decision.allowed:
            retry_after = max(1, math.ceil(decision.reset_after_seconds))
            logger.warning(
                "Rate limit exceeded | policy=%s | count=%s | limit=%s | client=%s",
                policy_name,
                decision.count,
                limit,
                self._fingerprint(client_id),
            )
            response = RateLimitErrorResponse(
                status="error",
                error_code="RATE_LIMIT_EXCEEDED",
                message="Too many requests. Please try again later.",
                retry_after=retry_after,
            )
            headers["Retry-After"] = str(retry_after)
            return JSONResponse(
                status_code=429,
                content=response.model_dump(mode="json"),
                headers=headers,
            )

        logger.debug(
            "Rate limit check | policy=%s | count=%s | limit=%s | path=%s",
            policy_name,
            decision.count,
            limit,
            path,
        )
        response = await call_next(request)
        response.headers.update(headers)
        return response


def add_rate_limiting(app: FastAPI, *, config: Settings = settings) -> None:
    """Add rate limiting and provision the bounded non-production backend."""
    if _resolved_backend_name(config) == "memory":
        app.state.rate_limit_backend = InMemoryRateLimitBackend(
            max_buckets=config.rate_limit_memory_max_buckets
        )
    else:
        app.state.rate_limit_backend = None

    app.add_middleware(
        RateLimitMiddleware,
        requests=config.rate_limit_requests,
        window_seconds=config.rate_limit_window_seconds,
        auth_requests=config.auth_rate_limit_requests,
        auth_window_seconds=config.auth_rate_limit_window_seconds,
        key_prefix=config.rate_limit_redis_key_prefix,
        use_app_backend=True,
    )
    logger.info(
        "Rate limiting enabled: %s requests per %s seconds",
        config.rate_limit_requests,
        config.rate_limit_window_seconds,
    )
