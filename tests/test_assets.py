from __future__ import annotations

from fastapi.testclient import TestClient

from freellmpool.api import app
from freellmpool.api.db import Base, engine

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)
    client.post("/auth/register", json={"email": "asset@example.com", "password": "correct-horse-battery"})
    login = client.post("/auth/login", json={"email": "asset@example.com", "password": "correct-horse-battery"})
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def _package() -> tuple[dict, dict]:
    organization = client.post("/organizations", json={"name": "Asset Org"}).json()
    project = client.post("/projects", json={"organization_id": organization["id"], "name": "Asset Project"}).json()
    package = client.post(
        "/packages",
        json={"project_id": project["id"], "name": "Motor Package", "category": "MOTOR", "mode": "STANDARD"},
    ).json()
    return organization, package


def test_asset_create_and_list() -> None:
    organization, package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "manufacturer": "ABB", "model": "M3BP 160", "part_number": "3GBA162410"},
    ).json()
    asset = client.post(
        f"/packages/{package['id']}/assets",
        json={
            "asset_id": "MOTOR-001",
            "offer_id": offer["id"],
            "manufacturer": "ABB",
            "model": "M3BP 160",
            "part_number": "3GBA162410",
            "serial_number": "SN-001",
            "installation_date": "2026-10-05T10:00:00Z",
            "commissioning_date": "2026-10-06T10:00:00Z",
            "warranty_start": "2026-10-06T10:00:00Z",
            "warranty_end": "2028-10-06T10:00:00Z",
        },
    )
    assert asset.status_code == 201, asset.text
    assert asset.json()["serial_number"] == "SN-001"
    assert client.get(f"/packages/{package['id']}/assets").status_code == 200
    assert len(client.get(f"/organizations/{organization['id']}/assets").json()) == 1


def test_asset_rejects_wrong_offer_and_duplicate() -> None:
    _organization, package = _package()
    second_project = client.post("/projects", json={"organization_id": 1, "name": "Second"}).json()
    second_package = client.post(
        "/packages", json={"project_id": second_project["id"], "name": "Second Package", "category": "MOTOR", "mode": "STANDARD"}
    ).json()
    foreign_offer = client.post(f"/packages/{second_package['id']}/offers", json={"vendor_name": "Other"}).json()
    wrong = client.post(
        f"/packages/{package['id']}/assets",
        json={"asset_id": "A-1", "offer_id": foreign_offer["id"]},
    )
    assert wrong.status_code == 422
    first = client.post(f"/packages/{package['id']}/assets", json={"asset_id": "A-1"})
    assert first.status_code == 201
    duplicate = client.post(f"/packages/{package['id']}/assets", json={"asset_id": "A-1"})
    assert duplicate.status_code == 409
