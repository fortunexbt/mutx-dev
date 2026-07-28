import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import pytest
from pydantic import ValidationError
from starlette.requests import Request

from src.api.config import Settings
from src.api.middleware.rate_limit import (
    InMemoryRateLimitBackend,
    RateLimitMiddleware,
    RedisRateLimitBackend,
    start_rate_limiting,
)


class FakeRedis:
    """Deterministic fake implementing the one atomic operation used by the limiter."""

    def __init__(self, *, fail_ping: bool = False, fail_eval: bool = False) -> None:
        self.now_ms = 0
        self.fail_ping = fail_ping
        self.fail_eval = fail_eval
        self.closed = False
        self.eval_calls = 0
        self.keys: list[str] = []
        self._entries: dict[str, tuple[int, int]] = {}
        self._lock = asyncio.Lock()

    async def eval(self, _script: str, numkeys: int, *keys_and_args: object) -> list[int]:
        if self.fail_eval:
            raise ConnectionError("redis unavailable")
        assert numkeys == 1
        key = str(keys_and_args[0])
        window_ms = int(keys_and_args[1])
        limit = int(keys_and_args[2])

        async with self._lock:
            self.eval_calls += 1
            self.keys.append(key)
            entry = self._entries.get(key)
            if entry is None or entry[1] <= self.now_ms:
                count = 1
                expires_at = self.now_ms + window_ms
                allowed = 1
            else:
                count, expires_at = entry
                allowed = int(count < limit)
                if allowed:
                    count += 1
            self._entries[key] = (count, expires_at)
            return [count, expires_at - self.now_ms, allowed]

    async def ping(self) -> bool:
        if self.fail_ping:
            raise ConnectionError("redis unavailable")
        return True

    async def aclose(self) -> None:
        self.closed = True

    def advance(self, *, milliseconds: int) -> None:
        self.now_ms += milliseconds


def _request_with_headers(
    headers: list[tuple[bytes, bytes]],
    client_host: str = "127.0.0.1",
    state: dict | None = None,
    path: str = "/v1/test",
    method: str = "GET",
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "state": state or {},
        "app": FastAPI(),
    }
    return Request(scope)


async def _ok_response(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True}, status_code=200)


def test_get_client_ip_ignores_spoofable_forwarded_headers() -> None:
    middleware = RateLimitMiddleware(FastAPI(), requests=5, window_seconds=60)
    request = _request_with_headers(
        headers=[
            (b"x-forwarded-for", b"203.0.113.10"),
            (b"forwarded", b"for=203.0.113.11"),
            (b"host", b"testserver"),
        ],
        client_host="192.0.2.50",
    )

    assert middleware._get_client_ip(request) == "192.0.2.50"


def test_get_client_identifier_preserves_authenticated_api_key_contract() -> None:
    middleware = RateLimitMiddleware(FastAPI(), requests=5, window_seconds=60)
    request = _request_with_headers(
        headers=[(b"host", b"testserver")],
        client_host="192.0.2.50",
        state={"auth_api_key_identifier": "managed:00000000-0000-0000-0000-000000000001"},
    )

    assert (
        middleware._get_client_identifier(request)
        == "api_key:managed:00000000-0000-0000-0000-000000000001"
    )


def test_get_client_identifier_isolates_authenticated_users_behind_one_peer() -> None:
    middleware = RateLimitMiddleware(FastAPI(), requests=5, window_seconds=60)
    first_user = _request_with_headers(
        headers=[(b"host", b"testserver")],
        client_host="192.0.2.50",
        state={"auth_user_id": "00000000-0000-0000-0000-000000000001"},
    )
    second_user = _request_with_headers(
        headers=[(b"host", b"testserver")],
        client_host="192.0.2.50",
        state={"auth_user_id": "00000000-0000-0000-0000-000000000002"},
    )

    assert middleware._get_client_identifier(first_user) == (
        "user:00000000-0000-0000-0000-000000000001"
    )
    assert middleware._get_client_identifier(second_user) == (
        "user:00000000-0000-0000-0000-000000000002"
    )


