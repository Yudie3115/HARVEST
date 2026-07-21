"""Tests for /admin/access-codes routes."""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client():
    from src.api.routes.admin_access import router
    from src.api.routes.admin import require_admin
    from src.api.dependencies import get_db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: "admin"
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False), db


def _fake_code_row(**overrides):
    row = MagicMock()
    row.id = overrides.get("id", uuid.uuid4())
    row.label = overrides.get("label", "Group A")
    row.organization_name = overrides.get("organization_name")
    row.contact_message = overrides.get("contact_message")
    row.monthly_limit = overrides.get("monthly_limit", 100)
    row.status = overrides.get("status", "active")
    row.usage_count = overrides.get("usage_count", 0)
    row.period_start.isoformat.return_value = "2026-07-01T00:00:00+00:00"
    row.created_at.isoformat.return_value = "2026-07-01T00:00:00+00:00"
    row.created_by = overrides.get("created_by", "admin")
    return row


class TestCreateAccessCode:
    def test_requires_admin(self):
        from src.api.routes.admin_access import router
        from src.api.dependencies import get_db
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/admin/access-codes", json={"label": "X", "monthly_limit": 10})
        assert resp.status_code in (401, 403)

    def test_creates_and_returns_plaintext_code_once(self, monkeypatch):
        client, db = _make_client()
        import src.api.routes.admin_access as route_mod
        row = _fake_code_row(label="Farmer Group")
        monkeypatch.setattr(
            route_mod.access_service, "create_access_code",
            lambda db, **kw: (row, "mango-river-granary"),
        )
        resp = client.post(
            "/admin/access-codes",
            json={"label": "Farmer Group", "monthly_limit": 100},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["code"] == "mango-river-granary"
        assert body["label"] == "Farmer Group"


class TestListAccessCodes:
    def test_returns_paginated_items(self):
        client, db = _make_client()
        rows = [_fake_code_row(label="A"), _fake_code_row(label="B")]
        db.query.return_value.count.return_value = 2
        db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = rows

        resp = client.get("/admin/access-codes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2


class TestUpdateAccessCode:
    def test_patches_editable_fields(self):
        client, db = _make_client()
        row = _fake_code_row(label="Old Label")
        db.get.return_value = row

        resp = client.patch(
            f"/admin/access-codes/{row.id}", json={"label": "New Label"},
        )
        assert resp.status_code == 200
        assert row.label == "New Label"

    def test_missing_code_returns_404(self):
        client, db = _make_client()
        db.get.return_value = None
        resp = client.patch(f"/admin/access-codes/{uuid.uuid4()}", json={"label": "X"})
        assert resp.status_code == 404


class TestRevokeReactivate:
    def test_revoke_sets_status_revoked(self):
        client, db = _make_client()
        row = _fake_code_row(status="active")
        db.get.return_value = row

        resp = client.post(f"/admin/access-codes/{row.id}/revoke")
        assert resp.status_code == 200
        assert row.status == "revoked"

    def test_reactivate_sets_status_active(self):
        client, db = _make_client()
        row = _fake_code_row(status="revoked")
        db.get.return_value = row

        resp = client.post(f"/admin/access-codes/{row.id}/reactivate")
        assert resp.status_code == 200
        assert row.status == "active"
