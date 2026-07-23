"""
Vector database facade for storing and searching document embeddings.

The application uses this module through ``VectorDBClient``. The concrete
backend is selected with ``VECTOR_DB_PROVIDER`` and can be either Qdrant or
ChromaDB.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Protocol

from loguru import logger

from src.config.settings import settings


class VectorDBBackend(Protocol):
    provider: str
    collection: str
    dimension: int
    client: Any

    def ensure_collection(self, recreate: bool = False) -> None:
        ...

    def upsert_chunks(
        self,
        chunk_ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
    ) -> None:
        ...

    def upsert_chunk(
        self,
        chunk_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        ...

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        ...

    def delete_by_document(self, document_id: str) -> None:
        ...

    def delete_chunk(self, chunk_id: str) -> None:
        ...

    def delete_point(self, point_id: str) -> None:
        ...

    def get_collection_info(self) -> Dict[str, Any]:
        ...

    def check_connection(self) -> bool:
        ...


def _validate_batch_lengths(
    chunk_ids: List[str],
    vectors: List[List[float]],
    payloads: List[Dict[str, Any]],
) -> None:
    if not (len(chunk_ids) == len(vectors) == len(payloads)):
        raise ValueError("chunk_ids, vectors, and payloads must have equal length")


def _chroma_encode_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert payload values to Chroma-compatible scalar metadata."""
    metadata: Dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
        elif isinstance(value, (list, dict)):
            metadata[key] = json.dumps(value)
        else:
            metadata[key] = str(value)
    return metadata


def _chroma_decode_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Restore JSON-encoded Chroma metadata fields to normal payload values."""
    if not metadata:
        return {}

    payload: Dict[str, Any] = {}
    for key, value in metadata.items():
        if key in {"topics", "crops", "regions"} and isinstance(value, str):
            try:
                payload[key] = json.loads(value)
                continue
            except json.JSONDecodeError:
                pass
        payload[key] = value
    return payload


def _chroma_where(filters: Dict[str, Any]) -> Dict[str, Any]:
    encoded = _chroma_encode_metadata(filters)
    if len(encoded) <= 1:
        return encoded
    return {"$and": [{key: value} for key, value in encoded.items()]}


class QdrantVectorDBBackend:
    """
    Qdrant vector database backend.

    Collection schema
    -----------------
    Vector size : matches settings.embedding_dimension
    Distance    : Cosine
    """

    provider = "qdrant"

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection: str | None = None,
    ):
        self.url = url or settings.qdrant_url
        self.api_key = api_key or settings.qdrant_api_key or None
        self.collection = collection or settings.qdrant_collection
        self.dimension = settings.embedding_dimension

        try:
            from qdrant_client import QdrantClient

            self.client = QdrantClient(
                url=self.url,
                api_key=self.api_key,
            )
            logger.info(f"Initialized Qdrant client: {self.url}")
        except ImportError:
            raise ImportError(
                "qdrant-client not installed. Install with: pip install qdrant-client"
            )

    def ensure_collection(self, recreate: bool = False) -> None:
        """Create the Qdrant collection if it does not already exist."""
        from qdrant_client.models import Distance, VectorParams

        existing = [c.name for c in self.client.get_collections().collections]

        if recreate and self.collection in existing:
            self.client.delete_collection(self.collection)
            existing.remove(self.collection)
            logger.info(f"Deleted existing Qdrant collection: {self.collection}")

        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                f"Created Qdrant collection: {self.collection} (dim={self.dimension})"
            )
        else:
            logger.debug(f"Qdrant collection already exists: {self.collection}")

    def upsert_chunks(
        self,
        chunk_ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
    ) -> None:
        """Upsert a batch of chunk vectors into Qdrant."""
        from qdrant_client.models import PointStruct

        _validate_batch_lengths(chunk_ids, vectors, payloads)

        points = [
            PointStruct(id=cid, vector=vec, payload=pay)
            for cid, vec, pay in zip(chunk_ids, vectors, payloads)
        ]

        self.client.upsert(
            collection_name=self.collection,
            points=points,
            wait=True,
        )
        logger.debug(f"Upserted {len(points)} vectors into Qdrant {self.collection}")

    def upsert_chunk(
        self,
        chunk_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """Upsert a single chunk vector."""
        self.upsert_chunks([chunk_id], [vector], [payload])

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search: find top-k most similar chunks."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        qdrant_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            qdrant_filter = Filter(must=conditions)

        response = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=top_k,
            score_threshold=score_threshold if score_threshold > 0 else None,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in response.points
        ]

    def delete_by_document(self, document_id: str) -> None:
        """Delete all vectors belonging to a specific document."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
        )
        logger.debug(f"Deleted Qdrant vectors for document {document_id}")

    def delete_chunk(self, chunk_id: str) -> None:
        """Delete a single vector by chunk ID."""
        from qdrant_client.models import PointIdsList

        self.client.delete(
            collection_name=self.collection,
            points_selector=PointIdsList(points=[chunk_id]),
        )

    def delete_point(self, point_id: str) -> None:
        """Delete a single vector by its stable point ID."""
        self.delete_chunk(point_id)

    def get_collection_info(self) -> Dict[str, Any]:
        """Return collection statistics."""
        try:
            info = self.client.get_collection(self.collection)
            vectors_count = (
                getattr(info, "vectors_count", None)
                or getattr(info, "points_count", 0)
                or 0
            )
            points_count = getattr(info, "points_count", 0) or 0
            return {
                "provider": self.provider,
                "name": self.collection,
                "vectors_count": vectors_count,
                "points_count": points_count,
                "status": str(getattr(info, "status", "unknown")),
            }
        except Exception as e:
            logger.error(f"Failed to get Qdrant collection info: {e}")
            return {}

    def check_connection(self) -> bool:
        """Verify that the Qdrant service is accessible."""
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant connection check failed: {e}")
            return False


