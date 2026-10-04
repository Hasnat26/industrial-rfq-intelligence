from fastapi.testclient import TestClient

from freellmpool.api import app
from freellmpool.api.db import Base, engine


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_project_epc_gate() -> None:
    organization = client.post("/organizations", json={"name": "Demo EPC"}).json()
    project = client.post("/projects", json={"organization_id": organization["id"], "name": "Project A"}).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "VFD Package",
            "category": "VFD",
            "mode": "PROJECT_EPC",
            "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}],
        },
    ).json()
    rfq = client.get(f"/packages/{package['id']}/rfq")
    assert rfq.status_code == 200
    assert rfq.json()["requirements"][0]["parameter"] == "Rated voltage"

    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "price": "10000", "currency": "USD"},
    )
    assert offer.status_code == 201
    claim = client.post(
        f"/offers/{offer.json()['id']}/claims",
        json={"parameter": "Rated voltage", "value": "415 V", "evidence": "Vendor quotation p.1", "claim_status": "VERIFIED"},
    )
    assert claim.status_code == 201
    comparison = client.get(f"/packages/{package['id']}/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["rows"][0]["status"] == "COMPLIANT"
    blocked = client.post(f"/packages/{package['id']}/commercial-open")
    assert blocked.status_code == 409
    locked = client.post(f"/packages/{package['id']}/technical-lock")
    assert locked.status_code == 200
    opened = client.post(f"/packages/{package['id']}/commercial-open")
    assert opened.status_code == 200
    assert opened.json()["commercial_evaluation_open"] is True


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
