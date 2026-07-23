"""Tests for explanatory document-processing status logs."""
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.flows.processing import (
    _log_processing_status,
    process_document,
    process_documents_batch,
)


@pytest.mark.parametrize(
    ("status", "log_method"),
    [
        ("processing", "info"),
        ("processed", "info"),
        ("skipped", "warning"),
        ("failed", "error"),
    ],
)
def test_processing_status_uses_an_appropriate_log_level(status, log_method):
    with patch("src.flows.processing.logger") as mock_logger:
        _log_processing_status(
            document_id="document-123",
            url="https://example.org/guide.pdf",
            status=status,
            explanation="human-readable outcome",
        )

    getattr(mock_logger, log_method).assert_called_once()


def test_processing_status_log_contains_identity_status_and_explanation():
    with patch("src.flows.processing.logger") as mock_logger:
        _log_processing_status(
            document_id="document-123",
            url="https://example.org/guide.pdf",
            status="skipped",
            explanation="no usable text was extracted; no chunks were indexed",
        )

    message = mock_logger.warning.call_args.args[0]
    assert "status=skipped" in message
    assert "document_id=document-123" in message
    assert "url=https://example.org/guide.pdf" in message
    assert "no usable text was extracted" in message
    assert "no chunks were indexed" in message


def test_no_content_result_explains_why_document_was_skipped():
    document_id = str(uuid4())
    with (
        patch("src.flows.processing.PostgresClient"),
        patch("src.flows.processing.download_document", return_value={"content": b"raw"}),
        patch("src.flows.processing.extract_content", return_value=None),
        patch("src.flows.processing._log_processing_status") as mock_status_log,
    ):
        result = process_document.fn(
            document_id=document_id,
            url="https://example.org/image-only.pdf",
        )

    assert result["status"] == "skipped"
    assert result["reason"] == "no_extractable_content"
    assert result["url"] == "https://example.org/image-only.pdf"
    skipped_log = next(
        call for call in mock_status_log.call_args_list if call.kwargs["status"] == "skipped"
    )
    assert "no usable text" in skipped_log.kwargs["explanation"]
    assert "no chunks were indexed" in skipped_log.kwargs["explanation"]


def test_batch_log_reports_skipped_separately_from_failed():
    documents = [
        {"id": uuid4(), "url": "https://example.org/processed"},
        {"id": uuid4(), "url": "https://example.org/skipped"},
        {"id": uuid4(), "url": "https://example.org/failed"},
    ]
    results = [
        {"status": "processed"},
        {"status": "skipped"},
        {"status": "failed"},
    ]
    with (
        patch("src.flows.processing.process_document", side_effect=results),
        patch("src.flows.processing.logger") as mock_logger,
    ):
        assert process_documents_batch.fn(documents) == results

    summary = mock_logger.info.call_args_list[-1].args[0]
    assert "processed=1" in summary
    assert "skipped=1" in summary
    assert "failed=1" in summary
