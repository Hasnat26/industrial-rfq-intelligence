from __future__ import annotations

from typing import Any

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
        json={"email": "pilot@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "pilot@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def _claim(offer_id: int, parameter: str, value: str, evidence: str) -> None:
    response = client.post(
        f"/offers/{offer_id}/claims",
        json={
            "parameter": parameter,
            "value": value,
            "evidence": evidence,
            "claim_status": "VERIFIED",
        },
    )
    assert response.status_code == 201, response.text


def _run_pilot_flow() -> dict[str, Any]:
    """Drive the documented 415 V pilot workflow through the API.

    Returns the identifiers later assertions need. Gate probes that must fail
    are asserted inside the flow so both acceptance tests exercise them.
    """
    organization = client.post("/organizations", json={"name": "Pilot EPC"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Motor Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "415 V Induction Motors & VFD Supply",
            "category": "MOTOR",
            "mode": "PROJECT_EPC",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"},
                {"tag": "R-02", "parameter": "Motor power", "required_value": "75 kW"},
                {"tag": "R-03", "parameter": "Efficiency class", "required_value": "IE3"},
            ],
        },
    ).json()
    package_id = package["id"]

    # Vendor A quotes one mandatory parameter only; the rest need clarification.
    vendor_a = client.post(
        f"/packages/{package_id}/offers",
        json={
            "vendor_name": "Vendor A",
            "technical_revision": "R1",
            "price": "10000",
            "currency": "USD",
            "lead_time": "10 weeks",
            "warranty": "24 months",
        },
    ).json()
    _claim(vendor_a["id"], "Rated voltage", "415 V", "Vendor A quotation p.1")

    # Vendor B is complete but cheaper and deviates on a mandatory requirement.
    vendor_b = client.post(
        f"/packages/{package_id}/offers",
        json={
            "vendor_name": "Vendor B",
            "technical_revision": "R1",
            "price": "9000",
            "currency": "USD",
            "lead_time": "12 weeks",
            "warranty": "12 months",
        },
    ).json()
    _claim(vendor_b["id"], "Rated voltage", "415 V", "Vendor B quotation p.1")
    _claim(vendor_b["id"], "Motor power", "75 kW", "Vendor B quotation p.1")
    _claim(vendor_b["id"], "Efficiency class", "IE2", "Vendor B quotation p.2")

    # Technical clarification loop for Vendor A: request -> answer -> close.
    request = client.post(f"/offers/{vendor_a['id']}/technical-clarification-request")
    assert request.status_code == 201, request.text
    gaps = request.json()["gaps"]
    assert {gap["parameter"] for gap in gaps} == {"Motor power", "Efficiency class"}
    assert all(gap["rfq_revision_id"] == 1 for gap in gaps)
    assert all(gap["requirement_id"] in {2, 3} for gap in gaps)

    clarifications = client.get(f"/offers/{vendor_a['id']}/clarifications").json()
    assert len(clarifications) == 2
    for clarification in clarifications:
        answered = client.post(
            f"/clarifications/{clarification['id']}/answer",
            json={"response": "Provided in the revised technical offer."},
        )
        assert answered.status_code == 200, answered.text
        closed = client.post(
            f"/clarifications/{clarification['id']}/close",
            json={"note": "Vendor response reviewed."},
        )
        assert closed.status_code == 200, closed.text

    # Vendor A resubmits; the revision becomes the active technical offer.
    resubmission = client.post(
        f"/offers/{vendor_a['id']}/technical-resubmission",
        data={"technical_revision": "R2"},
        files={
            "file": (
                "VendorA_R2.txt",
                b"Rated voltage: 415 V\nMotor power: 75 kW\nEfficiency class: IE3\n",
                "text/plain",
            )
        },
    )
    assert resubmission.status_code == 201, resubmission.text
    vendor_a_r2 = resubmission.json()
    assert vendor_a_r2["parent_offer_id"] == vendor_a["id"]
    assert vendor_a_r2["technical_revision"] == "R2"
    assert vendor_a_r2["technical_status"] == "IN_REVIEW"

    # Sequence gates: commercial work is impossible before the technical lock.
    assert client.post(f"/packages/{package_id}/commercial-open").status_code == 409
    assert (
        client.get(f"/packages/{package_id}/commercial-comparison").status_code == 409
    )

    # Technical statuses must reach terminal states before the lock.
    accepted = client.post(
        f"/offers/{vendor_a_r2['id']}/technical-status",
        json={"status": "ACCEPTED"},
    )
    assert accepted.status_code == 200, accepted.text
    rejected = client.post(
        f"/offers/{vendor_b['id']}/technical-status",
        json={"status": "REJECTED"},
    )
    assert rejected.status_code == 200, rejected.text

    locked = client.post(f"/packages/{package_id}/technical-lock")
    assert locked.status_code == 200, locked.text
    opened = client.post(f"/packages/{package_id}/commercial-open")
    assert opened.status_code == 200, opened.text

    # Commercially locked offers cannot be evaluated or selected.
    locked_status = client.post(
        f"/offers/{vendor_b['id']}/commercial-status",
        json={"status": "OPEN"},
    )
    assert locked_status.status_code == 409
    premature_decision = client.post(
        f"/packages/{package_id}/decision",
        json={"selected_offer_id": vendor_b["id"], "rationale": "Cheaper bid."},
    )
    assert premature_decision.status_code == 409

    commercial = client.get(f"/packages/{package_id}/commercial-comparison")
    assert commercial.status_code == 200
    rows = commercial.json()["rows"]
    assert [row["vendor"] for row in rows] == ["Vendor A"]
    # The technical resubmission must not drop the original commercial terms.
    assert rows[0]["price"] == "10000"
    assert rows[0]["currency"] == "USD"
    assert rows[0]["lead_time"] == "10 weeks"
    assert rows[0]["warranty"] == "24 months"
    assert rows[0]["technical_revision"] == "R2"

    for next_status in ("IN_REVIEW", "COMPLETED"):
        advanced = client.post(
            f"/offers/{vendor_a_r2['id']}/commercial-status",
            json={"status": next_status},
        )
        assert advanced.status_code == 200, advanced.text

    decision = client.post(
        f"/packages/{package_id}/decision",
        json={
            "selected_offer_id": vendor_a_r2["id"],
            "rationale": "Vendor A revision R2 is technically accepted after clarification.",
        },
    )
    assert decision.status_code == 201, decision.text

    return {
        "package_id": package_id,
        "vendor_a_original": vendor_a["id"],
        "vendor_a_r2": vendor_a_r2["id"],
        "vendor_b": vendor_b["id"],
    }


