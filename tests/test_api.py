from __future__ import annotations

import importlib
import io
import json
import os

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from freellmpool.api import app
from freellmpool.api.db import Base, engine

client = TestClient(app)


def _pdf_pages(count: int) -> bytes:
    buffer = io.BytesIO()
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    return buffer.getvalue()


def _blank_pdf() -> bytes:
    return _pdf_pages(1)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)
    registered = client.post(
        "/auth/register",
        json={"email": "engineer@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "engineer@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def test_project_epc_gate() -> None:
    organization = client.post("/organizations", json={"name": "Demo EPC"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project A"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "VFD Package",
            "category": "VFD",
            "mode": "PROJECT_EPC",
            "requirements": [
                {
                    "tag": "R-01",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                }
            ],
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
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "Vendor quotation p.1",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 201
    comparison = client.get(f"/packages/{package['id']}/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["rows"][0]["status"] == "COMPLIANT"
    blocked = client.post(f"/packages/{package['id']}/commercial-open")
    assert blocked.status_code == 409
    premature_lock = client.post(f"/packages/{package['id']}/technical-lock")
    assert premature_lock.status_code == 409
    deviation = client.post(
        f"/offers/{offer.json()['id']}/deviations",
        json={
            "parameter": "Rated voltage",
            "severity": "MINOR",
            "description": "Vendor proposes equivalent 400 V design.",
        },
    )
    assert deviation.status_code == 201
    premature_lock_with_issue = client.post(f"/packages/{package['id']}/technical-lock")
    assert premature_lock_with_issue.status_code == 409
    clarification = client.post(
        f"/offers/{offer.json()['id']}/clarifications",
        json={"question": "Confirm final voltage basis.", "status": "ANSWERED", "response": "415 V"},
    )
    assert clarification.status_code == 201
    resolved_deviation = client.post(
        f"/deviations/{deviation.json()['id']}/resolve",
        json={"note": "Engineering review accepted the deviation."},
    )
    assert resolved_deviation.status_code == 200
    assert resolved_deviation.json()["status"] == "RESOLVED"
    evaluated = client.post(
        f"/offers/{offer.json()['id']}/technical-status",
        json={"status": "ACCEPTED_WITH_DEVIATION"},
    )
    assert evaluated.status_code == 200
    locked = client.post(f"/packages/{package['id']}/technical-lock")
    assert locked.status_code == 200
    opened = client.post(f"/packages/{package['id']}/commercial-open")
    assert opened.status_code == 200
    assert opened.json()["commercial_evaluation_open"] is True


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_technical_status_cannot_change_after_commercial_open() -> None:
    organization = client.post("/organizations", json={"name": "Org B"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project B"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "mode": "PROJECT_EPC",
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor B"},
    ).json()
    status_response = client.post(
        f"/offers/{offer['id']}/technical-status",
        json={"status": "REJECTED"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["technical_status"] == "REJECTED"
    locked = client.post(f"/packages/{package['id']}/technical-lock")
    assert locked.status_code == 200
    opened = client.post(f"/packages/{package['id']}/commercial-open")
    assert opened.status_code == 200
    blocked = client.post(
        f"/offers/{offer['id']}/technical-status",
        json={"status": "ACCEPTED"},
    )
    assert blocked.status_code == 409


def test_vendor_document_ingestion() -> None:
    organization = client.post("/organizations", json={"name": "Org Documents"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Document Project"},
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
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor Docs"},
    ).json()
    response = client.post(
        f"/offers/{offer['id']}/documents",
        files={"file": ("quotation.txt", b"Rated voltage: 415 V", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["filename"] == "quotation.txt"
    assert response.json()["page_count"] == 1
    document = client.get(f"/documents/{response.json()['id']}")
    assert document.status_code == 200


def test_vendor_offer_revision() -> None:
    organization = client.post("/organizations", json={"name": "Org Revision"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Revision Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "VFD Package",
            "category": "VFD",
            "mode": "PROJECT_EPC",
            "requirements": [
                {
                    "tag": "R-01",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                }
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={
            "vendor_name": "Vendor Revision",
            "technical_revision": "R1",
            "price": "10000",
            "currency": "USD",
        },
    ).json()
    claim = client.post(
        f"/offers/{offer['id']}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "quotation p.1",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 201
    revision = client.post(
        f"/offers/{offer['id']}/revisions",
        json={"technical_revision": "R2"},
    )
    assert revision.status_code == 201
    assert revision.json()["technical_revision"] == "R2"
    duplicate = client.post(
        f"/offers/{offer['id']}/revisions",
        json={"technical_revision": "R2"},
    )
    assert duplicate.status_code == 409
    offers = client.get(f"/packages/{package['id']}/offers").json()
    assert [item["technical_revision"] for item in offers] == ["R1", "R2"]
    assert offers[0]["id"] == offer["id"]
    comparison = client.get(f"/packages/{package['id']}/comparison")
    assert comparison.status_code == 200
    rows = comparison.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["status"] == "COMPLIANT"


def _seed_package(mode: str = "STANDARD") -> dict:
    organization = client.post(
        "/organizations", json={"name": f"Org Batch {os.urandom(4).hex()}"}
    ).json()
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
            "mode": mode,
            "requirements": [
                {
                    "tag": "R-01",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                }
            ],
        },
    ).json()
    return {"organization": organization, "project": project, "package": package}


def _post_batch(package_id: int, entries: list, files: list):
    return client.post(
        f"/packages/{package_id}/quotations/batch",
        data={"entries": json.dumps(entries)},
        files=[("files", (name, body, content_type)) for name, body, content_type in files],
    )


def _seed_offer(mode: str = "PROJECT_EPC") -> dict:
    organization = client.post("/organizations", json={"name": f"Org {mode} {os.urandom(4).hex()}"}).json()
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
            "mode": mode,
            "requirements": [
                {
                    "tag": "R-01",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                }
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor Flow", "price": "5000", "currency": "USD"},
    ).json()
    return {"package": package, "offer": offer}


def test_document_ingestion_formats_and_rejections() -> None:
    seeded = _seed_offer(mode="STANDARD")
    offer_id = seeded["offer"]["id"]

    markdown = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("technical-offer.md", b"# Offer\nRated voltage: 415 V", "text/markdown")},
    )
    assert markdown.status_code == 201
    assert markdown.json()["filename"] == "technical-offer.md"
    assert markdown.json()["page_count"] == 1
    assert markdown.json()["pages"][0]["page_number"] == 1

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    pdf = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("quotation.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert pdf.status_code == 201
    assert pdf.json()["filename"] == "quotation.pdf"
    assert pdf.json()["page_count"] == 1

    unsupported = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("tool.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert unsupported.status_code == 415

    traversal = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("../../evil.txt", b"Rated voltage: 415 V", "text/plain")},
    )
    assert traversal.status_code == 201
    stored_name = traversal.json()["filename"]
    assert stored_name == "evil.txt"
    assert "/" not in stored_name and ".." not in stored_name

    oversized = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("big.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")},
    )
    assert oversized.status_code == 413

    fetched = client.get(f"/documents/{markdown.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["filename"] == "technical-offer.md"
    assert client.get("/documents/999999").status_code == 404


def test_document_upload_blocked_after_technical_lock() -> None:
    seeded = _seed_offer()
    offer_id = seeded["offer"]["id"]
    package_id = seeded["package"]["id"]
    accepted = client.post(
        f"/offers/{offer_id}/technical-status",
        json={"status": "ACCEPTED"},
    )
    assert accepted.status_code == 200
    locked = client.post(f"/packages/{package_id}/technical-lock")
    assert locked.status_code == 200
    blocked = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("late.txt", b"more evidence", "text/plain")},
    )
    assert blocked.status_code == 409


def test_evidence_traceability() -> None:
    seeded = _seed_offer(mode="STANDARD")
    offer_id = seeded["offer"]["id"]
    document = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("nameplate.pdf", _blank_pdf(), "application/pdf")},
    ).json()

    linked = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "nameplate.pdf p.1",
            "claim_status": "VERIFIED",
            "source_document_id": document["id"],
            "source_page": 1,
            "source_section": "Nameplate",
        },
    )
    assert linked.status_code == 201

    unlinked_location = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "source_page": 1,
        },
    )
    assert unlinked_location.status_code == 422

    other = _seed_offer(mode="STANDARD")
    foreign_document = client.post(
        f"/offers/{other['offer']['id']}/documents",
        files={"file": ("other.txt", b"other vendor", "text/plain")},
    ).json()
    foreign = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "source_document_id": foreign_document["id"],
            "source_page": 1,
        },
    )
    assert foreign.status_code == 404

    bad_status = client.post(
        f"/offers/{offer_id}/claims",
        json={"parameter": "Rated voltage", "value": "415 V", "claim_status": "MAGIC"},
    )
    assert bad_status.status_code == 422

    evidence = client.get(f"/packages/{seeded['package']['id']}/evidence")
    assert evidence.status_code == 200
    rows = evidence.json()["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["vendor"] == "Vendor Flow"
    assert row["technical_revision"] == "R1"
    assert row["source_document_filename"] == "nameplate.pdf"
    assert row["page"] == 1
    assert row["section"] == "Nameplate"
    assert row["claim_status"] == "VERIFIED"
    assert row["review_required"] == "NO"


def test_technical_freeze_blocks_claims_revisions_documents() -> None:
    seeded = _seed_offer()
    offer_id = seeded["offer"]["id"]
    package_id = seeded["package"]["id"]

    hidden = client.get(f"/packages/{package_id}/offers").json()
    assert hidden[0]["price"] is None

    accepted = client.post(
        f"/offers/{offer_id}/technical-status",
        json={"status": "ACCEPTED"},
    )
    assert accepted.status_code == 200
    assert client.post(f"/packages/{package_id}/technical-lock").status_code == 200

    late_claim = client.post(
        f"/offers/{offer_id}/claims",
        json={"parameter": "Rated voltage", "value": "415 V"},
    )
    assert late_claim.status_code == 409
    late_revision = client.post(
        f"/offers/{offer_id}/revisions",
        json={"technical_revision": "R2"},
    )
    assert late_revision.status_code == 409
    late_status = client.post(
        f"/offers/{offer_id}/technical-status",
        json={"status": "REJECTED"},
    )
    assert late_status.status_code == 409

    opened = client.post(f"/packages/{package_id}/commercial-open")
    assert opened.status_code == 200
    revealed = client.get(f"/packages/{package_id}/offers").json()
    assert revealed[0]["price"] == "5000"
    post_open_claim = client.post(
        f"/offers/{offer_id}/claims",
        json={"parameter": "Rated voltage", "value": "415 V"},
    )
    assert post_open_claim.status_code == 409


def test_clarification_close_preserves_vendor_response() -> None:
    seeded = _seed_offer(mode="STANDARD")
    offer_id = seeded["offer"]["id"]
    clarification = client.post(
        f"/offers/{offer_id}/clarifications",
        json={
            "question": "Confirm voltage basis.",
            "status": "ANSWERED",
            "response": "415 V",
        },
    ).json()
    closed = client.post(
        f"/clarifications/{clarification['id']}/close",
        json={"note": "Engineering accepted the answer."},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["response"] == "415 V"
    assert closed.json()["resolution"] == "Engineering accepted the answer."
    again = client.post(
        f"/clarifications/{clarification['id']}/close",
        json={"note": "Second note must not overwrite."},
    )
    assert again.status_code == 409

    deviation = client.post(
        f"/offers/{offer_id}/deviations",
        json={
            "parameter": "Rated voltage",
            "severity": "MAJOR",
            "description": "Offers 400 V design.",
        },
    ).json()
    resolved = client.post(
        f"/deviations/{deviation['id']}/resolve",
        json={"note": "Accepted by engineering."},
    )
    assert resolved.status_code == 200
    reresolve = client.post(
        f"/deviations/{deviation['id']}/resolve",
        json={"note": "Overwrite attempt."},
    )
    assert reresolve.status_code == 409


def test_deviation_creation_only_permits_open_state() -> None:
    seeded = _seed_offer(mode="STANDARD")
    offer_id = seeded["offer"]["id"]

    terminal = client.post(
        f"/offers/{offer_id}/deviations",
        json={
            "parameter": "Rated voltage",
            "severity": "MINOR",
            "description": "Shortcut attempt.",
            "status": "RESOLVED",
        },
    )
    assert terminal.status_code == 422
    disposition = client.post(
        f"/offers/{offer_id}/deviations",
        json={
            "parameter": "Rated voltage",
            "severity": "MINOR",
            "description": "Disposition attempt.",
            "status": "ACCEPTED",
        },
    )
    assert disposition.status_code == 422

    created = client.post(
        f"/offers/{offer_id}/deviations",
        json={
            "parameter": "Rated voltage",
            "severity": "MINOR",
            "description": "Offers 400 V design.",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "OPEN"
    resolved = client.post(
        f"/deviations/{created.json()['id']}/resolve",
        json={"note": "Engineering accepted the deviation."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolution"] == "Engineering accepted the deviation."


def test_clarification_creation_only_permits_non_terminal_states() -> None:
    seeded = _seed_offer(mode="STANDARD")
    offer_id = seeded["offer"]["id"]

    closed_directly = client.post(
        f"/offers/{offer_id}/clarifications",
        json={"question": "Shortcut attempt.", "status": "CLOSED"},
    )
    assert closed_directly.status_code == 422

    opened = client.post(
        f"/offers/{offer_id}/clarifications",
        json={"question": "Confirm voltage basis."},
    )
    assert opened.status_code == 201
    assert opened.json()["status"] == "OPEN"
    closed = client.post(
        f"/clarifications/{opened.json()['id']}/close",
        json={"note": "No vendor answer received; closed for review."},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["resolution"] == "No vendor answer received; closed for review."

    answered = client.post(
        f"/offers/{offer_id}/clarifications",
        json={"question": "Confirm frequency.", "status": "ANSWERED", "response": "50 Hz"},
    )
    assert answered.status_code == 201
    closed_answered = client.post(
        f"/clarifications/{answered.json()['id']}/close",
        json={"note": "Engineering accepted the answer."},
    )
    assert closed_answered.status_code == 200
    assert closed_answered.json()["response"] == "50 Hz"
    assert closed_answered.json()["status"] == "CLOSED"


def test_duplicate_initial_offer_protection() -> None:
    seeded = _seed_offer(mode="PROJECT_EPC")
    package_id = seeded["package"]["id"]

    exact = client.post(
        f"/packages/{package_id}/offers",
        json={"vendor_name": "Vendor Flow"},
    )
    assert exact.status_code == 409

    variant = client.post(
        f"/packages/{package_id}/offers",
        json={"vendor_name": "  vendor\tFLOW  "},
    )
    assert variant.status_code == 409

    other_revision = client.post(
        f"/packages/{package_id}/offers",
        json={"vendor_name": "Vendor Flow", "technical_revision": "R2"},
    )
    assert other_revision.status_code == 201

    other_vendor = client.post(
        f"/packages/{package_id}/offers",
        json={"vendor_name": "Vendor Other"},
    )
    assert other_vendor.status_code == 201

    offers = client.get(f"/packages/{package_id}/offers").json()
    revisions = {
        (item["vendor_name"], item["technical_revision"]) for item in offers
    }
    assert revisions == {("Vendor Flow", "R1"), ("Vendor Flow", "R2"), ("Vendor Other", "R1")}


def test_duplicate_offer_database_backstop_handles_races(monkeypatch) -> None:
    seeded = _seed_offer(mode="PROJECT_EPC")
    package_id = seeded["package"]["id"]

    app_module = importlib.import_module("freellmpool.api.app")
    monkeypatch.setattr(app_module, "_find_duplicate_offer", lambda *_args, **_kwargs: None)

    raced = client.post(
        f"/packages/{package_id}/offers",
        json={"vendor_name": "vendor flow"},
    )
    assert raced.status_code == 409

    offers = client.get(f"/packages/{package_id}/offers").json()
    assert len(offers) == 1


def test_claim_source_page_must_exist_in_document() -> None:
    seeded = _seed_offer(mode="STANDARD")
    offer_id = seeded["offer"]["id"]

    one_page = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("single.txt", b"Rated voltage: 415 V", "text/plain")},
    ).json()
    assert one_page["page_count"] == 1

    valid_first = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "source_document_id": one_page["id"],
            "source_page": 1,
        },
    )
    assert valid_first.status_code == 201

    zero_page = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "source_document_id": one_page["id"],
            "source_page": 0,
        },
    )
    assert zero_page.status_code == 422

    beyond = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "source_document_id": one_page["id"],
            "source_page": 9999,
        },
    )
    assert beyond.status_code == 422
    assert "source_page" in beyond.json()["detail"]

    two_pages = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("double.pdf", _pdf_pages(2), "application/pdf")},
    ).json()
    assert two_pages["page_count"] == 2
    valid_last = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "source_document_id": two_pages["id"],
            "source_page": 2,
        },
    )
    assert valid_last.status_code == 201
    over_last = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "source_document_id": two_pages["id"],
            "source_page": 3,
        },
    )
    assert over_last.status_code == 422

    foreign = _seed_offer(mode="STANDARD")
    foreign_doc = client.post(
        f"/offers/{foreign['offer']['id']}/documents",
        files={"file": ("foreign.txt", b"other vendor", "text/plain")},
    ).json()
    cross = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "source_document_id": foreign_doc["id"],
            "source_page": 1,
        },
    )
    assert cross.status_code == 404


