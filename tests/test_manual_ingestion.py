"""
Tests for manual document ingestion.
All external services (DB, MinIO, LLM, vector DB) are mocked.
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


# ---------------------------------------------------------------------------
# ingest_manual_document tests
# ---------------------------------------------------------------------------

FAKE_DOC_ID = str(uuid4())
FAKE_CRAWL_RUN_ID = uuid4()


def _make_fake_doc():
    doc = MagicMock()
    doc.id = UUID(FAKE_DOC_ID)
    return doc


def _make_fake_crawl_run():
    run = MagicMock()
    run.id = FAKE_CRAWL_RUN_ID
    return run


def _make_good_classification(score=7.5):
    return {
        "relevance_score": score,
        "topics": ["storage"],
        "crops": ["maize"],
        "regions": ["Uganda"],
        "document_type": "extension_guide",
        "target_audience": ["farmers"],
        "language": "en",
        "summary": "A guide to maize storage.",
        "key_practices": [],
        "actionable": True,
        "has_data": False,
        "llm_model": "gpt-4o-mini",
        "llm_metadata": {},
    }


@pytest.fixture
def ingestion_mocks():
    """Patch all external dependencies for ingest_manual_document."""
    fake_doc = _make_fake_doc()
    fake_run = _make_fake_crawl_run()

    fake_db = MagicMock()
    fake_db.get_or_create_manual_crawl_run.return_value = fake_run
    fake_db.create_document.return_value = fake_doc
    fake_db.create_classification.return_value = MagicMock()

    fake_minio = MagicMock()

    with patch("src.flows.manual_ingestion.PostgresClient", return_value=fake_db), \
         patch("src.flows.manual_ingestion.MinIOClient", return_value=fake_minio), \
         patch("src.flows.manual_ingestion.extract_content", return_value="Long extracted text about maize storage " * 20) as mock_extract, \
         patch("src.flows.manual_ingestion.classify_document_content", return_value=_make_good_classification()) as mock_classify, \
         patch("src.flows.manual_ingestion.chunk_and_embed", return_value=[{"chunk_index": 0}] * 3) as mock_chunk, \
         patch("src.flows.manual_ingestion.store_chunks", return_value=3) as mock_store, \
         patch("src.flows.manual_ingestion.download_document") as mock_download, \
         patch("src.flows.manual_ingestion.hash_content", return_value="a" * 64):
        yield {
            "db": fake_db,
            "minio": fake_minio,
            "extract": mock_extract,
            "classify": mock_classify,
            "chunk": mock_chunk,
            "store": mock_store,
            "download": mock_download,
        }


class TestIngestManualDocument:
    def test_file_bytes_produces_processed_result(self, ingestion_mocks):
        from src.flows.manual_ingestion import ingest_manual_document

        result = ingest_manual_document(
            content=b"%PDF fake content",
            filename="guide.pdf",
            title="Maize Storage Guide",
        )

        assert result["status"] == "processed"
        assert result["chunks"] == 3
        assert result["relevance_score"] == 7.5
        # MinIO upload must happen
        ingestion_mocks["minio"].upload_bytes.assert_called_once()
        # download_document must NOT be called for file uploads
        ingestion_mocks["download"].assert_not_called()

    def test_classification_written_to_document_metadata(self, ingestion_mocks):
        """The dashboard reads relevance from extra_metadata['llm_classification'],
        so manual ingestion must stash the classification there (like the crawl path)."""
        from src.flows.manual_ingestion import ingest_manual_document

        ingest_manual_document(content=b"%PDF fake", filename="guide.pdf")

        ingestion_mocks["db"].update_document_metadata.assert_called_once()
        _, meta = ingestion_mocks["db"].update_document_metadata.call_args.args
        assert meta["llm_classification"]["relevance_score"] == 7.5
        assert meta["relevance_score"] == 7.5

    def test_low_relevance_still_records_metadata(self, ingestion_mocks):
        """Even when gated out, the score should surface in the dashboard."""
        ingestion_mocks["classify"].return_value = _make_good_classification(score=2.0)
        from src.flows.manual_ingestion import ingest_manual_document

        result = ingest_manual_document(content=b"%PDF fake", filename="guide.pdf")

        assert result["status"] == "skipped"
        ingestion_mocks["db"].update_document_metadata.assert_called_once()
        _, meta = ingestion_mocks["db"].update_document_metadata.call_args.args
        assert meta["relevance_score"] == 2.0

    def test_url_ingestion_calls_download_document(self, ingestion_mocks):
        ingestion_mocks["download"].return_value = {
            "minio_path": "fakeid.pdf",
            "file_hash": "b" * 64,
            "file_size": 5000,
            "mime_type": "application/pdf",
            "doc_type": "pdf",
            "content": b"fake pdf bytes",
        }

        from src.flows.manual_ingestion import ingest_manual_document

        result = ingest_manual_document(url="https://example.org/guide.pdf")

        assert result["status"] == "processed"
        ingestion_mocks["download"].assert_called_once()
        # MinIO.upload_bytes must NOT be called — download_document handles it
        ingestion_mocks["minio"].upload_bytes.assert_not_called()

    def test_low_relevance_returns_skipped(self, ingestion_mocks):
        ingestion_mocks["classify"].return_value = _make_good_classification(score=3.0)

        from src.flows.manual_ingestion import ingest_manual_document

        result = ingest_manual_document(content=b"irrelevant bytes", filename="random.pdf")

        assert result["status"] == "skipped"
        assert result["reason"] == "low_relevance"
        assert result["relevance_score"] == 3.0
        # Classification should be stored even for skipped docs
        ingestion_mocks["db"].create_classification.assert_called_once()
        # No chunks should be stored
        ingestion_mocks["store"].assert_not_called()

    def test_no_extractable_content_returns_skipped(self, ingestion_mocks):
        ingestion_mocks["extract"].return_value = None

        from src.flows.manual_ingestion import ingest_manual_document

        result = ingest_manual_document(content=b"unreadable", filename="scan.pdf")

        assert result["status"] == "skipped"
        assert result["reason"] == "no_content"
        ingestion_mocks["classify"].assert_not_called()

    def test_missing_both_content_and_url_raises(self):
        from src.flows.manual_ingestion import ingest_manual_document

        with pytest.raises(ValueError, match="content.*url|url.*content"):
            ingest_manual_document()

    def test_content_without_filename_raises(self):
        from src.flows.manual_ingestion import ingest_manual_document

        with pytest.raises(ValueError, match="filename"):
            ingest_manual_document(content=b"bytes")

    def test_synthetic_url_used_for_file_uploads(self, ingestion_mocks):
        from src.flows.manual_ingestion import ingest_manual_document

        result = ingest_manual_document(content=b"data", filename="report.pdf")

        call_kwargs = ingestion_mocks["db"].create_document.call_args
        url_arg = call_kwargs.kwargs.get("url") or call_kwargs.args[0]
        assert url_arg.startswith("upload://")
        assert "report.pdf" in url_arg

    def test_real_url_preserved_for_url_ingestion(self, ingestion_mocks):
        ingestion_mocks["download"].return_value = {
            "minio_path": "x.html",
            "file_hash": "c" * 64,
            "file_size": 1000,
            "mime_type": "text/html",
            "doc_type": "html",
            "content": b"<html>...</html>",
        }

        from src.flows.manual_ingestion import ingest_manual_document

        ingest_manual_document(url="https://example.org/doc.html")

        call_kwargs = ingestion_mocks["db"].create_document.call_args
        url_arg = call_kwargs.kwargs.get("url") or call_kwargs.args[0]
        assert url_arg == "https://example.org/doc.html"

    def test_chunk_embed_exception_sets_failed_status(self, ingestion_mocks):
        ingestion_mocks["chunk"].side_effect = RuntimeError("Vector DB unreachable")

        from src.flows.manual_ingestion import ingest_manual_document

        result = ingest_manual_document(content=b"some content", filename="guide.pdf")

        assert result["status"] == "failed"
        assert result["chunks"] == 0
        # Status must be set to FAILED (not left as PROCESSING)
        status_calls = ingestion_mocks["db"].update_document_status.call_args_list
        statuses = [call.args[1] for call in status_calls]
        from src.storage.models import DocumentStatus
        assert DocumentStatus.FAILED in statuses
        assert DocumentStatus.PROCESSED not in statuses

    def test_download_failure_returns_failed(self, ingestion_mocks):
        ingestion_mocks["download"].return_value = None

        from src.flows.manual_ingestion import ingest_manual_document

        result = ingest_manual_document(url="https://example.org/doc.pdf")

        assert result["status"] == "failed"
        assert result["chunks"] == 0
        ingestion_mocks["extract"].assert_not_called()


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestCLI:
    def _run(self, argv: list, mock_ingest_result: dict):
        with patch("src.flows.manual_ingestion.ingest_manual_document",
                   return_value=mock_ingest_result) as mock_fn:
            from scripts.ingest_document import main
            exit_code = main(argv)
        return exit_code, mock_fn

    def test_file_flag_reads_file_and_calls_ingest(self, tmp_path):
        pdf = tmp_path / "guide.pdf"
        pdf.write_bytes(b"%PDF fake")

        exit_code, mock_fn = self._run(
            ["--file", str(pdf)],
            {"status": "processed", "document_id": str(uuid4()),
             "url": "upload://x/guide.pdf", "chunks": 4, "relevance_score": 8.0},
        )

        assert exit_code == 0
        mock_fn.assert_called_once()
        call_kw = mock_fn.call_args.kwargs
        assert call_kw["content"] == b"%PDF fake"
        assert call_kw["filename"] == "guide.pdf"

    def test_url_flag_calls_ingest_with_url(self):
        exit_code, mock_fn = self._run(
            ["--url", "https://example.org/doc.pdf"],
            {"status": "processed", "document_id": str(uuid4()),
             "url": "https://example.org/doc.pdf", "chunks": 2, "relevance_score": 7.0},
        )

        assert exit_code == 0
        mock_fn.assert_called_once()
        assert mock_fn.call_args.kwargs["url"] == "https://example.org/doc.pdf"

    def test_skipped_low_relevance_exits_nonzero(self):
        exit_code, _ = self._run(
            ["--url", "https://example.org/doc.html"],
            {"status": "skipped", "reason": "low_relevance", "relevance_score": 2.0,
             "document_id": str(uuid4()), "url": "https://example.org/doc.html", "chunks": 0},
        )
        assert exit_code == 1

    def test_no_args_prints_usage_and_exits(self, capsys):
        with pytest.raises(SystemExit):
            from scripts.ingest_document import main
            main([])

    def test_title_and_site_forwarded(self, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"data")

        _, mock_fn = self._run(
            ["--file", str(pdf), "--title", "My Guide", "--site", "fao"],
            {"status": "processed", "document_id": str(uuid4()),
             "url": "upload://x/x.pdf", "chunks": 1, "relevance_score": 7.5},
        )

        kw = mock_fn.call_args.kwargs
        assert kw["title"] == "My Guide"
        assert kw["site_name"] == "fao"

    def test_nonexistent_file_exits_nonzero(self):
        exit_code, mock_fn = self._run(
            ["--file", "/tmp/does_not_exist_abc123.pdf"],
            {},  # ingest_manual_document should not be called
        )
        assert exit_code == 1
        mock_fn.assert_not_called()

    # --- Directory ingestion --------------------------------------------------

    def _processed(self):
        return {"status": "processed", "document_id": str(uuid4()),
                "url": "upload://x/f", "chunks": 3, "relevance_score": 8.0}

    def test_dir_ingests_each_matching_file_and_ignores_others(self, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"a")
        (tmp_path / "b.docx").write_bytes(b"b")
        (tmp_path / "notes.txt").write_bytes(b"skip me")  # non-matching
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.pdf").write_bytes(b"deep")  # ignored (non-recursive)

        exit_code, mock_fn = self._run(["--dir", str(tmp_path)], self._processed())

        assert exit_code == 0
        assert mock_fn.call_count == 2
        names = {c.kwargs["filename"] for c in mock_fn.call_args_list}
        assert names == {"a.pdf", "b.docx"}

    def test_dir_recursive_picks_up_nested_files(self, tmp_path):
        (tmp_path / "top.pdf").write_bytes(b"a")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.pdf").write_bytes(b"b")

        exit_code, mock_fn = self._run(
            ["--dir", str(tmp_path), "--recursive"], self._processed()
        )

        assert exit_code == 0
        assert mock_fn.call_count == 2

    def test_dir_forwards_site_and_omits_title(self, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"a")

        _, mock_fn = self._run(["--dir", str(tmp_path), "--site", "fao"], self._processed())

        kw = mock_fn.call_args.kwargs
        assert kw["site_name"] == "fao"
        assert kw["title"] is None

    def test_dir_no_matching_files_exits_nonzero(self, tmp_path):
        (tmp_path / "notes.txt").write_bytes(b"nope")

        exit_code, mock_fn = self._run(["--dir", str(tmp_path)], self._processed())

        assert exit_code == 1
        mock_fn.assert_not_called()

    def test_dir_skipped_files_still_exit_zero(self, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"a")

        exit_code, _ = self._run(
            ["--dir", str(tmp_path)],
            {"status": "skipped", "reason": "low_relevance", "relevance_score": 2.0},
        )
        assert exit_code == 0

    def test_dir_failed_file_exits_nonzero(self, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"a")

        exit_code, _ = self._run(
            ["--dir", str(tmp_path)],
            {"status": "failed", "document_id": str(uuid4()), "chunks": 0},
        )
        assert exit_code == 1

    def test_nonexistent_dir_exits_nonzero(self):
        exit_code, mock_fn = self._run(
            ["--dir", "/tmp/does_not_exist_dir_abc123"], {}
        )
        assert exit_code == 1
        mock_fn.assert_not_called()

    def test_title_with_dir_errors(self, tmp_path):
        with pytest.raises(SystemExit):
            from scripts.ingest_document import main
            main(["--dir", str(tmp_path), "--title", "Nope"])
