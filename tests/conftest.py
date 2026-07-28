"""
Pytest configuration and fixtures for MUTX API tests.
"""

import asyncio
from datetime import datetime, timezone
from collections.abc import AsyncGenerator
import os
from pathlib import Path
import sys
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set environment before any imports
os.environ.setdefault("DATABASE_REQUIRED_ON_STARTUP", "false")
os.environ.setdefault("BACKGROUND_MONITOR_ENABLED", "false")
os.environ.setdefault("ENABLE_RAG_API", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-32")
os.environ["OPENCLAW_HOME"] = "/tmp/mutx-test-openclaw-home"

# Use an isolated SQLite database for tests by default.
# Do not inherit DATABASE_URL from the shell, or tests can accidentally hit a
# real/dev database and fail in misleading ways.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT / "sdk"

for entry in (str(ROOT), str(SDK_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)


@pytest.fixture(autouse=True)
def prevent_external_transactional_email(monkeypatch: pytest.MonkeyPatch):
    """Keep API tests from contacting a developer-configured email provider."""
    from src.api.routes import auth as auth_routes

    async def not_delivered(*_args, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(auth_routes, "send_verification_email", not_delivered)
    monkeypatch.setattr(auth_routes, "send_password_reset_email", not_delivered)


@compiles(PGUUID, "sqlite")
def compile_uuid_sqlite(_type, _compiler, **_kw):
    return "CHAR(36)"


def create_test_app():
    """Create a test FastAPI application using the production app factory."""
    from src.api.main import create_app

    app = create_app(
        enable_lifespan=False,
        background_monitor_enabled=False,
        database_required_on_startup=False,
    )
    app.state.start_time = datetime.now(timezone.utc).timestamp()
    app.state.database_ready = True
    app.state.database_error = None
    app.state.database_error_detail = None
    app.state.schema_repairs_applied = []
    return app


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine."""
    # Import models before Base.metadata.create_all() so SQLAlchemy has the
    # declarative tables registered. Without this, create_all() can silently
    # create an empty schema and tests fail later with misleading "no such table"
    # errors.
    from src.api.models import models as _models  # noqa: F401
    from src.api.database import Base

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in TEST_DATABASE_URL else {},
        poolclass=StaticPool if "sqlite" in TEST_DATABASE_URL else None,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession, test_user):
    """Create test client with database and auth overrides."""
    from src.api.database import get_db
    from src.api.middleware.auth import (
        get_current_user,
        get_current_user_optional,
        get_current_user_or_api_key,
    )
    from src.api.routes.webhooks import get_webhook_auth
    from src.api.routes.ingest import get_ingest_auth

    # Create test app
    test_app = create_test_app()

    async def override_get_db():
        yield db_session

    # Override get_current_user to return test user
    async def override_get_current_user():
        return test_user

    # Override get_current_user_or_api_key to return test user
    async def override_get_current_user_or_api_key():
        return test_user

    async def override_get_current_user_optional():
        return test_user

    async def override_get_webhook_auth():
        return test_user

    async def override_get_ingest_auth():
        return test_user

    # Override dependencies
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = override_get_current_user
    test_app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    test_app.dependency_overrides[get_current_user_or_api_key] = (
        override_get_current_user_or_api_key
    )
    test_app.dependency_overrides[get_webhook_auth] = override_get_webhook_auth
    test_app.dependency_overrides[get_ingest_auth] = override_get_ingest_auth

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        client.app = test_app
        yield client

    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def client_no_auth(db_session: AsyncSession):
    """Create test client without auth override (for testing auth)."""
    from src.api.database import get_db

    test_app = create_test_app()

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        client.app = test_app
        yield client

    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def other_user_client(db_session: AsyncSession, other_user):
    """Create test client authenticated as other_user."""
    from src.api.database import get_db
    from src.api.middleware.auth import (
        get_current_user,
        get_current_user_optional,
        get_current_user_or_api_key,
    )
    from src.api.routes.webhooks import get_webhook_auth
    from src.api.routes.ingest import get_ingest_auth

    test_app = create_test_app()

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return other_user

    async def override_get_current_user_or_api_key():
        return other_user

    async def override_get_current_user_optional():
        return other_user

    async def override_get_webhook_auth():
        return other_user

    async def override_get_ingest_auth():
        return other_user

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = override_get_current_user
    test_app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    test_app.dependency_overrides[get_current_user_or_api_key] = (
        override_get_current_user_or_api_key
    )
    test_app.dependency_overrides[get_webhook_auth] = override_get_webhook_auth
    test_app.dependency_overrides[get_ingest_auth] = override_get_ingest_auth

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        client.app = test_app
        yield client

    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    from src.api.models.models import User

    user = User(
        id=uuid.UUID("11111111-1111-4111-a111-111111111111"),
        email="test@mutx.dev",
        password_hash="hashedpassword",
        is_active=True,
        is_email_verified=True,
        name="Test User",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession):
    """Create another test user for authorization tests."""
    from src.api.models.models import User

    user = User(
        id=uuid.UUID("22222222-2222-4222-a222-222222222222"),
        email="other@example.com",
        password_hash="hashedpassword",
        is_active=True,
        name="Other User",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_agent(db_session: AsyncSession, test_user):
    """Create a test agent."""
    from src.api.models.models import Agent, AgentStatus

    agent = Agent(
        id=uuid.UUID("33333333-3333-4333-a333-333333333333"),
        name="test-agent",
        description="A test agent",
        config='{"model": "gpt-4"}',
        user_id=test_user.id,
        status=AgentStatus.CREATING,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


@pytest_asyncio.fixture
async def test_deployment(db_session: AsyncSession, test_agent):
    """Create a test deployment."""
    from src.api.models.models import Deployment

    deployment = Deployment(
        id=uuid.UUID("44444444-4444-4444-a444-444444444444"),
        agent_id=test_agent.id,
        status="running",
        replicas=1,
    )
    db_session.add(deployment)
    await db_session.commit()
    return deployment


@pytest.fixture(scope="session", autouse=True)
def shutdown_telemetry_after_tests() -> None:
    """Gracefully shut down OpenTelemetry after all tests complete.

    This prevents the BatchSpanProcessor background thread from writing
    to pytest's closed stdout/stderr (ValueError: I/O operation on closed file).
    Must run after all tests and at all process exits — including forked workers.
    """
    yield
    # Runs after the session ends but before the process exits.
    # We need to be defensive since the telemetry module may not have been imported.
    try:
        from src.api.telemetry.telemetry import shutdown_telemetry

        shutdown_telemetry()
    except Exception:
        pass  # telemetry may not be imported in this test run