class ChromaVectorDBBackend:
    """Persistent local ChromaDB backend."""

    provider = "chroma"

    def __init__(
        self,
        path: str | None = None,
        collection: str | None = None,
    ):
        self.path = path or settings.chroma_path
        self.collection = collection or settings.chroma_collection
        self.dimension = settings.embedding_dimension

        try:
            os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
            import chromadb
            from chromadb.config import Settings

            self.client = chromadb.PersistentClient(
                path=self.path,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = None
            logger.info(f"Initialized ChromaDB client: {self.path}")
        except ImportError:
            raise ImportError("chromadb not installed. Install with: pip install chromadb")

    def ensure_collection(self, recreate: bool = False) -> None:
        """Create the Chroma collection if it does not already exist."""
        if recreate:
            try:
                self.client.delete_collection(self.collection)
                logger.info(f"Deleted existing Chroma collection: {self.collection}")
            except Exception:
                pass

        self._collection = self.client.get_or_create_collection(
            name=self.collection,
            metadata={"hnsw:space": "cosine", "embedding_dimension": self.dimension},
        )
        logger.debug(f"Chroma collection ready: {self.collection}")

    @property
    def chroma_collection(self):
        if self._collection is None:
            self.ensure_collection()
        return self._collection

    def upsert_chunks(
        self,
        chunk_ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
    ) -> None:
        """Upsert a batch of chunk vectors into ChromaDB."""
        _validate_batch_lengths(chunk_ids, vectors, payloads)

        metadatas = [_chroma_encode_metadata(payload) for payload in payloads]
        documents = [payload.get("text", "") for payload in payloads]

        self.chroma_collection.upsert(
            ids=chunk_ids,
            embeddings=vectors,
            metadatas=metadatas,
            documents=documents,
        )
        logger.debug(f"Upserted {len(chunk_ids)} vectors into Chroma {self.collection}")

    def upsert_chunk(
        self,
        chunk_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """Upsert a single chunk vector."""
        self.upsert_chunks([chunk_id], [vector], [payload])

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search returning the same result shape as Qdrant."""
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": top_k,
            "include": ["metadatas", "documents", "distances"],
        }
        if filters:
            kwargs["where"] = _chroma_where(filters)

        response = self.chroma_collection.query(**kwargs)
        ids = response.get("ids", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        documents = response.get("documents", [[]])[0]
        distances = response.get("distances", [[]])[0]

        results: List[Dict[str, Any]] = []
        for chunk_id, metadata, document, distance in zip(
            ids, metadatas, documents, distances
        ):
            score = max(0.0, 1.0 - float(distance))
            if score_threshold > 0 and score < score_threshold:
                continue
            payload = _chroma_decode_metadata(metadata)
            payload.setdefault("text", document or "")
            results.append(
                {
                    "id": str(chunk_id),
                    "score": score,
                    "payload": payload,
                }
            )
        return results

    def delete_by_document(self, document_id: str) -> None:
        """Delete all vectors belonging to a specific document."""
        self.chroma_collection.delete(where={"document_id": document_id})
        logger.debug(f"Deleted Chroma vectors for document {document_id}")

    def delete_chunk(self, chunk_id: str) -> None:
        """Delete a single vector by chunk ID."""
        self.chroma_collection.delete(ids=[chunk_id])

    def delete_point(self, point_id: str) -> None:
        """Delete a single vector by its stable point ID."""
        self.delete_chunk(point_id)

    def get_collection_info(self) -> Dict[str, Any]:
        """Return collection statistics."""
        try:
            count = self.chroma_collection.count()
            return {
                "provider": self.provider,
                "name": self.collection,
                "vectors_count": count,
                "points_count": count,
                "status": "ok",
                "path": self.path,
            }
        except Exception as e:
            logger.error(f"Failed to get Chroma collection info: {e}")
            return {}

    def check_connection(self) -> bool:
        """Verify that the local Chroma store is usable."""
        try:
            self.ensure_collection()
            self.chroma_collection.count()
            return True
        except Exception as e:
            logger.error(f"Chroma connection check failed: {e}")
            return False


class VectorDBClient:
    """
    Provider-selecting vector database client.

    Use ``VECTOR_DB_PROVIDER=chroma`` for local persistent ChromaDB or
    ``VECTOR_DB_PROVIDER=qdrant`` for Qdrant.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection: str | None = None,
        provider: str | None = None,
        path: str | None = None,
    ):
        self.provider = (provider or settings.vector_db_provider).lower()

        if self.provider == "qdrant":
            self._backend: VectorDBBackend = QdrantVectorDBBackend(
                url=url,
                api_key=api_key,
                collection=collection,
            )
        elif self.provider == "chroma":
            self._backend = ChromaVectorDBBackend(
                path=path,
                collection=collection,
            )
        else:
            raise ValueError(
                f"Unsupported vector DB provider '{self.provider}'. "
                "Expected 'qdrant' or 'chroma'."
            )

        self.client = self._backend.client
        self.collection = self._backend.collection
        self.dimension = self._backend.dimension

    def ensure_collection(self, recreate: bool = False) -> None:
        self._backend.ensure_collection(recreate=recreate)

    def upsert_chunks(
        self,
        chunk_ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
    ) -> None:
        self._backend.upsert_chunks(chunk_ids, vectors, payloads)

    def upsert_chunk(
        self,
        chunk_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        self._backend.upsert_chunk(chunk_id, vector, payload)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return self._backend.search(
            query_vector=query_vector,
            top_k=top_k,
            score_threshold=score_threshold,
            filters=filters,
        )

    def delete_by_document(self, document_id: str) -> None:
        self._backend.delete_by_document(document_id)

    def delete_chunk(self, chunk_id: str) -> None:
        self._backend.delete_chunk(chunk_id)

    def delete_point(self, point_id: str) -> None:
        self._backend.delete_point(point_id)

    def get_collection_info(self) -> Dict[str, Any]:
        return self._backend.get_collection_info()

    def check_connection(self) -> bool:
        return self._backend.check_connection()
