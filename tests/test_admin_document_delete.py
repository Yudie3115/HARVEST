"""Tests for DELETE /admin/documents/{id}."""
import uuid
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client():
    from src.api.dependencies import get_db, get_vector_db_client
    from src.api.routes.admin import require_admin, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: "admin-user"
    db = MagicMock()
    vector_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_vector_db_client] = lambda: vector_db
    return TestClient(app, raise_server_exceptions=False), db, vector_db


def _fake_document(*, status=None, file_path="documents/guide.pdf"):
    from src.storage.models import DocumentStatus

    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.status = status or DocumentStatus.PROCESSED
    doc.file_path = file_path
    return doc


def test_delete_removes_vectors_rows_and_source_object():
    client, db, vector_db = _make_client()
    doc = _fake_document()
    db.get.return_value = doc
    minio = MagicMock()

    with patch("src.storage.minio_client.MinIOClient", return_value=minio):
        response = client.delete(f"/admin/documents/{doc.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(doc.id),
        "status": "deleted",
        "source_file_deleted": True,
    }
    vector_db.delete_by_document.assert_called_once_with(str(doc.id))
    assert db.query.return_value.filter.return_value.delete.call_count == 3
    db.delete.assert_called_once_with(doc)
    db.commit.assert_called_once()
    minio.delete_object.assert_called_once_with(doc.file_path)


def test_delete_missing_document_returns_404():
    client, db, vector_db = _make_client()
    db.get.return_value = None

    response = client.delete(f"/admin/documents/{uuid.uuid4()}")

    assert response.status_code == 404
    vector_db.delete_by_document.assert_not_called()


def test_delete_in_progress_document_returns_409():
    from src.storage.models import DocumentStatus

    client, db, vector_db = _make_client()
    doc = _fake_document(status=DocumentStatus.PROCESSING)
    db.get.return_value = doc

    response = client.delete(f"/admin/documents/{doc.id}")

    assert response.status_code == 409
    vector_db.delete_by_document.assert_not_called()
    db.delete.assert_not_called()


def test_vector_failure_preserves_database_record():
    client, db, vector_db = _make_client()
    doc = _fake_document()
    db.get.return_value = doc
    vector_db.delete_by_document.side_effect = RuntimeError("Qdrant unavailable")

    response = client.delete(f"/admin/documents/{doc.id}")

    assert response.status_code == 502
    assert "No database records were deleted" in response.json()["detail"]
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_source_cleanup_failure_reports_partial_cleanup_without_restoring_document():
    client, db, vector_db = _make_client()
    doc = _fake_document()
    db.get.return_value = doc
    minio = MagicMock()
    minio.delete_object.side_effect = RuntimeError("MinIO unavailable")

    with patch("src.storage.minio_client.MinIOClient", return_value=minio):
        response = client.delete(f"/admin/documents/{doc.id}")

    assert response.status_code == 200
    assert response.json()["source_file_deleted"] is False
    db.delete.assert_called_once_with(doc)
    db.commit.assert_called_once()
