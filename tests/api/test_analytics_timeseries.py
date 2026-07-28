"""
Tests for /analytics/timeseries endpoint — auth enforcement and response structure.

Note: The timeseries route uses PostgreSQL `date_trunc` which is not available in
the SQLite test database. The response-structure tests monkeypatch the DB execute
to avoid this limitation. Auth tests run against the real route.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestAnalyticsTimeSeriesAuth:
    """Auth enforcement for /analytics/timeseries."""

    @pytest.mark.asyncio
    async def test_timeseries_requires_auth(self, client_no_auth: AsyncClient):
        """Unauthenticated requests should be rejected."""
        response = await client_no_auth.get(
            "/v1/analytics/timeseries",
            params={"metric": "runs"},
        )
        assert response.status_code in (401, 403)


class TestAnalyticsTimeSeriesResponse:
    """Test timeseries endpoint with DB layer monkeypatched.

    The timeseries route uses PostgreSQL date_trunc, which SQLite doesn't support.
    We patch db_session.execute to return fake rows so we can validate response shape.
    """

    @pytest.mark.asyncio
    async def test_timeseries_runs_returns_valid_structure(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch
    ):
        """Timeseries 'runs' metric returns correct response envelope."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        class FakeRow:
            ts = now
            count = 5

        async def fake_execute(statement, *args, **kwargs):
            class FakeResult:
                def __aiter__(self):
                    return self

                async def __anext__(self):
                    raise StopAsyncIteration

                # Support iteration pattern used by the route
                async def _exec(self):
                    return [FakeRow()]

            result = FakeResult()
            # Make it iterable
            result.__iter__ = lambda s: iter([FakeRow()])
            return result

        call_count = [0]

        async def counting_execute(stmt, *args, **kwargs):
            call_count[0] += 1

            # Return an object whose iteration yields one fake row
            class Row:
                ts = now
                count = 7

            class Result:
                def __iter__(self):
                    return iter([Row()])

            return Result()

        monkeypatch.setattr(db_session, "execute", counting_execute)

        response = await client.get(
            "/v1/analytics/timeseries",
            params={"metric": "runs", "period_start": "7d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["metric"] == "runs"
        assert "interval" in data
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 1
        assert data["data"][0]["value"] == 7

    @pytest.mark.asyncio
    async def test_timeseries_empty_data(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch
    ):
        """Timeseries returns empty data when no rows match."""

        async def empty_execute(stmt, *args, **kwargs):
            class Result:
                def __iter__(self):
                    return iter([])

            return Result()

        monkeypatch.setattr(db_session, "execute", empty_execute)

        response = await client.get(
            "/v1/analytics/timeseries",
            params={"metric": "runs", "period_start": "7d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["metric"] == "runs"

    @pytest.mark.asyncio
    async def test_timeseries_latency_metric(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch
    ):
        """Timeseries 'latency' metric returns correct response envelope."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        async def latency_execute(stmt, *args, **kwargs):
            class Row:
                ts = now
                avg = 150.5

            class Result:
                def __iter__(self):
                    return iter([Row()])

            return Result()

        monkeypatch.setattr(db_session, "execute", latency_execute)

        response = await client.get(
            "/v1/analytics/timeseries",
            params={"metric": "latency", "period_start": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["metric"] == "latency"
        assert len(data["data"]) == 1
        assert data["data"][0]["value"] == 150.5

    @pytest.mark.asyncio
    async def test_timeseries_api_calls_metric(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch
    ):
        """Timeseries 'api_calls' metric returns correct response envelope."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        async def fake_execute(stmt, *args, **kwargs):
            class Row:
                ts = now
                count = 42

            class Result:
                def __iter__(self):
                    return iter([Row()])

            return Result()

        monkeypatch.setattr(db_session, "execute", fake_execute)

        response = await client.get(
            "/v1/analytics/timeseries",
            params={"metric": "api_calls", "period_start": "30d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["metric"] == "api_calls"
        assert len(data["data"]) == 1
        assert data["data"][0]["value"] == 42
