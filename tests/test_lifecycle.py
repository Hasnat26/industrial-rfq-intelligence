from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from freellmpool.api import app
from freellmpool.api.db import Base, engine

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)
    registered = client.post(
        "/auth/register",
        json={"email": "lifecycle@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "lifecycle@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def _package() -> tuple[dict, dict, dict]:
    organization = client.post(
        "/organizations", json={"name": "Lifecycle Org"}
    ).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Lifecycle Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "mode": "STANDARD",
        },
    ).json()
    return organization, project, package


def test_lifecycle_event_create_and_list() -> None:
    organization, _project, package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={
            "vendor_name": "Vendor A",
            "manufacturer": "ABB",
            "model": "M3BP 160",
            "part_number": "3GBA162410",
        },
    )
    assert offer.status_code == 201

    event = client.post(
        f"/packages/{package['id']}/lifecycle-events",
        json={
            "asset_id": "MOTOR-001",
            "event_type": "COMMISSIONING",
            "event_date": "2026-10-05T10:00:00Z",
            "description": "Motor commissioned successfully.",
            "evidence": "Commissioning report CR-001",
            "offer_id": offer.json()["id"],
        },
    )
    assert event.status_code == 201, event.text
    payload = event.json()
    assert payload["package_id"] == package["id"]
    assert payload["offer_id"] == offer.json()["id"]
    assert payload["event_type"] == "COMMISSIONING"
    assert payload["asset_id"] == "MOTOR-001"

    events = client.get(f"/packages/{package['id']}/lifecycle-events")
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["description"] == "Motor commissioned successfully."

    org_events = client.get(f"/organizations/{organization['id']}/lifecycle-events")
    assert org_events.status_code == 200
    assert len(org_events.json()) == 1


def test_lifecycle_events_are_ordered_and_validate_event_type() -> None:
    _organization, _project, package = _package()
    base = datetime.now(UTC)
    for event_type, offset in [("FAILURE", 2), ("INSTALLATION", 1)]:
        response = client.post(
            f"/packages/{package['id']}/lifecycle-events",
            json={
                "asset_id": "ASSET-001",
                "event_type": event_type,
                "event_date": (base + timedelta(days=offset)).isoformat(),
                "description": event_type.title(),
            },
        )
        assert response.status_code == 201

    events = client.get(f"/packages/{package['id']}/lifecycle-events")
    assert events.status_code == 200
    assert [item["event_type"] for item in events.json()] == ["INSTALLATION", "FAILURE"]

    invalid = client.post(
        f"/packages/{package['id']}/lifecycle-events",
        json={
            "asset_id": "ASSET-001",
            "event_type": "UNSUPPORTED",
            "event_date": base.isoformat(),
            "description": "Invalid event",
        },
    )
    assert invalid.status_code == 422


def test_lifecycle_event_rejects_offer_from_another_package() -> None:
    _organization, _project, package = _package()
    second_project = client.post(
        "/projects",
        json={"organization_id": 1, "name": "Second Project"},
    ).json()
    second_package = client.post(
        "/packages",
        json={
            "project_id": second_project["id"],
            "name": "Second Package",
            "category": "MOTOR",
            "mode": "STANDARD",
        },
    ).json()
    offer = client.post(
        f"/packages/{second_package['id']}/offers",
        json={"vendor_name": "Other Vendor"},
    ).json()

    response = client.post(
        f"/packages/{package['id']}/lifecycle-events",
        json={
            "asset_id": "ASSET-001",
            "event_type": "DELIVERY",
            "event_date": "2026-10-05T10:00:00Z",
            "description": "Wrong package offer",
            "offer_id": offer["id"],
        },
    )
    assert response.status_code == 422


def test_lifecycle_event_tenant_isolation() -> None:
    _organization, _project, package = _package()
    created = client.post(
        f"/packages/{package['id']}/lifecycle-events",
        json={
            "asset_id": "ASSET-001",
            "event_type": "INSTALLATION",
            "event_date": "2026-10-05T10:00:00Z",
            "description": "Installed.",
        },
    )
    assert created.status_code == 201

    outsider = client.post(
        "/auth/register",
        json={"email": "lifecycle-outsider@example.com", "password": "correct-horse-battery"},
    )
    assert outsider.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "lifecycle-outsider@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200

    token = login.json()["access_token"]
    hidden = client.get(
        f"/packages/{package['id']}/lifecycle-events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hidden.status_code == 404