def test_pilot_end_to_end_preserves_history_and_enforces_gates() -> None:
    context = _run_pilot_flow()
    package_id = context["package_id"]

    # Original offer history stays readable after the revision took over.
    original_offers = client.get(f"/packages/{package_id}/offers").json()
    by_id = {item["id"]: item for item in original_offers}
    assert by_id[context["vendor_a_r2"]]["parent_offer_id"] == context["vendor_a_original"]
    assert by_id[context["vendor_a_r2"]]["technical_status"] == "ACCEPTED"
    history = client.get(f"/offers/{context['vendor_a_original']}/clarifications")
    assert history.status_code == 200
    assert len(history.json()) == 2
    assert {item["status"] for item in history.json()} == {"CLOSED"}

    # Comparison evaluates the current revision, not the superseded one.
    comparison = client.get(f"/packages/{package_id}/comparison").json()
    vendor_a_rows = [row for row in comparison["rows"] if row["vendor"] == "Vendor A"]
    assert {row["status"] for row in vendor_a_rows} == {"COMPLIANT"}
    assert {row["offered"] for row in vendor_a_rows} == {"415 V", "75 kW", "IE3"}
    vendor_b_efficiency = [
        row
        for row in comparison["rows"]
        if row["vendor"] == "Vendor B" and row["parameter"] == "Efficiency class"
    ]
    assert vendor_b_efficiency[0]["status"] == "DEVIATION"
    assert vendor_b_efficiency[0]["offered"] == "IE2"

    # The cheaper vendor with a mandatory failure cannot be selected.
    decision = client.get(f"/packages/{package_id}/decision").json()
    assert decision["selected_offer_id"] == context["vendor_a_r2"]

    integrated = client.get(f"/packages/{package_id}/integrated-evaluation").json()
    assert integrated["status"] == "TECHNICAL_REVIEW_REQUIRED"
    profiles = {item["vendor"]: item for item in integrated["vendor_profiles"]}
    assert profiles["Vendor B"]["technical_gate"] == "BLOCKED"
    assert profiles["Vendor B"]["disposition"] == "TECHNICAL_REVIEW_REQUIRED"
    assert profiles["Vendor A"]["technical_gate"] == "PASS"
    assert profiles["Vendor A"]["price"] == 10000.0
    assert profiles["Vendor B"]["price"] == 9000.0
    assert all(
        item["disposition"] in {"TECHNICAL_REVIEW_REQUIRED", "COMMERCIAL_REVIEW_REQUIRED"}
        or item["disposition"] == "READY_FOR_HUMAN_SELECTION"
        for item in integrated["vendor_profiles"]
    )
    assert "supplier is selected automatically" not in integrated["decision_note"].lower()

    weighting = client.get(f"/packages/{package_id}/evaluation-weighting").json()
    assert weighting["locked"] is True
    assert weighting["technical_weight"] + weighting["commercial_weight"] == 100.0

    # The audit trail keeps every milestone in workflow order.
    events = [item["event_type"] for item in client.get(f"/packages/{package_id}/audit").json()]
    milestones = [
        "TECHNICAL_CLARIFICATION_REQUESTED",
        "CLARIFICATION_ANSWERED",
        "CLARIFICATION_CLOSED",
        "TECHNICAL_OFFER_RESUBMITTED",
        "TECHNICAL_BID_LOCKED",
        "COMMERCIAL_EVALUATION_OPENED",
        "FINAL_DECISION_CREATED",
    ]
    positions = [events.index(name) for name in milestones]
    assert positions == sorted(positions), events


