"""RAG and Vector endpoints for embeddings and similarity search."""

import json
import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import require_roles
from src.api.config import get_settings
from src.api.database import get_db
from src.api.integrations.local_embeddings import LocalHashEmbeddings
from src.api.models import User
from src.api.models.numeric import DegradedNumericResponseModel
from src.api.services.rag_store import (
    RagDocumentConflictError,
    RagIndexModelConflictError,
    RagQuotaExceededError,
    RagSearchScanLimitError,
    RagStore,
)
from src.api.services.usage import track_usage_best_effort

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])
settings = get_settings()
MAX_EMBED_TEXT_LENGTH = 8000
MAX_BATCH_TEXTS = 32
MAX_BATCH_TOTAL_LENGTH = 32000
MAX_SEARCH_QUERY_LENGTH = 4000
MAX_SEARCH_TOP_K = 20
MAX_INGEST_DOCUMENTS = 100
MAX_AGGREGATE_INPUT_BYTES = 64 * 1024
MAX_COLLECTION_NAME_LENGTH = 255
MAX_DOCUMENT_ID_LENGTH = 255
MAX_MODEL_NAME_LENGTH = 120
MAX_METADATA_DEPTH = 4
MAX_METADATA_BYTES = 8 * 1024
MAX_TOTAL_METADATA_BYTES = 64 * 1024
MAX_TENANT_COLLECTIONS = 64
MAX_TENANT_DOCUMENTS = 10_000
MAX_TENANT_STORAGE_BYTES = 256 * 1024 * 1024
MAX_SEARCH_SCAN_DOCUMENTS = 2_000

EmbeddingText = Annotated[str, Field(min_length=1, max_length=MAX_EMBED_TEXT_LENGTH)]
SearchQuery = Annotated[str, Field(min_length=1, max_length=MAX_SEARCH_QUERY_LENGTH)]
CollectionName = Annotated[str, Field(min_length=1, max_length=MAX_COLLECTION_NAME_LENGTH)]
ModelName = Annotated[str, Field(min_length=1, max_length=MAX_MODEL_NAME_LENGTH)]
DocumentId = Annotated[str, Field(min_length=1, max_length=MAX_DOCUMENT_ID_LENGTH)]

BAD_REQUEST_RESPONSE = {
    400: {"description": "The requested embedding model or semantic input is invalid."}
}
CONFLICT_RESPONSE = {
    409: {
        "description": (
            "The collection embedding configuration conflicts, a document ID exists, "
            "a tenant quota would be exceeded, or bounded search capacity was reached."
        )
    }
}

# Direct and batch embedding generation use the API-wide per-principal rate limiter.
# These hard per-request ceilings are the cost-control boundary; usage events below
# are best-effort telemetry, not a spend quota.


class EmbedRequest(BaseModel):
    """Request model for embedding generation."""

    model_config = ConfigDict(extra="forbid")

    text: EmbeddingText
    model: ModelName = "text-embedding-3-small"

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty")
        return value


class EmbedResponse(DegradedNumericResponseModel):
    """Response model for embedding generation."""

    embedding: list[float | None]
    model: str
    tokens: int


