"""
Tests for manual document ingestion.
All external services (DB, MinIO, LLM, Qdrant) are mocked.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from uuid import UUID, uuid4


# ---------------------------------------------------------------------------
# PostgresClient helper method tests
# ---------------------------------------------------------------------------

class TestGetOrCreateManualCrawlRun:
    def _make_db(self, session_mock):
        """Build a PostgresClient whose session is fully mocked."""
        with patch("src.storage.postgres.create_engine"), \
             patch("src.storage.postgres.sessionmaker", return_value=lambda: session_mock):
            from src.storage.postgres import PostgresClient
            db = PostgresClient.__new__(PostgresClient)
            db.SessionLocal = lambda: session_mock
            return db

    def test_returns_existing_run_when_present(self):
        existing = MagicMock()
        existing.site_name = "manual"

        session = MagicMock()
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        session.query.return_value.filter.return_value.first.return_value = existing

        db = self._make_db(session)
        result = db.get_or_create_manual_crawl_run()

        session.add.assert_not_called()
        assert result is existing

    def test_creates_new_run_when_absent(self):
        session = MagicMock()
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        session.query.return_value.filter.return_value.first.return_value = None

        db = self._make_db(session)
        result = db.get_or_create_manual_crawl_run()

        session.add.assert_called_once()
        session.commit.assert_called_once()


class TestUpdateDocumentFileInfo:
    def _make_db(self, session_mock):
        with patch("src.storage.postgres.create_engine"), \
             patch("src.storage.postgres.sessionmaker", return_value=lambda: session_mock):
            from src.storage.postgres import PostgresClient
            db = PostgresClient.__new__(PostgresClient)
            db.SessionLocal = lambda: session_mock
            return db

    def test_updates_file_fields_on_document(self):
        doc = MagicMock()
        doc_id = uuid4()

        session = MagicMock()
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        session.query.return_value.filter.return_value.first.return_value = doc

        db = self._make_db(session)
        db.update_document_file_info(
            document_id=doc_id,
            file_path="abc.pdf",
            file_hash="deadbeef" * 8,
            file_size_bytes=12345,
            mime_type="application/pdf",
        )

        assert doc.file_path == "abc.pdf"
        assert doc.file_hash == "deadbeef" * 8
        assert doc.file_size_bytes == 12345
        assert doc.mime_type == "application/pdf"
        session.commit.assert_called_once()

    def test_no_op_when_document_not_found(self):
        session = MagicMock()
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        session.query.return_value.filter.return_value.first.return_value = None

        db = self._make_db(session)
        db.update_document_file_info(
            document_id=uuid4(),
            file_path="x.pdf",
            file_hash="a" * 64,
            file_size_bytes=100,
            mime_type="application/pdf",
        )

        session.commit.assert_not_called()
