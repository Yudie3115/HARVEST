"""Tests for access gating and quota reservation on /chat and /chat/stream."""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client():
    from src.api.routes.chat import router
    from src.api.dependencies import (
        get_db, get_embedding_client, get_llm_client,
        get_translation_client, get_vector_db_client,
    )
    from src.api.services.access_service import AccessError, access_error_handler

    app = FastAPI()
    app.add_exception_handler(AccessError, access_error_handler)
    app.include_router(router)
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm_client] = lambda: MagicMock()
    app.dependency_overrides[get_embedding_client] = lambda: MagicMock()
    app.dependency_overrides[get_vector_db_client] = lambda: MagicMock()
    app.dependency_overrides[get_translation_client] = lambda: MagicMock()
    return app, TestClient(app, raise_server_exceptions=False), db


def _override_grant(app, resolved):
    from src.api.dependencies import get_web_grant
    app.dependency_overrides[get_web_grant] = lambda: resolved


def _fake_resolved(grant_id=None, code_status="active"):
    resolved = MagicMock()
    resolved.grant.id = grant_id or uuid.uuid4()
    resolved.access_code.id = uuid.uuid4()
    resolved.access_code.status = code_status
    return resolved


class TestChat:
    def test_missing_token_returns_401_without_reserving_quota(self, monkeypatch):
        app, client, db = _make_client()
        import src.api.routes.chat as route_mod
        reserved = []
        monkeypatch.setattr(route_mod.access_service, "reserve_quota", lambda db, cid: reserved.append(cid))

        resp = client.post("/chat", json={"session_id": str(uuid.uuid4()), "message": "hi"})
        assert resp.status_code == 401
        assert reserved == []

    def test_session_owned_by_another_grant_returns_403(self, monkeypatch):
        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)

        other_session = MagicMock()
        other_session.access_grant_id = uuid.uuid4()
        db.get.return_value = other_session

        resp = client.post("/chat", json={"session_id": str(uuid.uuid4()), "message": "hi"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "session_forbidden"

    def test_quota_exhausted_prevents_rag_processing(self, monkeypatch):
        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)

        owned_session = MagicMock()
        owned_session.access_grant_id = resolved.grant.id
        db.get.return_value = owned_session

        import src.api.routes.chat as route_mod
        from src.api.services.access_service import QuotaExhaustedError

        def _raise(db, cid):
            raise QuotaExhaustedError("exhausted")
        monkeypatch.setattr(route_mod.access_service, "reserve_quota", _raise)

        process_called = []
        monkeypatch.setattr(route_mod, "process_chat", lambda **kw: process_called.append(1))

        resp = client.post("/chat", json={"session_id": str(uuid.uuid4()), "message": "hi"})
        assert resp.status_code == 429
        assert process_called == []

    def test_valid_request_reserves_quota_before_processing(self, monkeypatch):
        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)

        owned_session = MagicMock()
        owned_session.access_grant_id = resolved.grant.id
        db.get.return_value = owned_session

        import src.api.routes.chat as route_mod
        call_order = []
        monkeypatch.setattr(
            route_mod.access_service, "reserve_quota",
            lambda db, cid: call_order.append("reserve"),
        )
        fake_response = MagicMock(answer="hi there", detected_language="eng", sources=[], session_id=str(owned_session.id), no_results=False)

        def _fake_process_chat(**kwargs):
            call_order.append("process")
            return fake_response
        monkeypatch.setattr(route_mod, "process_chat", _fake_process_chat)

        resp = client.post("/chat", json={"session_id": str(uuid.uuid4()), "message": "hi"})
        assert resp.status_code == 200
        assert call_order == ["reserve", "process"]


class TestChatStream:
    def test_missing_token_returns_401_and_never_starts_the_stream(self, monkeypatch):
        app, client, db = _make_client()
        import src.api.routes.chat as route_mod
        started = []
        monkeypatch.setattr(route_mod, "process_chat_stream", lambda **kw: started.append(1) or iter([]))

        resp = client.post("/chat/stream", json={"session_id": str(uuid.uuid4()), "message": "hi"})
        assert resp.status_code == 401
        assert started == []

    def test_quota_exhausted_returns_normal_json_error_not_sse(self, monkeypatch):
        app, client, db = _make_client()
        resolved = _fake_resolved()
        _override_grant(app, resolved)

        owned_session = MagicMock()
        owned_session.access_grant_id = resolved.grant.id
        db.get.return_value = owned_session

        import src.api.routes.chat as route_mod
        from src.api.services.access_service import QuotaExhaustedError

        def _raise(db, cid):
            raise QuotaExhaustedError("exhausted")
        monkeypatch.setattr(route_mod.access_service, "reserve_quota", _raise)

        resp = client.post("/chat/stream", json={"session_id": str(uuid.uuid4()), "message": "hi"})
        assert resp.status_code == 429
        assert resp.headers["content-type"].startswith("application/json")
