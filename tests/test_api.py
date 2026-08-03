from fastapi.testclient import TestClient

from cloud_steward.main import create_app
from cloud_steward.settings import Settings


def test_plan_api_never_executes_and_records_approval(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        gemini_api_key=None,
        datahub_mcp_url=None,
        datahub_gms_url=None,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/plans",
        json={
            "goal": "Reduce checkout latency without breaking invoices",
            "context_query": "checkout billing invoice",
            "environment": "production",
            "dry_run": True,
        },
    )

    assert response.status_code == 201
    plan = response.json()
    assert plan["status"] == "proposed"
    assert plan["requires_approval"] is True

    approval = client.post(
        f"/api/plans/{plan['id']}/approve",
        json={"approved_by": "reviewer", "note": "Demo only"},
    )
    assert approval.status_code == 200
    assert approval.json()["status"] == "approved"

    status = client.get("/api/status").json()
    assert "No execution boundary" in status["safeguards"]


def test_dashboard_and_health_are_available(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'health.db'}")
    client = TestClient(create_app(settings))

    assert client.get("/").status_code == 200
    assert client.get("/healthz").json()["status"] == "ok"
