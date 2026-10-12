"""Tests for retrying manual uploads without losing or re-downloading their files."""
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.flows.manual_ingestion import ingest_manual_upload_flow
from src.flows.processing import download_document
from src.storage.models import DocumentStatus


def _stored_upload(file_path="doc.pdf"):
    document = MagicMock()
    document.file_path = file_path
    document.mime_type = "application/pdf"
    document.document_type = "pdf"
    return document


def test_upload_retry_reads_stored_file_instead_of_http():
    doc_id = str(uuid4())
    db = MagicMock()
    db.get_document.return_value = _stored_upload()
    minio = MagicMock()
    minio.get_object.return_value = b"%PDF bytes"

    with patch("src.flows.processing.PostgresClient", return_value=db), patch(
        "src.flows.processing.MinIOClient", return_value=minio
    ), patch("src.flows.processing.httpx.Client") as mock_http:
        result = download_document.fn(doc_id, f"upload://{uuid4()}/guide.pdf")

    mock_http.assert_not_called()
    minio.get_object.assert_called_once_with("doc.pdf")
    assert result["content"] == b"%PDF bytes"
    assert result["doc_type"] == "pdf"
    assert db.update_document_status.call_args.args[1] == DocumentStatus.QUEUED


def test_upload_retry_without_stored_file_fails_with_clear_message():
    doc_id = str(uuid4())
    db = MagicMock()
    db.get_document.return_value = _stored_upload(file_path=None)

    with patch("src.flows.processing.PostgresClient", return_value=db), patch(
        "src.flows.processing.httpx.Client"
    ) as mock_http:
        result = download_document.fn(doc_id, f"upload://{uuid4()}/guide.pdf")

    assert result is None
    mock_http.assert_not_called()
    args, kwargs = db.update_document_status.call_args
    assert args[1] == DocumentStatus.FAILED
    assert "upload it again" in kwargs["error_log"]


@pytest.mark.parametrize(
    ("status", "deleted"),
    [("processed", True), ("skipped", True), ("duplicate", True), ("failed", False)],
)
def test_staging_object_kept_only_when_ingestion_failed(status, deleted):
    minio = MagicMock()
    minio.get_object.return_value = b"bytes"

    with patch("src.flows.manual_ingestion.MinIOClient", return_value=minio), patch(
        "src.flows.manual_ingestion.ingest_manual_document", return_value={"status": status}
    ):
        ingest_manual_upload_flow.fn(staging_object="staging/x.pdf", filename="x.pdf")

    assert minio.delete_object.called is deleted


def test_staging_object_kept_when_ingestion_raises():
    minio = MagicMock()
    minio.get_object.return_value = b"bytes"

    with patch("src.flows.manual_ingestion.MinIOClient", return_value=minio), patch(
        "src.flows.manual_ingestion.ingest_manual_document", side_effect=ValueError("NUL")
    ):
        with pytest.raises(ValueError):
            ingest_manual_upload_flow.fn(staging_object="staging/x.pdf", filename="x.pdf")

    minio.delete_object.assert_not_called()
