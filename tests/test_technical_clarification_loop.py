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
    assert data["gaps"][0]["rfq_revision_id"] == 1
    assert data["gaps"][0]["requirement_id"] == 2
    assert data["gaps"][0]["gap_type"] == "MISSING"
    assert data["gaps"][0]["evidence"] == "No matching quotation field"
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
    assert {item["rfq_revision_id"] for item in persisted} == {1}
    assert {item["requirement_id"] for item in persisted} == {1, 2}
    assert {item["gap_type"] for item in persisted} == {"MISSING"}
    assert all(item["evaluated_offered"] is None for item in persisted)
    assert all(item["evaluation_status"] == "UNVERIFIED" for item in persisted)
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


def test_manual_clarification_create_persists_current_rfq_traceability() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    response = client.post(
        f"/offers/{offer['id']}/clarifications",
        json={
            "question": "Confirm final voltage basis.",
            "response": "415 V",
            "status": "ANSWERED",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["rfq_revision_id"] == 1
    assert data["requirement_id"] is None
    assert data["gap_type"] is None
    assert data["evaluated_offered"] is None
    assert data["evaluation_status"] is None
    assert data["evaluation_evidence"] is None


def test_clarification_lifecycle_open_answered_closed() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    created = client.post(
        f"/offers/{offer['id']}/clarifications",
        json={"question": "Confirm protection class."},
    )
    assert created.status_code == 201
    clarification_id = created.json()["id"]
    assert created.json()["status"] == "OPEN"

    answered = client.post(
        f"/clarifications/{clarification_id}/answer",
        json={"response": "IP55"},
    )
    assert answered.status_code == 200
    assert answered.json()["status"] == "ANSWERED"
    assert answered.json()["response"] == "IP55"

    closed = client.post(
        f"/clarifications/{clarification_id}/close",
        json={"note": "Vendor response reviewed."},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["resolution"] == "Vendor response reviewed."

    duplicate = client.post(
        f"/clarifications/{clarification_id}/answer",
        json={"response": "IP66"},
    )
    assert duplicate.status_code == 409


def test_clarification_close_requires_answered_status() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    created = client.post(
        f"/offers/{offer['id']}/clarifications",
        json={"question": "Confirm protection class."},
    )
    assert created.status_code == 201

    response = client.post(
        f"/clarifications/{created.json()['id']}/close",
        json={"note": "Cannot close unanswered clarification."},
    )
    assert response.status_code == 409


def test_clarification_lifecycle_is_audited() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()

    created = client.post(
        f"/offers/{offer['id']}/clarifications",
        json={"question": "Confirm protection class."},
    )
    assert created.status_code == 201
    clarification_id = created.json()["id"]

    answered = client.post(
        f"/clarifications/{clarification_id}/answer",
        json={"response": "IP55"},
    )
    assert answered.status_code == 200

    closed = client.post(
        f"/clarifications/{clarification_id}/close",
        json={"note": "Vendor response reviewed."},
    )
    assert closed.status_code == 200

    audit = client.get(f"/packages/{package['id']}/audit")
    assert audit.status_code == 200
    events = [
        item
        for item in audit.json()
        if item["event_type"].startswith("CLARIFICATION_")
    ]
    assert [(item["event_type"], item["from_status"], item["to_status"]) for item in events] == [
        ("CLARIFICATION_CREATED", None, "OPEN"),
        ("CLARIFICATION_ANSWERED", "OPEN", "ANSWERED"),
        ("CLARIFICATION_CLOSED", "ANSWERED", "CLOSED"),
    ]
    assert all(item["offer_id"] == offer["id"] for item in events)
    assert all(item["actor_user_id"] is not None for item in events)


def test_rfq_revision_supersedes_old_baseline_and_reanchors_evaluation() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()
    assert offer["technical_revision"] == "R1"

    revision = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Customer updated the required motor duty.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
                {"tag": "R-02", "parameter": "Motor power", "required_value": "90 kW"},
            ],
        },
    )
    assert revision.status_code == 201
    data = revision.json()
    assert data["revision"] == "R2"
    assert data["status"] == "CURRENT"
    assert data["reason"] == "Customer updated the required motor duty."

    offers = client.get(f"/packages/{package['id']}/offers")
    assert offers.status_code == 200
    assert offers.json()[0]["technical_status"] == "SUPERSEDED"

    evaluation = client.get(f"/packages/{package['id']}/technical-evaluation")
    assert evaluation.status_code == 200
    assert evaluation.json()["rfq_revision"] == "R2"
    assert evaluation.json()["rfq_revision_id"] == data["id"]
    assert evaluation.json()["rows"] == []
    stale_clarification = client.post(
        f"/offers/{offer['id']}/clarifications",
        json={"question": "Stale offer question", "status": "OPEN"},
    )
    assert stale_clarification.status_code == 409
    stale_revision = client.post(
        f"/offers/{offer['id']}/revisions",
        json={"technical_revision": "R2", "source_text": "stale resubmission"},
    )
    assert stale_revision.status_code == 409
    comparison = client.get(f"/packages/{package['id']}/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["rows"] == []
    decision_support = client.get(f"/packages/{package['id']}/decision-support")
    assert decision_support.status_code == 200
    assert decision_support.json()["vendors_checked"] == 0
    integrated = client.get(f"/packages/{package['id']}/integrated-evaluation")
    assert integrated.status_code == 200
    assert integrated.json()["vendor_profiles"] == []
    engineering = client.get(f"/packages/{package['id']}/engineering-decision-summary")
    assert engineering.status_code == 200
    assert engineering.json()["vendor_profiles"] == []
    evidence = client.get(f"/packages/{package['id']}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["rows"] == []
    stale_decision = client.post(
        f"/packages/{package['id']}/decision",
        json={"selected_offer_id": offer["id"], "rationale": "stale offer must be rejected"},
    )
    assert stale_decision.status_code == 409

    audit = client.get(f"/packages/{package['id']}/audit")
    assert audit.status_code == 200
    events = audit.json()
    assert any(item["event_type"] == "RFQ_REVISION_CREATED" for item in events)
    assert any(
        item["event_type"] == "RFQ_REVISION_SUPERSEDED_OFFER"
        and item["offer_id"] == offer["id"]
        for item in events
    )


def test_rfq_revision_is_blocked_after_technical_lock() -> None:
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

    # The old offer belongs to R1 and must not reappear in R2 commercial comparison.
    # This endpoint is gated by commercial-open, so the assertion is exercised after the R2 cycle is opened.
    assert client.post(f"/packages/{package['id']}/commercial-open").status_code == 200
    commercial = client.get(f"/packages/{package['id']}/commercial-comparison")
    assert commercial.status_code == 200
    assert commercial.json()["rows"] == []

    response = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Late customer change.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
            ],
        },
    )
    assert response.status_code == 409


