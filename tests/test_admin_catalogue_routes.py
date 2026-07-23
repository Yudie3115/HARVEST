"""Tests for admin catalogue review/publication status-transition guards."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.storage.models import CatalogueEntry, CatalogueStatusEnum


def _make_client():
    from src.api.routes.admin import require_admin
    from src.api.routes.admin_catalogue import router
    from src.api.dependencies import get_db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: "admin-user"
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False), db


def _fake_entry(**overrides) -> CatalogueEntry:
    entry = CatalogueEntry(
        id=overrides.get("id", uuid.uuid4()),
        question_en=overrides.get("question_en", "How should maize be dried?"),
        answer_en=overrides.get("answer_en", "Dry maize before storage."),
        status=overrides.get("status", CatalogueStatusEnum.pending),
        source_message_id=None,
        grounding_score=overrides.get("grounding_score", 0.8),
        llm_score=overrides.get("llm_score", 0.9),
        served_count=overrides.get("served_count", 0),
        helpful_count=overrides.get("helpful_count", 0),
        candidate_duplicate_count=overrides.get("candidate_duplicate_count", 0),
        publish_error=overrides.get("publish_error", None),
        publish_attempts=overrides.get("publish_attempts", 0),
        question_translations=overrides.get("question_translations", None),
        answer_translations=overrides.get("answer_translations", None),
        created_at=overrides.get("created_at", datetime(2026, 7, 1, tzinfo=timezone.utc)),
        updated_at=overrides.get("updated_at", None),
        approved_at=overrides.get("approved_at", None),
    )
    return entry


def _db_returning(entry):
    db = MagicMock()
    db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
    return db


class TestRequiresAdmin:
    def test_approve_requires_admin(self):
        from src.api.routes.admin_catalogue import router
        from src.api.dependencies import get_db

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(f"/admin/catalogue/{uuid.uuid4()}/approve")
        assert resp.status_code in (401, 403)


class TestApprove:
    def test_missing_entry_returns_404(self):
        client, db = _make_client()
        db.get.return_value = None
        resp = client.post(f"/admin/catalogue/{uuid.uuid4()}/approve")
        assert resp.status_code == 404

    def test_approves_pending_entry(self):
        entry = _fake_entry(status=CatalogueStatusEnum.pending)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/approve")
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"

    def test_approves_publish_failed_entry(self):
        entry = _fake_entry(status=CatalogueStatusEnum.publish_failed)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/approve")
        assert resp.status_code == 202

    def test_rejects_already_approved_entry(self):
        entry = _fake_entry(status=CatalogueStatusEnum.approved)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/approve")
        assert resp.status_code == 409

    def test_rejects_entry_still_publishing(self):
        entry = _fake_entry(status=CatalogueStatusEnum.publishing)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/approve")
        assert resp.status_code == 409


class TestReject:
    def test_rejects_pending_entry(self):
        entry = _fake_entry(status=CatalogueStatusEnum.pending)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
        assert entry.status == CatalogueStatusEnum.rejected

    def test_cannot_reject_approved_entry(self):
        entry = _fake_entry(status=CatalogueStatusEnum.approved)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/reject")
        assert resp.status_code == 409
        assert entry.status == CatalogueStatusEnum.approved


class TestRetract:
    def test_retracts_approved_entry_and_enqueues_vector_deletion(self):
        entry = _fake_entry(status=CatalogueStatusEnum.approved)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/retract")
        assert resp.status_code == 202
        assert resp.json()["status"] == "retracted"
        assert entry.status == CatalogueStatusEnum.retracted

    def test_cannot_retract_non_approved_entry(self):
        entry = _fake_entry(status=CatalogueStatusEnum.pending)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/retract")
        assert resp.status_code == 409
        assert entry.status == CatalogueStatusEnum.pending


class TestRetryPublish:
    def test_retries_publish_failed_entry(self):
        entry = _fake_entry(status=CatalogueStatusEnum.publish_failed, publish_error="boom")
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/retry-publish")
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"

    def test_cannot_retry_when_not_failed(self):
        entry = _fake_entry(status=CatalogueStatusEnum.pending)
        client, db = _make_client()
        db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
        resp = client.post(f"/admin/catalogue/{entry.id}/retry-publish")
        assert resp.status_code == 409
