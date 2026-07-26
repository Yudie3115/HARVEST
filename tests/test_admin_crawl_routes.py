"""Tests for the Admin Prefect crawl triggers."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


def _make_client():
    from src.api.routes.admin import require_admin, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: "admin-user"
    return TestClient(app)


def test_full_crawl_uses_configured_environment(monkeypatch):
    import src.api.routes.admin as admin

    monkeypatch.setattr(admin.settings, "environment", "development")
    trigger = AsyncMock(return_value={"id": "full-run-id"})

    with patch.object(admin, "_trigger_prefect_deployment", trigger):
        response = _make_client().post("/admin/crawl/full")

    assert response.status_code == 200
    assert response.json() == {"status": "triggered", "flow_run_id": "full-run-id"}
    trigger.assert_awaited_once_with("post_harvest_scraper/daily-scraper-development")


def test_incremental_crawl_uses_configured_environment(monkeypatch):
    import src.api.routes.admin as admin

    monkeypatch.setattr(admin.settings, "environment", "staging")
    trigger = AsyncMock(return_value={"id": "incremental-run-id"})

    with patch.object(admin, "_trigger_prefect_deployment", trigger):
        response = _make_client().post("/admin/crawl/incremental")

    assert response.status_code == 200
    assert response.json() == {
        "status": "triggered",
        "flow_run_id": "incremental-run-id",
    }
    trigger.assert_awaited_once_with("incremental_update/incremental-update-staging")


@pytest.mark.asyncio
async def test_trigger_resolves_deployment_id_before_creating_run(monkeypatch):
    import src.api.routes.admin as admin

    monkeypatch.setattr(admin.settings, "prefect_api_url", "http://prefect:4200/api")
    deployment_response = MagicMock()
    deployment_response.json.return_value = {"id": "deployment-id"}
    run_response = MagicMock()
    run_response.json.return_value = {"id": "flow-run-id"}

    client = AsyncMock()
    client.get.return_value = deployment_response
    client.post.return_value = run_response
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=False)

    with patch.object(admin.httpx, "AsyncClient", return_value=client_context):
        result = await admin._trigger_prefect_deployment("flow/deployment-development")

    assert result == {"id": "flow-run-id"}
    client.get.assert_awaited_once_with(
        "http://prefect:4200/api/deployments/name/flow/deployment-development",
        headers={},
    )
    deployment_response.raise_for_status.assert_called_once_with()
    client.post.assert_awaited_once_with(
        "http://prefect:4200/api/deployments/deployment-id/create_flow_run",
        json={},
        headers={},
    )
    run_response.raise_for_status.assert_called_once_with()
