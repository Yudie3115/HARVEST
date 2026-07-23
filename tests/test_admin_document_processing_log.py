"""Tests for processing outcomes exposed in the admin document list."""
from unittest.mock import MagicMock

import pytest

from src.api.routes.admin import _document_processing_log
from src.storage.models import DocumentStatus


@pytest.mark.parametrize(
    ("status", "level", "summary_fragment"),
    [
        (DocumentStatus.DISCOVERED, "default", "waiting"),
        (DocumentStatus.QUEUED, "info", "queued"),
        (DocumentStatus.PROCESSING, "info", "in progress"),
        (DocumentStatus.PROCESSED, "success", "successfully"),
        (DocumentStatus.SKIPPED, "warning", "skipped"),
        (DocumentStatus.FAILED, "error", "failed"),
    ],
)
def test_processing_log_explains_each_status(status, level, summary_fragment):
    document = MagicMock(status=status, error_log=None)

    result = _document_processing_log(document)

    assert result["level"] == level
    assert summary_fragment in result["summary"]


@pytest.mark.parametrize("status", [DocumentStatus.SKIPPED, DocumentStatus.FAILED])
def test_negative_processing_log_includes_stored_detail(status):
    document = MagicMock(status=status, error_log="No extractable content")

    result = _document_processing_log(document)

    assert result["details"] == "No extractable content"


def test_processed_log_hides_stale_failure_detail():
    document = MagicMock(
        status=DocumentStatus.PROCESSED,
        error_log="Old failure from before a successful retry",
    )

    result = _document_processing_log(document)

    assert result["details"] is None
