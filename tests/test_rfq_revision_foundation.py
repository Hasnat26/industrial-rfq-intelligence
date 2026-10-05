from __future__ import annotations

from fastapi.testclient import TestClient

from freellmpool.api.app import app
from freellmpool.api.db import (
    Base,
    ProcurementPackage,
    RfqRevision,
    SessionLocal,
    VendorOffer,
    engine,
)

client = TestClient(app)


def setup_function() -> None:
    """Reset the isolated API database before each foundation test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)
    registered = client.post(
        "/auth/register",
        json={"email": "rfq-foundation@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "rfq-foundation@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def test_new_package_creates_r1_and_binds_requirements_and_offer() -> None:
    organization = client.post("/organizations", json={"name": "RFQ Foundation Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Foundation Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "300 TPD Mill",
            "category": "PROCESS_PLANT",
            "requirements": [
                {
                    "tag": "R-01",
                    "parameter": "Production capacity",
                    "required_value": "300 TPD",
                },
                {
                    "tag": "R-02",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                },
            ],
        },
    )
    assert package.status_code == 201, package.text
    package_id = package.json()["id"]

    offer = client.post(
        f"/packages/{package_id}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    )
    assert offer.status_code == 201, offer.text
    offer_id = offer.json()["id"]

    session = SessionLocal()
    try:
        revision = session.query(RfqRevision).filter_by(package_id=package_id).one()
        persisted_offer = session.get(VendorOffer, offer_id)
        assert revision.revision == "R1"
        assert revision.status == "CURRENT"
        assert revision.reason == "Initial RFQ baseline"
        package_row = session.get(ProcurementPackage, package_id)
        assert package_row is not None
        assert package_row.current_rfq_revision_id == revision.id
        assert persisted_offer is not None
        assert persisted_offer.rfq_revision_id == revision.id
        assert all(item.rfq_revision_id == revision.id for item in revision.requirements)
        assert {item.parameter for item in revision.requirements} == {
            "Production capacity",
            "Rated voltage",
        }
    finally:
        session.close()



def test_generated_rfq_uses_only_current_revision_requirements() -> None:
    organization = client.post("/organizations", json={"name": "RFQ Generation Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
    ).json()

    revision = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Customer updated the motor duty.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "690 V"},
                {"tag": "R-02", "parameter": "Motor power", "required_value": "90 kW"},
            ],
        },
    )
    assert revision.status_code == 201, revision.text

    rfq = client.get(f"/packages/{package['id']}/rfq")
    assert rfq.status_code == 200, rfq.text
    assert rfq.json()["requirements"] == [
        {"tag": "R-01", "parameter": "Rated voltage", "required_value": "690 V", "requirement_type": "MANDATORY", "acceptance_rule": None},
        {"tag": "R-02", "parameter": "Motor power", "required_value": "90 kW", "requirement_type": "MANDATORY", "acceptance_rule": None},
    ]


def test_superseded_offer_cannot_change_workflow_status() -> None:
    organization = client.post("/organizations", json={"name": "RFQ Workflow Isolation Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    revision = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Customer revised voltage requirement.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "690 V"}
            ],
        },
    )
    assert revision.status_code == 201, revision.text

    technical = client.post(
        f"/offers/{offer['id']}/technical-status",
        json={"status": "ACCEPTED"},
    )
    assert technical.status_code == 409
    assert "superseded RFQ revision" in technical.json()["detail"]

def test_vendor_offer_revision_stays_on_current_rfq_baseline() -> None:
    organization = client.post("/organizations", json={"name": "RFQ Revision Link Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor B", "technical_revision": "R1"},
    ).json()

    revision = client.post(
        f"/offers/{offer['id']}/revisions",
        json={"technical_revision": "R2"},
    )
    assert revision.status_code == 201, revision.text

    session = SessionLocal()
    try:
        r1 = session.get(VendorOffer, offer["id"])
        r2 = session.get(VendorOffer, revision.json()["id"])
        assert r1.rfq_revision_id is not None
        assert r2.rfq_revision_id == r1.rfq_revision_id
    finally:
        session.close()

def test_technical_lock_requires_current_rfq_offer() -> None:
    organization = client.post("/organizations", json={"name": "RFQ Lock Isolation Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
    ).json()
    client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    revision = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Customer revised the voltage requirement.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "690 V"}
            ],
        },
    )
    assert revision.status_code == 201, revision.text

    lock = client.post(f"/packages/{package['id']}/technical-lock")
    assert lock.status_code == 409
    assert "current vendor offer" in lock.json()["detail"]


def test_workflow_counts_only_current_rfq_offers() -> None:
    organization = client.post("/organizations", json={"name": "RFQ Workflow Counts Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
    ).json()
    client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    revision = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Customer revised the voltage requirement.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "690 V"}
            ],
        },
    )
    assert revision.status_code == 201, revision.text

    workflow = client.get(f"/packages/{package['id']}/workflow")
    assert workflow.status_code == 200, workflow.text
    body = workflow.json()
    assert body["offer_count"] == 0
    assert body["technical_status_counts"] == {}
    assert body["open_deviation_count"] == 0
    assert body["open_clarification_count"] == 0

def test_cross_tenant_user_cannot_access_package_or_offer_workflow() -> None:
    organization = client.post("/organizations", json={"name": "Tenant A Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Tenant A Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Tenant A Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Tenant A Vendor", "technical_revision": "R1"},
    ).json()

    registered = client.post(
        "/auth/register",
        json={"email": "tenant-b@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201, registered.text
    login = client.post(
        "/auth/login",
        json={"email": "tenant-b@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200, login.text
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    revision = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Unauthorized cross-tenant revision.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "690 V"}
            ],
        },
    )
    assert revision.status_code == 404

    workflow = client.get(f"/packages/{package['id']}/workflow")
    assert workflow.status_code == 404

    technical = client.post(
        f"/offers/{offer['id']}/technical-status",
        json={"status": "ACCEPTED"},
    )
    assert technical.status_code == 404

def test_superseded_offer_cannot_mutate_claim_deviation_or_clarification_workflow() -> None:
    organization = client.post("/organizations", json={"name": "RFQ Stale Mutation Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    revision = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Customer revised the voltage requirement.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "690 V"}
            ],
        },
    )
    assert revision.status_code == 201, revision.text

    claim = client.post(
        f"/offers/{offer['id']}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "Legacy R1 evidence",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 409
    assert "superseded RFQ revision" in claim.json()["detail"]

    deviation = client.post(
        f"/offers/{offer['id']}/deviations",
        json={
            "parameter": "Rated voltage",
            "severity": "MAJOR",
            "description": "Legacy R1 deviation",
            "status": "OPEN",
        },
    )
    assert deviation.status_code == 409
    assert "superseded RFQ revision" in deviation.json()["detail"]

    preview = client.get(f"/offers/{offer['id']}/technical-clarification-package")
    assert preview.status_code == 409
    assert "superseded RFQ revision" in preview.json()["detail"]

    request = client.post(f"/offers/{offer['id']}/technical-clarification-request")
    assert request.status_code == 409
    assert "superseded RFQ revision" in request.json()["detail"]

def test_procurement_offer_mutations_are_audited() -> None:
    organization = client.post("/organizations", json={"name": "Audit Mutation Org"}).json()
    project = client.post(
        "/projects", json={"organization_id": organization["id"], "name": "Project"}
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Audit Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
    ).json()

    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    revision = client.post(
        f"/offers/{offer['id']}/revisions",
        json={"technical_revision": "R2", "source_text": "revised"},
    )
    assert revision.status_code == 201, revision.text

    revision_offer = revision.json()
    claim = client.post(
        f"/offers/{revision_offer['id']}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "Vendor document evidence",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 201, claim.text

    document = client.post(
        f"/offers/{revision_offer['id']}/documents",
        files={"file": ("offer.txt", b"Rated voltage: 415 V", "text/plain")},
    )
    assert document.status_code == 201, document.text

    audit = client.get(f"/packages/{package['id']}/audit")
    assert audit.status_code == 200, audit.text
    events = audit.json()
    event_types = [item["event_type"] for item in events]
    assert event_types[:3] == [
        "TECHNICAL_OFFER_CREATED",
        "TECHNICAL_OFFER_REVISION_CREATED",
        "VENDOR_CLAIM_CREATED",
    ]
    assert "VENDOR_DOCUMENT_UPLOADED" in event_types
    assert all(item["package_id"] == package["id"] for item in events)
    assert all(item["actor_user_id"] is not None for item in events)
    assert all(
        item["offer_id"] is None
        or item["offer_id"] in {offer["id"], revision_offer["id"]}
        for item in events
    )
