"""
Unit tests for storage clients (mocked – no live services required)
"""
import sys
from types import SimpleNamespace
import pytest
from unittest.mock import MagicMock, patch, call
from uuid import uuid4


# ---------------------------------------------------------------------------
# Hashing utility (used in storage tests)
# ---------------------------------------------------------------------------

class TestHashingIntegration:
    def test_hash_content_used_for_dedup(self):
        """Verify hash_content produces consistent results for dedup use case"""
        from src.utils.hashing import hash_content
        url = "https://naro.go.ug/publication.pdf"
        h1 = hash_content(url)
        h2 = hash_content(url)
        assert h1 == h2
        assert len(h1) == 64


# ---------------------------------------------------------------------------
# VectorDBClient
# ---------------------------------------------------------------------------

class TestVectorDBClient:
    def _make_client(self, mock_qdrant):
        with patch("src.storage.vector_db.settings") as s:
            s.vector_db_provider = "qdrant"
            s.qdrant_url = "http://localhost:6333"
            s.qdrant_api_key = ""
            s.qdrant_collection = "test_collection"
            s.embedding_dimension = 1536
            with patch("qdrant_client.QdrantClient", return_value=mock_qdrant):
                from src.storage.vector_db import VectorDBClient
                return VectorDBClient()

    def test_ensure_collection_creates_new(self):
        mock_qdrant = MagicMock()
        # Simulate collection not existing
        mock_qdrant.get_collections.return_value = MagicMock(collections=[])
        client = self._make_client(mock_qdrant)
        client.ensure_collection()
        mock_qdrant.create_collection.assert_called_once()

    def test_ensure_collection_skips_existing(self):
        mock_qdrant = MagicMock()
        existing_col = MagicMock()
        existing_col.name = "test_collection"
        mock_qdrant.get_collections.return_value = MagicMock(
            collections=[existing_col]
        )
        client = self._make_client(mock_qdrant)
        client.ensure_collection()
        mock_qdrant.create_collection.assert_not_called()

    def test_upsert_chunks_calls_qdrant(self):
        mock_qdrant = MagicMock()
        client = self._make_client(mock_qdrant)

        ids = [str(uuid4()), str(uuid4())]
        vectors = [[0.1] * 1536, [0.2] * 1536]
        payloads = [{"text": "chunk 1"}, {"text": "chunk 2"}]

        client.upsert_chunks(ids, vectors, payloads)
        mock_qdrant.upsert.assert_called_once()

    def test_upsert_chunks_mismatched_lengths(self):
        mock_qdrant = MagicMock()
        client = self._make_client(mock_qdrant)
        with pytest.raises(ValueError, match="equal length"):
            client.upsert_chunks(["id1"], [[0.1] * 1536], [])

    def test_search_returns_results(self):
        mock_qdrant = MagicMock()
        mock_hit = MagicMock()
        mock_hit.id = "abc123"
        mock_hit.score = 0.92
        mock_hit.payload = {"text": "storage guide", "topics": ["storage"]}
        # qdrant-client >= 1.7 uses query_points() which returns QueryResponse with .points
        mock_qdrant.query_points.return_value = MagicMock(points=[mock_hit])

        client = self._make_client(mock_qdrant)
        results = client.search(query_vector=[0.1] * 1536, top_k=5)

        assert len(results) == 1
        assert results[0]["score"] == 0.92
        assert results[0]["payload"]["text"] == "storage guide"

    def test_delete_by_document_calls_qdrant(self):
        mock_qdrant = MagicMock()
        client = self._make_client(mock_qdrant)
        doc_id = str(uuid4())
        client.delete_by_document(doc_id)
        mock_qdrant.delete.assert_called_once()

    def test_get_collection_info(self):
        mock_qdrant = MagicMock()
        mock_info = MagicMock()
        mock_info.vectors_count = 1000
        mock_info.points_count = 1000
        mock_info.status = "green"
        mock_qdrant.get_collection.return_value = mock_info

        client = self._make_client(mock_qdrant)
        info = client.get_collection_info()

        assert info["vectors_count"] == 1000
        assert "status" in info

    def test_check_connection_success(self):
        mock_qdrant = MagicMock()
        mock_qdrant.get_collections.return_value = MagicMock(collections=[])
        client = self._make_client(mock_qdrant)
        assert client.check_connection() is True

    def test_check_connection_failure(self):
        mock_qdrant = MagicMock()
        mock_qdrant.get_collections.side_effect = Exception("connection refused")
        client = self._make_client(mock_qdrant)
        assert client.check_connection() is False