def test_get_client_identifier_does_not_trust_unauthenticated_api_key_header() -> None:
    middleware = RateLimitMiddleware(FastAPI(), requests=5, window_seconds=60)
    request = _request_with_headers(
        headers=[(b"x-api-key", b"mutx_live_abc123"), (b"host", b"testserver")],
        client_host="192.0.2.50",
    )

    assert middleware._get_client_identifier(request) == "ip:192.0.2.50"


def test_bucket_keys_are_stable_hashed_and_contain_no_raw_identity() -> None:
    middleware_one = RateLimitMiddleware(
        FastAPI(), requests=5, window_seconds=60, key_prefix="mutx:test"
    )
    middleware_two = RateLimitMiddleware(
        FastAPI(), requests=5, window_seconds=60, key_prefix="mutx:test"
    )
    client_id = "ip:192.0.2.50"

    first_key = middleware_one._build_bucket_key("default", client_id)
    second_key = middleware_two._build_bucket_key("default", client_id)

    assert first_key == second_key
    assert first_key.startswith("mutx:test:default:")
    assert client_id not in first_key
    assert "192.0.2.50" not in first_key


@pytest.mark.asyncio
async def test_redis_check_is_atomic_under_concurrency() -> None:
    backend = RedisRateLimitBackend(FakeRedis())

    decisions = await asyncio.gather(
        *(backend.check("bucket", limit=7, window_seconds=60) for _ in range(40))
    )

    assert sum(decision.allowed for decision in decisions) == 7
    assert max(decision.count for decision in decisions) == 7
    assert all(decision.remaining >= 0 for decision in decisions)


@pytest.mark.asyncio
async def test_redis_window_resets_after_exact_expiry() -> None:
    client = FakeRedis()
    backend = RedisRateLimitBackend(client)

    first = await backend.check("bucket", limit=1, window_seconds=10)
    blocked = await backend.check("bucket", limit=1, window_seconds=10)
    client.advance(milliseconds=10_000)
    reset = await backend.check("bucket", limit=1, window_seconds=10)

    assert first.allowed is True
    assert blocked.allowed is False
    assert blocked.reset_after_seconds == 10
    assert reset.allowed is True
    assert reset.count == 1
    assert reset.reset_after_seconds == 10


@pytest.mark.asyncio
async def test_dispatch_sets_unambiguous_rate_limit_and_retry_headers() -> None:
    client = FakeRedis()
    middleware = RateLimitMiddleware(
        FastAPI(),
        requests=1,
        window_seconds=60,
        backend=RedisRateLimitBackend(client),
    )
    request = _request_with_headers(headers=[(b"host", b"testserver")], client_host="192.0.2.50")

    allowed = await middleware.dispatch(request, _ok_response)
    blocked = await middleware.dispatch(request, _ok_response)
    payload = json.loads(blocked.body)

    assert allowed.status_code == 200
    assert allowed.headers["RateLimit-Limit"] == "1"
    assert allowed.headers["RateLimit-Remaining"] == "0"
    assert allowed.headers["RateLimit-Reset"] == "60"
    assert allowed.headers["RateLimit-Policy"] == "1;w=60"
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"
    assert blocked.headers["RateLimit-Reset"] == "60"
    assert payload["retry_after"] == 60
    assert all("192.0.2.50" not in key for key in client.keys)


