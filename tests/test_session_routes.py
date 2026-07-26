"""Tests for access gating on /session/new and /session/{id}/history."""
import uuid
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client():
    from src.api.routes.session import router
    from src.api.dependencies import get_db
    from src.api.services.access_service import AccessError, access_error_handler

    app = FastAPI()
    app.add_exception_handler(AccessError, access_error_handler)
    app.include_router(router, prefix="/session")
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    return app, TestClient(app, raise_server_exceptions=False), db


def _override_grant(app, resolved):
    from src.api.dependencies import get_web_grant

    app.dependency_overrides[get_web_grant] = lambda: resolved


def _fake_resolved(grant_id=None, code_status="active"):
    resolved = MagicMock()
    resolved.grant.id = grant_id or uuid.uuid4()
    resolved.access_code.status = code_status
    return resolved


class TestCreateSession:
    def test_missing_token_returns_401(self):
        app, client, db = _make_client()
        resp = client.post("/session/new", json={"channel": "web"})
        assert resp.status_code == 401

    def test_revoked_code_returns_403(self):
        app, client, db = _make_client()
        _override_grant(app, _fake_resolved(code_status="revoked"))
        resp = client.post("/session/new", json={"channel": "web"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "access_revoked"

    def test_valid_grant_creates_session_owned_by_the_grant(self):
        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)

        resp = client.post("/session/new", json={"channel": "web"})
        assert resp.status_code == 201
        added = db.add.call_args[0][0]
        assert added.access_grant_id == resolved.grant.id


class TestCreateSessionFromCatalogue:
    def test_requires_access_grant(self):
        _, client, _ = _make_client()
        resp = client.post(
            "/session/from-catalogue",
            json={"catalogue_entry_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 401

    def test_rejects_nonapproved_entry_with_uniform_404(self):
        from src.storage.models import CatalogueEntry, CatalogueStatusEnum

        app, client, db = _make_client()
        _override_grant(app, _fake_resolved())
        entry = CatalogueEntry(
            id=uuid.uuid4(),
            question_en="Question",
            answer_en="Answer",
            status=CatalogueStatusEnum.retracted,
        )
        db.get.return_value = entry

        resp = client.post(
            "/session/from-catalogue",
            json={"catalogue_entry_id": str(entry.id)},
        )
        assert resp.status_code == 404

    def test_seeds_approved_question_and_answer_without_reserving_quota(self):
        from src.storage.models import CatalogueEntry, CatalogueStatusEnum, ChatSession

        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)
        entry = CatalogueEntry(
            id=uuid.uuid4(),
            question_en="How should maize be dried?",
            answer_en="Dry it before storage.",
            status=CatalogueStatusEnum.approved,
            source_message_id=None,
        )
        db.get.return_value = entry

        def assign_id(row):
            if isinstance(row, ChatSession):
                row.id = uuid.uuid4()

        db.add.side_effect = assign_id
        resp = client.post(
            "/session/from-catalogue",
            json={"catalogue_entry_id": str(entry.id)},
        )

        assert resp.status_code == 201
        seeded = db.add_all.call_args[0][0]
        assert [message.content for message in seeded] == [
            entry.question_en,
            entry.answer_en,
        ]
        assert all(message.session_id == seeded[0].session_id for message in seeded)


class TestSessionHistory:
    def test_missing_token_returns_401(self):
        app, client, db = _make_client()
        resp = client.get(f"/session/{uuid.uuid4()}/history")
        assert resp.status_code == 401

    def test_session_owned_by_another_grant_returns_403(self):
        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)

        other_session = MagicMock()
        other_session.access_grant_id = uuid.uuid4()  # different grant
        db.get.return_value = other_session

        resp = client.get(f"/session/{uuid.uuid4()}/history")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "session_forbidden"

    def test_session_with_no_grant_id_returns_403(self):
        """Pre-migration rows (access_grant_id=None) can never match a resolved grant."""
        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)

        legacy_session = MagicMock()
        legacy_session.access_grant_id = None
        db.get.return_value = legacy_session

        resp = client.get(f"/session/{uuid.uuid4()}/history")
        assert resp.status_code == 403

    def test_own_session_returns_history(self):
        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)

        owned_session = MagicMock()
        owned_session.access_grant_id = resolved.grant.id
        db.get.return_value = owned_session
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )

        resp = client.get(f"/session/{uuid.uuid4()}/history")
        assert resp.status_code == 200

        order = db.query.return_value.filter.return_value.order_by.call_args.args
        assert len(order) == 3
        assert "CASE" in str(order[1])
        assert "chat_messages.role" in str(order[1])
