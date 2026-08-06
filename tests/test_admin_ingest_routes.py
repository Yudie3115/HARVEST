"""Tests for the protected Admin document-ingestion endpoint.

Ingestion runs in the Prefect worker, not in the API process. The endpoint
streams the upload to a MinIO staging object, checks for duplicates, and
triggers a flow run — so these assert on staging and triggering rather than
on the pipeline itself.
"""
from unittest.mock import AsyncMock, patch

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


def test_file_ingest_stages_upload_and_triggers_flow():
    client = _make_client()

    with (
        patch(
            "src.api.routes.admin._stage_upload",
            return_value=("staging/abc.pdf", "hash-1"),
        ) as stage,
        patch("src.api.routes.admin._find_duplicate_by_hash", return_value=None),
        patch(
            "src.api.routes.admin._trigger_prefect_deployment",
            new=AsyncMock(return_value={"id": "flow-run-1"}),
        ) as trigger,
    ):
        response = client.post(
            "/admin/documents/ingest",
            files={"file": ("guide.pdf", b"%PDF test", "application/pdf")},
            data={"title": "Storage guide", "site_name": "naro"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "queued",
        "flow_run_id": "flow-run-1",
        "filename": "guide.pdf",
        "url": None,
    }
    stage.assert_called_once()

    deployment_name, parameters = trigger.await_args.args
    assert deployment_name.startswith("ingest_manual_upload/ingest-upload-")
    assert parameters == {
        "staging_object": "staging/abc.pdf",
        "filename": "guide.pdf",
        "title": "Storage guide",
        "site_name": "naro",
    }


def test_url_ingest_triggers_flow_without_staging():
    client = _make_client()

    with (
        patch("src.api.routes.admin._stage_upload") as stage,
        patch(
            "src.api.routes.admin._trigger_prefect_deployment",
            new=AsyncMock(return_value={"id": "flow-run-2"}),
        ) as trigger,
    ):
        response = client.post(
            "/admin/documents/ingest",
            data={"url": "https://example.org/a.pdf", "site_name": "naro"},
        )

    assert response.status_code == 200
    assert response.json()["flow_run_id"] == "flow-run-2"
    stage.assert_not_called()
    assert trigger.await_args.args[1] == {
        "url": "https://example.org/a.pdf",
        "title": None,
        "site_name": "naro",
    }


def test_duplicate_is_reported_synchronously_and_staging_discarded():
    client = _make_client()
    duplicate = {
        "document_id": "existing-id",
        "url": "upload://x/guide.pdf",
        "status": "duplicate",
        "chunks": 0,
        "reason": "duplicate_content",
        "existing_title": "Storage guide",
    }

    with (
        patch(
            "src.api.routes.admin._stage_upload",
            return_value=("staging/abc.pdf", "hash-1"),
        ),
        patch("src.api.routes.admin._find_duplicate_by_hash", return_value=duplicate),
        patch("src.api.routes.admin._discard_staged_upload") as discard,
        patch(
            "src.api.routes.admin._trigger_prefect_deployment",
            new=AsyncMock(),
        ) as trigger,
    ):
        response = client.post(
            "/admin/documents/ingest",
            files={"file": ("guide.pdf", b"%PDF test", "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json() == duplicate
    discard.assert_called_once_with("staging/abc.pdf")
    trigger.assert_not_awaited()


def test_oversized_upload_is_rejected_before_staging_to_minio():
    client = _make_client()

    with (
        patch("src.api.routes.admin._MAX_DOCUMENT_UPLOAD_BYTES", 4),
        patch("src.storage.minio_client.MinIOClient") as minio,
        patch(
            "src.api.routes.admin._trigger_prefect_deployment", new=AsyncMock()
        ) as trigger,
    ):
        response = client.post(
            "/admin/documents/ingest",
            files={"file": ("large.pdf", b"12345", "application/pdf")},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "large.pdf exceeds the 50 MB upload limit."
    minio.assert_not_called()
    trigger.assert_not_awaited()


def test_empty_upload_is_rejected():
    client = _make_client()

    with patch("src.storage.minio_client.MinIOClient") as minio:
        response = client.post(
            "/admin/documents/ingest",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "empty.pdf is empty."
    minio.assert_not_called()


def test_ingest_requires_a_file_or_url():
    response = _make_client().post("/admin/documents/ingest")

    assert response.status_code == 400
    assert response.json()["detail"] == "Provide either a file upload or a url field."


def test_unexpected_ingest_failure_returns_readable_cors_response():
    client = _make_client()

    with patch(
        "src.api.routes.admin._stage_upload",
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
