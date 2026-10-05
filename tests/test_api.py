from __future__ import annotations

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
    blocked_by_answered_clarification = client.post(f"/packages/{package['id']}/technical-lock")
    assert blocked_by_answered_clarification.status_code == 409
    closed_clarification = client.post(
        f"/clarifications/{clarification.json()['id']}/close",
        json={"note": "Final answer accepted by engineering."},
    )
    assert closed_clarification.status_code == 200
    locked = client.post(f"/packages/{package['id']}/technical-lock")
    assert locked.status_code == 200
    opened = client.post(f"/packages/{package['id']}/commercial-open")
    assert opened.status_code == 200
    assert opened.json()["commercial_evaluation_open"] is True


def test_engineering_decision_summary_endpoint_is_auditable() -> None:
    organization = client.post("/organizations", json={"name": "Decision Summary"}).json()
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
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
                {"tag": "R-02", "parameter": "Motor power", "required_value": "75 kW"},
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    ).json()
    claim = client.post(
        f"/offers/{offer['id']}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "quotation.pdf, page 1",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 201

    response = client.get(f"/packages/{package['id']}/engineering-decision-summary")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "EVIDENCE_OR_DEVIATION_REVIEW_REQUIRED"
    profile = data["vendor_profiles"][0]
    assert profile["vendor"] == "Vendor A"
    assert profile["missing_evidence_count"] == 1
    assert profile["evidence_coverage_pct"] == 50.0
    assert data["review_actions"]


def test_package_report_contains_engineering_decision_summary() -> None:
    organization = client.post("/organizations", json={"name": "Report Summary"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Empty Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
            ],
        },
    ).json()
    response = client.get(f"/packages/{package['id']}/report")
    assert response.status_code == 200
    data = response.json()
    assert "decision_support" in data
    assert "engineering_decision_summary" in data
    assert data["engineering_decision_summary"]["status"] == "INSUFFICIENT_VENDOR_DATA"



def test_integrated_evaluation_endpoint_exposes_auditable_gates() -> None:
    organization = client.post("/organizations", json={"name": "Integrated Evaluation"}).json()
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
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={
            "vendor_name": "Vendor A",
            "technical_revision": "R1",
            "price": "10000",
            "currency": "USD",
            "lead_time": "8 weeks",
            "warranty": "24 months",
        },
    ).json()
    claim = client.post(
        f"/offers/{offer['id']}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "quote.pdf, page 1",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 201

    response = client.get(f"/packages/{package['id']}/integrated-evaluation")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMMERCIAL_REVIEW_REQUIRED"
    profile = data["vendor_profiles"][0]
    assert profile["technical_score"] == 100.0
    assert profile["technical_gate"] == "PASS"
    assert profile["commercial_gate"] == "REVIEW"
    assert "EVIDENCE_REVIEW" in profile["commercial_flags"]


def test_customer_web_app_exposes_batch_quotation_intake() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Upload vendor quotations" in response.text
    assert "quotations/batch" in response.text
    assert "FormData" in response.text


def test_batch_quotation_auto_extracts_claims_with_provenance() -> None:
    organization = client.post("/organizations", json={"name": "Auto Extract"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Motor Review"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
                {"tag": "R-02", "parameter": "Motor power", "required_value": "75 kW"},
            ],
        },
    ).json()
    response = client.post(
        f"/packages/{package['id']}/quotations/batch",
        data={"entries": json.dumps([{"vendor_name": "Vendor Alpha"}])},
        files=[(
            "files",
            (
                "alpha.txt",
                b"# Technical Data\nRated Voltage: 415 V\nMotor Power | 75 kW\nUnrelated: ignore",
                "text/plain",
            ),
        )],
    )
    assert response.status_code == 201, response.text
    comparison = client.get(f"/packages/{package['id']}/comparison")
    assert comparison.status_code == 200
    rows = comparison.json()["rows"]
    assert [row["status"] for row in rows] == ["COMPLIANT", "COMPLIANT"]

    evidence = client.get(f"/packages/{package['id']}/evidence")
    assert evidence.status_code == 200
    rows = evidence.json()["rows"]
    assert len(rows) == 2
    assert {row["claim_status"] for row in rows} == {"VERIFIED"}
    assert {row["source_page"] if "source_page" in row else row["page"] for row in rows} == {1}
    assert {row["source_document_filename"] for row in rows} == {"alpha.txt"}
    assert all("page 1:" in row["evidence"] for row in rows)


