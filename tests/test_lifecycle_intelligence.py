from fastapi.testclient import TestClient

from freellmpool.api import app
from freellmpool.api.db import Base, engine

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)
    client.post("/auth/register", json={"email": "life-intel@example.com", "password": "correct-horse-battery"})
    login = client.post("/auth/login", json={"email": "life-intel@example.com", "password": "correct-horse-battery"})
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def test_lifecycle_intelligence_aggregates_asset_events() -> None:
    organization = client.post("/organizations", json={"name": "Lifecycle Org"}).json()
    project = client.post("/projects", json={"organization_id": organization["id"], "name": "Plant"}).json()
    package = client.post(
        "/packages",
        json={"project_id": project["id"], "name": "Drive Package", "category": "VFD", "mode": "STANDARD"},
    ).json()
    asset = client.post(
        f"/packages/{package['id']}/assets",
        json={"asset_id": "VFD-001", "manufacturer": "ABB", "model": "ACS880", "status": "ACTIVE"},
    ).json()
    for event_type, date in [
        ("INSTALLATION", "2026-01-01T00:00:00Z"),
        ("COMMISSIONING", "2026-01-03T00:00:00Z"),
        ("FAILURE", "2026-06-01T00:00:00Z"),
        ("MAINTENANCE", "2026-06-02T00:00:00Z"),
        ("FAILURE", "2026-08-01T00:00:00Z"),
    ]:
        response = client.post(
            f"/packages/{package['id']}/lifecycle-events",
            json={"asset_id": asset["asset_id"], "event_type": event_type, "event_date": date, "description": event_type},
        )
        assert response.status_code == 201, response.text

    result = client.get(f"/organizations/{organization['id']}/lifecycle-intelligence")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["asset_count"] == 1
    assert body["event_count"] == 5
    assert body["event_counts_by_type"]["FAILURE"] == 2
    summary = body["assets"][0]
    assert summary["failure_count"] == 2
    assert summary["maintenance_count"] == 1
    assert summary["first_event_date"].startswith("2026-01-01")
    assert summary["latest_event_date"].startswith("2026-08-01")


def test_lifecycle_intelligence_is_tenant_isolated() -> None:
    client.post("/organizations", json={"name": "First Org"}).json()
    second = client.post("/organizations", json={"name": "Second Org"}).json()
    response = client.get(f"/organizations/{second['id']}/lifecycle-intelligence")
    assert response.status_code == 404
    assert response.json()["detail"] == "organization not found"


def test_lifecycle_intelligence_includes_costs_and_warranty_dates() -> None:
    organization = client.post("/organizations", json={"name": "Economics Org"}).json()
    project = client.post("/projects", json={"organization_id": organization["id"], "name": "Plant"}).json()
    package = client.post(
        "/packages",
        json={"project_id": project["id"], "name": "Motor", "category": "MOTOR", "mode": "STANDARD"},
    ).json()
    asset = client.post(
        f"/packages/{package['id']}/assets",
        json={
            "asset_id": "M-001",
            "warranty_start": "2026-01-01T00:00:00Z",
            "warranty_end": "2028-01-01T00:00:00Z",
        },
    ).json()
    for amount, currency in [(1000, "USD"), (250, "USD"), (100, "EUR")]:
        response = client.post(
            f"/packages/{package['id']}/lifecycle-costs",
            json={
                "asset_id": asset["asset_id"],
                "cost_type": "MAINTENANCE",
                "amount": amount,
                "currency": currency,
                "cost_date": "2026-09-01T00:00:00Z",
                "description": "Lifecycle cost",
            },
        )
        assert response.status_code == 201, response.text

    result = client.get(f"/organizations/{organization['id']}/lifecycle-intelligence")
    assert result.status_code == 200, result.text
    summary = result.json()["assets"][0]
    assert summary["lifecycle_costs_by_currency"] == {"EUR": 100.0, "USD": 1250.0}
    assert summary["warranty_start"].startswith("2026-01-01")
    assert summary["warranty_end"].startswith("2028-01-01")


def test_lifecycle_intelligence_reports_reliability_indicators() -> None:
    organization = client.post("/organizations", json={"name": "Reliability Org"}).json()
    project = client.post("/projects", json={"organization_id": organization["id"], "name": "Plant"}).json()
    package = client.post(
        "/packages",
        json={"project_id": project["id"], "name": "Drive", "category": "VFD", "mode": "STANDARD"},
    ).json()
    client.post(
        f"/packages/{package['id']}/assets",
        json={"asset_id": "VFD-REL-001"},
    )
    events = [
        ("COMMISSIONING", "2026-01-01T00:00:00Z"),
        ("FAILURE", "2026-02-01T00:00:00Z"),
        ("MAINTENANCE", "2026-02-03T00:00:00Z"),
        ("FAILURE", "2026-03-05T00:00:00Z"),
        ("MAINTENANCE", "2026-03-06T00:00:00Z"),
    ]
    for event_type, date in events:
        response = client.post(
            f"/packages/{package['id']}/lifecycle-events",
            json={
                "asset_id": "VFD-REL-001",
                "event_type": event_type,
                "event_date": date,
                "description": event_type,
            },
        )
        assert response.status_code == 201, response.text
    result = client.get(f"/organizations/{organization['id']}/lifecycle-intelligence")
    assert result.status_code == 200, result.text
    summary = result.json()["assets"][0]
    assert summary["reliability_failure_intervals_days"] == [32.0]
    assert summary["mean_failure_interval_days"] == 32.0
    assert summary["mean_failure_to_maintenance_days"] == 1.5
