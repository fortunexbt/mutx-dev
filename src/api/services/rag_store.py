from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.models import User
from src.api.models.rag import RagDocument, RagIndex


class RagIndexModelConflictError(Exception):
    """The collection is bound to a different embedding space."""


class RagDocumentConflictError(Exception):
    """One or more caller-supplied document IDs already exist in the collection."""


class RagQuotaExceededError(Exception):
    """A tenant RAG collection, document, or logical-storage quota was exceeded."""


class RagSearchScanLimitError(Exception):
    """A collection is too large for the bounded in-process similarity scan."""


@dataclass(frozen=True)
class RagSearchMatch:
    content: str
    score: float


@dataclass(frozen=True)
class RagIngestPreflight:
    document_ids: tuple[str, ...]
    storage_bytes: tuple[int, ...]


class RagStore:
    """Async database repository whose every operation is tenant-scoped."""

    def __init__(self, db: AsyncSession, owner_id: uuid.UUID) -> None:
        self._db = db
        self._owner_id = owner_id

    async def get_index(self, name: str) -> RagIndex | None:
        return (
            await self._db.execute(
                select(RagIndex).where(
                    RagIndex.owner_id == self._owner_id,
                    RagIndex.name == name,
                )
            )
        ).scalar_one_or_none()

    async def count_indexes(self) -> int:
        result = await self._db.execute(
            select(func.count(RagIndex.id)).where(RagIndex.owner_id == self._owner_id)
        )
        return int(result.scalar_one())

    async def count_documents(self, index: RagIndex | None = None) -> int:
        statement = select(func.count(RagDocument.id)).where(RagDocument.owner_id == self._owner_id)
        if index is not None:
            statement = statement.where(RagDocument.index_id == index.id)
        result = await self._db.execute(statement)
        return int(result.scalar_one())

    async def get_storage_bytes(self) -> int:
        result = await self._db.execute(
            select(func.coalesce(func.sum(RagDocument.storage_bytes), 0)).where(
                RagDocument.owner_id == self._owner_id
            )
        )
        return int(result.scalar_one())

    async def preflight_ingest(
        self,
        *,
        collection_name: str,
        embedding_backend: str,
        model: str,
        dimensions: int,
        texts: list[str],
        metadatas: list[dict] | None,
        document_ids: list[str] | None,
        max_collections: int,
        max_documents: int,
        max_storage_bytes: int,
    ) -> RagIngestPreflight:
        """Reject deterministic conflicts and quota failures before embedding work."""
        if metadatas is not None and len(metadatas) != len(texts):
            raise ValueError("Metadata count must match the ingested documents")
        if document_ids is not None and len(document_ids) != len(texts):
            raise ValueError("Document ID count must match the ingested documents")

        resolved_ids = tuple(document_ids or [str(uuid.uuid4()) for _ in texts])
        if len(set(resolved_ids)) != len(resolved_ids):
            raise RagDocumentConflictError("Document IDs must be unique within a collection")

        index = await self.get_index(collection_name)
        if index is None:
            collection_count = await self.count_indexes()
            if collection_count >= max_collections:
                raise RagQuotaExceededError(
                    f"Tenant RAG collection quota of {max_collections} has been reached"
                )
        else:
            self._validate_embedding_space(
                index,
                embedding_backend=embedding_backend,
                model=model,
                dimensions=dimensions,
            )
            existing_ids = set(
                (
                    await self._db.execute(
                        select(RagDocument.external_id).where(
                            RagDocument.owner_id == self._owner_id,
                            RagDocument.index_id == index.id,
                            RagDocument.external_id.in_(resolved_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if existing_ids:
                raise RagDocumentConflictError(
                    "Document IDs already exist in this collection: "
                    + ", ".join(sorted(existing_ids))
                )

        document_count = await self.count_documents()
        projected_document_count = document_count + len(texts)
        if projected_document_count > max_documents:
            raise RagQuotaExceededError(
                f"Tenant RAG document quota of {max_documents} would be exceeded"
            )

        metadata_values = metadatas if metadatas is not None else [{} for _ in texts]
        incoming_storage = tuple(
            _document_storage_bytes(
                document_id=document_id,
                content=text,
                metadata=metadata,
                embedding_dimensions=dimensions,
            )
            for document_id, text, metadata in zip(
                resolved_ids,
                texts,
                metadata_values,
                strict=True,
            )
        )
        projected_storage = await self.get_storage_bytes() + sum(incoming_storage)
        if projected_storage > max_storage_bytes:
            raise RagQuotaExceededError(
                f"Tenant RAG logical-storage quota of {max_storage_bytes} bytes would be exceeded"
            )

        return RagIngestPreflight(
            document_ids=resolved_ids,
            storage_bytes=incoming_storage,
        )

    async def preflight_search(
        self,
        *,
        collection_name: str,
        embedding_backend: str,
        model: str,
        dimensions: int,
        max_scan_documents: int,
    ) -> RagIndex | None:
        """Validate collection identity and bounded-scan eligibility before embedding."""
        if max_scan_documents < 1:
            raise ValueError("max_scan_documents must be positive")
        index = await self.get_index(collection_name)
        if index is None:
            return None
        self._validate_embedding_space(
            index,
            embedding_backend=embedding_backend,
            model=model,
            dimensions=dimensions,
        )
        document_count = await self.count_documents(index)
        if document_count > max_scan_documents:
            raise RagSearchScanLimitError(
                f"Collection '{collection_name}' contains {document_count} documents; "
                f"bounded similarity search supports at most {max_scan_documents} until "
                "indexed vector search is configured"
            )
        return index

    async def ingest(
        self,
        *,
        collection_name: str,
        embedding_backend: str,
        model: str,
        dimensions: int,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None,
        document_ids: list[str] | None,
        max_collections: int,
        max_documents: int,
        max_storage_bytes: int,
    ) -> list[str]:
        if len(embeddings) != len(texts) or any(
            len(embedding) != dimensions for embedding in embeddings
        ):
            raise ValueError("Embedding count and dimensions must match the ingested documents")

        # Serialize quota enforcement for a tenant on databases that support row locks.
        await self._db.execute(select(User.id).where(User.id == self._owner_id).with_for_update())
        preflight = await self.preflight_ingest(
            collection_name=collection_name,
            embedding_backend=embedding_backend,
            model=model,
            dimensions=dimensions,
            texts=texts,
            metadatas=metadatas,
            document_ids=document_ids,
            max_collections=max_collections,
            max_documents=max_documents,
            max_storage_bytes=max_storage_bytes,
        )

        index = await self.get_index(collection_name)
        if index is None:
            index = RagIndex(
                owner_id=self._owner_id,
                name=collection_name,
                embedding_backend=embedding_backend,
                embedding_model=model,
                embedding_dimensions=dimensions,
            )
            self._db.add(index)
            try:
                await self._db.flush()
            except IntegrityError:
                await self._db.rollback()
                index = await self.get_index(collection_name)
                if index is None:
                    raise
        self._validate_embedding_space(
            index,
            embedding_backend=embedding_backend,
            model=model,
            dimensions=dimensions,
        )

        metadata_values = metadatas if metadatas is not None else [{} for _ in texts]
        for document_id, text, metadata, embedding, storage_bytes in zip(
            preflight.document_ids,
            texts,
            metadata_values,
            embeddings,
            preflight.storage_bytes,
            strict=True,
        ):
            self._db.add(
                RagDocument(
                    owner_id=self._owner_id,
                    index_id=index.id,
                    external_id=document_id,
                    content=text,
                    extra_metadata=metadata,
                    embedding=embedding,
                    storage_bytes=storage_bytes,
                )
            )

        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise RagDocumentConflictError(
                "One or more document IDs already exist in this collection"
            ) from exc
        return list(preflight.document_ids)

    async def search(
        self,
        *,
        collection_name: str,
        embedding_backend: str,
        model: str,
        dimensions: int,
        query_embedding: list[float],
        top_k: int,
        max_scan_documents: int,
    ) -> list[RagSearchMatch]:
        index = await self.preflight_search(
            collection_name=collection_name,
            embedding_backend=embedding_backend,
            model=model,
            dimensions=dimensions,
            max_scan_documents=max_scan_documents,
        )
        if index is None:
            return []
        if len(query_embedding) != dimensions:
            raise ValueError(
                "Query embedding dimensions do not match the requested embedding space"
            )

        records = (
            (
                await self._db.execute(
                    select(RagDocument)
                    .where(
                        RagDocument.owner_id == self._owner_id,
                        RagDocument.index_id == index.id,
                    )
                    .order_by(RagDocument.created_at, RagDocument.id)
                    .limit(max_scan_documents)
                )
            )
            .scalars()
            .all()
        )
        ranked = [
            RagSearchMatch(
                content=record.content,
                score=_cosine_similarity(query_embedding, record.embedding),
            )
            for record in records
        ]
        ranked.sort(key=lambda match: match.score, reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _validate_embedding_space(
        index: RagIndex,
        *,
        embedding_backend: str,
        model: str,
        dimensions: int,
    ) -> None:
        stored_identity = (
            index.embedding_backend,
            index.embedding_model,
            index.embedding_dimensions,
        )
        requested_identity = (embedding_backend, model, dimensions)
        if stored_identity == requested_identity:
            return

        raise RagIndexModelConflictError(
            f"Collection '{index.name}' is bound to embedding backend "
            f"'{index.embedding_backend}', model '{index.embedding_model}', and "
            f"{index.embedding_dimensions} dimensions; this request resolved to backend "
            f"'{embedding_backend}', model '{model}', and {dimensions} dimensions. "
            "Restore the collection's original embedding backend or ingest into a new "
            "collection and reindex its documents."
        )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(x * y for x, y in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return float(numerator / (left_norm * right_norm))


def _document_storage_bytes(
    *,
    document_id: str,
    content: str,
    metadata: dict,
    embedding_dimensions: int,
) -> int:
    """Return stable logical bytes used for tenant quota accounting."""
    metadata_bytes = json.dumps(
        metadata,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return (
        len(document_id.encode("utf-8"))
        + len(content.encode("utf-8"))
        + len(metadata_bytes)
        + (embedding_dimensions * 8)
    )