def test_batch_quotation_conflicting_explicit_claims_fail_closed() -> None:
    organization = client.post("/organizations", json={"name": "Conflict Check"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Motor Review"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
            ],
        },
    ).json()
    response = client.post(
        f"/packages/{package['id']}/quotations/batch",
        data={"entries": json.dumps([{"vendor_name": "Vendor Conflict"}])},
        files=[(
            "files",
            (
                "conflict.txt",
                b"Rated voltage: 415 V\nRated voltage: 400 V",
                "text/plain",
            ),
        )],
    )
    assert response.status_code == 201, response.text
    comparison = client.get(f"/packages/{package['id']}/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["rows"][0]["status"] == "UNVERIFIED"
    evidence = client.get(f"/packages/{package['id']}/evidence")
    assert evidence.status_code == 200
    assert len(evidence.json()["rows"]) == 2


def test_batch_quotation_missing_or_ambiguous_field_remains_unverified() -> None:
    organization = client.post("/organizations", json={"name": "Ambiguous Check"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Motor Review"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
            ],
        },
    ).json()
    response = client.post(
        f"/packages/{package['id']}/quotations/batch",
        data={"entries": json.dumps([{"vendor_name": "Vendor Ambiguous"}])},
        files=[(
            "files",
            (
                "ambiguous.txt",
                b"The vendor datasheet will confirm the final voltage selection during engineering review.",
                "text/plain",
            ),
        )],
    )
    assert response.status_code == 201, response.text
    evidence = client.get(f"/packages/{package['id']}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["rows"] == []
    comparison = client.get(f"/packages/{package['id']}/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["rows"][0]["status"] == "UNVERIFIED"
    evidence = client.get(f"/packages/{package['id']}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["rows"] == []


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
    assert revision.json()["parent_offer_id"] == offer["id"]
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


def test_batch_quotation_ingestion_is_atomic_and_persists_documents() -> None:
    seeded = _seed_package(mode="PROJECT_EPC")
    package_id = seeded["package"]["id"]
    entries = [
        {"vendor_name": "Vendor Alpha", "technical_revision": "R1", "price": "10000", "currency": "USD"},
        {"vendor_name": "Vendor Beta", "technical_revision": "R1", "price": "11000", "currency": "USD"},
    ]
    response = _post_batch(
        package_id,
        entries,
        [
            ("alpha.txt", b"Rated voltage: 415 V", "text/plain"),
            ("beta.txt", b"Rated voltage: 400 V", "text/plain"),
        ],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert len(data["offers"]) == 2
    assert len(data["document_ids"]) == 2
    offers = client.get(f"/packages/{package_id}/offers").json()
    assert [item["vendor_name"] for item in offers] == ["Vendor Alpha", "Vendor Beta"]
    for document_id in data["document_ids"]:
        document = client.get(f"/documents/{document_id}")
        assert document.status_code == 200
        assert document.json()["page_count"] == 1


def test_batch_quotation_ingestion_rejects_conflicts_without_partial_write() -> None:
    seeded = _seed_package(mode="STANDARD")
    package_id = seeded["package"]["id"]
    first = _post_batch(
        package_id,
        [{"vendor_name": "Vendor Alpha", "technical_revision": "R1"}],
        [("alpha.txt", b"Offer", "text/plain")],
    )
    assert first.status_code == 201
    before = client.get(f"/packages/{package_id}/offers").json()
    conflicting = _post_batch(
        package_id,
        [
            {"vendor_name": "Vendor Alpha", "technical_revision": "R1"},
            {"vendor_name": "Vendor Gamma", "technical_revision": "R1"},
        ],
        [
            ("alpha2.txt", b"Conflict", "text/plain"),
            ("gamma.txt", b"New offer", "text/plain"),
        ],
    )
    assert conflicting.status_code == 409
    after = client.get(f"/packages/{package_id}/offers").json()
    assert len(after) == len(before) == 1
    assert after[0]["vendor_name"] == "Vendor Alpha"


def test_batch_quotation_ingestion_requires_one_file_per_entry() -> None:
    seeded = _seed_package()
    response = _post_batch(
        seeded["package"]["id"],
        [{"vendor_name": "Vendor Alpha", "technical_revision": "R1"}],
        [],
    )
    assert response.status_code == 422


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


def test_decision_support_endpoint_returns_auditable_vendor_scores() -> None:
    organization = client.post("/organizations", json={"name": "Decision Support"}).json()
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
                {
                    "tag": "R-01",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                },
                {
                    "tag": "R-02",
                    "parameter": "Motor power",
                    "required_value": "75 kW",
                    "requirement_type": "OPTIONAL",
                },
            ],
        },
    ).json()
    for vendor in ("Vendor A", "Vendor B", "Vendor C"):
        offer = client.post(
            f"/packages/{package['id']}/offers",
            json={"vendor_name": vendor},
        ).json()
        if vendor == "Vendor A":
            claims = [
                ("Rated voltage", "415 V", "a.pdf p.1"),
                ("Motor power", "75 kW", "a.pdf p.1"),
            ]
        elif vendor == "Vendor B":
            claims = [
                ("Rated voltage", "400 V", "b.pdf p.1"),
                ("Motor power", "70 kW", "b.pdf p.1"),
            ]
        else:
            claims = []
        for parameter, value, evidence in claims:
            response = client.post(
                f"/offers/{offer['id']}/claims",
                json={
                    "parameter": parameter,
                    "value": value,
                    "evidence": evidence,
                    "claim_status": "VERIFIED",
                },
            )
            assert response.status_code == 201

    response = client.get(f"/packages/{package['id']}/decision-support")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["requirements_checked"] == 2
    assert data["vendors_checked"] == 3
    vendors = {item["vendor"]: item for item in data["vendors"]}
    assert vendors["Vendor A"]["technical_score"] == 100.0
    assert vendors["Vendor A"]["evidence_coverage_pct"] == 100.0
    assert vendors["Vendor B"]["technical_score"] == 33.33
    assert vendors["Vendor B"]["major_deviation_count"] == 1
    assert vendors["Vendor B"]["minor_deviation_count"] == 1
    assert vendors["Vendor C"]["technical_score"] == 0.0
    assert vendors["Vendor C"]["missing_evidence_count"] == 2
    assert data["formula"]["technical_score"] == "100 * weighted_points / weighted_requirements"

    repeated = client.get(f"/packages/{package['id']}/decision-support")
    assert repeated.status_code == 200
    assert repeated.json() == data


def test_decision_support_is_tenant_isolated() -> None:
    first = _seed_package()
    first_token = client.headers["Authorization"]

    registered = client.post(
        "/auth/register",
        json={"email": "second@example.com", "password": "second-password"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "second@example.com", "password": "second-password"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    second = client.post("/organizations", json={"name": "Other Tenant"}).json()
    other_project = client.post(
        "/projects",
        json={"organization_id": second["id"], "name": "Other Project"},
    ).json()
    other_package = client.post(
        "/packages",
        json={
            "project_id": other_project["id"],
            "name": "Other Package",
            "category": "MOTOR",
            "requirements": [
                {
                    "tag": "R-01",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                }
            ],
        },
    ).json()

    client.headers["Authorization"] = first_token
    forbidden = client.get(f"/packages/{other_package['id']}/decision-support")
    assert forbidden.status_code == 404
    allowed = client.get(f"/packages/{first['package']['id']}/decision-support")
    assert allowed.status_code == 200

def test_evidence_traceability() -> None:
    _seed_offer(mode="STANDARD")

def test_customer_can_configure_evaluation_weighting_and_it_locks_at_commercial_open() -> None:
    organization = client.post("/organizations", json={"name": "Weighting Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Weighted Package",
            "category": "MOTOR",
            "mode": "STANDARD",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
            ],
        },
    ).json()
    package_id = package["id"]

    default = client.get(f"/packages/{package_id}/evaluation-weighting")
    assert default.status_code == 200
    assert default.json()["technical_weight"] == 70.0
    assert default.json()["commercial_weight"] == 30.0
    assert default.json()["locked"] is False

    updated = client.put(
        f"/packages/{package_id}/evaluation-weighting",
        json={"technical_weight": 40, "commercial_weight": 60},
    )
    assert updated.status_code == 200
    assert updated.json()["technical_weight"] == 40.0
    assert updated.json()["commercial_weight"] == 60.0

    invalid = client.put(
        f"/packages/{package_id}/evaluation-weighting",
        json={"technical_weight": 40, "commercial_weight": 50},
    )
    assert invalid.status_code == 422

    opened = client.post(f"/packages/{package_id}/commercial-open")
    assert opened.status_code == 200

    locked = client.get(f"/packages/{package_id}/evaluation-weighting")
    assert locked.status_code == 200
    assert locked.json()["locked"] is True

    rejected = client.put(
        f"/packages/{package_id}/evaluation-weighting",
        json={"technical_weight": 70, "commercial_weight": 30},
    )
    assert rejected.status_code == 409


def test_evaluation_weighting_is_tenant_isolated() -> None:
    organization = client.post("/organizations", json={"name": "Tenant A"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Project A"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "Package A",
            "category": "MOTOR",
            "requirements": [],
        },
    ).json()

    client.post("/auth/register", json={"email": "other@example.com", "password": "correct-horse-battery"})
    login = client.post("/auth/login", json={"email": "other@example.com", "password": "correct-horse-battery"})
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    response = client.get(f"/packages/{package['id']}/evaluation-weighting")
    assert response.status_code == 404


def test_technical_status_rejects_backward_transition() -> None:
    seeded = _seed_offer()
    offer_id = seeded["offer"]["id"]

    accepted = client.post(
        f"/offers/{offer_id}/technical-status",
        json={"status": "ACCEPTED"},
    )
    assert accepted.status_code == 200

    backward = client.post(
        f"/offers/{offer_id}/technical-status",
        json={"status": "PENDING"},
    )
    assert backward.status_code == 409
    assert "invalid technical status transition" in backward.json()["detail"]


def test_technical_status_allows_normal_progression() -> None:
    seeded = _seed_offer()
    offer_id = seeded["offer"]["id"]

    for status_value in ("IN_REVIEW", "CLARIFICATION_REQUIRED", "ACCEPTED"):
        response = client.post(
            f"/offers/{offer_id}/technical-status",
            json={"status": status_value},
        )
        assert response.status_code == 200, response.text
        assert response.json()["technical_status"] == status_value
