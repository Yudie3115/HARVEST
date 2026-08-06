"""Tests for the protected Admin reprocess-stuck-documents endpoint.

The endpoint delegates to a Prefect deployment rather than running the
pipeline in-process, so these assert on the trigger call, not on
reset_stuck_documents/process_documents_batch.
"""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client() -> TestClient:
    from src.api.routes.admin import require_admin, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: "admin-user"
    return TestClient(app, raise_server_exceptions=False)


def test_reprocess_stuck_triggers_prefect_deployment():
    client = _make_client()

    with patch(
        "src.api.routes.admin._trigger_prefect_deployment",
        new=AsyncMock(return_value={"id": "flow-run-123"}),
    ) as trigger:
        response = client.post("/admin/documents/reprocess-stuck")

    assert response.status_code == 200
    assert response.json() == {"status": "triggered", "flow_run_id": "flow-run-123"}
    trigger.assert_awaited_once()
    deployment_name, parameters = trigger.await_args.args
    assert deployment_name.startswith("reprocess_stuck/reprocess-stuck-")
    assert parameters == {"limit": 200}


def test_reprocess_stuck_forwards_limit_to_the_flow_run():
    client = _make_client()

    with patch(
        "src.api.routes.admin._trigger_prefect_deployment",
        new=AsyncMock(return_value={"id": "flow-run-456"}),
    ) as trigger:
        response = client.post("/admin/documents/reprocess-stuck?limit=25")

    assert response.status_code == 200
    assert trigger.await_args.args[1] == {"limit": 25}


def test_reprocess_stuck_does_not_run_the_pipeline_in_process():
    """Regression: running the pipeline here starved the connection pool and
    held the request open past the proxy timeout ("Failed to fetch")."""
    client = _make_client()

    with (
        patch(
            "src.api.routes.admin._trigger_prefect_deployment",
            new=AsyncMock(return_value={"id": "flow-run-789"}),
        ),
        patch("src.flows.orchestration.reset_stuck_documents") as reset,
        patch("src.flows.processing.process_documents_batch") as process_batch,
    ):
        response = client.post("/admin/documents/reprocess-stuck")

    assert response.status_code == 200
    reset.assert_not_called()
    process_batch.assert_not_called()


def test_reprocess_stuck_surfaces_prefect_errors():
    client = _make_client()

    with patch(
        "src.api.routes.admin._trigger_prefect_deployment",
        new=AsyncMock(side_effect=_prefect_unavailable()),
    ):
        response = client.post("/admin/documents/reprocess-stuck")

    assert response.status_code == 502


def _prefect_unavailable():
    from fastapi import HTTPException

    return HTTPException(status_code=502, detail="Could not reach Prefect: boom")
