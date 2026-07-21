"""Tests for PATCH /admin/documents/{id}/publication."""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client():
    from src.api.routes.admin import router, require_admin
    from src.api.dependencies import get_db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: "admin-user"
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False), db


def _fake_document(**overrides):
    from src.storage.models import DocumentStatus
    doc = MagicMock()
    doc.id = overrides.get("id", uuid.uuid4())
    doc.status = overrides.get("status", DocumentStatus.PROCESSED)
    doc.url = overrides.get("url", "https://example.org/doc")
    doc.public_source_url = overrides.get("public_source_url", None)
    doc.publicly_visible = overrides.get("publicly_visible", False)
    doc.published_at = None
    doc.published_by = None
    return doc


class TestPublicationEndpoint:
    def test_requires_admin(self):
        from src.api.routes.admin import router
        from src.api.dependencies import get_db
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(f"/admin/documents/{uuid.uuid4()}/publication", json={"publicly_visible": True})
        assert resp.status_code in (401, 403)

    def test_missing_document_returns_404(self):
        client, db = _make_client()
        db.get.return_value = None
        resp = client.patch(f"/admin/documents/{uuid.uuid4()}/publication", json={"publicly_visible": True})
        assert resp.status_code == 404

    def test_publishing_unprocessed_document_returns_400(self):
        from src.storage.models import DocumentStatus
        client, db = _make_client()
        doc = _fake_document(status=DocumentStatus.DISCOVERED)
        db.get.return_value = doc
        resp = client.patch(f"/admin/documents/{doc.id}/publication", json={"publicly_visible": True})
        assert resp.status_code == 400

    def test_publishing_upload_source_without_public_url_returns_400(self):
        client, db = _make_client()
        doc = _fake_document(url=f"upload://{uuid.uuid4()}/guide.pdf", public_source_url=None)
        db.get.return_value = doc
        resp = client.patch(f"/admin/documents/{doc.id}/publication", json={"publicly_visible": True})
        assert resp.status_code == 400

    def test_publishing_upload_source_with_public_url_in_request_succeeds(self):
        client, db = _make_client()
        doc = _fake_document(url=f"upload://{uuid.uuid4()}/guide.pdf", public_source_url=None)
        db.get.return_value = doc
        resp = client.patch(
            f"/admin/documents/{doc.id}/publication",
            json={"publicly_visible": True, "public_source_url": "https://realsite.example/guide.pdf"},
        )
        assert resp.status_code == 200
        assert doc.publicly_visible is True
        assert doc.public_source_url == "https://realsite.example/guide.pdf"
        assert doc.published_by == "admin-user"
        assert doc.published_at is not None

    def test_publishing_normal_crawled_document_succeeds(self):
        client, db = _make_client()
        doc = _fake_document(url="https://naro.go.ug/guide.pdf")
        db.get.return_value = doc
        resp = client.patch(f"/admin/documents/{doc.id}/publication", json={"publicly_visible": True})
        assert resp.status_code == 200
        assert doc.publicly_visible is True
        assert doc.published_by == "admin-user"

    def test_unpublishing_does_not_clear_published_at_or_published_by(self):
        from datetime import datetime, timezone
        client, db = _make_client()
        doc = _fake_document(publicly_visible=True)
        doc.published_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
        doc.published_by = "previous-admin"
        db.get.return_value = doc
        resp = client.patch(f"/admin/documents/{doc.id}/publication", json={"publicly_visible": False})
        assert resp.status_code == 200
        assert doc.publicly_visible is False
        assert doc.published_by == "previous-admin"
        assert doc.published_at == datetime(2026, 7, 1, tzinfo=timezone.utc)

    def test_public_source_url_can_be_set_independent_of_publishing(self):
        client, db = _make_client()
        doc = _fake_document(publicly_visible=False)
        db.get.return_value = doc
        resp = client.patch(
            f"/admin/documents/{doc.id}/publication",
            json={"publicly_visible": False, "public_source_url": "https://realsite.example/x.pdf"},
        )
        assert resp.status_code == 200
        assert doc.public_source_url == "https://realsite.example/x.pdf"
        assert doc.publicly_visible is False

    def test_empty_public_source_url_does_not_clear_existing_value(self):
        client, db = _make_client()
        doc = _fake_document(publicly_visible=True, public_source_url="https://realsite.example/existing.pdf")
        db.get.return_value = doc
        resp = client.patch(
            f"/admin/documents/{doc.id}/publication",
            json={"publicly_visible": False, "public_source_url": ""},
        )
        assert resp.status_code == 200
        assert doc.public_source_url == "https://realsite.example/existing.pdf"
        assert doc.publicly_visible is False
