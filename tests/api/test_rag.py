"""Tenant isolation, durability, and RBAC tests for /v1/rag."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import get_current_user
from src.api.database import get_db
from src.api.main import create_app
from src.api.models import User
from src.api.routes import rag as rag_routes


async def _set_roles(db: AsyncSession, user: User, *roles: str) -> None:
    user.roles = list(roles)
    await db.commit()


@pytest_asyncio.fixture
async def developer_client(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
) -> AsyncClient:
    await _set_roles(db_session, test_user, "DEVELOPER")
    return client


class RecordingEmbeddings:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    async def create(self, *, model: str, input: list[str]):
        texts = list(input)
        self.calls.append((model, texts))
        dimensions = rag_routes.EMBEDDING_MODELS[model]
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=index,
                    embedding=[float(index + 1)] * dimensions,
                )
                for index, _text in enumerate(texts)
            ],
            usage=SimpleNamespace(total_tokens=sum(len(text.split()) for text in texts)),
        )


def _install_recording_provider(monkeypatch: pytest.MonkeyPatch) -> RecordingEmbeddings:
    embeddings = RecordingEmbeddings()
    monkeypatch.setattr(
        rag_routes,
        "get_client",
        lambda: SimpleNamespace(embeddings=embeddings),
    )
    return embeddings


@asynccontextmanager
async def _new_client(db: AsyncSession, user: User):
    """Build a new app instance against the same durable database."""
    app = create_app(
        enable_lifespan=False,
        background_monitor_enabled=False,
        database_required_on_startup=False,
    )

    async def override_get_db():
        yield db

    async def override_get_current_user() -> User:
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as new_client:
        yield new_client


@pytest.mark.asyncio
async def test_generate_embedding_returns_local_embedding_for_developer(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = await developer_client.post(
        "/v1/rag/embed",
        json={"text": "hello world", "model": "text-embedding-3-small"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "text-embedding-3-small"
    assert payload["tokens"] == 2
    assert len(payload["embedding"]) == 1536
    assert any(value != 0.0 for value in payload["embedding"])


@pytest.mark.asyncio
async def test_viewer_cannot_generate_direct_or_batch_embeddings(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _install_recording_provider(monkeypatch)

    direct = await client.post("/v1/rag/embed", json={"text": "forbidden"})
    batch = await client.post("/v1/rag/embed/batch", json={"texts": ["forbidden"]})

    assert direct.status_code == 403
    assert batch.status_code == 403
    assert provider.calls == []


@pytest.mark.asyncio
async def test_developer_can_generate_direct_and_batch_embeddings(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _install_recording_provider(monkeypatch)

    direct = await developer_client.post("/v1/rag/embed", json={"text": "allowed"})
    batch = await developer_client.post(
        "/v1/rag/embed/batch",
        json={"texts": ["first", "second"]},
    )

    assert direct.status_code == 200
    assert batch.status_code == 200
    assert provider.calls == [
        ("text-embedding-3-small", ["allowed"]),
        ("text-embedding-3-small", ["first", "second"]),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/v1/rag/embed", {"text": "x" * (rag_routes.MAX_EMBED_TEXT_LENGTH + 1)}),
        (
            "/v1/rag/embed/batch",
            {"texts": ["x"] * (rag_routes.MAX_BATCH_TEXTS + 1)},
        ),
        (
            "/v1/rag/embed/batch",
            {"texts": ["x" * (rag_routes.MAX_EMBED_TEXT_LENGTH + 1)]},
        ),
        (
            "/v1/rag/embed/batch",
            {
                "texts": ["x" * rag_routes.MAX_EMBED_TEXT_LENGTH] * 4 + ["x"],
            },
        ),
    ],
    ids=["direct-text", "batch-cardinality", "batch-item", "batch-total"],
)
async def test_oversized_embedding_requests_return_422_without_provider_call(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict[str, object],
):
    provider = _install_recording_provider(monkeypatch)

    response = await developer_client.post(path, json=payload)

    assert response.status_code == 422
    assert provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/v1/rag/embed", {"text": "safe", "user_id": "other-tenant"}),
        (
            "/v1/rag/embed/batch",
            {"texts": ["safe"], "tenant_id": "other-tenant"},
        ),
    ],
    ids=["direct", "batch"],
)
async def test_embedding_requests_reject_unknown_tenant_fields_before_provider_call(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict[str, object],
):
    provider = _install_recording_provider(monkeypatch)

    response = await developer_client.post(path, json=payload)

    assert response.status_code == 422
    assert provider.calls == []


@pytest.mark.asyncio
async def test_embedding_request_limits_are_inclusive(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _install_recording_provider(monkeypatch)
    direct_text = "x" * rag_routes.MAX_EMBED_TEXT_LENGTH
    batch_texts = [
        "x" * (rag_routes.MAX_BATCH_TOTAL_LENGTH // rag_routes.MAX_BATCH_TEXTS)
    ] * rag_routes.MAX_BATCH_TEXTS

    direct = await developer_client.post("/v1/rag/embed", json={"text": direct_text})
    batch = await developer_client.post("/v1/rag/embed/batch", json={"texts": batch_texts})

    assert direct.status_code == 200
    assert batch.status_code == 200
    assert provider.calls == [
        ("text-embedding-3-small", [direct_text]),
        ("text-embedding-3-small", batch_texts),
    ]


@pytest.mark.asyncio
async def test_ingest_search_and_restart_persistence(
    developer_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ingest_response = await developer_client.post(
        "/v1/rag/ingest",
        json={
            "texts": [
                "python api design patterns",
                "gardening tips for tomatoes",
                "async fastapi route testing",
            ],
            "ids": ["doc-api", "doc-garden", "doc-fastapi"],
        },
    )
    assert ingest_response.status_code == 200
    assert ingest_response.json()["document_ids"] == ["doc-api", "doc-garden", "doc-fastapi"]

    async with _new_client(db_session, test_user) as restarted_client:
        response = await restarted_client.post(
            "/v1/rag/search",
            json={"query": "fastapi api testing", "top_k": 2},
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["text"] in {
        "python api design patterns",
        "async fastapi route testing",
    }
    assert payload[0]["score"] >= payload[1]["score"]


@pytest.mark.asyncio
async def test_collection_name_document_id_search_and_health_are_tenant_scoped(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    await _set_roles(db_session, test_user, "DEVELOPER")
    await _set_roles(db_session, other_user, "DEVELOPER")

    first_ingest = await client.post(
        "/v1/rag/ingest",
        json={
            "collection_name": "private-index",
            "texts": ["first tenant private alpha knowledge"],
            "ids": ["guessed-document-id"],
        },
    )
    guessed_search = await other_user_client.post(
        "/v1/rag/search",
        json={"collection_name": "private-index", "query": "private alpha"},
    )
    other_health_before = await other_user_client.get("/v1/rag/health")
    second_ingest = await other_user_client.post(
        "/v1/rag/ingest",
        json={
            "collection_name": "private-index",
            "texts": ["second tenant private beta knowledge"],
            "ids": ["guessed-document-id"],
        },
    )
    first_search = await client.post(
        "/v1/rag/search",
        json={"collection_name": "private-index", "query": "alpha knowledge"},
    )
    second_search = await other_user_client.post(
        "/v1/rag/search",
        json={"collection_name": "private-index", "query": "beta knowledge"},
    )

    assert first_ingest.status_code == 200
    assert guessed_search.status_code == 200
    assert guessed_search.json() == []
    assert other_health_before.json()["vector_store"] == "not_configured"
    assert second_ingest.status_code == 200
    assert first_search.json()[0]["text"] == "first tenant private alpha knowledge"
    assert second_search.json()[0]["text"] == "second tenant private beta knowledge"


@pytest.mark.asyncio
async def test_viewer_can_search_and_check_health_but_cannot_ingest(
    client: AsyncClient,
):
    search = await client.post("/v1/rag/search", json={"query": "safe read"})
    health = await client.get("/v1/rag/health")
    ingest = await client.post("/v1/rag/ingest", json={"texts": ["forbidden"]})

    assert search.status_code == 200
    assert search.json() == []
    assert health.status_code == 200
    assert ingest.status_code == 403


@pytest.mark.asyncio
async def test_roleless_user_cannot_use_safe_read_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    await _set_roles(db_session, test_user)

    embed = await client.post("/v1/rag/embed", json={"text": "blocked"})
    search = await client.post("/v1/rag/search", json={"query": "blocked"})
    health = await client.get("/v1/rag/health")

    assert embed.status_code == 403
    assert search.status_code == 403
    assert health.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_document_ids_fail_closed_with_conflict(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _install_recording_provider(monkeypatch)
    first = await developer_client.post(
        "/v1/rag/ingest",
        json={"texts": ["first"], "ids": ["stable-id"]},
    )
    duplicate = await developer_client.post(
        "/v1/rag/ingest",
        json={"texts": ["replacement"], "ids": ["stable-id"]},
    )
    assert provider.calls == [("text-embedding-3-small", ["first"])]

    search = await developer_client.post("/v1/rag/search", json={"query": "first"})

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert search.json()[0]["text"] == "first"


@pytest.mark.asyncio
async def test_existing_index_rejects_embedding_model_changes(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    created = await developer_client.post(
        "/v1/rag/ingest",
        json={"texts": ["small model document"]},
    )
    conflicting_ingest = await developer_client.post(
        "/v1/rag/ingest",
        json={
            "texts": ["large model document"],
            "model": "text-embedding-3-large",
        },
    )
    conflicting_search = await developer_client.post(
        "/v1/rag/search",
        json={"query": "document", "model": "text-embedding-3-large"},
    )

    assert created.status_code == 200
    assert conflicting_ingest.status_code == 409
    assert conflicting_search.status_code == 409


@pytest.mark.asyncio
async def test_existing_index_rejects_embedding_backend_availability_switch(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    created = await developer_client.post(
        "/v1/rag/ingest",
        json={"texts": ["local-only document"], "ids": ["local-doc"]},
    )
    assert created.status_code == 200

    class FakeEmbeddings:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[str]]] = []

        async def create(self, *, model: str, input: list[str]):
            self.calls.append((model, list(input)))
            assert model == "text-embedding-3-small"
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=index, embedding=[0.25] * 1536)
                    for index, _text in enumerate(input)
                ],
                usage=SimpleNamespace(total_tokens=len(input)),
            )

    fake_embeddings = FakeEmbeddings()
    monkeypatch.setattr(
        rag_routes,
        "get_client",
        lambda: SimpleNamespace(embeddings=fake_embeddings),
    )
    conflicting_search = await developer_client.post(
        "/v1/rag/search",
        json={"query": "local document"},
    )
    conflicting_ingest = await developer_client.post(
        "/v1/rag/ingest",
        json={"texts": ["must not mix"], "ids": ["openai-doc"]},
    )

    assert conflicting_search.status_code == 409
    assert conflicting_ingest.status_code == 409
    assert fake_embeddings.calls == []
    detail = conflicting_search.json()["detail"]
    assert "local_hash" in detail
    assert "openai" in detail
    assert "new collection" in detail

    monkeypatch.setattr(rag_routes, "get_client", lambda: None)
    original_space = await developer_client.post(
        "/v1/rag/search",
        json={"query": "local document"},
    )
    assert original_space.status_code == 200
    assert [result["text"] for result in original_space.json()] == ["local-only document"]


@pytest.mark.asyncio
async def test_admin_can_ingest_with_existing_admin_semantics(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    await _set_roles(db_session, test_user, "ADMIN")

    response = await client.post("/v1/rag/ingest", json={"texts": ["admin document"]})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_request_schema_and_error_responses_publish_hard_limits(
    developer_client: AsyncClient,
):
    batch_schema = rag_routes.BatchEmbedRequest.model_json_schema()
    search_schema = rag_routes.SearchRequest.model_json_schema()
    ingest_schema = rag_routes.IngestRequest.model_json_schema()

    assert batch_schema["properties"]["texts"]["maxItems"] == rag_routes.MAX_BATCH_TEXTS
    assert batch_schema["properties"]["texts"]["items"]["maxLength"] == (
        rag_routes.MAX_EMBED_TEXT_LENGTH
    )
    assert search_schema["properties"]["top_k"] == {
        "default": 5,
        "maximum": rag_routes.MAX_SEARCH_TOP_K,
        "minimum": 1,
        "title": "Top K",
        "type": "integer",
    }
    assert ingest_schema["properties"]["texts"]["maxItems"] == (rag_routes.MAX_INGEST_DOCUMENTS)
    metadata_schema = ingest_schema["properties"]["metadatas"]
    assert metadata_schema["x-mutx-max-depth"] == rag_routes.MAX_METADATA_DEPTH
    assert metadata_schema["x-mutx-max-bytes-per-document"] == rag_routes.MAX_METADATA_BYTES
    assert metadata_schema["x-mutx-max-total-bytes"] == rag_routes.MAX_TOTAL_METADATA_BYTES

    openapi = developer_client.app.openapi()
    for path in ("/v1/rag/embed", "/v1/rag/embed/batch", "/v1/rag/search", "/v1/rag/ingest"):
        assert "400" in openapi["paths"][path]["post"]["responses"]
    for path in ("/v1/rag/search", "/v1/rag/ingest"):
        assert "409" in openapi["paths"][path]["post"]["responses"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/v1/rag/ingest",
            {"texts": ["x"] * (rag_routes.MAX_INGEST_DOCUMENTS + 1)},
        ),
        (
            "/v1/rag/ingest",
            {"texts": ["x" * rag_routes.MAX_EMBED_TEXT_LENGTH] * 4 + ["x"]},
        ),
        (
            "/v1/rag/ingest",
            {
                "texts": [
                    "😀" * rag_routes.MAX_EMBED_TEXT_LENGTH,
                    "😀" * rag_routes.MAX_EMBED_TEXT_LENGTH,
                    "😀" * 385,
                ]
            },
        ),
        (
            "/v1/rag/ingest",
            {
                "texts": ["safe"],
                "metadatas": [{"a": {"b": {"c": {"d": {"e": "too deep"}}}}}],
            },
        ),
        (
            "/v1/rag/ingest",
            {
                "texts": ["safe"],
                "metadatas": [{"value": "x" * rag_routes.MAX_METADATA_BYTES}],
            },
        ),
        (
            "/v1/rag/ingest",
            {
                "texts": ["safe"] * 9,
                "metadatas": [{"value": "x" * 7_500}] * 9,
            },
        ),
        (
            "/v1/rag/ingest",
            {
                "texts": ["safe"],
                "ids": ["x" * (rag_routes.MAX_DOCUMENT_ID_LENGTH + 1)],
            },
        ),
        (
            "/v1/rag/ingest",
            {
                "texts": ["safe"],
                "collection_name": "x" * (rag_routes.MAX_COLLECTION_NAME_LENGTH + 1),
            },
        ),
        (
            "/v1/rag/search",
            {"query": "safe", "top_k": rag_routes.MAX_SEARCH_TOP_K + 1},
        ),
        (
            "/v1/rag/search",
            {"query": "x" * (rag_routes.MAX_SEARCH_QUERY_LENGTH + 1)},
        ),
    ],
    ids=[
        "ingest-count",
        "aggregate-characters",
        "aggregate-utf8-bytes",
        "metadata-depth",
        "metadata-size",
        "metadata-aggregate-size",
        "document-id",
        "collection-name",
        "top-k",
        "query",
    ],
)
async def test_adversarial_requests_are_rejected_without_provider_calls(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict[str, object],
):
    provider = _install_recording_provider(monkeypatch)

    response = await developer_client.post(path, json=payload)

    assert response.status_code == 422
    assert provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/v1/rag/embed", {"text": "safe", "model": "unsupported"}),
        ("/v1/rag/embed/batch", {"texts": ["safe"], "model": "unsupported"}),
        ("/v1/rag/search", {"query": "safe", "model": "unsupported"}),
        ("/v1/rag/ingest", {"texts": ["safe"], "model": "unsupported"}),
    ],
    ids=["embed", "batch", "search", "ingest"],
)
async def test_unsupported_models_return_declared_400_without_provider_calls(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict[str, object],
):
    provider = _install_recording_provider(monkeypatch)

    response = await developer_client.post(path, json=payload)

    assert response.status_code == 400
    assert provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("quota_name", "quota_value", "first_payload", "rejected_payload"),
    [
        (
            "MAX_TENANT_COLLECTIONS",
            1,
            {"collection_name": "first", "texts": ["first"], "ids": ["first"]},
            {"collection_name": "second", "texts": ["second"], "ids": ["second"]},
        ),
        (
            "MAX_TENANT_DOCUMENTS",
            1,
            {"texts": ["first"], "ids": ["first"]},
            {"texts": ["second"], "ids": ["second"]},
        ),
        (
            "MAX_TENANT_STORAGE_BYTES",
            13_000,
            {"texts": ["first"], "ids": ["first"]},
            {"texts": ["second"], "ids": ["second"]},
        ),
    ],
    ids=["collection", "document", "logical-storage"],
)
async def test_tenant_quota_rejections_make_zero_additional_provider_calls(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    quota_name: str,
    quota_value: int,
    first_payload: dict[str, object],
    rejected_payload: dict[str, object],
):
    monkeypatch.setattr(rag_routes, quota_name, quota_value)
    provider = _install_recording_provider(monkeypatch)

    first = await developer_client.post("/v1/rag/ingest", json=first_payload)
    rejected = await developer_client.post("/v1/rag/ingest", json=rejected_payload)

    assert first.status_code == 200
    assert rejected.status_code == 409
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_tenant_document_quota_does_not_consume_another_tenants_capacity(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    await _set_roles(db_session, test_user, "DEVELOPER")
    await _set_roles(db_session, other_user, "DEVELOPER")
    monkeypatch.setattr(rag_routes, "MAX_TENANT_DOCUMENTS", 1)
    provider = _install_recording_provider(monkeypatch)

    first = await client.post(
        "/v1/rag/ingest",
        json={"texts": ["first tenant"], "ids": ["shared-id"]},
    )
    second = await other_user_client.post(
        "/v1/rag/ingest",
        json={"texts": ["second tenant"], "ids": ["shared-id"]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_search_refuses_to_load_or_embed_an_unbounded_collection(
    developer_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _install_recording_provider(monkeypatch)
    ingested = await developer_client.post(
        "/v1/rag/ingest",
        json={
            "texts": ["first", "second", "third"],
            "ids": ["first", "second", "third"],
        },
    )
    assert ingested.status_code == 200

    provider.calls.clear()
    monkeypatch.setattr(rag_routes, "MAX_SEARCH_SCAN_DOCUMENTS", 2)
    search = await developer_client.post("/v1/rag/search", json={"query": "bounded"})

    assert search.status_code == 409
    assert "at most 2" in search.json()["detail"]
    assert provider.calls == []
