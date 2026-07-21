"""Tests for /access/redeem and /access/status."""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client():
    from src.api.routes.access import router
    from src.api.dependencies import get_db
    from src.api.services.access_service import AccessError, access_error_handler

    app = FastAPI()
    app.add_exception_handler(AccessError, access_error_handler)
    app.include_router(router)
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False), db


def _fake_result(token="new-token", label="Group A", monthly_limit=100, usage_count=3):
    result = MagicMock()
    result.token = token
    result.access_code.label = label
    result.access_code.monthly_limit = monthly_limit
    result.access_code.usage_count = usage_count
    import datetime
    result.access_code.period_start = datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc)
    return result


class TestRedeem:
    def test_valid_code_returns_token(self, monkeypatch):
        client, db = _make_client()
        import src.api.routes.access as route_mod
        monkeypatch.setattr(route_mod.access_service, "check_redemption_throttle", lambda db, ident: None)
        monkeypatch.setattr(route_mod.access_service, "clear_redemption_throttle", lambda db, ident: None)
        monkeypatch.setattr(route_mod.access_service, "redeem_web_code", lambda db, code: _fake_result())

        resp = client.post("/access/redeem", json={"code": "mango-river-granary"})
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "new-token"

    def test_invalid_code_records_failed_attempt_and_returns_401(self, monkeypatch):
        client, db = _make_client()
        import src.api.routes.access as route_mod
        from src.api.services.access_service import AccessInvalidError

        monkeypatch.setattr(route_mod.access_service, "check_redemption_throttle", lambda db, ident: None)
        recorded = []
        monkeypatch.setattr(
            route_mod.access_service, "record_failed_redemption_attempt",
            lambda db, ident: recorded.append(ident),
        )

        def _raise(db, code):
            raise AccessInvalidError("nope")
        monkeypatch.setattr(route_mod.access_service, "redeem_web_code", _raise)

        resp = client.post("/access/redeem", json={"code": "bad-bad-bad"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "access_invalid"
        assert len(recorded) == 1

    def test_throttled_client_gets_429_before_redemption_is_attempted(self, monkeypatch):
        client, db = _make_client()
        import src.api.routes.access as route_mod
        from src.api.services.access_service import RedemptionRateLimitedError

        def _throttled(db, ident):
            raise RedemptionRateLimitedError("slow down")
        monkeypatch.setattr(route_mod.access_service, "check_redemption_throttle", _throttled)

        called = []
        monkeypatch.setattr(
            route_mod.access_service, "redeem_web_code",
            lambda db, code: called.append(1),
        )

        resp = client.post("/access/redeem", json={"code": "mango-river-granary"})
        assert resp.status_code == 429
        assert called == []


class TestStatus:
    def test_missing_token_returns_401(self):
        client, db = _make_client()
        resp = client.get("/access/status")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "access_required"

    def test_valid_token_reports_status_without_gating_on_revocation(self, monkeypatch):
        client, db = _make_client()
        import src.api.routes.access as route_mod

        resolved = _fake_result()
        resolved.access_code.status = "revoked"
        monkeypatch.setattr(route_mod.access_service, "resolve_web_grant", lambda db, token: resolved)

        resp = client.get("/access/status", headers={"X-Access-Token": "any-token"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"