def test_pilot_report_agrees_with_api_material_results() -> None:
    context = _run_pilot_flow()
    package_id = context["package_id"]

    report = client.get(f"/packages/{package_id}/report").json()
    comparison = client.get(f"/packages/{package_id}/comparison").json()
    decision_support = client.get(f"/packages/{package_id}/decision-support").json()
    integrated = client.get(f"/packages/{package_id}/integrated-evaluation").json()
    engineering = client.get(f"/packages/{package_id}/engineering-decision-summary").json()

    # Report matrix and API comparison agree on every material row.
    api_rows = {
        (row["vendor"], row["parameter"]): (row["status"], row["offered"])
        for row in comparison["rows"]
    }
    report_rows = {
        (row["vendor"], row["parameter"]): (row["status"], row["offered"])
        for row in report["matrix"]
    }
    assert report_rows == api_rows

    # Decision support, integrated evaluation and engineering summary agree.
    assert report["decision_support"]["vendors"] == decision_support["vendors"]
    assert report["decision_support"]["rows"] == decision_support["rows"]
    assert report["decision_support"]["formula"] == decision_support["formula"]
    assert report["integrated_evaluation"]["status"] == integrated["status"]
    assert report["integrated_evaluation"]["vendor_profiles"] == integrated["vendor_profiles"]
    assert report["integrated_evaluation"]["decision_note"] == integrated["decision_note"]
    assert (
        report["engineering_decision_summary"]["vendor_profiles"]
        == engineering["vendor_profiles"]
    )
    assert report["engineering_decision_summary"]["status"] == engineering["status"]

    # Commercial risk flags in the report match the integrated evaluation gates.
    risk_flags = {
        row["vendor"]: row["flags"] for row in report["commercial_risk_review"]
    }
    for profile in integrated["vendor_profiles"]:
        assert risk_flags[profile["vendor"]] == profile["commercial_flags"]

    # Summary counts match the comparison rows.
    summary = report["summary"]
    deviation_rows = [row for row in comparison["rows"] if row["status"] == "DEVIATION"]
    assert summary["deviations"] == len(deviation_rows)
    assert summary["vendors_checked"] == 2
    assert summary["requirements_checked"] == 3

    # The Markdown export renders the same material results.
    markdown = client.get(f"/packages/{package_id}/report/markdown")
    assert markdown.status_code == 200
    assert "text/markdown" in markdown.headers["content-type"]
    body = markdown.text
    assert "Vendor A" in body and "Vendor B" in body
    assert "IE2" in body and "IE3" in body