class TestChromaVectorDBClient:
    def _make_client(self, mock_chroma):
        fake_chromadb = SimpleNamespace(
            PersistentClient=MagicMock(return_value=mock_chroma)
        )
        fake_chromadb_config = SimpleNamespace(
            Settings=lambda **kwargs: SimpleNamespace(**kwargs)
        )
        with patch.dict(
            sys.modules,
            {"chromadb": fake_chromadb, "chromadb.config": fake_chromadb_config},
        ):
            with patch("src.storage.vector_db.settings") as s:
                s.vector_db_provider = "chroma"
                s.chroma_path = "./data/test-chroma"
                s.chroma_collection = "test_collection"
                s.embedding_dimension = 1536
                from src.storage.vector_db import VectorDBClient

                return VectorDBClient()

    def test_ensure_collection_creates_or_gets_collection(self):
        mock_chroma = MagicMock()
        mock_collection = MagicMock()
        mock_chroma.get_or_create_collection.return_value = mock_collection

        client = self._make_client(mock_chroma)
        client.ensure_collection()

        mock_chroma.get_or_create_collection.assert_called_once()

    def test_upsert_chunks_normalizes_metadata(self):
        mock_chroma = MagicMock()
        mock_collection = MagicMock()
        mock_chroma.get_or_create_collection.return_value = mock_collection
        client = self._make_client(mock_chroma)

        chunk_id = str(uuid4())
        client.upsert_chunks(
            [chunk_id],
            [[0.1] * 1536],
            [{
                "text": "chunk 1",
                "topics": ["storage"],
                "crops": ["maize"],
                "regions": ["Uganda"],
                "source_url": "https://example.com",
            }],
        )

        mock_collection.upsert.assert_called_once()
        kwargs = mock_collection.upsert.call_args.kwargs
        assert kwargs["ids"] == [chunk_id]
        assert kwargs["documents"] == ["chunk 1"]
        assert kwargs["metadatas"][0]["topics"] == '["storage"]'

    def test_search_returns_qdrant_compatible_results(self):
        mock_chroma = MagicMock()
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [["abc123"]],
            "distances": [[0.08]],
            "documents": [["storage guide"]],
            "metadatas": [[
                {
                    "text": "storage guide",
                    "topics": '["storage"]',
                    "source_url": "https://example.com",
                }
            ]],
        }
        mock_chroma.get_or_create_collection.return_value = mock_collection

        client = self._make_client(mock_chroma)
        results = client.search(query_vector=[0.1] * 1536, top_k=5)

        assert len(results) == 1
        assert results[0]["id"] == "abc123"
        assert results[0]["score"] == pytest.approx(0.92)
        assert results[0]["payload"]["topics"] == ["storage"]
        assert results[0]["payload"]["text"] == "storage guide"

    def test_search_applies_score_threshold(self):
        mock_chroma = MagicMock()
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [["abc123"]],
            "distances": [[0.6]],
            "documents": [["storage guide"]],
            "metadatas": [[{"text": "storage guide"}]],
        }
        mock_chroma.get_or_create_collection.return_value = mock_collection

        client = self._make_client(mock_chroma)
        results = client.search(
            query_vector=[0.1] * 1536,
            top_k=5,
            score_threshold=0.5,
        )

        assert results == []

    def test_delete_by_document_calls_chroma(self):
        mock_chroma = MagicMock()
        mock_collection = MagicMock()
        mock_chroma.get_or_create_collection.return_value = mock_collection

        client = self._make_client(mock_chroma)
        doc_id = str(uuid4())
        client.delete_by_document(doc_id)

        mock_collection.delete.assert_called_once_with(where={"document_id": doc_id})


# ---------------------------------------------------------------------------
# PostgresClient (lightweight method-level tests)
# ---------------------------------------------------------------------------

class TestPostgresClient:
    def _make_client(self):
        with patch("src.storage.postgres.create_engine") as mock_engine:
            with patch("src.storage.postgres.sessionmaker") as mock_session:
                with patch("src.storage.postgres.settings") as s:
                    s.database_url = "postgresql://test:test@localhost/test"
                    s.database_pool_size = 5
                    s.database_max_overflow = 0
                    from src.storage.postgres import PostgresClient
                    return PostgresClient()

    def test_get_crawl_stats_returns_dict(self):
        client = self._make_client()
        # Mock the session query
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.count.return_value = 0
        mock_session.query.return_value.filter.return_value.count.return_value = 0
        client.SessionLocal = MagicMock(return_value=mock_session)

        stats = client.get_crawl_stats()
        assert "total_documents" in stats
        assert "processed_documents" in stats
        assert "processing_rate" in stats
