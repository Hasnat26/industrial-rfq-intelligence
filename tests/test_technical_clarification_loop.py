from __future__ import annotations

import io

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from freellmpool.api import app
from freellmpool.api.db import Base, engine

client = TestClient(app)


def _blank_pdf() -> bytes:
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    return buffer.getvalue()


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)
    registered = client.post(
        "/auth/register",
        json={"email": "clarification@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "clarification@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def _package() -> dict[str, object]:
    organization = client.post("/organizations", json={"name": "Clarification EPC"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    return client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "mode": "PROJECT_EPC",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
                {"tag": "R-02", "parameter": "Motor power", "required_value": "75 kW"},
            ],
        },
    ).json()


def test_vendor_specific_clarification_package_is_generated_from_gaps() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()
    claim = client.post(
        f"/offers/{offer['id']}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "quotation.pdf p.1",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 201

    response = client.get(f"/offers/{offer['id']}/technical-clarification-package")
    assert response.status_code == 200
    data = response.json()
    assert data["vendor"] == "Vendor A"
    assert len(data["gaps"]) == 1
    assert data["gaps"][0]["parameter"] == "Motor power"
    assert data["gaps"][0]["status"] == "UNVERIFIED"
    assert "75 kW" in data["gaps"][0]["request"]
    assert data["subject"].startswith("Technical Clarification Required")
    assert "Motor power" in data["body"]


def test_create_clarification_is_audited_and_sets_vendor_status() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    response = client.post(f"/offers/{offer['id']}/technical-clarification-request")
    assert response.status_code == 201
    data = response.json()
    assert len(data["clarification_ids"]) == 2

    offers = client.get(f"/packages/{package['id']}/offers")
    assert offers.status_code == 200
    assert offers.json()[0]["technical_status"] == "CLARIFICATION_REQUIRED"

    clarifications = client.get(f"/offers/{offer['id']}/clarifications")
    assert clarifications.status_code == 200
    persisted = clarifications.json()
    assert len(persisted) == 2
    assert all(item["rfq_revision_id"] is None for item in persisted)
    assert all(item["requirement_id"] is None for item in persisted)
    assert all(item["gap_type"] is None for item in persisted)
    assert all("evaluation_evidence" in item for item in persisted)

    audit = client.get(f"/packages/{package['id']}/audit")
    assert audit.status_code == 200
    events = [item["event_type"] for item in audit.json()]
    assert "TECHNICAL_CLARIFICATION_REQUESTED" in events

    second = client.post(f"/offers/{offer['id']}/technical-clarification-request")
    assert second.status_code == 201
    assert second.json()["clarification_ids"] == []


def test_technical_resubmission_creates_revision_and_reextracts_claims() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()
    client.post(f"/offers/{offer['id']}/technical-clarification-request")

    response = client.post(
        f"/offers/{offer['id']}/technical-resubmission",
        data={"technical_revision": "R2"},
        files={"file": ("VendorA_R2.txt", b"Rated voltage: 415 V\nMotor power: 75 kW\n", "text/plain")},
    )
    assert response.status_code == 201
    revision = response.json()
    assert revision["parent_offer_id"] == offer["id"]
    assert revision["technical_revision"] == "R2"
    assert revision["technical_status"] == "IN_REVIEW"

    comparison = client.get(f"/packages/{package['id']}/comparison")
    assert comparison.status_code == 200
    rows = comparison.json()["rows"]
    assert all(row["status"] == "COMPLIANT" for row in rows)
    assert {row["offered"] for row in rows} == {"415 V", "75 kW"}

    documents = client.get(f"/offers/{revision['id']}/clarifications")
    assert documents.status_code == 200

    audit = client.get(f"/packages/{package['id']}/audit").json()
    assert any(item["event_type"] == "TECHNICAL_OFFER_RESUBMITTED" for item in audit)


def test_resubmission_is_rejected_after_technical_lock() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()
    for parameter, value in [("Rated voltage", "415 V"), ("Motor power", "75 kW")]:
        assert client.post(
            f"/offers/{offer['id']}/claims",
            json={
                "parameter": parameter,
                "value": value,
                "evidence": "quotation.pdf p.1",
                "claim_status": "VERIFIED",
            },
        ).status_code == 201
    assert client.post(
        f"/offers/{offer['id']}/technical-status",
        json={"status": "ACCEPTED"},
    ).status_code == 200
    assert client.post(f"/packages/{package['id']}/technical-lock").status_code == 200

    response = client.post(
        f"/offers/{offer['id']}/technical-resubmission",
        data={"technical_revision": "R2"},
        files={"file": ("VendorA_R2.txt", b"Rated voltage: 415 V\nMotor power: 75 kW\n", "text/plain")},
    )
    assert response.status_code == 409
