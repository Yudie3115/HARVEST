"""Tests for the protected Admin reprocess-stuck-documents endpoint."""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client() -> TestClient:
    from src.api.routes.admin import require_admin, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: "admin-user"
    return TestClient(app, raise_server_exceptions=False)


def test_reprocess_stuck_resets_documents_and_schedules_processing():
    client = _make_client()
    documents = [
        {"id": "doc-1", "url": "https://example.org/a.pdf", "site_name": "naro"},
        {"id": "doc-2", "url": "https://example.org/b.pdf", "site_name": "naro"},
    ]

    with (
        patch(
            "src.flows.orchestration.reset_stuck_documents", return_value=documents
        ) as reset,
        patch("src.flows.processing.process_documents_batch") as process_batch,
    ):
        response = client.post("/admin/documents/reprocess-stuck")

    assert response.status_code == 200
    assert response.json() == {"queued": 2}
    reset.assert_called_once_with(limit=200)
    process_batch.assert_called_once_with(documents)


def test_reprocess_stuck_with_no_stuck_documents_skips_processing():
    client = _make_client()

    with (
        patch("src.flows.orchestration.reset_stuck_documents", return_value=[]),
        patch("src.flows.processing.process_documents_batch") as process_batch,
    ):
        response = client.post("/admin/documents/reprocess-stuck")

    assert response.status_code == 200
    assert response.json() == {"queued": 0}
    process_batch.assert_not_called()
