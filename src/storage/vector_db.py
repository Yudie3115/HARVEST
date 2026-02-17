"""
Qdrant vector database client for storing and searching document embeddings
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from loguru import logger

from src.config.settings import settings


class VectorDBClient:
    """
    Qdrant vector database client.

    Collection schema
    -----------------
    Vector size : matches settings.embedding_dimension
    Distance    : Cosine

    Payload fields stored alongside each vector:
      chunk_id       – UUID of the ContentChunk row in PostgreSQL
      document_id    – UUID of the parent Document row
      text           – chunk text (for retrieval)
      topics         – list[str]
      crops          – list[str]
      regions        – list[str]
      source_url     – str
      document_type  – str
      relevance_score – float
      site_name      – str
      created_at     – ISO-8601 datetime string
    """

    def __init__(
        self,
        url: str = None,
        api_key: str = None,
        collection: str = None,
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
                "qdrant-client not installed. "
                "Install with: pip install qdrant-client"
            )

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def ensure_collection(self, recreate: bool = False) -> None:
        """
        Create the Qdrant collection if it does not already exist.

        Args:
            recreate: If True, delete and recreate the collection
        """
        from qdrant_client.models import Distance, VectorParams

        existing = [c.name for c in self.client.get_collections().collections]

        if recreate and self.collection in existing:
            self.client.delete_collection(self.collection)
            existing.remove(self.collection)
            logger.info(f"Deleted existing collection: {self.collection}")

        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                f"Created Qdrant collection: {self.collection} "
                f"(dim={self.dimension})"
            )
        else:
            logger.debug(f"Collection already exists: {self.collection}")

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunk_ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
    ) -> None:
        """
        Upsert a batch of chunk vectors into Qdrant.

        Args:
            chunk_ids: List of unique string IDs (typically UUID strings)
            vectors:   Corresponding embedding vectors
            payloads:  Corresponding metadata dicts
        """
        from qdrant_client.models import PointStruct

        if not (len(chunk_ids) == len(vectors) == len(payloads)):
            raise ValueError("chunk_ids, vectors, and payloads must have equal length")

        points = [
            PointStruct(id=cid, vector=vec, payload=pay)
            for cid, vec, pay in zip(chunk_ids, vectors, payloads)
        ]

        self.client.upsert(
            collection_name=self.collection,
            points=points,
            wait=True,
        )
        logger.debug(f"Upserted {len(points)} vectors into {self.collection}")

    def upsert_chunk(
        self,
        chunk_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """Upsert a single chunk vector"""
        self.upsert_chunks([chunk_id], [vector], [payload])

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search: find top-k most similar chunks.

        Args:
            query_vector:    Embedding of the query text
            top_k:           Number of results to return
            score_threshold: Minimum similarity score
            filters:         Optional payload filter dict, e.g.
                             {"topics": "storage"} or {"site_name": "naro"}

        Returns:
            List of result dicts with keys: id, score, payload
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        qdrant_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            qdrant_filter = Filter(must=conditions)

        # qdrant-client >= 1.7: query_points() replaces the deprecated search()
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

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_by_document(self, document_id: str) -> None:
        """
        Delete all vectors belonging to a specific document.

        Args:
            document_id: UUID string of the document
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

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
        logger.debug(f"Deleted vectors for document {document_id}")

    def delete_chunk(self, chunk_id: str) -> None:
        """Delete a single vector by chunk ID"""
        from qdrant_client.models import PointIdsList

        self.client.delete(
            collection_name=self.collection,
            points_selector=PointIdsList(points=[chunk_id]),
        )

    # ------------------------------------------------------------------
    # Stats / health
    # ------------------------------------------------------------------

    def get_collection_info(self) -> Dict[str, Any]:
        """Return collection statistics.

        Uses getattr fallbacks to handle API differences across qdrant-client versions.
        In older versions vectors_count is a top-level field; in newer versions it may
        be nested or renamed to points_count.
        """
        try:
            info = self.client.get_collection(self.collection)
            # vectors_count may be None or absent in some client versions
            vectors_count = (
                getattr(info, "vectors_count", None)
                or getattr(info, "points_count", 0)
                or 0
            )
            points_count = getattr(info, "points_count", 0) or 0
            return {
                "name": self.collection,
                "vectors_count": vectors_count,
                "points_count": points_count,
                "status": str(getattr(info, "status", "unknown")),
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}

    def check_connection(self) -> bool:
        """Verify that the Qdrant service is accessible"""
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant connection check failed: {e}")
            return False