def test_batch_quotation_ingestion_creates_offers_and_documents() -> None:
    seeded = _seed_package(mode="STANDARD")
    package_id = seeded["package"]["id"]
    response = _post_batch(
        package_id,
        entries=[
            {
                "vendor_name": "Vendor Alpha",
                "price": "1000",
                "currency": "USD",
                "source_text": "Rated voltage: 415 V",
            },
            {
                "vendor_name": "Vendor Beta",
                "price": "1100",
                "currency": "USD",
                "source_text": "Rated voltage: 400 V",
            },
        ],
        files=[
            ("alpha.txt", b"Rated voltage: 415 V", "text/plain"),
            ("beta.txt", b"Rated voltage: 400 V", "text/plain"),
        ],
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["package_id"] == package_id
    assert len(payload["offers"]) == 2
    assert [offer["vendor_name"] for offer in payload["offers"]] == [
        "Vendor Alpha",
        "Vendor Beta",
    ]
    assert payload["offers"][0]["price"] == "1000"
    # Each ingested quotation carries its own extracted, retrievable document.
    for document_id, expected_name in zip(
        payload["document_ids"], ["alpha.txt", "beta.txt"], strict=True
    ):
        document = client.get(f"/documents/{document_id}")
        assert document.status_code == 200
        assert document.json()["filename"] == expected_name
        assert document.json()["page_count"] == 1
    offers = client.get(f"/packages/{package_id}/offers").json()
    assert [offer["vendor_name"] for offer in offers] == ["Vendor Alpha", "Vendor Beta"]


def test_batch_quotation_ingestion_is_atomic_on_duplicate_vendor() -> None:
    seeded = _seed_package(mode="STANDARD")
    package_id = seeded["package"]["id"]
    first = _post_batch(
        package_id,
        entries=[{"vendor_name": "Vendor Alpha"}],
        files=[("alpha.txt", b"Rated voltage: 415 V", "text/plain")],
    )
    assert first.status_code == 201, first.text
    duplicate = _post_batch(
        package_id,
        entries=[
            {"vendor_name": "Vendor Gamma"},
            {"vendor_name": "vendor  alpha"},
        ],
        files=[
            ("gamma.txt", b"Rated voltage: 415 V", "text/plain"),
            ("dup.txt", b"Rated voltage: 415 V", "text/plain"),
        ],
    )
    assert duplicate.status_code == 409
    # All-or-nothing: the accepted Vendor Gamma entry must not persist.
    offers = client.get(f"/packages/{package_id}/offers").json()
    assert [offer["vendor_name"] for offer in offers] == ["Vendor Alpha"]


def test_batch_quotation_ingestion_rejects_length_mismatch() -> None:
    seeded = _seed_package(mode="STANDARD")
    package_id = seeded["package"]["id"]
    mismatch = _post_batch(
        package_id,
        entries=[{"vendor_name": "Vendor Alpha"}, {"vendor_name": "Vendor Beta"}],
        files=[("alpha.txt", b"Rated voltage: 415 V", "text/plain")],
    )
    assert mismatch.status_code == 422
    empty = _post_batch(package_id, entries=[], files=[])
    assert empty.status_code == 422
    offers = client.get(f"/packages/{package_id}/offers").json()
    assert offers == []


def test_batch_quotation_ingestion_rejects_unsupported_document() -> None:
    seeded = _seed_package(mode="STANDARD")
    package_id = seeded["package"]["id"]
    unsupported = _post_batch(
        package_id,
        entries=[{"vendor_name": "Vendor Alpha"}, {"vendor_name": "Vendor Beta"}],
        files=[
            ("alpha.txt", b"Rated voltage: 415 V", "text/plain"),
            ("payload.exe", b"MZ\x90\x00", "application/octet-stream"),
        ],
    )
    assert unsupported.status_code == 415
    offers = client.get(f"/packages/{package_id}/offers").json()
    assert offers == []


def test_batch_quotation_ingestion_blocked_after_technical_lock() -> None:
    seeded = _seed_offer()  # PROJECT_EPC package with one offer
    package_id = seeded["package"]["id"]
    offer_id = seeded["offer"]["id"]
    accepted = client.post(
        f"/offers/{offer_id}/technical-status", json={"status": "ACCEPTED"}
    )
    assert accepted.status_code == 200
    locked = client.post(f"/packages/{package_id}/technical-lock")
    assert locked.status_code == 200
    blocked = _post_batch(
        package_id,
        entries=[{"vendor_name": "Vendor Late"}],
        files=[("late.txt", b"more evidence", "text/plain")],
    )
    assert blocked.status_code == 409


def test_batch_quotation_ingestion_requires_authentication() -> None:
    seeded = _seed_package(mode="STANDARD")
    package_id = seeded["package"]["id"]
    client.headers.pop("Authorization", None)
    unauthenticated = client.post(
        f"/packages/{package_id}/quotations/batch",
        data={"entries": json.dumps([{"vendor_name": "Vendor Alpha"}])},
        files=[("files", ("alpha.txt", b"Rated voltage: 415 V", "text/plain"))],
    )
    assert unauthenticated.status_code == 401
    assert "WWW-Authenticate" in unauthenticated.headers
    login = client.post(
        "/auth/login",
        json={"email": "engineer@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def test_batch_quotation_ingestion_cross_tenant_is_rejected() -> None:
    seeded = _seed_package(mode="STANDARD")
    package_id = seeded["package"]["id"]
    # A second, unrelated account must not ingest into the first org's package.
    outsider_register = client.post(
        "/auth/register",
        json={"email": "outsider-batch@example.com", "password": "correct-horse-battery"},
    )
    assert outsider_register.status_code == 201
    outsider_login = client.post(
        "/auth/login",
        json={"email": "outsider-batch@example.com", "password": "correct-horse-battery"},
    )
    assert outsider_login.status_code == 200
    outsider = {"Authorization": f"Bearer {outsider_login.json()['access_token']}"}
    client.headers.pop("Authorization", None)
    response = client.post(
        f"/packages/{package_id}/quotations/batch",
        data={"entries": json.dumps([{"vendor_name": "Vendor Alpha"}])},
        files=[("files", ("alpha.txt", b"Rated voltage: 415 V", "text/plain"))],
        headers=outsider,
    )
    assert response.status_code == 404
    # Restore the setup_function session for any subsequent tests.
    login = client.post(
        "/auth/login",
        json={"email": "engineer@example.com", "password": "correct-horse-battery"},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def test_product_category_catalog_requires_authentication() -> None:
    client.headers.pop("Authorization", None)
    response = client.get("/product-categories")
    assert response.status_code == 401


def test_product_category_catalog_returns_configured_categories() -> None:
    response = client.get("/product-categories")
    assert response.status_code == 200
    payload = response.json()
    keys = {item["key"] for item in payload}
    assert {"MOTOR", "VFD", "PLC", "INSTRUMENTATION", "VALVE", "SWITCHGEAR"} <= keys
    motor = next(item for item in payload if item["key"] == "MOTOR")
    assert motor["parameters"][0] == {
        "key": "rated_power",
        "label": "Rated power",
        "mandatory": True,
        "unit": "kW",
    }


def test_product_category_lookup_is_case_insensitive() -> None:
    response = client.get("/product-categories/motor")
    assert response.status_code == 200
    assert response.json()["key"] == "MOTOR"


def test_product_category_lookup_returns_404_for_unknown_category() -> None:
    response = client.get("/product-categories/does-not-exist")
    assert response.status_code == 404



def test_package_report_and_markdown_export() -> None:
    seeded = _seed_offer(mode="STANDARD")
    package_id = seeded["package"]["id"]
    offer_id = seeded["offer"]["id"]

    claim = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "Quotation p.1",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 201

    report = client.get(f"/packages/{package_id}/report")
    assert report.status_code == 200
    payload = report.json()
    assert payload["summary"]["requirements_checked"] == 1
    assert payload["summary"]["vendors_checked"] == 1
    assert payload["matrix"][0]["status"] == "COMPLIANT"
    assert payload["evidence_register"][0]["claim_status"] == "VERIFIED"

    markdown = client.get(f"/packages/{package_id}/report/markdown")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert 'filename="rfq-review-package-' in markdown.headers["content-disposition"]
    assert "# Industrial RFQ Engineering Review" in markdown.text
    assert "Technical compliance matrix" in markdown.text
