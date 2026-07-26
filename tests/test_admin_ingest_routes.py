"""Tests for the protected Admin document-ingestion endpoint."""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware


def _make_client() -> TestClient:
    from src.api.routes.admin import require_admin, router

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: "admin-user"
    return TestClient(app, raise_server_exceptions=False)


def test_file_ingest_forwards_upload_metadata():
    client = _make_client()
    result = {
        "status": "processed",
        "document_id": "document-id",
        "chunks": 3,
        "relevance_score": 8.0,
    }

    with patch(
        "src.flows.manual_ingestion.ingest_manual_document",
        return_value=result,
    ) as ingest:
        response = client.post(
            "/admin/documents/ingest",
            files={"file": ("guide.pdf", b"%PDF test", "application/pdf")},
            data={"title": "Storage guide", "site_name": "naro"},
        )

    assert response.status_code == 200
    assert response.json() == result
    ingest.assert_called_once_with(
        content=b"%PDF test",
        filename="guide.pdf",
        title="Storage guide",
        site_name="naro",
    )


def test_file_ingest_rejects_oversized_upload_before_processing():
    client = _make_client()

    with (
        patch("src.api.routes.admin._MAX_DOCUMENT_UPLOAD_BYTES", 4),
        patch("src.flows.manual_ingestion.ingest_manual_document") as ingest,
    ):
        response = client.post(
            "/admin/documents/ingest",
            files={"file": ("large.pdf", b"12345", "application/pdf")},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "large.pdf exceeds the 50 MB upload limit."
    ingest.assert_not_called()


def test_ingest_requires_a_file_or_url():
    response = _make_client().post("/admin/documents/ingest")

    assert response.status_code == 400
    assert response.json()["detail"] == "Provide either a file upload or a url field."


def test_unexpected_ingest_failure_returns_readable_cors_response():
    client = _make_client()

    with patch(
        "src.flows.manual_ingestion.ingest_manual_document",
        side_effect=RuntimeError("storage unavailable"),
    ):
        response = client.post(
            "/admin/documents/ingest",
            files={"file": ("guide.pdf", b"%PDF test", "application/pdf")},
            headers={"Origin": "http://localhost:5173"},
        )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.json()["detail"] == (
        "Could not ingest guide.pdf: RuntimeError: storage unavailable"
    )
