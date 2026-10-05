from fastapi.testclient import TestClient

from freellmpool.api import app
from freellmpool.api.db import Base, engine

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)
    client.post("/auth/register", json={"email": "cost@example.com", "password": "correct-horse-battery"})
    login = client.post("/auth/login", json={"email": "cost@example.com", "password": "correct-horse-battery"})
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def test_lifecycle_cost_create_list_and_summary() -> None:
    org = client.post("/organizations", json={"name": "Cost Org"}).json()
    project = client.post("/projects", json={"organization_id": org["id"], "name": "Plant"}).json()
    package = client.post(
        "/packages",
        json={"project_id": project["id"], "name": "Motor", "category": "MOTOR", "mode": "STANDARD"},
    ).json()
    asset = client.post(f"/packages/{package['id']}/assets", json={"asset_id": "M-001"}).json()
    event = client.post(
        f"/packages/{package['id']}/lifecycle-events",
        json={"asset_id": asset["asset_id"], "event_type": "MAINTENANCE", "event_date": "2026-10-01T00:00:00Z", "description": "Bearing service"},
    ).json()
    for amount, cost_type in [(1000, "PURCHASE"), (250, "MAINTENANCE"), (150, "SPARE_PART")]:
        response = client.post(
            f"/packages/{package['id']}/lifecycle-costs",
            json={
                "asset_id": asset["asset_id"],
                "event_id": event["id"] if cost_type != "PURCHASE" else None,
                "cost_type": cost_type,
                "amount": amount,
                "currency": "USD",
                "cost_date": "2026-10-01T00:00:00Z",
                "description": cost_type,
            },
        )
        assert response.status_code == 201, response.text
    summary = client.get(f"/organizations/{org['id']}/lifecycle-cost-summary")
    assert summary.status_code == 200
    assert summary.json()["totals_by_asset_currency"]["M-001"]["USD"] == 1400.0


def test_lifecycle_cost_rejects_foreign_event() -> None:
    org = client.post("/organizations", json={"name": "Cost Org"}).json()
    project = client.post("/projects", json={"organization_id": org["id"], "name": "Plant"}).json()
    package = client.post(
        "/packages", json={"project_id": project["id"], "name": "Motor", "category": "MOTOR", "mode": "STANDARD"}
    ).json()
    event = client.post(
        f"/packages/{package['id']}/lifecycle-events",
        json={"asset_id": "M-001", "event_type": "FAILURE", "event_date": "2026-10-01T00:00:00Z", "description": "Failure"},
    ).json()
    second_package = client.post(
        "/packages", json={"project_id": project["id"], "name": "Motor 2", "category": "MOTOR", "mode": "STANDARD"}
    ).json()
    bad = client.post(
        f"/packages/{second_package['id']}/lifecycle-costs",
        json={
            "asset_id": "M-002",
            "event_id": event["id"],
            "cost_type": "FAILURE",
            "amount": 10,
            "currency": "USD",
            "cost_date": "2026-10-01T00:00:00Z",
            "description": "Invalid link",
        },
    )
    assert bad.status_code == 422