# Supported embedding models and their dimensions
EMBEDDING_MODELS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def get_client():
    """Get OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set - falling back to local deterministic embeddings")
        return None
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key)


def get_local_embedding_backend(model: str) -> LocalHashEmbeddings:
    return LocalHashEmbeddings(dimensions=EMBEDDING_MODELS[model])


def require_enabled_rag_api() -> None:
    if not settings.enable_rag_api:
        raise HTTPException(status_code=404, detail="RAG API is disabled")


def _resolve_embedding_target(model: str) -> tuple[Any | None, str, int]:
    client = get_client()
    backend = "openai" if client is not None else "local_hash"
    return client, backend, EMBEDDING_MODELS[model]


async def _embed_texts(
    texts: list[str],
    model: str,
    *,
    client: Any | None,
    backend: str,
) -> tuple[list[list[float]], int, str]:
    if client is None:
        embeddings = get_local_embedding_backend(model).embed_documents(texts)
        return embeddings, sum(len(text.split()) for text in texts), backend

    response = await client.embeddings.create(model=model, input=texts)
    sorted_data = sorted(response.data, key=lambda item: item.index)
    usage = getattr(response, "usage", None)
    total_tokens = int(
        getattr(usage, "total_tokens", None)
        or getattr(usage, "tokens", None)
        or sum(len(text.split()) for text in texts)
    )
    return [item.embedding for item in sorted_data], total_tokens, backend


def _validate_embedding_model(model: str) -> None:
    if model not in EMBEDDING_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model. Supported: {list(EMBEDDING_MODELS.keys())}",
        )


def _validate_aggregate_input(texts: list[str]) -> None:
    total_length = sum(len(text) for text in texts)
    if total_length > MAX_BATCH_TOTAL_LENGTH:
        raise ValueError(
            f"embedding input exceeds maximum aggregate length of "
            f"{MAX_BATCH_TOTAL_LENGTH} characters"
        )
    total_bytes = sum(len(text.encode("utf-8")) for text in texts)
    if total_bytes > MAX_AGGREGATE_INPUT_BYTES:
        raise ValueError(
            f"embedding input exceeds maximum aggregate size of "
            f"{MAX_AGGREGATE_INPUT_BYTES} UTF-8 bytes"
        )


def _validate_metadata_object(metadata: dict[str, JsonValue], index: int) -> None:
    depth = _json_container_depth(metadata)
    if depth > MAX_METADATA_DEPTH:
        raise ValueError(
            f"metadatas[{index}] exceeds maximum nesting depth of {MAX_METADATA_DEPTH}"
        )
    byte_size = len(_canonical_json_bytes(metadata))
    if byte_size > MAX_METADATA_BYTES:
        raise ValueError(f"metadatas[{index}] exceeds maximum size of {MAX_METADATA_BYTES} bytes")


def _json_container_depth(value: JsonValue) -> int:
    if isinstance(value, dict):
        return 1 + max((_json_container_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_json_container_depth(item) for item in value), default=0)
    return 0


def _canonical_json_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@router.post("/embed", response_model=EmbedResponse, responses=BAD_REQUEST_RESPONSE)
async def generate_embedding(
    request: EmbedRequest,
    current_user: User = Depends(require_roles("DEVELOPER")),
) -> EmbedResponse:
    """
    Generate embeddings for text input using OpenAI's embedding models.

    Supports text-embedding-3-small, text-embedding-3-large, and text-embedding-ada-002.
    """
    require_enabled_rag_api()
    _validate_embedding_model(request.model)
    client, backend, _dimensions = _resolve_embedding_target(request.model)

    logger.info(
        "RAG embedding request accepted",
        extra={
            "user_id": str(current_user.id),
            "model": request.model,
            "text_length": len(request.text),
        },
    )

    try:
        embeddings, total_tokens, mode = await _embed_texts(
            [request.text],
            request.model,
            client=client,
            backend=backend,
        )
        await track_usage_best_effort(
            user_id=current_user.id,
            event_type="rag.embed",
            resource_type="rag",
            resource_id=request.model,
            metadata={
                "text_length": len(request.text),
                "tokens": total_tokens,
                "mode": mode,
            },
        )
        return EmbedResponse(
            embedding=embeddings[0],
            model=request.model,
            tokens=total_tokens,
        )
    except Exception as exc:
        logger.exception("Embedding generation failed")
        raise HTTPException(status_code=500, detail="Embedding generation failed") from exc


class BatchEmbedRequest(BaseModel):
    """Request model for batch embedding generation."""

    model_config = ConfigDict(extra="forbid")

    texts: list[EmbeddingText] = Field(min_length=1, max_length=MAX_BATCH_TEXTS)
    model: ModelName = "text-embedding-3-small"

    @field_validator("texts", mode="before")
    @classmethod
    def validate_texts(cls, values: Any) -> Any:
        if not isinstance(values, list):
            return values
        for index, value in enumerate(values):
            if not isinstance(value, str):
                raise ValueError("texts must contain only strings")
            if not value.strip():
                raise ValueError(f"texts[{index}] must not be empty")
            if len(value) > MAX_EMBED_TEXT_LENGTH:
                raise ValueError(
                    f"texts[{index}] exceeds maximum length of {MAX_EMBED_TEXT_LENGTH} characters"
                )
        _validate_aggregate_input(values)
        return values


class BatchEmbedResponse(DegradedNumericResponseModel):
    """Response model for batch embedding generation."""

    embeddings: list[list[float | None]]
    model: str
    total_tokens: int


@router.post("/embed/batch", response_model=BatchEmbedResponse, responses=BAD_REQUEST_RESPONSE)
async def generate_batch_embeddings(
    request: BatchEmbedRequest,
    current_user: User = Depends(require_roles("DEVELOPER")),
) -> BatchEmbedResponse:
    """
    Generate embeddings for multiple texts in a single request.
    """
    require_enabled_rag_api()
    _validate_embedding_model(request.model)
    client, backend, _dimensions = _resolve_embedding_target(request.model)
    total_length = sum(len(text) for text in request.texts)

    logger.info(
        "RAG batch embedding request accepted",
        extra={
            "user_id": str(current_user.id),
            "model": request.model,
            "batch_size": len(request.texts),
            "total_length": total_length,
        },
    )

    try:
        embeddings, total_tokens, mode = await _embed_texts(
            request.texts,
            request.model,
            client=client,
            backend=backend,
        )
        await track_usage_best_effort(
            user_id=current_user.id,
            event_type="rag.embed.batch",
            resource_type="rag",
            resource_id=request.model,
            metadata={
                "batch_size": len(request.texts),
                "total_length": total_length,
                "tokens": total_tokens,
                "mode": mode,
            },
        )

        return BatchEmbedResponse(
            embeddings=embeddings, model=request.model, total_tokens=total_tokens
        )
    except Exception as exc:
        logger.exception("Batch embedding generation failed")
        raise HTTPException(status_code=500, detail="Batch embedding generation failed") from exc


class SearchRequest(BaseModel):
    """Request model for similarity search."""

    model_config = ConfigDict(extra="forbid")

    query: SearchQuery
    top_k: int = Field(default=5, ge=1, le=MAX_SEARCH_TOP_K)
    model: ModelName = "text-embedding-3-small"
    collection_name: CollectionName = "default"

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value

    @field_validator("collection_name")
    @classmethod
    def validate_collection(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("collection_name must not be empty")
        return value


class SearchResult(DegradedNumericResponseModel):
    """Single search result."""

    text: str
    score: float | None


@router.post(
    "/search",
    response_model=list[SearchResult],
    responses={**BAD_REQUEST_RESPONSE, **CONFLICT_RESPONSE},
)
async def similarity_search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
) -> list[SearchResult]:
    """Run similarity search against an authenticated user's collection."""
    require_enabled_rag_api()
    _validate_embedding_model(request.model)
    client, backend, dimensions = _resolve_embedding_target(request.model)

    logger.info(
        "RAG similarity search requested",
        extra={
            "user_id": str(current_user.id),
            "model": request.model,
            "top_k": request.top_k,
            "query_length": len(request.query),
        },
    )

    store = RagStore(db, current_user.id)
    try:
        index = await store.preflight_search(
            collection_name=request.collection_name,
            embedding_backend=backend,
            model=request.model,
            dimensions=dimensions,
            max_scan_documents=MAX_SEARCH_SCAN_DOCUMENTS,
        )
        if index is None:
            return []
        embeddings, _, mode = await _embed_texts(
            [request.query],
            request.model,
            client=client,
            backend=backend,
        )
        results = await store.search(
            collection_name=request.collection_name,
            embedding_backend=mode,
            model=request.model,
            dimensions=dimensions,
            query_embedding=embeddings[0],
            top_k=request.top_k,
            max_scan_documents=MAX_SEARCH_SCAN_DOCUMENTS,
        )
        await track_usage_best_effort(
            user_id=current_user.id,
            event_type="rag.search",
            resource_type="rag",
            resource_id=request.model,
            metadata={"top_k": request.top_k, "query_length": len(request.query)},
        )
        return [
            SearchResult(text=result.content, score=round(result.score, 4)) for result in results
        ]

    except HTTPException:
        raise
    except (RagIndexModelConflictError, RagSearchScanLimitError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG search failed")
        raise HTTPException(status_code=500, detail="RAG search failed") from exc


@router.get("/health")
async def rag_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Health check for RAG service."""
    require_enabled_rag_api()
    api_key_present = bool(os.getenv("OPENAI_API_KEY"))

    index_count = await RagStore(db, current_user.id).count_indexes()
    store_status = f"active ({index_count} store(s))" if index_count else "not_configured"

    return {
        "status": "available",
        "feature": "embeddings, search, ingest",
        "openai_configured": api_key_present,
        "vector_store": store_status,
        "supported_models": list(EMBEDDING_MODELS.keys()),
    }


class IngestRequest(BaseModel):
    """Request model for document ingestion."""

    model_config = ConfigDict(extra="forbid")

    texts: list[EmbeddingText] = Field(min_length=1, max_length=MAX_INGEST_DOCUMENTS)
    collection_name: CollectionName = "default"
    model: ModelName = "text-embedding-3-small"
    metadatas: list[dict[str, JsonValue]] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_INGEST_DOCUMENTS,
        json_schema_extra={
            "x-mutx-max-depth": MAX_METADATA_DEPTH,
            "x-mutx-max-bytes-per-document": MAX_METADATA_BYTES,
            "x-mutx-max-total-bytes": MAX_TOTAL_METADATA_BYTES,
        },
    )
    ids: list[DocumentId] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_INGEST_DOCUMENTS,
    )

    @field_validator("texts", mode="before")
    @classmethod
    def validate_texts(cls, values: Any) -> Any:
        if not isinstance(values, list):
            return values
        for index, value in enumerate(values):
            if not isinstance(value, str):
                raise ValueError("texts must contain only strings")
            if not value.strip():
                raise ValueError(f"texts[{index}] must not be empty")
            if len(value) > MAX_EMBED_TEXT_LENGTH:
                raise ValueError(
                    f"texts[{index}] exceeds maximum length of {MAX_EMBED_TEXT_LENGTH} characters"
                )
        return values

    @field_validator("collection_name")
    @classmethod
    def validate_collection(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("collection_name must not be empty")
        return value

    @field_validator("ids", mode="before")
    @classmethod
    def validate_ids(cls, values: Any) -> Any:
        if values is None:
            return None
        if not isinstance(values, list):
            return values
        if any(not isinstance(value, str) for value in values):
            raise ValueError("document IDs must contain only strings")
        if any(len(value) > MAX_DOCUMENT_ID_LENGTH for value in values):
            raise ValueError(f"document IDs must not exceed {MAX_DOCUMENT_ID_LENGTH} characters")
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("document IDs must not be empty")
        return normalized

    @field_validator("metadatas", mode="before")
    @classmethod
    def validate_metadatas(
        cls,
        values: Any,
    ) -> Any:
        if values is None:
            return None
        if not isinstance(values, list):
            return values
        if any(not isinstance(metadata, dict) for metadata in values):
            raise ValueError("metadatas must contain only JSON objects")
        total_bytes = 0
        for index, metadata in enumerate(values):
            _validate_metadata_object(metadata, index)
            total_bytes += len(_canonical_json_bytes(metadata))
        if total_bytes > MAX_TOTAL_METADATA_BYTES:
            raise ValueError(
                f"metadata exceeds maximum aggregate size of {MAX_TOTAL_METADATA_BYTES} bytes"
            )
        return values

    @model_validator(mode="after")
    def validate_aggregate_payload(self) -> "IngestRequest":
        _validate_aggregate_input(self.texts)
        if self.metadatas is not None and len(self.metadatas) != len(self.texts):
            raise ValueError("metadatas must match texts length")
        if self.ids is not None and len(self.ids) != len(self.texts):
            raise ValueError("ids must match texts length")
        return self


class IngestResponse(BaseModel):
    """Response model for document ingestion."""

    document_ids: list[str]
    collection_name: str
    document_count: int


@router.post(
    "/ingest",
    response_model=IngestResponse,
    responses={**BAD_REQUEST_RESPONSE, **CONFLICT_RESPONSE},
)
async def ingest_documents(
    request: IngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
) -> IngestResponse:
    """Ingest documents into the named vector-store collection."""
    require_enabled_rag_api()
    total_length = sum(len(t) for t in request.texts)
    _validate_embedding_model(request.model)
    client, backend, dimensions = _resolve_embedding_target(request.model)

    logger.info(
        "RAG document ingestion requested",
        extra={
            "user_id": str(current_user.id),
            "collection": request.collection_name,
            "document_count": len(request.texts),
            "total_length": total_length,
        },
    )

    try:
        store = RagStore(db, current_user.id)
        preflight = await store.preflight_ingest(
            collection_name=request.collection_name,
            embedding_backend=backend,
            model=request.model,
            dimensions=dimensions,
            texts=request.texts,
            metadatas=request.metadatas,
            document_ids=request.ids,
            max_collections=MAX_TENANT_COLLECTIONS,
            max_documents=MAX_TENANT_DOCUMENTS,
            max_storage_bytes=MAX_TENANT_STORAGE_BYTES,
        )
        embeddings, _, mode = await _embed_texts(
            request.texts,
            request.model,
            client=client,
            backend=backend,
        )
        doc_ids = await store.ingest(
            collection_name=request.collection_name,
            embedding_backend=mode,
            model=request.model,
            dimensions=dimensions,
            texts=request.texts,
            embeddings=embeddings,
            metadatas=request.metadatas,
            document_ids=list(preflight.document_ids),
            max_collections=MAX_TENANT_COLLECTIONS,
            max_documents=MAX_TENANT_DOCUMENTS,
            max_storage_bytes=MAX_TENANT_STORAGE_BYTES,
        )

        await track_usage_best_effort(
            user_id=current_user.id,
            event_type="rag.ingest",
            resource_type="rag",
            resource_id=request.collection_name,
            metadata={
                "document_count": len(request.texts),
                "total_length": total_length,
                "collection": request.collection_name,
            },
        )

        return IngestResponse(
            document_ids=doc_ids,
            collection_name=request.collection_name,
            document_count=len(doc_ids),
        )

    except HTTPException:
        raise
    except (
        RagDocumentConflictError,
        RagIndexModelConflictError,
        RagQuotaExceededError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG ingestion failed")
        raise HTTPException(status_code=500, detail="RAG ingestion failed") from exc