@pytest.mark.asyncio
async def test_auth_sensitive_policy_and_exemptions_are_preserved() -> None:
    client = FakeRedis()
    middleware = RateLimitMiddleware(
        FastAPI(),
        requests=10,
        window_seconds=60,
        auth_requests=1,
        auth_window_seconds=30,
        backend=RedisRateLimitBackend(client),
    )
    auth_request = _request_with_headers(headers=[(b"host", b"testserver")], path="/v1/auth/login")
    health_request = _request_with_headers(headers=[], path="/health")
    options_request = _request_with_headers(headers=[], method="OPTIONS")

    first_auth = await middleware.dispatch(auth_request, _ok_response)
    second_auth = await middleware.dispatch(auth_request, _ok_response)
    health = await middleware.dispatch(health_request, _ok_response)
    options = await middleware.dispatch(options_request, _ok_response)

    assert first_auth.status_code == 200
    assert first_auth.headers["RateLimit-Policy"] == "1;w=30"
    assert second_auth.status_code == 429
    assert health.status_code == 200
    assert options.status_code == 200
    assert client.eval_calls == 2


@pytest.mark.asyncio
async def test_runtime_redis_failure_fails_closed_without_fallback() -> None:
    middleware = RateLimitMiddleware(
        FastAPI(),
        requests=5,
        window_seconds=60,
        backend=RedisRateLimitBackend(FakeRedis(fail_eval=True)),
    )
    request = _request_with_headers(headers=[(b"host", b"testserver")])

    response = await middleware.dispatch(request, _ok_response)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert json.loads(response.body)["error_code"] == "RATE_LIMIT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_required_redis_failure_aborts_startup_and_closes_client() -> None:
    app = FastAPI()
    app.state.rate_limit_backend = None
    client = FakeRedis(fail_ping=True)
    config = Settings(
        _env_file=None,
        RATE_LIMIT_BACKEND="redis",
        REDIS_URL="redis://redis:6379/0",
    )

    with pytest.raises(RuntimeError, match="Required rate-limit backend is unavailable"):
        await start_rate_limiting(app, config=config, redis_client_factory=lambda _config: client)

    assert client.closed is True
    assert app.state.rate_limit_backend is None


@pytest.mark.asyncio
async def test_in_memory_backend_is_concurrency_safe_and_strictly_bounded() -> None:
    now = [100.0]
    backend = InMemoryRateLimitBackend(max_buckets=3, clock=lambda: now[0])

    decisions = await asyncio.gather(
        *(backend.check("shared", limit=4, window_seconds=10) for _ in range(25))
    )
    for index in range(20):
        await backend.check(f"bucket-{index}", limit=1, window_seconds=10)

    assert sum(decision.allowed for decision in decisions) == 4
    assert backend.bucket_count == 3


@pytest.mark.asyncio
async def test_in_memory_backend_resets_expired_bucket_deterministically() -> None:
    now = [100.0]
    backend = InMemoryRateLimitBackend(max_buckets=2, clock=lambda: now[0])

    first = await backend.check("bucket", limit=1, window_seconds=5)
    blocked = await backend.check("bucket", limit=1, window_seconds=5)
    now[0] = 105.0
    reset = await backend.check("bucket", limit=1, window_seconds=5)

    assert first.allowed is True
    assert blocked.allowed is False
    assert reset.allowed is True
    assert reset.count == 1


def test_config_rejects_memory_backend_in_production() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_BACKEND must be redis in production"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            RATE_LIMIT_BACKEND="memory",
        )


@pytest.mark.parametrize(
    ("environment_name", "environment_value", "message"),
    [
        ("REDIS_URL", "https://redis.example.com/0", "REDIS_URL must be a valid"),
        (
            "RATE_LIMIT_REDIS_MAX_CONNECTIONS",
            "0",
            "RATE_LIMIT_REDIS_MAX_CONNECTIONS",
        ),
        ("RATE_LIMIT_MEMORY_MAX_BUCKETS", "0", "RATE_LIMIT_MEMORY_MAX_BUCKETS"),
    ],
)
def test_config_rejects_invalid_rate_limit_settings(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
    environment_value: str,
    message: str,
) -> None:
    monkeypatch.setenv(environment_name, environment_value)

    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None)