def test_whitespace_only_clarification_answer_is_rejected() -> None:
    package = _package()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()
    created = client.post(
        f"/offers/{offer['id']}/clarifications",
        json={"question": "Confirm protection class."},
    )
    assert created.status_code == 201

    response = client.post(
        f"/clarifications/{created.json()['id']}/answer",
        json={"response": "   "},
    )
    assert response.status_code == 422


def test_rfq_revision_ignores_superseded_offers_when_locking_new_cycle() -> None:
    package = _package()
    old_offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()
    client.post(f"/offers/{old_offer['id']}/technical-clarification-request")

    revision = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "Customer updated the required motor duty.",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
                {"tag": "R-02", "parameter": "Motor power", "required_value": "90 kW"},
            ],
        },
    )
    assert revision.status_code == 201

    new_offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor B", "technical_revision": "R1"},
    ).json()
    for parameter, value in [("Rated voltage", "415 V"), ("Motor power", "90 kW")]:
        assert client.post(
            f"/offers/{new_offer['id']}/claims",
            json={
                "parameter": parameter,
                "value": value,
                "evidence": "quotation-r2.pdf p.1",
                "claim_status": "VERIFIED",
            },
        ).status_code == 201
    assert client.post(
        f"/offers/{new_offer['id']}/technical-status",
        json={"status": "ACCEPTED"},
    ).status_code == 200

    locked = client.post(f"/packages/{package['id']}/technical-lock")
    assert locked.status_code == 200


def test_rfq_revision_rejects_blank_reason() -> None:
    package = _package()
    response = client.post(
        f"/packages/{package['id']}/rfq-revisions",
        json={
            "reason": "   ",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
            ],
        },
    )
    assert response.status_code == 422
