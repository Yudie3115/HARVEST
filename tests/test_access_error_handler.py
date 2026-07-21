"""Tests for the global AccessError -> JSON contract exception handler."""
import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app():
    from src.api.services.access_service import AccessError, access_error_handler

    app = FastAPI()
    app.add_exception_handler(AccessError, access_error_handler)

    @app.get("/boom-plain")
    def boom_plain():
        from src.api.services.access_service import AccessRequiredError
        raise AccessRequiredError("Token absent.")

    @app.get("/boom-quota")
    def boom_quota():
        from src.api.services.access_service import QuotaExhaustedError
        reset = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
        raise QuotaExhaustedError("Quota used up.", period_resets_at=reset)

    return TestClient(app, raise_server_exceptions=False)


def test_plain_access_error_has_no_period_resets_at():
    client = _make_app()
    resp = client.get("/boom-plain")
    assert resp.status_code == 401
    body = resp.json()
    assert body == {"error": {"code": "access_required", "message": "Token absent."}}


def test_quota_exhausted_includes_period_resets_at():
    client = _make_app()
    resp = client.get("/boom-quota")
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "quota_exhausted"
    assert body["error"]["message"] == "Quota used up."
    assert body["error"]["period_resets_at"] == "2026-08-01T00:00:00+00:00"
